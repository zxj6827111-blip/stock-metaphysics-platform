"""EvidenceBundle 构建（Phase 2E）—— 从已落库的分析结果组装证据包。

它只做**组装**，不做任何计算：
所有数字都来自确定性代码已经产出的盘面 / 因子 / 观点 / 共识 / 研究状态。
这样 Narrator 才不可能"顺便算一点东西"。

古籍检索是唯一的外部输入，且**强制同时返回支持与反证**。
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from src.core.schemas.analysis import AnalysisRun, MetaphysicsOpinion
from src.core.schemas.common import Availability, VersionStamp, Warning_
from src.core.schemas.evidence import (
    EvidenceBirthProfile,
    EvidenceBundle,
    EvidenceClassical,
    EvidenceHistorical,
    EvidenceMarketQuality,
    EvidenceStock,
)
from src.knowledge.ingest.loader import corpus_meta
from src.knowledge.retrieval.provider import KnowledgeProvider, build_query_from_factors

#: 语料层面的固定提示（写入每个 bundle 的 classical.corpus_warnings）
CORPUS_WARNINGS: tuple[str, ...] = (
    "古籍语料**未逐字校勘**（见 knowledge/*/classical_seed.json 的 _meta）。"
    "正式发布前必须完成校勘；任何引用不得声称已校核。",
    "古籍条文只说明传统术数的说法，**不构成对股票收益的任何判断**。",
    "检索结果同时包含支持与反证，以避免『先有结论后找古籍』。",
)


def _opinion_assumptions(opinions: dict[str, MetaphysicsOpinion]) -> list[str]:
    out: list[str] = []
    for key in sorted(opinions):
        for a in opinions[key].assumptions:
            label = f"[{key}] {a}"
            if label not in out:
                out.append(label)
    return out


def build_evidence_bundle(
    *,
    run: AnalysisRun,
    ziwei_charts: dict[str, dict] | None = None,
    raw_bazi_chart: dict | None = None,
    raw_huangli: dict | None = None,
    knowledge: KnowledgeProvider | None = None,
    historical_stats: dict | None = None,
    negative_control_stats: dict | None = None,
    research_status: str = "NOT_RUN",
    research_status_reasons: list[str] | None = None,
    market_quality: EvidenceMarketQuality | None = None,
    extra_warnings: list[Warning_] | None = None,
) -> EvidenceBundle:
    """组装 EvidenceBundle。

    **只允许读取已确定的结果**，不得在此处调用任何引擎。
    """
    bundle = EvidenceBundle(
        analysis_id=run.analysis_id,
        generated_at=datetime.now(),
        stock=_stock_of(run),
        birth_profile=_birth_profile_of(run),
        market_data_quality=market_quality or EvidenceMarketQuality(),
        bazi_chart=raw_bazi_chart or (run.factor_set and None) or None,
        ziwei_charts=dict(ziwei_charts or {}),
        huangli=raw_huangli,
        factors=run.factor_set,
        engine_opinions=dict(run.opinions or {}),
        consensus=run.consensus,
        conflicts=run.conflict,
        research_status=research_status,
        historical=EvidenceHistorical(
            research_status=research_status,
            research_status_reasons=list(research_status_reasons or []),
            stats=dict(historical_stats or {}),
            negative_control=dict(negative_control_stats or {}),
            note=(
                "规则强度与统计有效性是两件事：分数只表达传统规则认为的方向与强弱，"
                "它是否在历史上有信息量由 research_status 回答。"
            ),
        ),
        negative_control_stats=dict(negative_control_stats or {}),
        versions=run.versions or VersionStamp(),
        assumptions=_opinion_assumptions(run.opinions or {}),
        warnings=list(extra_warnings or []) + list(run.warnings or []),
    )

    # --- 古籍证据（支持 + 反证） ---
    bundle.classical, bundle.classical_support, bundle.classical_counter_evidence = _classical(
        run, knowledge,
    )
    return bundle


def _stock_of(run: AnalysisRun) -> EvidenceStock | None:
    if run.stock is None:
        return None
    return EvidenceStock(
        stock_code=run.stock.stock_code,
        name=run.stock.name or "",
        exchange=str(run.stock.exchange or ""),
        board=run.stock.board or "",
        industry=run.stock.industry or "",
        listing_date=str(run.stock.listing_date or ""),
    )


def _birth_profile_of(run: AnalysisRun) -> EvidenceBirthProfile | None:
    bp = run.birth_profile
    if bp is None:
        return None
    return EvidenceBirthProfile(
        birth_basis=str(bp.birth_basis or ""),
        birth_datetime=bp.birth_datetime.isoformat() if bp.birth_datetime else "",
        timezone=bp.timezone or "",
        variant_mode=str(bp.variant_mode or ""),
        birth_profile_version=bp.birth_profile_version or "",
        data_quality=(bp.data_quality.model_dump(mode="json") if bp.data_quality else {}),
        assumptions=[a.model_dump(mode="json") for a in (bp.assumptions or [])],
    )


def _classical(
    run: AnalysisRun, knowledge: KnowledgeProvider | None,
) -> tuple[EvidenceClassical, list[dict], list[dict]]:
    """检索古籍证据。检索失败时返回空集合 + 明确提示，**不伪造条文**。"""
    warnings = list(CORPUS_WARNINGS)
    meta = corpus_meta()
    if meta.get("textual_criticism_warning"):
        warnings.append(str(meta["textual_criticism_warning"]))
    if meta.get("missing_domains"):
        warnings.append(f"以下域的语料文件缺失，未参与检索：{meta['missing_domains']}")

    factors = run.factor_set
    if factors is None or knowledge is None:
        return (
            EvidenceClassical(
                retrieval_method="",
                corpus_warnings=warnings + ["本次未能执行古籍检索（缺少因子或知识库不可用）。"],
            ),
            [], [],
        )

    ranked = sorted(
        [o for o in factors.observations if o.normalized_value is not None],
        key=lambda o: -abs(o.normalized_value or 0.0),
    )[:12]
    query = build_query_from_factors([o.factor_id for o in ranked])
    query.top_k = 8
    try:
        bundle = knowledge.search(query)
    except Exception as exc:  # noqa: BLE001 - 检索失败不能拖垮报告
        return (
            EvidenceClassical(
                retrieval_method="",
                corpus_warnings=warnings + [f"古籍检索失败：{type(exc).__name__}: {exc}"],
            ),
            [], [],
        )

    def dump(items) -> list[dict]:  # type: ignore[no-untyped-def]
        return [
            {
                "entry_id": e.entry_id,
                "book": e.book,
                "chapter": e.chapter,
                "original_text": e.original_text,
                "modern_note": e.modern_note,
                "score": e.score,
                "stance": str(e.stance),
                "source": e.source,
                "edition": e.edition,
                "provenance": e.provenance,
                "license_status": str(e.license_status),
            }
            for e in items
        ]

    supporting = dump(getattr(bundle, "supporting_evidence", []) or [])
    counter = dump(getattr(bundle, "counter_evidence", []) or [])
    neutral = dump(getattr(bundle, "neutral_evidence", []) or [])

    return (
        EvidenceClassical(
            supporting=supporting, counter=counter, neutral=neutral,
            retrieval_method=getattr(bundle, "retrieval_method", ""),
            corpus_warnings=warnings,
        ),
        supporting, counter,
    )


def load_historical_stats(db: Session, stock_code: str, engine: str = "") -> dict:
    """读取与该股票相关的历史验证记录。

    ``backtest_result`` 表按 **experiment_id** 关联（不直接存 stock_code）——
    研究实验的股票池写在 ``backtest_experiment.payload_json`` 里。
    因此这里先用股票池过滤实验，再取结果；**没有记录就如实返回 NOT_RUN**，
    绝不编造统计数字。
    """
    from sqlalchemy import select

    from src.db.models import BacktestExperimentRow, BacktestResultRow

    exps = db.execute(select(BacktestExperimentRow)).scalars().all()
    matched = [
        e for e in exps
        if stock_code in json.dumps(e.payload_json or {}, ensure_ascii=False)
    ]
    if not matched:
        return {
            "status": "NOT_RUN",
            "note": f"{stock_code} 尚无历史验证实验记录（未运行 POST /api/v1/research/run）。",
        }
    ids = [e.experiment_id for e in matched]
    rows = db.execute(
        select(BacktestResultRow).where(BacktestResultRow.experiment_id.in_(ids))
    ).scalars().all()
    if not rows:
        return {
            "status": "NOT_RUN",
            "experiments": ids,
            "note": "实验存在但没有结果行。",
        }
    results = [
        {
            "experiment_id": r.experiment_id,
            "variant": r.variant,
            "horizon": r.horizon,
            "sample_count": r.sample_count,
            "up_rate": r.up_rate,
            "mean_return": r.mean_return,
            "median_return": r.median_return,
            "std_return": r.std_return,
            "excess_return": r.mean_excess_return,
            "max_drawdown": r.max_drawdown,
        }
        for r in rows[:40]
    ]
    payload = matched[0].payload_json or {}
    return {
        "status": "AVAILABLE",
        "engine_filter": engine,
        "experiments": ids,
        "universe_size": len(payload.get("universe", []) or []),
        "results": results,
        "methodology": matched[0].methodology or "",
        "note": (
            "以上是研究实验在**历史样本**上的统计结果。"
            "样本内结果不得外推；有效性判断以 ResearchStatus 为准。"
        ),
    }


__all__ = ["build_evidence_bundle", "load_historical_stats", "CORPUS_WARNINGS"]


_ = Availability
