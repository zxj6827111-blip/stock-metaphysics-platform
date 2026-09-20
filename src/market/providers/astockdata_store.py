"""AStockDataBlobStore：读取 E:\\AStockData 的 npz blob 数据集。

只读访问；"manifest" 是一份 JSON，声明 dataset_id / symbol -> blob_sha256 / 起止日期；
真实 OHLCV 按 blob 存储为 ``.npz``（键：``trade_date, open, high, low, close, volume, amount``）。

该模块**不做任何复权**；复权完全由调用者决定（见 ``src/research/universe/astockdata_adapter.py``）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_ROOT = Path(os.environ.get("SMP_ASTOCKDATA_ROOT", r"E:\AStockData"))
MANIFEST_DIR = Path("datasets/market_data/manifests")
BLOB_DIR = Path("datasets/market_data/blobs")


@dataclass(frozen=True)
class SymbolEntry:
    symbol: str            # SSE.STK.600519
    blob_sha256: str
    first_date: int        # yyyymmdd
    last_date: int
    row_count: int
    quality: str

    @property
    def stock_code(self) -> str:
        """``SSE.STK.600519`` → ``600519``"""
        return self.symbol.rsplit(".", 1)[-1]

    @property
    def exchange(self) -> str:
        """``SSE.STK.600519`` → ``SSE``"""
        return self.symbol.split(".", 1)[0]


class AStockDataManifest:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.payload = json.loads(path.read_text(encoding="utf-8"))
        self.symbols: dict[str, SymbolEntry] = {
            s["symbol"]: SymbolEntry(
                symbol=s["symbol"],
                blob_sha256=s["blob_sha256"],
                first_date=int(s["first_date"]),
                last_date=int(s["last_date"]),
                row_count=int(s["row_count"]),
                quality=str(s.get("quality", "")),
            )
            for s in self.payload.get("symbols", [])
        }

    @property
    def dataset_id(self) -> str:
        return str(self.payload.get("dataset_id", ""))

    @property
    def adjustment(self) -> str:
        return str(self.payload.get("adjustment", ""))

    @property
    def cutoff_date(self) -> int:
        return int(self.payload.get("data_cutoff_date") or 0)

    @property
    def delisted_coverage_complete(self) -> bool:
        return bool(self.payload.get("delisted_coverage_complete"))

    @property
    def survivorship_bias(self) -> bool | None:
        v = self.payload.get("survivorship_bias")
        return None if v is None else bool(v)


class AStockDataBlobStore:
    """``E:\\AStockData`` 的只读门面。

    用法::

        store = AStockDataBlobStore.latest_composite_none()
        for sym, entry in store.manifest.symbols.items():
            df = store.load_bars(entry)       # -> DataFrame with trade_date/open/...
            adj = store.load_adj_factor(sym)  # -> DataFrame with trade_date/adj_factor
    """

    def __init__(self, root: Path = DEFAULT_ROOT, manifest: AStockDataManifest | None = None) -> None:
        self.root = root
        if manifest is None:
            manifest = self._load_default_manifest()
        self.manifest = manifest

    # ------------------------------------------------------------------
    # 工厂
    # ------------------------------------------------------------------
    @classmethod
    def latest_composite_none(cls, root: Path = DEFAULT_ROOT) -> AStockDataBlobStore:
        """加载最新 ``internal_composite_none_1d_*.json``。"""
        mdir = root / MANIFEST_DIR
        candidates = sorted(mdir.glob("internal_composite_none_1d_*.json"))
        if not candidates:
            raise FileNotFoundError(
                f"未找到 composite_none manifest：{mdir}"
            )
        return cls(root=root, manifest=AStockDataManifest(candidates[-1]))

    @classmethod
    def from_manifest(cls, path: Path, root: Path = DEFAULT_ROOT) -> AStockDataBlobStore:
        return cls(root=root, manifest=AStockDataManifest(path))

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def load_bars(self, symbol: str) -> pd.DataFrame:
        """读取一只股票的完整 OHLCV。

        返回 DataFrame：``trade_date(datetime64), open, high, low, close, volume, amount``，
        按 ``trade_date`` 升序。
        """
        entry = self.manifest.symbols.get(symbol)
        if entry is None:
            raise KeyError(f"{symbol} 不在 manifest {self.manifest.dataset_id} 内")
        blob = self.root / BLOB_DIR / f"{entry.blob_sha256}.npz"
        if not blob.exists():
            raise FileNotFoundError(f"缺少 blob: {blob}")
        raw = np.load(blob, allow_pickle=True)
        df = pd.DataFrame({
            "trade_date": pd.to_datetime(raw["trade_date"].astype(str), format="%Y%m%d"),
            "open": raw["open"].astype(float),
            "high": raw["high"].astype(float),
            "low": raw["low"].astype(float),
            "close": raw["close"].astype(float),
            "volume": raw["volume"].astype(float),
            "amount": raw["amount"].astype(float),
        })
        return df

    def load_adj_factor(self, ts_code: str, *, snapshot: str | None = None) -> pd.DataFrame:
        """读取 ``adj_factor`` 历史（TuShare 格式: trade_date, adj_factor）。

        ``snapshot`` 默认 ``tsfactor_20260731T221443_49624041``
        （首个抓取的全量快照，背书最稳定）。
        """
        snap = snapshot or "tsfactor_20260731T221443_49624041"
        path = self.root / "factors" / "tushare" / "adj_factor" / snap / f"{ts_code}.csv"
        if not path.exists():
            raise FileNotFoundError(f"缺少 adj_factor: {path}")
        df = pd.read_csv(path, dtype={"trade_date": str, "adj_factor": float})
        df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
        return df.rename(columns={"adj_factor": "factor"})


__all__ = [
    "AStockDataBlobStore",
    "AStockDataManifest",
    "SymbolEntry",
    "DEFAULT_ROOT",
]
