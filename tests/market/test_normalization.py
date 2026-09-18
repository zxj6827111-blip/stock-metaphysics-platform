"""行情归一化与 MarketDataProvider 测试。

覆盖：
* 第三方字段（中文列名）→ 标准 Bar schema；
* 复权、去重、排序、类型转换；
* 异常检测（停牌 / 零成交量 / 异常跳变）；
* 降级链路（缓存 / 合成 / 结构化错误）不会让应用崩溃；
* 合成行情必须显式标注，绝不伪装成真实行情。
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.core.schemas.common import MarketDataSource
from src.market.normalization.errors import (
    FutureDataAccessError,
    InsufficientDataError,
    MarketDataError,
    ProviderUnavailableError,
    SymbolNotFoundError,
)
from src.market.normalization.frames import (
    build_series,
    clip_to_as_of,
    detect_anomalies,
    frame_to_bars,
    normalize_frame,
)


@pytest.fixture()
def raw_cn_frame() -> pd.DataFrame:
    """模拟 AKShare 返回的中文列名 DataFrame。"""
    return pd.DataFrame({
        "日期": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-03"],  # 故意含重复
        "开盘": ["10.00", "10.50", "10.30", "10.50"],
        "最高": ["10.60", "10.80", "10.40", "10.80"],
        "最低": ["9.90", "10.30", "10.10", "10.30"],
        "收盘": ["10.50", "10.35", "10.20", "10.35"],
        "成交量": ["100000", "120000", "90000", "120000"],
        "成交额": ["1050000", "1242000", "918000", "1242000"],
        "换手率": ["1.2", "1.4", "1.1", "1.4"],
        "涨跌幅": ["1.5", "-1.43", "-1.45", "-1.43"],
    })


class TestNormalization:
    def test_column_renaming(self, raw_cn_frame):
        norm = normalize_frame(raw_cn_frame)
        for col in ("trade_date", "open", "high", "low", "close", "volume", "amount",
                    "turnover", "pct_change"):
            assert col in norm.columns

    def test_types_are_numeric(self, raw_cn_frame):
        norm = normalize_frame(raw_cn_frame)
        for col in ("open", "high", "low", "close", "volume"):
            assert pd.api.types.is_numeric_dtype(norm[col])

    def test_dates_are_date_objects(self, raw_cn_frame):
        norm = normalize_frame(raw_cn_frame)
        assert all(isinstance(d, date) for d in norm["trade_date"])

    def test_dedup_keeps_last_and_sorts(self, raw_cn_frame):
        norm = normalize_frame(raw_cn_frame)
        assert len(norm) == 3
        dates = list(norm["trade_date"])
        assert dates == sorted(dates)

    def test_build_series(self, raw_cn_frame):
        series = build_series("600519", raw_cn_frame, source_name="test")
        assert len(series.bars) == 3
        assert series.start == date(2024, 1, 2)
        assert series.end == date(2024, 1, 4)
        assert series.bars[0].close == pytest.approx(10.5)

    def test_missing_columns_filled_with_none(self):
        df = pd.DataFrame({"日期": ["2024-01-02"], "收盘": ["10.0"]})
        series = build_series("600519", df)
        bar = series.bars[0]
        assert bar.close == 10.0
        assert bar.volume is None
        assert bar.turnover is None

    def test_empty_frame(self):
        series = build_series("600519", pd.DataFrame())
        assert series.bars == []
        assert series.start is None

    def test_missing_date_column_raises(self):
        with pytest.raises(ValueError, match="缺少日期列"):
            normalize_frame(pd.DataFrame({"开盘": [1.0]}))

    def test_unparsable_numbers_become_none(self):
        df = pd.DataFrame({"日期": ["2024-01-02"], "收盘": ["-"]})
        series = build_series("600519", df)
        assert series.bars[0].close is None


class TestAnomalyDetection:
    def test_zero_volume_flagged(self):
        df = pd.DataFrame({
            "日期": ["2024-01-02", "2024-01-03"],
            "收盘": [10.0, 10.2],
            "成交量": [0, 1000],
        })
        series = build_series("600519", df)
        codes = {w.code for w in detect_anomalies(series)}
        assert "MARKET_ZERO_VOLUME" in codes

    def test_price_jump_flagged(self):
        df = pd.DataFrame({
            "日期": ["2024-01-02", "2024-01-03"],
            "收盘": [10.0, 30.0],
            "涨跌幅": [0.0, 200.0],
        })
        series = build_series("600519", df)
        codes = {w.code for w in detect_anomalies(series)}
        assert "MARKET_PRICE_JUMP" in codes

    def test_empty_series_error(self):
        series = build_series("600519", pd.DataFrame())
        codes = {w.code for w in detect_anomalies(series)}
        assert "MARKET_EMPTY" in codes


class TestClipToAsOf:
    def test_clip(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2021, 12, 31))
        clipped = clip_to_as_of(series, date(2021, 1, 1))
        assert max(b.trade_date for b in clipped.bars) <= date(2021, 1, 1)
        assert len(clipped.bars) < len(series.bars)

    def test_clip_before_start_yields_empty(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2021, 12, 31))
        clipped = clip_to_as_of(series, date(2019, 1, 1))
        assert clipped.bars == []


class TestSyntheticProviderHonesty:
    def test_marked_as_degraded(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2020, 12, 31))
        assert series.is_degraded is True
        assert series.source == MarketDataSource.SYNTHETIC_DEMO
        assert any(w.severity == "error" for w in series.warnings)
        assert any("合成" in w.message for w in series.warnings)

    def test_deterministic(self, market):
        a = market.get_daily_bars("600519", date(2020, 1, 1), date(2020, 12, 31))
        b = market.get_daily_bars("600519", date(2020, 1, 1), date(2020, 12, 31))
        assert [x.close for x in a.bars] == [x.close for x in b.bars]

    def test_different_codes_differ(self, market):
        a = market.get_daily_bars("600519", date(2020, 1, 1), date(2020, 12, 31))
        b = market.get_daily_bars("000001", date(2020, 1, 1), date(2020, 12, 31))
        assert [x.close for x in a.bars] != [x.close for x in b.bars]

    def test_weekday_only(self, market):
        series = market.get_daily_bars("600519", date(2020, 1, 1), date(2020, 3, 31))
        assert all(b.trade_date.weekday() < 5 for b in series.bars)

    def test_benchmark_available(self, market):
        bench = market.get_benchmark_bars("000300", date(2020, 1, 1), date(2020, 12, 31))
        assert bench.bars
        assert bench.is_degraded is True

    def test_low_volatility_for_benchmark(self, market):
        bench = market.get_benchmark_bars("000300", date(2020, 1, 1), date(2021, 12, 31))
        stock = market.get_daily_bars("600519", date(2020, 1, 1), date(2021, 12, 31))
        import numpy as np

        b_vol = np.std([b.pct_change for b in bench.bars if b.pct_change is not None])
        s_vol = np.std([b.pct_change for b in stock.bars if b.pct_change is not None])
        assert b_vol < s_vol


class TestStructuredErrors:
    def test_error_payload_shape(self):
        err = ProviderUnavailableError("数据源不可用", detail="connection reset")
        payload = err.to_payload()
        assert payload["error"]["code"] == "MARKET_PROVIDER_UNAVAILABLE"
        assert payload["error"]["retryable"] is True
        assert err.http_status == 503

    def test_symbol_not_found_is_not_retryable(self):
        err = SymbolNotFoundError("代码不存在")
        assert err.retryable is False
        assert err.http_status == 404

    def test_future_data_access_is_p0(self):
        err = FutureDataAccessError("检测到未来数据访问")
        assert err.http_status == 500
        assert err.retryable is False

    def test_inheritance(self):
        assert issubclass(SymbolNotFoundError, MarketDataError)
        assert issubclass(InsufficientDataError, MarketDataError)


class TestAkshareProviderDegradation:
    """AKShare 不可用时的降级行为（不打真实网络）。"""

    def test_falls_back_to_synthetic_and_marks_it(self, monkeypatch):
        from src.market.providers import akshare_provider as ap

        provider = ap.AkshareMarketProvider(allow_synthetic_fallback=True)
        monkeypatch.setattr(
            provider, "_call_with_retry",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down")),
        )
        monkeypatch.setattr(provider, "_read_cache", lambda *a, **k: None)
        monkeypatch.setattr(provider, "_cache_is_fresh", lambda *a, **k: False)

        series = provider.get_daily_bars("600519", date(2020, 1, 1), date(2020, 6, 30))
        assert series.is_degraded is True
        assert series.source == MarketDataSource.SYNTHETIC_DEMO
        assert any(w.code == "MARKET_SYNTHETIC_FALLBACK" for w in series.warnings)

    def test_structured_error_when_fallback_disabled(self, monkeypatch):
        from src.market.providers import akshare_provider as ap

        provider = ap.AkshareMarketProvider(allow_synthetic_fallback=False)
        monkeypatch.setattr(
            provider, "_call_with_retry",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down")),
        )
        monkeypatch.setattr(provider, "_read_cache", lambda *a, **k: None)
        monkeypatch.setattr(provider, "_cache_is_fresh", lambda *a, **k: False)

        with pytest.raises(ProviderUnavailableError) as exc:
            provider.get_daily_bars("600519", date(2020, 1, 1), date(2020, 6, 30))
        assert exc.value.to_payload()["error"]["code"] == "MARKET_PROVIDER_UNAVAILABLE"

    def test_search_falls_back_to_builtin(self, monkeypatch):
        from src.market.providers import akshare_provider as ap

        provider = ap.AkshareMarketProvider()
        monkeypatch.setattr(
            provider, "_call_with_retry",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down")),
        )
        results = provider.search("茅台")
        assert results
        assert results[0].stock_code == "600519"

    def test_get_stock_falls_back_to_builtin(self, monkeypatch):
        from src.market.providers import akshare_provider as ap

        provider = ap.AkshareMarketProvider()
        monkeypatch.setattr(
            provider, "_call_with_retry",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network down")),
        )
        stock = provider.get_stock("600519")
        assert stock.name == "贵州茅台"
        assert stock.listing_date == date(2001, 8, 27)
        assert stock.data_quality.grade == "B"
        assert any("降级" in n for n in stock.data_quality.notes)
