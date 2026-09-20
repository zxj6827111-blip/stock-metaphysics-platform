"""Phase 4A/4B · 供应商数据通道与真实 size/value 暴露测试。

三层断言：
1. **数据读取正确性**：年包/因子包解析、代码与交易所映射、数值转换**不用 0 冒充缺失**；
2. **PIT 与防泄漏**：估值快照取的是"截止 as_of 的最后一条"（停牌也不能丢），
   价格类暴露对 as_of 之后的行情**逐位不敏感**；
3. **语义纪律**：负 PE/PB 必须变成 NaN（不能变成负收益率混进横截面），
   退市股的 size/value 必须是 NaN 且带显式状态。
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.core.schemas.common import MarketDataSource
from src.market.providers.vendor_parquet import (
    DEFAULT_VENDOR_DATA_DIR,
    VENDOR_DATA_VERSION,
    VendorParquetProvider,
    vendor_available,
)
from src.market.providers.vendor_zip_store import (
    BAR_COLUMNS,
    VALUATION_COLUMNS,
    VendorCode,
    VendorZipStore,
    to_numeric,
)
from src.research.neutralization.exposures import STYLE_EXPOSURE_COLUMNS
from src.research.neutralization.exposures_v2 import (
    EXPOSURE_VERSION_V2,
    STYLE_EXPOSURE_COLUMNS_V2,
    V2_NEW_COLUMNS,
    VALUATION_UNAVAILABLE_FOR_DELISTED,
    VALUE_BASIS,
    compute_price_exposures,
    exposure_availability_v2,
    safe_inverse,
    valuation_exposures,
)

#: 真实 Parquet 仓库（不存在则跳过依赖它的用例）
HAVE_VENDOR_REPO = vendor_available()


# ---------------------------------------------------------------------------
# 4A · ZIP 存储读取
# ---------------------------------------------------------------------------


def test_vendor_code_parses_exchange() -> None:
    assert VendorCode.parse("600519.SH").exchange == "SSE"
    assert VendorCode.parse("000001.SZ").exchange == "SZSE"
    assert VendorCode.parse("920001.BJ").exchange == "BSE"
    assert VendorCode.parse("600519").exchange == "UNKNOWN"
    assert VendorCode.parse("600519.SH").code == "600519"


def test_to_numeric_keeps_missing_as_nan() -> None:
    """空串必须变成 NaN，**绝不能变成 0**。"""
    frame = pd.DataFrame({
        "code": ["600000.SH"],
        "datetime": ["2020-01-02"],
        "close": ["10.0"],
        "pe_ttm": [""],
        "pb": ["1.5"],
        "total_mv": [""],
    })
    out = to_numeric(frame)
    assert out.loc[0, "close"] == 10.0
    assert pd.isna(out.loc[0, "pe_ttm"])
    assert pd.isna(out.loc[0, "total_mv"])
    assert out.loc[0, "pb"] == 1.5
    assert out.loc[0, "trade_date"] == date(2020, 1, 2)


def test_column_sets_cover_expected_fields() -> None:
    """行情列与估值列必须是**互斥**的两组（分表存放的前提）。"""
    assert not set(BAR_COLUMNS) & set(VALUATION_COLUMNS)
    for field in ("pe_ttm", "pb", "total_mv", "circ_mv", "total_share", "turnover_free"):
        assert field in VALUATION_COLUMNS


@pytest.mark.skipif(not Path(r"E:\AStockData").exists(), reason="本机无供应商原始包")
def test_zip_store_reads_real_year_package() -> None:
    store = VendorZipStore()
    years = store.years()
    assert years[0] == "2000"
    assert "2026" in years
    frame = store.read_year("2001")
    assert len(frame) > 100_000
    # read_year 返回**原始**列（datetime 尚未转成 trade_date，由 to_numeric 负责）
    assert {"stock_code", "exchange", "datetime"}.issubset(frame.columns)
    # exchange 必须解析出来（不能全是 UNKNOWN）
    assert set(frame["exchange"]) <= {"SSE", "SZSE", "BSE"}
    assert "UNKNOWN" not in set(frame["exchange"])
    converted = to_numeric(frame)
    assert "trade_date" in converted.columns
    assert converted["trade_date"].notna().all()


# ---------------------------------------------------------------------------
# 4A · Provider 契约
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not HAVE_VENDOR_REPO, reason="Parquet 仓库未构建")
class TestVendorParquetProvider:
    @pytest.fixture(scope="class")
    def provider(self) -> VendorParquetProvider:
        return VendorParquetProvider(DEFAULT_VENDOR_DATA_DIR)

    def test_is_market_data_provider_shape(self, provider: VendorParquetProvider) -> None:
        for method in ("search", "get_stock", "get_daily_bars", "get_benchmark_bars"):
            assert callable(getattr(provider, method))

    def test_catalog_covers_full_market(self, provider: VendorParquetProvider) -> None:
        catalog = provider.catalog()
        assert len(catalog) > 6_000
        assert int(catalog["has_valuation"].sum()) > 5_000

    def test_delisted_stock_has_bars_but_no_valuation(
        self, provider: VendorParquetProvider,
    ) -> None:
        """退市股：有行情、**没有**估值 —— 这是并集口径的核心不变式。"""
        catalog = provider.catalog()
        delisted = catalog[catalog["has_valuation"] == False]  # noqa: E712
        assert not delisted.empty
        code = str(delisted.iloc[0]["stock_code"])
        master = provider.get_stock(code)
        assert master.listing_date is not None
        first, last = master.listing_date, delisted.iloc[0]["last_date"].date()
        bars = provider.get_daily_bars(code, first, last)
        assert len(bars.bars) > 0
        valuation = provider.valuation(code, first, last)
        assert valuation.empty, "退市股不应有估值行"

    def test_active_stock_has_valuation_with_market_cap(
        self, provider: VendorParquetProvider,
    ) -> None:
        code = "600519"
        bars = provider.get_daily_bars(code, date(2024, 1, 1), date(2024, 1, 31))
        assert len(bars.bars) > 10
        assert bars.source == MarketDataSource.OFFLINE_IMPORT
        assert VENDOR_DATA_VERSION in bars.source_ref.source
        valuation = provider.valuation(code, date(2024, 1, 1), date(2024, 1, 31))
        assert len(valuation) > 10
        assert valuation["total_mv"].notna().all()
        assert (valuation["total_mv"] > 0).all()

    def test_unknown_code_raises(self, provider: VendorParquetProvider) -> None:
        from src.market.normalization.errors import SymbolNotFoundError

        with pytest.raises(SymbolNotFoundError):
            provider.get_stock("999999")
        with pytest.raises(SymbolNotFoundError):
            provider.get_daily_bars("999999", date(2024, 1, 1), date(2024, 1, 2))

    def test_benchmark_is_not_served_by_this_provider(
        self, provider: VendorParquetProvider,
    ) -> None:
        """基准指数不在供应商仓库里 —— 必须明确报错，而不是返回空序列。"""
        from src.market.normalization.errors import SymbolNotFoundError

        with pytest.raises(SymbolNotFoundError):
            provider.get_benchmark_bars("IDX000300", date(2024, 1, 1), date(2024, 1, 2))

    def test_bars_are_sorted_and_within_range(self, provider: VendorParquetProvider) -> None:
        bars = provider.get_daily_bars("000001", date(2023, 1, 1), date(2023, 12, 31))
        dates = [bar.trade_date for bar in bars.bars]
        assert dates == sorted(dates)
        assert all(date(2023, 1, 1) <= value <= date(2023, 12, 31) for value in dates)


# ---------------------------------------------------------------------------
# 4B · 估值语义
# ---------------------------------------------------------------------------


def test_safe_inverse_rejects_non_positive() -> None:
    """负 PE（亏损）与零 PE 必须 → NaN，**不能**变成负收益率。"""
    values = pd.Series([10.0, -5.0, 0.0, np.nan, 20.0])
    out = safe_inverse(values)
    assert out.iloc[0] == pytest.approx(0.1)
    assert pd.isna(out.iloc[1]), "负 PE 不能产生负的盈利收益率"
    assert pd.isna(out.iloc[2])
    assert pd.isna(out.iloc[3])
    assert out.iloc[4] == pytest.approx(0.05)


def test_valuation_exposures_uses_real_market_cap() -> None:
    snapshot = pd.DataFrame({
        "as_of": [date(2024, 1, 1)] * 3,
        "stock_code": ["A", "B", "C"],
        "total_mv": [1_000_000.0, 100.0, np.nan],
        "pe_ttm": [10.0, -3.0, 8.0],
        "pb": [2.0, 4.0, np.nan],
        "turnover_free": [1.5, 2.0, 3.0],
    })
    out = valuation_exposures(snapshot)
    assert out.loc[0, "size_log_market_cap"] == pytest.approx(np.log(1_000_000.0))
    assert out.loc[0, "value_ep"] == pytest.approx(0.1)
    assert out.loc[0, "value_bp"] == pytest.approx(0.5)
    assert pd.isna(out.loc[1, "value_ep"]), "负 PE → 不可用"
    assert pd.isna(out.loc[2, "size_log_market_cap"]), "缺市值 → 不可用（不是 0）"
    assert out.loc[0, "valuation_status"] == VALUE_BASIS
    assert out.loc[2, "valuation_status"] == VALUATION_UNAVAILABLE_FOR_DELISTED


def test_v2_columns_are_superset_of_new_fields() -> None:
    availability = exposure_availability_v2().to_dict()
    assert availability["exposure_version"] == EXPOSURE_VERSION_V2
    assert set(V2_NEW_COLUMNS) <= set(STYLE_EXPOSURE_COLUMNS_V2)
    assert availability["size_basis"] == "REAL_TOTAL_MARKET_CAP"
    assert "phase3e" not in EXPOSURE_VERSION_V2, "v2 必须是独立版本号"


def test_v1_columns_unchanged() -> None:
    """v1（Phase 3E 冻结口径）必须保持原样 —— v2 不能就地修改它。"""
    assert STYLE_EXPOSURE_COLUMNS == (
        "momentum_60d", "momentum_120d", "volatility_20d", "volatility_60d",
        "size_proxy_log_amount_20d",
    )
    assert "size_proxy_log_amount_20d" in STYLE_EXPOSURE_COLUMNS
    assert "size_proxy_log_amount_20d" not in STYLE_EXPOSURE_COLUMNS_V2


# ---------------------------------------------------------------------------
# 4B · 价格类暴露与防泄漏
# ---------------------------------------------------------------------------


def _bars(days: list[date], closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame({"trade_date": days, "close": closes})


def _business_days(start: date, count: int) -> list[date]:
    out: list[date] = []
    current = start
    while len(out) < count:
        if current.weekday() < 5:
            out.append(current)
        current += timedelta(days=1)
    return out


def test_price_exposures_frozen_against_future_bars() -> None:
    """核心防泄漏断言：改写 as_of 之后的 bar，暴露值必须**逐位不变**。"""
    days = _business_days(date(2020, 1, 1), 300)
    rng = np.random.default_rng(11)
    closes = 20.0 * np.exp(np.cumsum(rng.normal(0, 0.015, 300)))
    original = _bars(days, list(closes))
    as_of = days[199]

    tampered = original.copy()
    future = tampered["trade_date"] > as_of
    tampered.loc[future, "close"] = tampered.loc[future, "close"] * 1000.0

    base = compute_price_exposures(original, [as_of], stock_code="X")
    changed = compute_price_exposures(tampered, [as_of], stock_code="X")
    assert base == changed
    assert base[0]["momentum_60d"] is not None
    assert base[0]["volatility_20d"] is not None


def test_price_exposures_none_when_history_short() -> None:
    days = _business_days(date(2020, 1, 1), 30)
    rows = compute_price_exposures(_bars(days, [10.0] * 30), [days[-1]], stock_code="X")
    assert rows[0]["momentum_60d"] is None
    assert rows[0]["momentum_120d"] is None


def test_price_exposures_as_of_before_first_bar_are_skipped() -> None:
    days = _business_days(date(2020, 1, 1), 100)
    rows = compute_price_exposures(
        _bars(days, [10.0] * 100), [date(2019, 1, 1), days[-1]], stock_code="X",
    )
    assert len(rows) == 1, "as_of 早于第一根 bar 时不应产出该行"


# ---------------------------------------------------------------------------
# 4A · 估值快照的 as_of 语义（用合成数据验证"取最后一条"而非"取当天"）
# ---------------------------------------------------------------------------


def test_as_of_snapshot_rule_takes_last_row_not_same_day() -> None:
    """停牌场景：as_of 当天没有估值行时，必须回退到更早的最后一条。

    这里用一个最小 DuckDB 复现快照规则（与 ``phase4_build_valuation_snapshots``
    的 SQL 同构），确保"停牌不丢样本"这一条被测试守住。
    """
    import duckdb

    frame = pd.DataFrame({
        "stock_code": ["A", "A", "A", "B", "B"],
        "trade_date": [
            date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 10),   # A 停牌 1/4-1/9
            date(2024, 1, 2), date(2024, 1, 3),
        ],
        "total_mv": [100.0, 110.0, 130.0, 50.0, 55.0],
    })
    connection = duckdb.connect()
    connection.register("valuation", frame)
    sql = """
        with grid as (select unnest(?::date[]) as as_of),
        joined as (
            select g.as_of, v.stock_code, v.trade_date, v.total_mv,
                   date_diff('day', v.trade_date, g.as_of) as staleness_days
            from grid g join valuation v on v.trade_date <= g.as_of
        ),
        ranked as (
            select *, row_number() over (
                partition by as_of, stock_code order by trade_date desc
            ) as rn from joined
        )
        select * exclude (rn) from ranked where rn = 1 order by as_of, stock_code
    """
    out = connection.execute(sql, [["2024-01-05", "2024-01-12"]]).df()
    # A 在 1/5 停牌 → 应回退到 1/3 的 110，且 staleness=2
    row = out[(out.as_of.astype(str).str.startswith("2024-01-05")) & (out.stock_code == "A")].iloc[0]
    assert row["total_mv"] == 110.0
    assert int(row["staleness_days"]) == 2
    # B 在 1/5 也是回退到 1/3
    row_b = out[(out.as_of.astype(str).str.startswith("2024-01-05")) & (out.stock_code == "B")].iloc[0]
    assert row_b["total_mv"] == 55.0
    # A 在 1/12 取 1/10
    row_a2 = out[(out.as_of.astype(str).str.startswith("2024-01-12")) & (out.stock_code == "A")].iloc[0]
    assert row_a2["total_mv"] == 130.0
