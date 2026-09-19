"""未来收益标签的持久化（Phase 1.1）。

解决什么问题
------------
* ``/analysis/{id}/backtest`` 之前每次请求都把全库标签重算一遍（1-3s）；
* 标签不落库意味着"当时的结论依据哪些标签值"无法事后审计。

设计
----
* 唯一键 ``(stock_code, as_of, benchmark_code, label_source)``：同一来源重复计算幂等覆盖；
  不同数据来源（akshare / tencent_qfq_import / synthetic_demo）并存、可对比。
* ``is_degraded`` 与 ``label_source`` 让研究状态机能识别"这批标签能不能产出研究证据"。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.schemas.market import LabelSet
from src.db.models import ForwardLabelRow


def upsert_label(
    db: Session,
    labels: LabelSet,
    *,
    data_snapshot: str = "",
) -> None:
    """写入或更新一条标签（按唯一键幂等）。

    注意：本项目 session 统一 ``autoflush=False``，因此查询前必须显式
    ``flush()``，否则同会话内上一次 pending 的 INSERT 对本次 SELECT 不可见，
    会绕过应用层幂等直接撞数据库唯一约束。
    """
    db.flush()
    row = db.execute(
        select(ForwardLabelRow).where(
            ForwardLabelRow.stock_code == labels.stock_code,
            ForwardLabelRow.as_of == labels.as_of,
            ForwardLabelRow.benchmark_code == labels.benchmark_code,
            ForwardLabelRow.label_source == labels.data_source,
        )
    ).scalars().first()

    payload = dict(
        trade_date=labels.trade_date,
        ret_1d=labels.ret_1d, ret_5d=labels.ret_5d, ret_10d=labels.ret_10d,
        ret_20d=labels.ret_20d, ret_60d=labels.ret_60d,
        max_return_20d=labels.max_return_20d, max_drawdown_20d=labels.max_drawdown_20d,
        bench_ret_20d=labels.bench_ret_20d, excess_return_20d=labels.excess_return_20d,
        absolute_up_20d=labels.absolute_up_20d, excess_up_20d=labels.excess_up_20d,
        strong_up_20d=labels.strong_up_20d,
        drawdown_controlled_up_20d=labels.drawdown_controlled_up_20d,
        horizon_available_json=dict(labels.horizon_available),
        extra_returns_json=dict(labels.extra_returns),
        is_degraded=labels.data_is_degraded,
        data_snapshot=data_snapshot,
    )
    if row is None:
        db.add(ForwardLabelRow(
            stock_code=labels.stock_code, as_of=labels.as_of,
            benchmark_code=labels.benchmark_code, label_source=labels.data_source,
            **payload,
        ))
    else:
        for k, v in payload.items():
            setattr(row, k, v)


def load_label_rows(
    db: Session,
    *,
    benchmark_code: str,
    min_bars: int = 0,  # 兼容旧接口签名，不再使用
) -> tuple[list[dict], dict]:
    """从 ``forward_label`` 读取标签行与来源元数据。

    Returns:
        (rows, meta)；``meta`` 含 ``degraded_codes`` / ``label_sources`` /
        ``total``，供研究状态机使用。
    """
    rows = db.execute(
        select(ForwardLabelRow).where(ForwardLabelRow.benchmark_code == benchmark_code)
    ).scalars().all()

    out: list[dict] = []
    degraded_codes: set[str] = set()
    sources: dict[str, int] = {}
    for r in rows:
        if r.is_degraded:
            degraded_codes.add(r.stock_code)
        sources[r.label_source] = sources.get(r.label_source, 0) + 1
        out.append({
            "stock_code": r.stock_code,
            "trade_date": r.trade_date,
            "as_of": r.as_of,
            "ret_1d": r.ret_1d, "ret_5d": r.ret_5d, "ret_10d": r.ret_10d,
            "ret_20d": r.ret_20d, "ret_60d": r.ret_60d,
            "max_return_20d": r.max_return_20d,
            "max_drawdown_20d": r.max_drawdown_20d,
            "excess_return_20d": r.excess_return_20d,
            "bench_ret_20d": r.bench_ret_20d,
            "absolute_up_20d": r.absolute_up_20d,
            "excess_up_20d": r.excess_up_20d,
            "strong_up_20d": r.strong_up_20d,
        })
    meta = {
        "total": len(out),
        "degraded_codes": sorted(degraded_codes),
        "label_sources": sources,
    }
    return out, meta


__all__ = ["upsert_label", "load_label_rows"]
