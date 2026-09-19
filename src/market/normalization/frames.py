"""行情数据归一化：把任意第三方 DataFrame 变成标准 ``Bar`` 序列。

必须处理的现实问题（architecture §43）：

    复权、停牌、涨跌停、上市初期异常、字段缺失、单位不一致（手/股、元/万元）

统一输出字段：date / open / high / low / close / volume / amount / turnover / pct_change
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from src.core.schemas.common import MarketDataSource, SourceRef, Warning_
from src.core.schemas.market import Bar, BarSeries

# 第三方中文列名 → 标准字段
CN_COLUMN_MAP: dict[str, str] = {
    "日期": "trade_date",
    "时间": "trade_date",
    "date": "trade_date",
    "开盘": "open",
    "今开": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "最新价": "close",
    "成交量": "volume",
    "成交额": "amount",
    "换手率": "turnover",
    "涨跌幅": "pct_change",
    "涨跌额": "change",
    "股票代码": "stock_code",
    "代码": "stock_code",
    "名称": "name",
}

NUMERIC_FIELDS = ("open", "high", "low", "close", "volume", "amount", "turnover", "pct_change")


def normalize_frame(df: pd.DataFrame, *, adjust: str = "qfq") -> pd.DataFrame:
    """重命名列、统一类型、去重排序。"""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["trade_date", *NUMERIC_FIELDS])

    out = df.rename(columns={c: CN_COLUMN_MAP.get(str(c).strip(), str(c).strip()) for c in df.columns})
    if "trade_date" not in out.columns:
        raise ValueError(f"缺少日期列，实际列：{list(df.columns)}")

    out = out.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.date
    out = out.dropna(subset=["trade_date"])

    for field in NUMERIC_FIELDS:
        if field not in out.columns:
            out[field] = np.nan
        out[field] = pd.to_numeric(out[field], errors="coerce")

    out["adjust"] = adjust
    out = out.drop_duplicates(subset=["trade_date"], keep="last")
    return out.sort_values("trade_date").reset_index(drop=True)


def frame_to_bars(df: pd.DataFrame, *, source: str = "akshare") -> list[Bar]:
    """归一化后的 DataFrame → ``Bar`` 列表。"""
    bars: list[Bar] = []
    for row in df.to_dict("records"):
        td = row.get("trade_date")
        if not isinstance(td, date):
            continue
        bars.append(
            Bar(
                trade_date=td,
                open=_f(row.get("open")),
                high=_f(row.get("high")),
                low=_f(row.get("low")),
                close=_f(row.get("close")),
                volume=_f(row.get("volume")),
                amount=_f(row.get("amount")),
                turnover=_f(row.get("turnover")),
                pct_change=_f(row.get("pct_change")),
                adjust=str(row.get("adjust", "qfq")),
                source=source,
            )
        )
    return bars


def _f(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else f


def build_series(
    code: str,
    df: pd.DataFrame,
    *,
    adjust: str = "qfq",
    source: MarketDataSource = MarketDataSource.AKSHARE,
    source_name: str = "akshare",
    is_degraded: bool = False,
    warnings: list[Warning_] | None = None,
) -> BarSeries:
    """构造 ``BarSeries``。"""
    norm = normalize_frame(df, adjust=adjust)
    bars = frame_to_bars(norm, source=source_name)
    return BarSeries(
        stock_code=code,
        bars=bars,
        source=source,
        source_ref=SourceRef(source=source_name),
        adjust=adjust,
        start=bars[0].trade_date if bars else None,
        end=bars[-1].trade_date if bars else None,
        warnings=warnings or [],
        is_degraded=is_degraded,
    )


def detect_anomalies(series: BarSeries) -> list[Warning_]:
    """行情质量体检：缺口、零成交量、异常跳变。"""
    out: list[Warning_] = []
    bars = series.bars
    if not bars:
        return [Warning_(code="MARKET_EMPTY", message="行情序列为空", severity="error")]

    null_close = sum(1 for b in bars if b.close is None)
    if null_close:
        out.append(Warning_(
            code="MARKET_NULL_CLOSE",
            message=f"{null_close} 个交易日收盘价缺失（可能为停牌）",
            severity="warning",
            context={"count": null_close},
        ))

    zero_vol = sum(1 for b in bars if (b.volume or 0) == 0)
    if zero_vol:
        out.append(Warning_(
            code="MARKET_ZERO_VOLUME",
            message=f"{zero_vol} 个交易日成交量为 0（停牌或数据缺失）",
            severity="info",
            context={"count": zero_vol},
        ))

    jumps = [b for b in bars if b.pct_change is not None and abs(b.pct_change) > 21.0]
    if jumps:
        out.append(Warning_(
            code="MARKET_PRICE_JUMP",
            message=f"{len(jumps)} 个交易日涨跌幅超过 ±21%（可能为复权或数据异常）",
            severity="warning",
            context={"count": len(jumps), "sample": [b.trade_date.isoformat() for b in jumps[:5]]},
        ))
    return out


def clip_to_as_of(series: BarSeries, as_of: date) -> BarSeries:
    """**防未来数据泄漏的核心工具**：把序列裁剪到 ``as_of`` 当日及之前。

    任何"截至 as_of 的特征计算"都必须先经过本函数。
    """
    bars = [b for b in series.bars if b.trade_date <= as_of]
    return BarSeries(
        stock_code=series.stock_code,
        bars=bars,
        source=series.source,
        source_ref=series.source_ref,
        adjust=series.adjust,
        start=bars[0].trade_date if bars else None,
        end=bars[-1].trade_date if bars else None,
        warnings=series.warnings,
        is_degraded=series.is_degraded,
    )
