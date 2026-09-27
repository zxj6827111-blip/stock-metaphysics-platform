"""Phase 4 · 供应商 Parquet 行情仓库 Provider（全市场 + 逐日估值）。

定位
----
实现 ``MarketDataProvider`` 契约，数据来自 ``scripts/phase4_import_vendor.py``
产出的一次性 Parquet 仓库：

    data/vendor/daily_bars.parquet       OHLCV（含退市股补丁）
    data/vendor/daily_valuation.parquet  逐日估值/股本/市值（**Phase 3 缺的那部分**）
    data/vendor/adj_factor.parquet       后复权因子
    data/vendor/_meta.json              来源与覆盖说明

为什么独立于 SQLite 路径
------------------------
Phase 3 的 canonical 数据在 SQLite（``market_bar_daily``，500 只研究样本），
**不得改动** —— 它是 Phase 3 全部结论的可复现基础。全市场数据放在 Parquet 仓库里，
两条路径互不干扰，容器部署时把 Parquet 目录作为只读卷挂进去即可。

复权口径
--------
``daily_bars`` 与 ``daily_valuation`` 是**不复权原始价**（供应商导出即如此），
收益一律用 ``close × adj_factor`` 计算（``adj_factor.parquet`` 是后复权因子）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import pandas as pd

from src.core.schemas.common import MarketDataSource, SourceRef
from src.core.schemas.market import Bar, BarSeries
from src.core.schemas.stock import StockMaster
from src.market.normalization.errors import SymbolNotFoundError
from src.market.providers.base import MarketDataProvider

#: Parquet 仓库目录（NAS 上以 ``SMP_VENDOR_DATA_DIR`` 覆盖）
DEFAULT_VENDOR_DATA_DIR = Path(
    os.environ.get("SMP_VENDOR_DATA_DIR", "")
) if os.environ.get("SMP_VENDOR_DATA_DIR") else Path("data/vendor")

#: 数据源标识
VENDOR_SOURCE_NAME = "vendor_hfq"
DELISTED_SOURCE_NAME = "astockdata_delisted"
#: 版本号（写入 SourceRef，供报告披露）
VENDOR_DATA_VERSION = "phase4-vendor-hfq-v1"
#: 估值列（研究用；退市股一律 NaN）
VALUATION_FIELDS: tuple[str, ...] = (
    "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_yield", "dv_ttm",
    "total_share", "float_share", "free_share", "total_mv", "circ_mv",
    "turnover", "turnover_free", "volume_ratio",
)


def vendor_available(data_dir: Path | None = None) -> bool:
    """仓库是否就绪（三个 Parquet 都在）。"""
    base = Path(data_dir) if data_dir is not None else DEFAULT_VENDOR_DATA_DIR
    return all(
        (base / name).is_file()
        for name in ("daily_bars.parquet", "daily_valuation.parquet", "adj_factor.parquet")
    )


@dataclass(frozen=True)
class VendorRepoMeta:
    """仓库元数据（来源、快照、覆盖）。"""

    payload: dict

    @property
    def vendor_root(self) -> str:
        return str(self.payload.get("vendor_root", ""))

    @property
    def date_range(self) -> tuple[str, str]:
        span = self.payload.get("date_range", {})
        return str(span.get("min", "")), str(span.get("max", ""))

    def to_dict(self) -> dict:
        return dict(self.payload)


class VendorParquetProvider(MarketDataProvider):
    """``MarketDataProvider`` 实现：读 Parquet 仓库（全市场）。

    只读、无副作用；**不写任何东西**。构造函数不加载数据（惰性），
    首次查询时才读 Parquet（DuckDB 引擎，按 stock_code 行组裁剪）。
    """

    #: 契约要求的提供者标识（AGENTS.md §1-15：新行情源必须实现 MarketDataProvider）
    provider_id = "vendor_parquet"
    name = "vendor_parquet"

    def __init__(
        self, data_dir: Path | None = None, *, benchmark_fallback=None,
    ) -> None:  # type: ignore[no-untyped-def]
        """``benchmark_fallback``：供应商仓库不含指数，基准查询委派给它。"""
        self.benchmark_fallback = benchmark_fallback
        self.data_dir = Path(data_dir) if data_dir is not None else DEFAULT_VENDOR_DATA_DIR
        if not vendor_available(self.data_dir):
            raise FileNotFoundError(
                f"供应商 Parquet 仓库不完整：{self.data_dir}"
                "（先跑 scripts/phase4_import_vendor.py）"
            )
        self.meta = VendorRepoMeta(
            json.loads((self.data_dir / "_meta.json").read_text(encoding="utf-8"))
            if (self.data_dir / "_meta.json").is_file() else {}
        )
        self._catalog: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    def _query(self, sql: str, params: list | None = None) -> pd.DataFrame:
        import duckdb

        return duckdb.connect().execute(sql, params or []).df()

    def _bars_path(self) -> str:
        return str(self.data_dir / "daily_bars.parquet").replace("\\", "/")

    def _valuation_path(self) -> str:
        return str(self.data_dir / "daily_valuation.parquet").replace("\\", "/")

    def _factor_path(self) -> str:
        return str(self.data_dir / "adj_factor.parquet").replace("\\", "/")

    # ------------------------------------------------------------------
    @lru_cache(maxsize=1)  # noqa: B019 - 实例级缓存，进程内复用
    def catalog(self) -> pd.DataFrame:
        """``stock_code / exchange / source / first_date / last_date / rows / has_valuation``。"""
        frame = self._query(
            f"""
            select stock_code,
                   any_value(exchange) as exchange,
                   any_value(source) as source,
                   min(trade_date) as first_date,
                   max(trade_date) as last_date,
                   count(*) as rows
            from read_parquet('{self._bars_path()}')
            group by stock_code
            order by stock_code
            """
        )
        valued = self._query(
            f"""
            select stock_code, count(total_mv) as mv_rows
            from read_parquet('{self._valuation_path()}')
            group by stock_code
            """
        )
        frame = frame.merge(valued, on="stock_code", how="left")
        frame["has_valuation"] = frame["mv_rows"].fillna(0) > 0
        return frame

    # ------------------------------------------------------------------
    def search(self, query: str, limit: int = 20) -> list[StockMaster]:
        text = str(query or "").strip()
        if not text:
            return []
        catalog = self.catalog()
        hit = catalog[catalog["stock_code"].str.contains(text, case=False, regex=False)]
        return [self._to_master(row) for _index, row in hit.head(limit).iterrows()]

    def get_stock(self, code: str) -> StockMaster:
        catalog = self.catalog()
        hit = catalog[catalog["stock_code"] == str(code).strip()]
        if hit.empty:
            raise SymbolNotFoundError(f"{code} 不在供应商 Parquet 仓库内")
        return self._to_master(hit.iloc[0])

    def get_daily_bars(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
        *,
        adjust: str = "none",
    ) -> BarSeries:
        catalog = self.catalog()
        hit = catalog[catalog["stock_code"] == str(code).strip()]
        if hit.empty:
            raise SymbolNotFoundError(f"{code} 不在供应商 Parquet 仓库内")
        filters = ["stock_code = ?"]
        params: list[object] = [str(code).strip()]
        if start is not None:
            filters.append("trade_date >= ?")
            params.append(start)
        if end is not None:
            filters.append("trade_date <= ?")
            params.append(end)
        frame = self._query(
            f"""
            select trade_date, open, high, low, close, volume, amount
            from read_parquet('{self._bars_path()}')
            where {' and '.join(filters)}
            order by trade_date
            """,
            params,
        )
        _ = adjust  # 本 provider 一律给不复权价；复权由调用方用 adj_factor 处理
        bars = [
            Bar(
                trade_date=(
                    value.date() if hasattr(value, "date") else value
                ),
                open=_opt_float(row["open"]),
                high=_opt_float(row["high"]),
                low=_opt_float(row["low"]),
                close=_opt_float(row["close"]),
                volume=_opt_float(row["volume"]),
                amount=_opt_float(row["amount"]),
                turnover=None,
            )
            for value, (_idx, row) in zip(frame["trade_date"], frame.iterrows(), strict=True)
        ]
        source_name = str(hit.iloc[0]["source"])
        return BarSeries(
            stock_code=str(code).strip(),
            bars=tuple(bars),
            source=MarketDataSource.OFFLINE_IMPORT,
            source_ref=SourceRef(
                source=f"{source_name}@{VENDOR_DATA_VERSION}",
                url=str(self.data_dir),
                retrieved_at=None,
                extra={
                    "provider": self.name,
                    "vendor_root": self.meta.vendor_root,
                    "adjust": "none（复权因子在 adj_factor.parquet）",
                },
            ),
            adjust="none",
            start=bars[0].trade_date if bars else None,
            end=bars[-1].trade_date if bars else None,
        )

    def get_benchmark_bars(
        self, index_code: str, start: date, end: date, *, adjust: str = "none",
    ) -> BarSeries:
        """基准指数：供应商仓库只有个股，因此委派给 ``benchmark_fallback``。

        未配置回退时明确报错（**不返回空序列**，避免把"没有基准"伪装成"基准收益为 0"）。
        """
        if self.benchmark_fallback is not None:
            # 基准代码有两套命名约定，必须显式适配（不靠 try/except 兜）：
            #   SQLite / 研究侧：``IDX000300``（market_bar_daily.stock_code）
            #   文件通道 offline：``000300``（它自己会拼上 ``IDX`` 前缀）
            code = str(index_code).strip()
            if code.upper().startswith("IDX"):
                code = code[3:]
            return self.benchmark_fallback.get_benchmark_bars(
                code, start, end, adjust=adjust,
            )
        raise SymbolNotFoundError(
            f"供应商 Parquet 仓库不含指数 {index_code}，且未配置 benchmark_fallback"
        )

    # ------------------------------------------------------------------
    def valuation(self, code: str, start: date, end: date) -> pd.DataFrame:
        """逐日估值/股本/市值（研究用）。退市股返回空表（**不是 0**）。"""
        return self._query(
            f"""
            select trade_date, {', '.join(VALUATION_FIELDS)}
            from read_parquet('{self._valuation_path()}')
            where stock_code = ? and trade_date between ? and ?
            order by trade_date
            """,
            [str(code).strip(), start, end],
        )

    def adj_factors(self, code: str, start: date, end: date) -> pd.DataFrame:
        """后复权因子（``trade_date`` / ``factor``）。"""
        return self._query(
            f"""
            select trade_date, factor
            from read_parquet('{self._factor_path()}')
            where stock_code = ? and trade_date between ? and ?
            order by trade_date
            """,
            [str(code).strip(), start, end],
        )

    def bars_frame(self, code: str) -> pd.DataFrame:
        """单只股票的**全部**日线（``trade_date`` / OHLCV），按日期升序。

        研究侧（标签、暴露）用它一次性取全历史，避免自己拼 SQL 或访问私有方法。
        """
        return self._query(
            f"""
            select trade_date, open, high, low, close, volume, amount
            from read_parquet('{self._bars_path()}')
            where stock_code = ? order by trade_date
            """,
            [str(code).strip()],
        )

    def bars_path(self) -> str:
        """Parquet 行情文件的 DuckDB 可读路径（供外部批量查询复用）。"""
        return self._bars_path()

    def codes(self, *, with_valuation_only: bool = False) -> list[str]:
        catalog = self.catalog()
        if with_valuation_only:
            catalog = catalog[catalog["has_valuation"]]
        return [str(value) for value in catalog["stock_code"]]

    # ------------------------------------------------------------------
    def _to_master(self, row: pd.Series) -> StockMaster:
        from src.core.schemas.stock import Exchange

        exchange = str(row.get("exchange", "") or "")
        try:
            exchange_enum = Exchange(exchange)
        except ValueError:
            exchange_enum = Exchange.UNKNOWN
        first = row.get("first_date")
        return StockMaster(
            stock_code=str(row["stock_code"]),
            wind_code="",
            name="",
            exchange=exchange_enum,
            board="",
            industry="",
            listing_date=(
                first.date() if hasattr(first, "date") else (first or None)
            ),
            total_market_cap=None,
            circulating_market_cap=None,
            is_active=True,
            source=SourceRef(
                source=f"{row.get('source', VENDOR_SOURCE_NAME)}@{VENDOR_DATA_VERSION}",
                url=str(self.data_dir),
                retrieved_at=None,
                extra={"provider": self.name, "listing_date_basis": "供应商首个交易日"},
            ),
        )


def _opt_float(value: object) -> float | None:
    """``NaN`` → ``None``（不得用 0 冒充缺失）。"""
    try:
        numeric = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return None if pd.isna(numeric) else numeric


__all__ = [
    "DEFAULT_VENDOR_DATA_DIR",
    "DELISTED_SOURCE_NAME",
    "VALUATION_FIELDS",
    "VENDOR_DATA_VERSION",
    "VENDOR_SOURCE_NAME",
    "VendorParquetProvider",
    "VendorRepoMeta",
    "vendor_available",
]
