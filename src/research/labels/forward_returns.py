"""未来收益标签计算（architecture §41、§42）。

**P0 纪律：未来数据只能作为 label，绝不能作为 as_of 时刻的输入特征。**

本模块的所有函数签名都强制要求传入 ``as_of``，并且内部只允许**向后**取数据。
若要计算"截至 as_of 可见的特征"，请使用
``src.market.normalization.frames.clip_to_as_of``。

标签定义
--------
    ret_Nd              未来第 N 个交易日相对基准日收盘的收益率
    max_return_20d      未来 20 个交易日内的最大上涨幅度
    max_drawdown_20d    未来 20 个交易日内的最大回撤（负数）
    excess_return_20d   ret_20d − benchmark_ret_20d

「上涨」的多重定义（architecture §42），避免牛市里所有因子都显得"很准"：

    absolute_up_20d              ret_20d > 0
    excess_up_20d                ret_20d − bench_20d > 0
    strong_up_20d                ret_20d > 10%
    drawdown_controlled_up_20d   ret_20d > 0 且 max_drawdown_20d > −10%
"""

from __future__ import annotations

from datetime import date

from src.core.config import settings
from src.core.schemas.market import BarSeries, LabelSet

STRONG_UP_THRESHOLD = 0.10
DRAWDOWN_CONTROL_THRESHOLD = -0.10


class InsufficientForwardData(Exception):
    """未来数据不足（例如 as_of 太接近数据末端），该样本必须被跳过而非用 0 填充。"""


def _index_of(series: BarSeries, target: date) -> int | None:
    """找到 >= target 的第一个交易日索引。"""
    for i, bar in enumerate(series.bars):
        if bar.trade_date >= target:
            return i
    return None


def compute_labels(
    stock_series: BarSeries,
    as_of: date,
    *,
    benchmark_series: BarSeries | None = None,
    benchmark_code: str = "000300",
    horizons: tuple[int, ...] | None = None,
) -> LabelSet:
    """计算 ``as_of`` 之后的未来收益标签。

    Args:
        stock_series: 股票日线（**必须包含 as_of 之后的数据**，否则无法计算标签）。
        as_of: 特征基准日。标签基于 >= as_of 的第一个交易日收盘计算。
        benchmark_series: 基准指数日线（可选，用于超额收益）。

    Raises:
        InsufficientForwardData: 基准日或所需持有期数据缺失。
    """
    horizons = horizons or settings.label_horizons
    bars = stock_series.bars
    base_idx = _index_of(stock_series, as_of)
    if base_idx is None:
        raise InsufficientForwardData(f"{stock_series.stock_code} 在 {as_of} 之后无任何交易日数据")

    trade_date = bars[base_idx].trade_date
    base_close = bars[base_idx].close
    if base_close is None:
        raise InsufficientForwardData(f"{stock_series.stock_code} {trade_date} 收盘价缺失")

    labels = LabelSet(
        stock_code=stock_series.stock_code, as_of=as_of, trade_date=trade_date,
        benchmark_code=benchmark_code,
        data_is_degraded=bool(stock_series.is_degraded) or bool(
            benchmark_series and benchmark_series.is_degraded
        ),
        data_source=str(getattr(stock_series.source_ref, "source", "") or ""),
    )

    standard = set(settings.label_horizons)

    for h in horizons:
        idx = base_idx + h
        ok = idx < len(bars) and bars[idx].close is not None
        labels.horizon_available[f"{h}d"] = ok
        if not ok:
            continue
        ret = round(bars[idx].close / base_close - 1.0, 6)
        if h in standard:
            setattr(labels, f"ret_{h}d", ret)
        else:
            # 非标准持有期：显式落到 extra_returns，不做动态属性写入
            labels.extra_returns[f"ret_{h}d"] = ret

    # --- 20 日路径指标 ---
    fwd = bars[base_idx: base_idx + 21]
    if len(fwd) >= 2:
        closes = [b.close for b in fwd if b.close is not None]
        highs = [b.high for b in fwd if b.high is not None] or closes
        lows = [b.low for b in fwd if b.low is not None] or closes
        if closes:
            labels.max_return_20d = round(max(highs) / base_close - 1.0, 6)
            labels.max_drawdown_20d = round(min(lows) / base_close - 1.0, 6)

    # --- 基准与超额 ---
    # 审计修正：超额收益必须与股票相同的**日历区间**对齐，而不是与基准自身的
    # 第 20 根 bar 对齐。否则股票长期停牌时，个股窗口实际跨越远超 20 个自然日，
    # 而基准只走了 20 个交易日，两者口径错配。
    if benchmark_series is not None and labels.ret_20d is not None:
        stock_end_idx = base_idx + 20
        if stock_end_idx < len(bars):
            stock_end_date = bars[stock_end_idx].trade_date
            b_start = _index_of(benchmark_series, trade_date)
            b_end = _index_of(benchmark_series, stock_end_date)
            if b_start is not None and b_end is not None:
                b0 = benchmark_series.bars[b_start].close
                b1 = benchmark_series.bars[b_end].close
                if b0 and b1:
                    bench_ret = b1 / b0 - 1.0
                    labels.bench_ret_20d = round(bench_ret, 6)
                    labels.excess_return_20d = round(labels.ret_20d - bench_ret, 6)

    # --- 多重"上涨"定义 ---
    if labels.ret_20d is not None:
        labels.absolute_up_20d = labels.ret_20d > 0
        labels.strong_up_20d = labels.ret_20d > STRONG_UP_THRESHOLD
        if labels.max_drawdown_20d is not None:
            labels.drawdown_controlled_up_20d = (
                labels.ret_20d > 0 and labels.max_drawdown_20d > DRAWDOWN_CONTROL_THRESHOLD
            )
    if labels.excess_return_20d is not None:
        labels.excess_up_20d = labels.excess_return_20d > 0

    return labels


def visible_slice(series: BarSeries, as_of: date) -> BarSeries:
    """返回 ``as_of`` 及之前的行情 —— 任何特征计算的唯一合法输入。

    这是防未来数据泄漏的**唯一入口**，测试 ``test_no_future_data_access``
    会验证所有特征路径都经过它。
    """
    from src.market.normalization.frames import clip_to_as_of

    return clip_to_as_of(series, as_of)
