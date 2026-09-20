"""供应商历史数据存储（全 A 日 K + 复权因子）—— 只读门面。

数据来源与为什么单独一个模块
----------------------------
本机 ``E:\\AStockData\\raw\\local_vendor\\original_files\\incoming\\股票历史数据\\``
与 NAS ``/vol1/1000/股票历史数据/`` 是**同一份供应商导出**（TuShare 派生）：

    全A日K/YYYY.zip          每只股票一个 CSV：YYYY/{code}.{SH,SZ,BJ}.csv
    复权因子/复权因子_后复权.zip  每只股票一个 CSV：{code}.{SH,SZ}.csv

它的**独有价值**（Phase 3 的 canonical 快照没有的）：

* 逐日估值：``pe / pe_ttm / pb / ps / ps_ttm / dv_yield / dv_ttm``
* 逐日股本与市值：``total_share / float_share / free_share / total_mv / circ_mv``
* 交易活跃度：``turnover / turnover_free / volume_ratio``

这些正是 Phase 3 报告里记为 ``MARKET_CAP_UNAVAILABLE`` / ``VALUE_FACTOR_UNAVAILABLE``
的两条限制所需要的字段，而且**是逐日 PIT 的**（不是"当前值回填"）。

**它的缺口**：不含退市股（``survivorship_bias`` 意义上的样本外）。
退市股只能由 ``E:\\AStockData`` 的 ``delisted_complement`` 补齐（仅 OHLCV，无估值）。

纪律
----
* 本模块**只读**：不写、不改、不移动供应商文件。
* 年包是"按年分文件"的：读一只股票的完整历史需要扫全部年包，
  因此生产路径**必须**先用 ``scripts/phase4_import_vendor.py`` 一次性转成 Parquet，
  再由 ``src/market/providers/vendor_parquet.py`` 读取。本模块只服务那个转换脚本。
* 复权因子有**前复权与后复权两种**。本项目收益口径是 ``raw × adj_factor``（即后复权），
  因此只使用 ``复权因子_后复权.zip``；前复权包的存在是为了可核对，不参与计算。
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

#: 默认数据根（本机）；NAS 上以 ``SMP_VENDOR_ROOT`` 覆盖
DEFAULT_VENDOR_ROOT = Path(
    r"E:\AStockData\raw\local_vendor\original_files\incoming\股票历史数据"
)
#: 年包目录名与因子包名
DAILY_DIR = "全A日K"
ADJ_HFQ_ZIP = Path("复权因子") / "复权因子_后复权.zip"
ADJ_QFQ_ZIP = Path("复权因子") / "复权因子_前复权.zip"

#: 日 K CSV 的列（供应商原始表头；``code`` 与 ``datetime`` 是标识列）
DAILY_COLUMNS: tuple[str, ...] = (
    "code", "datetime", "open", "high", "low", "close", "pre_close", "change",
    "pct_chg", "volume", "amount", "turnover", "turnover_free", "volume_ratio",
    "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_yield", "dv_ttm",
    "total_share", "float_share", "free_share", "total_mv", "circ_mv",
)
#: 估值/股本列（研究用；与 OHLCV 分表存放）
VALUATION_COLUMNS: tuple[str, ...] = (
    "turnover", "turnover_free", "volume_ratio",
    "pe", "pe_ttm", "pb", "ps", "ps_ttm", "dv_yield", "dv_ttm",
    "total_share", "float_share", "free_share", "total_mv", "circ_mv",
)
#: 行情列
BAR_COLUMNS: tuple[str, ...] = (
    "open", "high", "low", "close", "pre_close", "change", "pct_chg", "volume", "amount",
)
#: 供应商代码后缀 → 交易所
SUFFIX_TO_EXCHANGE: dict[str, str] = {"SH": "SSE", "SZ": "SZSE", "BJ": "BSE"}


@dataclass(frozen=True)
class VendorCode:
    """供应商代码（``600519.SH``）解析结果。"""

    raw: str
    code: str
    suffix: str
    exchange: str

    @classmethod
    def parse(cls, value: str) -> VendorCode:
        text = str(value).strip().upper()
        if "." in text:
            code, suffix = text.split(".", 1)
        else:
            code, suffix = text, ""
        return cls(
            raw=text, code=code, suffix=suffix,
            exchange=SUFFIX_TO_EXCHANGE.get(suffix, "UNKNOWN"),
        )


class VendorZipStore:
    """``全A日K/*.zip`` + ``复权因子_后复权.zip`` 的只读读取器。"""

    def __init__(self, root: Path = DEFAULT_VENDOR_ROOT) -> None:
        self.root = Path(root)
        self.daily_dir = self.root / DAILY_DIR
        if not self.daily_dir.is_dir():
            raise FileNotFoundError(f"缺少供应商日 K 目录：{self.daily_dir}")

    # ------------------------------------------------------------------
    @property
    def year_zips(self) -> list[Path]:
        return sorted(self.daily_dir.glob("*.zip"))

    def years(self) -> list[str]:
        return [path.stem for path in self.year_zips]

    def code_index(self) -> dict[str, list[str]]:
        """``股票代码 -> 出现过的年份列表``（只要中央目录，不解压）。"""
        index: dict[str, list[str]] = {}
        for path in self.year_zips:
            year = path.stem
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.endswith(".csv") or name.startswith("__MACOSX"):
                        continue
                    stem = Path(name).stem          # 600966.SH
                    code = stem.split(".")[0]
                    index.setdefault(code, []).append(year)
        return index

    def read_year(self, year: str) -> pd.DataFrame:
        """读取一个年包的全部股票日 K（返回长表，含 ``stock_code`` / ``exchange``）。"""
        path = self.daily_dir / f"{year}.zip"
        if not path.is_file():
            raise FileNotFoundError(f"缺少年包：{path}")
        frames: list[pd.DataFrame] = []
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith(".csv") or name.startswith("__MACOSX"):
                    continue
                vendor = VendorCode.parse(Path(name).stem)
                with archive.open(name) as handle:
                    raw = handle.read()
                if not raw.strip():
                    continue
                frame = pd.read_csv(io.BytesIO(raw), dtype=str, encoding="utf-8-sig")
                if frame.empty:
                    continue
                frame["stock_code"] = vendor.code
                frame["exchange"] = vendor.exchange
                frames.append(frame)
        if not frames:
            return pd.DataFrame(columns=[*DAILY_COLUMNS, "stock_code", "exchange"])
        out = pd.concat(frames, ignore_index=True)
        out = out.loc[:, [c for c in DAILY_COLUMNS if c in out.columns]
                       + ["stock_code", "exchange"]]
        return out

    def read_adj_factors(self, *, which: str = "hfq") -> pd.DataFrame:
        """读取后复权（默认）或前复权因子；返回 ``stock_code`` / ``trade_date`` / ``factor``。"""
        rel = ADJ_HFQ_ZIP if which == "hfq" else ADJ_QFQ_ZIP
        path = self.root / rel
        if not path.is_file():
            raise FileNotFoundError(f"缺少复权因子包：{path}")
        frames: list[pd.DataFrame] = []
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if not name.endswith(".csv"):
                    continue
                code = Path(name).stem.split(".")[0]
                with archive.open(name) as handle:
                    raw = handle.read()
                if not raw.strip():
                    continue
                frame = pd.read_csv(io.BytesIO(raw), dtype=str, encoding="utf-8-sig")
                if frame.empty:
                    continue
                frame.columns = ["vendor_code", "trade_date", "factor"]
                frame["stock_code"] = code
                frames.append(frame[["stock_code", "trade_date", "factor"]])
        if not frames:
            return pd.DataFrame(columns=["stock_code", "trade_date", "factor"])
        return pd.concat(frames, ignore_index=True)


def to_numeric(frame: pd.DataFrame, columns: tuple[str, ...] = BAR_COLUMNS + VALUATION_COLUMNS) -> pd.DataFrame:
    """把供应商的字符串列转成数值（空串 → NaN，**不填 0**）。"""
    out = frame.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_numeric(out[column], errors="coerce")
    if "datetime" in out.columns:
        out["trade_date"] = pd.to_datetime(out["datetime"], errors="coerce").dt.date
        out = out.drop(columns=["datetime"])
    return out


__all__ = [
    "ADJ_HFQ_ZIP",
    "ADJ_QFQ_ZIP",
    "BAR_COLUMNS",
    "DAILY_COLUMNS",
    "DAILY_DIR",
    "DEFAULT_VENDOR_ROOT",
    "SUFFIX_TO_EXCHANGE",
    "VALUATION_COLUMNS",
    "VendorCode",
    "VendorZipStore",
    "to_numeric",
]
