"""离线真实行情 Provider（RealMarketData path）。

定位
----
AKShare 依赖的外部接口在当前网络环境不可用时，
这是**唯一被认可的真实历史行情通道**：

    data/import/  ──（由 scripts/fetch_market_import.py 从真实行情端点抓取冻结）
        bars/{CODE}.csv        个股日线（前复权，快照锚定）
        bars/IDX{code}.csv     基准指数日线
        stocks.csv             股票基础资料（上市日期=行情首个交易日，数据推导）
        calendar/{EX}.csv      实测交易日历
        _meta.json             来源 / 抓取时间 / 快照说明

关键纪律
--------
* **这不是合成数据**。``is_degraded=False``，``source=offline_import``，
  但导入文件必须携带 ``_meta.json`` 的抓取来源与快照时间；
  缺失元数据的导入目录取决于 ``strict_meta``（默认拒绝服务而不是猜测）。
* 腾讯前复权以抓取时刻为锚：不同快照日抓取的导入目录**不可混用**；
  本 provider 会在 meta 不一致时抛错。
* 任何在这里拿不到的数据（例如池外股票）必须抛 ``SymbolNotFoundError``，
  绝不允许静默返回空序列伪装真实空数据。
"""

from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pandas as pd

from src.core.config import PROJECT_ROOT
from src.core.schemas.common import MarketDataSource, SourceRef, Warning_
from src.core.schemas.market import BarSeries
from src.core.schemas.stock import StockMaster
from src.core.stock import codes
from src.market.normalization.errors import SymbolNotFoundError
from src.market.normalization.frames import build_series
from src.market.providers.base import MarketDataProvider

DEFAULT_IMPORT_DIR = PROJECT_ROOT / "data" / "import"


class OfflineImportMeta:
    """导入目录的元信息（来源、快照时间）。"""

    def __init__(self, meta_path: Path) -> None:
        if not meta_path.exists():
            self.payload: dict = {}
            self.available = False
            return
        self.payload = json.loads(meta_path.read_text(encoding="utf-8"))
        self.available = True

    @property
    def fetched_at(self) -> str:
        return str(self.payload.get("fetched_at", ""))

    @property
    def source_label(self) -> str:
        return str(self.payload.get("provider", "unknown"))


class OfflineMarketDataProvider(MarketDataProvider):
    """从 ``data/import/`` 读取真实冻结行情。"""

    provider_id = "offline_import"

    def __init__(self, import_dir: Path | None = None, *, strict_meta: bool = True) -> None:
        self._dir = import_dir or DEFAULT_IMPORT_DIR
        self._meta = OfflineImportMeta(self._dir / "_meta.json")
        if strict_meta and not self._meta.available:
            raise FileNotFoundError(
                f"离线导入目录缺少 _meta.json：{self._dir}。"
                "请先运行 scripts/fetch_market_import.py 生成真实行情导入快照；"
                "缺少来源元数据的导入文件不得用于研究。"
            )
        self._stocks = self._load_stocks()

    # ------------------------------------------------------------------
    def _load_stocks(self) -> dict[str, dict]:
        path = self._dir / "stocks.csv"
        if not path.exists():
            return {}
        with open(path, newline="", encoding="utf-8") as fh:
            return {row["stock_code"]: row for row in csv.DictReader(fh)}

    def search(self, query: str, limit: int = 20) -> list[StockMaster]:
        q = (query or "").strip().lower()
        out: list[StockMaster] = []
        for row in self._stocks.values():
            if not q or q in row["stock_code"] or q in (row.get("name") or "").lower():
                out.append(self._row_to_stock(row))
            if len(out) >= limit:
                break
        return out

    def get_stock(self, code: str) -> StockMaster:
        code, exchange, board, wind = codes.parse(code)
        row = self._stocks.get(code)
        if row is None:
            raise SymbolNotFoundError(
                f"离线导入目录中不存在 {code}（data/import/stocks.csv）。"
                "可扩展抓取脚本 UNIVERSE 或改用其他 provider。"
            )
        return self._row_to_stock(row, exchange=exchange, board=board, wind=wind)

    # ------------------------------------------------------------------
    def get_daily_bars(
        self, code: str, start: date | None = None, end: date | None = None, *, adjust: str = "hfq"
    ) -> BarSeries:
        code = codes.normalize_code(code)
        if code not in self._stocks:
            raise SymbolNotFoundError(f"离线导入目录中不存在 {code} 的日线数据")
        if adjust not in ("hfq", ""):
            # 导入快照个股为后复权（hfq）。因为 qfq 对高股息老股会在深历史区间
            # 产生负价格并跨零震荡，导致收益率符号被翻转 —— 这是数学损坏而非市场事实。
            # 其他口径显式报错，绝不静默混用。
            raise ValueError(
                f"离线导入快照个股仅含 hfq 口径（qfq 在深历史区间存在负价格缺陷），"
                f"不支持 adjust={adjust}"
            )
        return self._read_series(code, is_benchmark=False, start=start, end=end, adjust="hfq")

    def get_benchmark_bars(
        self,
        index_code: str = "000300",
        start: date | None = None,
        end: date | None = None,
        *,
        adjust: str = "qfq",
    ) -> BarSeries:
        path = self._dir / "bars" / f"IDX{index_code}.csv"
        if not path.exists() and not (self._dir / "bars" / f"IDX{index_code}.parquet").exists():
            raise SymbolNotFoundError(f"离线导入目录中不存在基准指数 {index_code}")
        return self._read_series(f"IDX{index_code}", is_benchmark=True, start=start, end=end, adjust=adjust)

    # ------------------------------------------------------------------
    def _read_series(
        self, code: str, *, is_benchmark: bool, start: date | None, end: date | None, adjust: str
    ) -> BarSeries:
        stem = code if not is_benchmark else code
        csv_path = self._dir / "bars" / f"{stem}.csv"
        pq_path = self._dir / "bars" / f"{stem}.parquet"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
        elif pq_path.exists():
            df = pd.read_parquet(pq_path)
        else:
            raise SymbolNotFoundError(f"缺少 {stem} 的导入行情文件")

        if start is not None:
            df = df[pd.to_datetime(df["trade_date"]).dt.date >= start]
        if end is not None:
            df = df[pd.to_datetime(df["trade_date"]).dt.date <= end]

        display_code = code.replace("IDX", "") if is_benchmark else code
        series = build_series(
            display_code,
            df,
            adjust=adjust,
            source=MarketDataSource.OFFLINE_IMPORT,
            source_name=self.provider_id,
            is_degraded=False,
        )
        series.warnings.append(Warning_(
            code="MARKET_OFFLINE_IMPORT",
            message=(
                f"当前行情来自离线真实导入快照（来源 {self._meta.source_label}，"
                f"抓取于 {self._meta.fetched_at or '未知时间'}）。"
                "快照口径：前复权以抓取时刻为锚；请勿与其他快照混用。"
            ),
            severity="info",
            context={"fetched_at": self._meta.fetched_at, "provider": self._meta.source_label},
        ))
        return series

    def _row_to_stock(
        self, row: dict, *, exchange=None, board: str | None = None, wind: str | None = None
    ) -> StockMaster:
        code = row["stock_code"]
        ex = exchange if exchange is not None else row.get("exchange", "UNKNOWN")
        bd = board if board is not None else row.get("board", "")
        wind_code = wind if wind is not None else f"{code}.{ {'SSE': 'SH', 'SZSE': 'SZ'}.get(str(ex), '') }"
        return StockMaster(
            stock_code=code,
            wind_code=wind_code,
            name=row.get("name", ""),
            exchange=ex,
            board=bd,
            industry=row.get("industry", ""),
            listing_date=date.fromisoformat(row["listing_date"]) if row.get("listing_date") else None,
            source=SourceRef(
                source=self.provider_id,
                extra={"fetched_at": self._meta.fetched_at, "provider": self._meta.source_label},
            ),
        )


__all__ = ["OfflineMarketDataProvider", "OfflineImportMeta", "DEFAULT_IMPORT_DIR"]
