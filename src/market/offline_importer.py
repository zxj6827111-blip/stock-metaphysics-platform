"""离线真实行情导入器：``data/import/`` → ``market_bar_daily`` 表。

纪律
----
* 只导入带有 ``_meta.json`` 来源信息的快照目录；
* 写入行标记 ``source=tencent_qfq_import``、``is_degraded=False``
  （这是真实历史行情，不是合成数据）；
* 每次导入覆盖同代码同复权口径的旧行（幂等），
  但**不同快照日的导入会改变历史价格锚点**，因此导入后必须同步
  ``settings.market_data_version`` 语义 —— 见 ``docs/methodology.md``。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.db.base import init_db, session_scope
from src.db.models import MarketBarDailyRow

IMPORT_SOURCE_TAG = "tencent_hfq_import"


def import_market_to_db(
    import_dir: Path | None = None,
    *,
    write_db: bool = True,
) -> dict:
    """校验并导入 data/import/ 的全部行情文件。

    Returns:
        统计与问题清单（``errors`` 非空时必须视为失败）。
    """
    from src.market.providers.offline import DEFAULT_IMPORT_DIR, OfflineImportMeta

    root = import_dir or DEFAULT_IMPORT_DIR
    meta = OfflineImportMeta(root / "_meta.json")
    errors: list[str] = []
    warnings: list[str] = []

    if not meta.available:
        return {
            "series_written": 0,
            "rows_written": 0,
            "errors": [f"缺少 _meta.json：{root}，导入被拒绝（来源不明的数据不得入库）"],
            "warnings": warnings,
        }

    bars_dir = root / "bars"
    if not bars_dir.exists():
        return {
            "series_written": 0, "rows_written": 0,
            "errors": [f"缺少 bars/ 目录：{bars_dir}"], "warnings": warnings,
        }

    frames: list[tuple[str, bool, pd.DataFrame]] = []
    for path in sorted(bars_dir.glob("*.csv")):
        code = path.stem
        is_bench = code.startswith("IDX")
        df = pd.read_csv(path)
        problems = _validate(df, code)
        errors.extend(problems)
        frames.append((code, is_bench, df))

    if errors:
        return {"series_written": 0, "rows_written": 0, "errors": errors, "warnings": warnings}

    if not write_db:
        return {
            "series_written": len(frames),
            "rows_written": int(sum(len(df) for _, _, df in frames)),
            "errors": [], "warnings": warnings,
        }

    init_db()
    total_rows = 0
    with session_scope() as db:
        from sqlalchemy import delete

        for code, is_bench, df in frames:
            db.execute(
                delete(MarketBarDailyRow).where(MarketBarDailyRow.stock_code == code)
            )
            for row in df.to_dict("records"):
                db.add(MarketBarDailyRow(
                    stock_code=code,
                    trade_date=pd.to_datetime(row["trade_date"]).date(),
                    open=_num(row.get("open")), high=_num(row.get("high")),
                    low=_num(row.get("low")), close=_num(row.get("close")),
                    volume=_num(row.get("volume")), amount=_num(row.get("amount")),
                    turnover=_num(row.get("turnover")), pct_change=_num(row.get("pct_change")),
                    adjust=_norm_adjust(row.get("adjust")),
                    is_benchmark=is_bench,
                    source=IMPORT_SOURCE_TAG,
                    is_degraded=False,
                ))
                total_rows += 1

    return {
        "series_written": len(frames),
        "rows_written": total_rows,
        "errors": [],
        "warnings": warnings,
        "source": IMPORT_SOURCE_TAG,
        "snapshot_fetched_at": meta.fetched_at,
    }


def _validate(df: pd.DataFrame, code: str) -> list[str]:
    problems: list[str] = []
    required = {"trade_date", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        return [f"{code}: 缺少列 {sorted(missing)}"]
    if len(df) == 0:
        return [f"{code}: 空文件"]
    dates = pd.to_datetime(df["trade_date"], errors="coerce")
    if dates.isna().any():
        problems.append(f"{code}: 存在无法解析的 trade_date")
    if not dates.is_monotonic_increasing:
        problems.append(f"{code}: 日期未单调递增")
    if dates.duplicated().any():
        problems.append(f"{code}: 存在重复交易日")
    closes = pd.to_numeric(df["close"], errors="coerce")
    if closes.isna().any():
        problems.append(f"{code}: 存在无法解析的收盘价")
    elif (closes <= 0).any():
        # hfq 快照必须恒为正；qfq 在深历史区间会产生负价格（除权减现金分红）
        # 导致收益率符号翻转 —— 非正价格一律拒绝导入，不得静默留毒。
        bad = df.loc[closes <= 0, "trade_date"].astype(str).head(3).tolist()
        problems.append(f"{code}: 存在非正收盘价（{bad} 等）—— 禁止导入")
    highs = pd.to_numeric(df["high"], errors="coerce")
    lows = pd.to_numeric(df["low"], errors="coerce")
    if ((highs < lows) & highs.notna() & lows.notna()).any():
        problems.append(f"{code}: 存在 high < low 行")
    return problems


def _num(v) -> float | None:  # type: ignore[no-untyped-def]
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if pd.isna(f) else f


def _norm_adjust(v) -> str:  # type: ignore[no-untyped-def]
    s = str(v).strip() if v is not None else ""
    return s if s in ("hfq", "qfq", "none") else ("none" if s in ("", "nan", "None") else s)


def import_status(import_dir: Path | None = None) -> dict:
    """供 API / doctor 查询当前真实导入快照状态。"""
    from src.market.providers.offline import DEFAULT_IMPORT_DIR, OfflineImportMeta

    root = import_dir or DEFAULT_IMPORT_DIR
    meta = OfflineImportMeta(root / "_meta.json")
    stocks_path = root / "stocks.csv"
    stocks = 0
    if stocks_path.exists():
        stocks = max(0, len(stocks_path.read_text(encoding="utf-8").splitlines()) - 1)
    return {
        "available": meta.available,
        "fetched_at": meta.fetched_at or None,
        "source": meta.payload.get("provider"),
        "stocks": stocks,
        "snapshot_note": meta.payload.get("snapshot_note", ""),
    }


__all__ = ["import_market_to_db", "import_status", "IMPORT_SOURCE_TAG"]
