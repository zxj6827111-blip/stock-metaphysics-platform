"""分析编排服务 —— 把「股票 → 出生档案 → 历法 → 黄历 → 八字 → 因子 → 落库」串起来。

这是 API 层唯一应该调用的业务入口。业务层不直接接触任何第三方库。
"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.schemas.analysis import (
    AnalysisRun,
    BaziAnalysisResponse,
    ConflictSnapshot,
    ConsensusSnapshot,
    MetaphysicsOpinion,
    MultiAnalysisResponse,
    ReasonItem,
)
from src.core.schemas.common import (
    CONSENSUS_CN_LABEL,
    Availability,
    ConsensusLabel,
    DataQuality,
    EngineId,
    VariantMode,
    VersionStamp,
    Warning_,
)
from src.core.schemas.factor import FactorSet
from src.core.schemas.stock import BirthProfileCreateRequest, StockBirthProfile, StockMaster
from src.core.stock import birth_profile as bp
from src.core.stock.exchange_sessions import ex_value
from src.db.models import (
    AnalysisRunRow,
    ChartArtifactRow,
    EngineRunRow,
    EngineVersionRow,
    FactorObservationRow,
    StockBirthProfileRow,
    StockMasterRow,
)
from src.engines.base import EngineContext
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine
from src.engines.huangli.huangli_engine import HuangliEngine
from src.engines.ziwei.ziwei_engine import ZiweiEngine, ZiweiUnavailableError
from src.factors.registry.compute import compute_factor_set
from src.factors.registry.definitions import DEFINITION_INDEX

# 方向标签（中文）
DIRECTION_LABEL: dict[int, str] = {1: "偏强", 0: "中性", -1: "偏弱"}

#: 引擎 → 因子命名空间前缀。观点聚合只能消费自己的命名空间，
#: 防止某个引擎"借"其他引擎的因子制造虚假一致（Phase 2 多模型纪律）。
ENGINE_FACTOR_PREFIX: dict[EngineId, str] = {
    EngineId.BAZI: "B_",
    EngineId.HUANGLI: "H_",
    EngineId.ZIWEI: "Z_",
}

#: 各引擎观点所依赖的**假设**。分歧分析需要它：如果两个引擎的差异来自
#: 假设不同（而不是模型不同），那本身不是"模型分歧"，必须能分辨出来。
OPINION_ASSUMPTIONS: dict[EngineId, tuple[str, ...]] = {
    EngineId.BAZI: (
        "股票出生的时柱口径：23:00 后归次日子时（晚子时）。",
        "运限方向 variant 在 not_applicable 下不输出大运，大运不进入本观点的因子。",
    ),
    EngineId.HUANGLI: (
        "黄历宜忌采用 lunar-python 内置通书口径；不同通书之间存在差异。",
        "神煞类字段（建除/黄黑道/十二神/星宿）置信度 ≤ 0.55，权重已相应降低。",
    ),
    EngineId.ZIWEI: (
        "股票无真实性别：紫微运限以方向 variant（顺行/逆行）表达，不默认男女。",
        "顺行/逆行 variant 的差异仅限于大限/小限顺逆与长生十二神顺逆，"
        "两者不是两条独立证据。",
        f"宫位→金融含义的映射属于本项目研究假设（{settings.ziwei_stock_mapping_version}），"
        "不是传统紫微定论。",
    ),
}


def _agreement_label(agreement_score: float, label: ConsensusLabel) -> str:
    """把方向一致度翻译成可读标签。

    注意：``MIXED`` 一定是"低" —— 即使一致度数值看起来不低，
    只要存在反向引擎，一致性就不该被描述为"中/高"。
    """
    if label == ConsensusLabel.MIXED:
        return "低（存在反向引擎）"
    if agreement_score >= 1.0:
        return "高（方向完全一致）"
    if agreement_score >= 0.6:
        return "中"
    return "低"


def direction_from_score(score: float | None) -> int:
    if score is None:
        return 0
    if score >= 58:
        return 1
    if score <= 42:
        return -1
    return 0


class AnalysisService:
    """分析编排。"""

    def __init__(
        self,
        calendar: CalendarEngine | None = None,
        huangli: HuangliEngine | None = None,
        bazi: BaziEngine | None = None,
        ziwei: ZiweiEngine | None = None,
    ) -> None:
        self.calendar = calendar or CalendarEngine()
        self.huangli = huangli or HuangliEngine(self.calendar)
        self.bazi = bazi or BaziEngine(self.calendar)
        self.ziwei = ziwei if ziwei is not None else ZiweiEngine()

    # ------------------------------------------------------------------
    # 持久化辅助
    # ------------------------------------------------------------------
    def upsert_stock(self, db: Session, stock: StockMaster) -> StockMasterRow:
        row = db.get(StockMasterRow, stock.stock_code)
        payload = {
            "wind_code": stock.wind_code,
            "name": stock.name,
            "exchange": ex_value(stock.exchange),
            "board": stock.board,
            "industry": stock.industry,
            "listing_date": stock.listing_date,
            "total_market_cap": stock.total_market_cap,
            "circulating_market_cap": stock.circulating_market_cap,
            "is_active": stock.is_active,
            "source": stock.source.source,
        }
        if row is None:
            row = StockMasterRow(stock_code=stock.stock_code, **payload)
            db.add(row)
        else:
            for k, v in payload.items():
                if v not in (None, ""):
                    setattr(row, k, v)
        db.flush()
        return row

    def save_birth_profile(self, db: Session, profile: StockBirthProfile) -> StockBirthProfileRow:
        """保存出生档案；已存在同版本则更新，**不允许覆盖其他版本**。"""
        stmt = select(StockBirthProfileRow).where(
            StockBirthProfileRow.stock_code == profile.stock_code,
            StockBirthProfileRow.birth_basis == ex_value(profile.birth_basis),
            StockBirthProfileRow.birth_profile_version == profile.birth_profile_version,
        )
        row = db.execute(stmt).scalars().first()
        payload = bp.to_row(profile)
        if row is None:
            row = StockBirthProfileRow(**payload)
            db.add(row)
        else:
            for k, v in payload.items():
                setattr(row, k, v)
        db.flush()
        return row

    def save_chart_artifact(
        self,
        db: Session,
        *,
        engine_id: str,
        engine_version: str,
        stock_code: str,
        as_of: datetime,
        input_payload: dict,
        raw_chart: dict,
        assumptions: list[dict] | None = None,
        warnings: list[dict] | None = None,
        birth_profile_version: str = "",
    ) -> str:
        chart_id = f"{engine_id}-{stock_code}-{as_of.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        db.add(ChartArtifactRow(
            chart_id=chart_id,
            stock_code=stock_code,
            engine=engine_id,
            engine_version=engine_version,
            config_version=settings.config_version,
            birth_profile_version=birth_profile_version,
            as_of=as_of,
            input_json=input_payload,
            raw_chart=raw_chart,
            assumptions_json=assumptions or [],
            warnings_json=warnings or [],
            calculated_at=datetime.now(),
        ))
        db.flush()
        return chart_id

    def save_factors(self, db: Session, factor_set: FactorSet) -> int:
        """写入因子观测（幂等：同 (code, as_of, factor_id, rule_version) 覆盖）。"""
        saved = 0
        for obs in factor_set.observations:
            stmt = select(FactorObservationRow).where(
                FactorObservationRow.stock_code == obs.stock_code,
                FactorObservationRow.as_of == obs.as_of,
                FactorObservationRow.factor_id == obs.factor_id,
                FactorObservationRow.rule_version == obs.rule_version,
            )
            row = db.execute(stmt).scalars().first()
            payload = {
                "trade_date": obs.trade_date,
                "engine": ex_value(obs.engine),
                "category": ex_value(obs.category),
                "name": obs.name,
                "raw_value_json": {"value": obs.raw_value},
                "normalized_value": obs.normalized_value,
                "direction": int(obs.direction),
                "rule_score": obs.rule_score,
                "confidence": obs.confidence,
                "availability": obs.availability,
                "engine_version": obs.engine_version,
                "config_version": obs.config_version,
                "evidence_json": obs.evidence,
                "explanation": obs.explanation,
                "warnings_json": obs.warnings,
                "computed_at": obs.computed_at,
            }
            if row is None:
                db.add(FactorObservationRow(
                    factor_id=obs.factor_id, stock_code=obs.stock_code,
                    as_of=obs.as_of, rule_version=obs.rule_version, **payload,
                ))
            else:
                for k, v in payload.items():
                    setattr(row, k, v)
            saved += 1
        db.flush()
        return saved

    def register_engine_versions(self, db: Session) -> None:
        from src.engines.bazi.bazi_engine import BaziEngine as _B
        from src.engines.calendar.calendar_engine import CalendarEngine as _C
        from src.engines.huangli.huangli_engine import HuangliEngine as _H
        from src.engines.ziwei.ziwei_engine import ZiweiEngine as _Z

        for engine in (_C(), _H(), _B(), _Z()):
            meta = engine.metadata
            stmt = select(EngineVersionRow).where(
                EngineVersionRow.engine_id == meta.engine_id,
                EngineVersionRow.engine_version == meta.engine_version,
            )
            if db.execute(stmt).scalars().first() is None:
                db.add(EngineVersionRow(
                    engine_id=meta.engine_id, engine_version=meta.engine_version,
                    display_name=meta.display_name, config_version=meta.config_version,
                    third_party=meta.third_party, third_party_commit=meta.third_party_commit,
                    notes=meta.notes,
                ))
        db.flush()

    def log_engine_run(
        self,
        db: Session,
        *,
        engine_id: str,
        engine_version: str,
        stock_code: str,
        as_of: datetime,
        status: str,
        duration_ms: int,
        warnings: list[dict] | None = None,
        error: str = "",
    ) -> None:
        db.add(EngineRunRow(
            run_id=f"{engine_id}-{uuid.uuid4().hex[:8]}",
            engine_id=engine_id, engine_version=engine_version,
            config_version=settings.config_version,
            stock_code=stock_code, as_of=as_of, status=status,
            duration_ms=duration_ms, warnings_json=warnings or [], error=error,
        ))
        db.flush()

    # ------------------------------------------------------------------
    # opinions / 展示层共识
    # ------------------------------------------------------------------
    @staticmethod
    def build_opinion(
        engine: EngineId,
        factor_set: FactorSet,
        engine_version: str,
        *,
        unavailable_reason: str = "",
    ) -> MetaphysicsOpinion:
        """由因子集合聚合出引擎观点（传统规则强度，不是收益预测）。

        每个引擎只消费**自己的**因子命名空间：
        bazi → ``B_*``、huangli → ``H_*``、ziwei → ``Z_*``。
        这保证三个观点彼此独立，不会互相"借"因子制造虚假一致。
        """
        prefix = ENGINE_FACTOR_PREFIX.get(engine)
        if prefix is None:
            return MetaphysicsOpinion(
                engine=engine, engine_version=engine_version,
                availability=Availability.UNAVAILABLE, direction=0, score=None,
                confidence=0.0,
                note=f"引擎 {engine} 尚未定义因子命名空间，不产出观点（禁止用 0 分冒充）。",
            )
        obs = [o for o in factor_set.observations if o.factor_id.startswith(prefix)
               and o.availability == "ok"]

        if not obs:
            return MetaphysicsOpinion(
                engine=engine, engine_version=engine_version,
                availability=Availability.UNAVAILABLE, direction=0, score=None,
                confidence=0.0,
                note=unavailable_reason or (
                    f"该引擎未能产出任何可用因子（命名空间 {prefix}*），"
                    "分数返回 null（不使用 0 分代替）。"
                ),
            )

        # 归一化值加权（权重 = confidence），映射到 0-100
        weights = [max(o.confidence, 1e-6) for o in obs]
        vals = [o.normalized_value or 0.0 for o in obs]
        wsum = sum(weights)
        raw = sum(v * w for v, w in zip(vals, weights, strict=True)) / wsum if wsum else 0.0
        score = max(0.0, min(100.0, 50.0 + raw * 50.0))
        direction = direction_from_score(score)

        pos = sorted(
            [o for o in obs if (o.normalized_value or 0) > 0.3],
            key=lambda x: -abs(x.normalized_value or 0),
        )[:5]
        neg = sorted(
            [o for o in obs if (o.normalized_value or 0) < -0.3],
            key=lambda x: -abs(x.normalized_value or 0),
        )[:5]

        return MetaphysicsOpinion(
            engine=engine,
            engine_version=engine_version,
            availability=Availability.OK,
            direction=direction,
            score=round(score, 2),
            confidence=round(sum(weights) / len(weights), 4),
            assumptions=list(OPINION_ASSUMPTIONS.get(engine, ())),
            top_positive_reasons=[
                ReasonItem(
                    text=o.explanation,
                    factor_ids=[o.factor_id],
                    rule_score=o.rule_score,
                    evidence=o.evidence[:2],
                )
                for o in pos
            ],
            top_negative_reasons=[
                ReasonItem(
                    text=o.explanation,
                    factor_ids=[o.factor_id],
                    rule_score=o.rule_score,
                    evidence=o.evidence[:2],
                )
                for o in neg
            ],
            factor_ids=[o.factor_id for o in obs],
            note=(
                "该分数由传统规则强度（因子 rule_score × 归一化方向）聚合而成，"
                "属于研究性指标，**不代表收益率预测，也不代表上涨概率**。"
            ),
        )

    # ------------------------------------------------------------------
    # 正式 Consensus / Conflict（Phase 2C）
    # ------------------------------------------------------------------
    @staticmethod
    def build_consensus_and_conflict(
        opinions: dict[str, MetaphysicsOpinion],
        *,
        factor_set: FactorSet | None = None,
        data_quality: str = "B",
        research_status: str = "NOT_RUN",
        historical_stats: dict | None = None,
        historical_conflict_stats: dict | None = None,
    ) -> tuple[ConsensusSnapshot, ConflictSnapshot]:
        """产出**正式**共识与分歧（``display_only=False``）。

        与展示层实现的区别：
          * 六分类 + ``agreement_score``（方向一致度，不是分数平均）；
          * 携带 ``research_status`` 与 ``historical_consensus_stats``；
          * ``interpretation`` 统一生成"共识 + 历史有效性"文案；
          * 分歧检测覆盖方向 / 因子 / 时间尺度 / 假设四层。
        """
        from src.core.orchestration.consensus import build_consensus_and_conflict

        report, conflict_report = build_consensus_and_conflict(
            opinions, factor_set=factor_set, data_quality=data_quality,
            research_status=research_status, historical_stats=historical_stats,
            historical_conflict_stats=historical_conflict_stats,
        )

        consensus = ConsensusSnapshot(
            display_only=False,
            label=report.consensus_class,
            label_cn=report.label_cn,
            participating_engines=[EngineId(k) for k in report.directions],
            unavailable_engines=[EngineId(k) for k in report.unavailable_engines],
            directions=report.directions,
            mean_score=(
                round(sum(v.score or 0.0 for v in opinions.values()
                          if v.availability == Availability.OK and v.score is not None)
                      / max(report.available_engine_count, 1), 2)
                if report.available_engine_count else None
            ),
            agreement=_agreement_label(report.agreement_score, report.consensus_class),
            historical_validity=(
                f"ResearchStatus={report.research_status}；"
                "共识与历史有效性是两件事，必须分开阅读。"
            ),
            data_quality=str(report.data_quality.get("grade", data_quality)),
            note="；".join(report.notes),
            # 注意：ConsensusLabel 是 str-Enum，str() 会给出 "ConsensusLabel.X"，
            # 必须走 ex_value() 取真正的值（HANDOFF §12.1#8 同类坑）。
            consensus_class=ex_value(report.consensus_class),
            agreement_score=report.agreement_score,
            available_engine_count=report.available_engine_count,
            positive_engine_count=report.positive_engine_count,
            negative_engine_count=report.negative_engine_count,
            neutral_engine_count=report.neutral_engine_count,
            engine_opinions=report.engine_opinions,
            research_status=report.research_status,
            historical_consensus_stats=report.historical_consensus_stats,
            interpretation=report.interpretation,
            notes=list(report.notes),
        )
        conflict = ConflictSnapshot(
            display_only=False,
            has_conflict=conflict_report.has_conflict,
            severity=conflict_report.severity,
            conflicting_engines=[EngineId(k) for k in conflict_report.conflicting_engines],
            directions=conflict_report.directions,
            reasons=conflict_report.reasons,
            conflicting_factor_ids=[
                f for c in conflict_report.factor_conflicts for f in (c["factor_a"], c["factor_b"])
            ],
            note="；".join(conflict_report.notes),
            conflict_level=conflict_report.conflict_level,
            major_conflicts=conflict_report.major_conflicts,
            factor_conflicts=conflict_report.factor_conflicts,
            time_horizon_conflicts=conflict_report.time_horizon_conflicts,
            assumption_conflicts=conflict_report.assumption_conflicts,
            historical_conflict_stats=conflict_report.historical_conflict_stats,
            notes=list(conflict_report.notes),
        )
        return consensus, conflict

    @staticmethod
    def build_display_consensus(
        opinions: dict[str, MetaphysicsOpinion],
        data_quality: str = "B",
    ) -> ConsensusSnapshot:
        """展示层共识（Phase 1 不做正式 Consensus Engine）。"""
        available = {
            k: v for k, v in opinions.items()
            if v.availability == Availability.OK and v.score is not None
        }
        unavailable = [EngineId(k) for k, v in opinions.items()
                       if v.availability != Availability.OK]

        if not available:
            return ConsensusSnapshot(
                label=ConsensusLabel.NEUTRAL, label_cn="不可评估",
                unavailable_engines=unavailable,
                agreement="不可评估", historical_validity="未计算",
                data_quality=data_quality,
                note="没有任何引擎产出可用结果，共识不可评估。",
            )

        directions = {k: v.direction for k, v in available.items()}
        mean_score = sum(v.score or 0.0 for v in available.values()) / len(available)
        pos = sum(1 for d in directions.values() if d > 0)
        neg = sum(1 for d in directions.values() if d < 0)
        total = len(directions)

        if total == 1:
            label = ConsensusLabel.NEUTRAL
            agreement = "仅单一引擎可用，无法评估一致性"
            label_cn = f"{DIRECTION_LABEL.get(next(iter(directions.values())), '中性')}（单引擎）"
        elif pos == total:
            label = (ConsensusLabel.STRONG_POSITIVE_CONSENSUS if mean_score >= 70
                     else ConsensusLabel.POSITIVE_CONSENSUS)
            agreement = "高" if mean_score >= 65 else "中"
            label_cn = CONSENSUS_CN_LABEL[label.value]
        elif neg == total:
            label = (ConsensusLabel.STRONG_NEGATIVE_CONSENSUS if mean_score <= 30
                     else ConsensusLabel.NEGATIVE_CONSENSUS)
            agreement = "高" if mean_score <= 35 else "中"
            label_cn = CONSENSUS_CN_LABEL[label.value]
        elif pos > 0 and neg > 0:
            label = ConsensusLabel.MIXED
            agreement = "低（存在反向引擎）"
            label_cn = CONSENSUS_CN_LABEL[label.value]
        else:
            label = ConsensusLabel.NEUTRAL
            agreement = "中（部分引擎中性）"
            label_cn = CONSENSUS_CN_LABEL[label.value]

        return ConsensusSnapshot(
            display_only=True,
            label=label, label_cn=label_cn,
            participating_engines=[EngineId(k) for k in available],
            unavailable_engines=unavailable,
            directions=directions,
            mean_score=round(mean_score, 2),
            agreement=agreement,
            historical_validity="未计算（Phase 1 不做正式 Consensus）",
            data_quality=data_quality,
            note=(
                "Phase 1 未实现正式 ConsensusEngine。此处仅为**展示层**聚合，"
                "参与引擎数、可用性均如实展示；不可用引擎不会被按 0 分计入。"
            ),
        )

    @staticmethod
    def build_display_conflict(opinions: dict[str, MetaphysicsOpinion]) -> ConflictSnapshot:
        available = {k: v for k, v in opinions.items()
                     if v.availability == Availability.OK and v.score is not None}
        directions = {k: v.direction for k, v in available.items()}
        pos = [k for k, d in directions.items() if d > 0]
        neg = [k for k, d in directions.items() if d < 0]

        if not (pos and neg):
            return ConflictSnapshot(
                has_conflict=False, severity="none",
                directions=directions,
                note="当前无显著冲突：各可用模型方向一致或均为中性。",
            )

        reasons = []
        for k in pos:
            top = available[k].top_positive_reasons[:2]
            reasons.append(f"{k} 偏强：{'；'.join(r.text[:60] for r in top) or '无明细'}")
        for k in neg:
            top = available[k].top_negative_reasons[:2]
            reasons.append(f"{k} 偏弱：{'；'.join(r.text[:60] for r in top) or '无明细'}")

        return ConflictSnapshot(
            display_only=True,
            has_conflict=True,
            severity="major" if len(pos) >= 1 and len(neg) >= 1 else "minor",
            conflicting_engines=[EngineId(k) for k in (pos + neg)],
            directions=directions,
            reasons=reasons,
            conflicting_factor_ids=[],
            note="**禁止用平均分掩盖分歧**。本系统如实并列展示各模型方向与依据。",
        )

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def run_bazi_analysis(
        self,
        db: Session,
        *,
        stock: StockMaster,
        birth_profile: StockBirthProfile,
        as_of: datetime,
        horizon: str = "20d",
        huangli_days: int = 31,
        persist: bool = True,
    ) -> BaziAnalysisResponse:
        """执行一次八字分析（含黄历与因子）。"""
        started = time.perf_counter()
        warnings: list[Warning_] = []
        analysis_id = f"AN-{as_of.strftime('%Y%m%d%H%M%S')}-{stock.stock_code}-{uuid.uuid4().hex[:6]}"

        # --- 历法 / 黄历 ---
        t0 = time.perf_counter()
        huangli = self.huangli.snapshot(as_of, days=huangli_days)
        huangli_ms = int((time.perf_counter() - t0) * 1000)

        # --- 八字 ---
        t0 = time.perf_counter()
        chart = self.bazi.build_chart(
            birth_datetime=birth_profile.birth_datetime.replace(tzinfo=None),
            as_of=as_of,
            variant_mode=VariantMode(birth_profile.variant_mode),
            stock_code=stock.stock_code,
        )
        bazi_ms = int((time.perf_counter() - t0) * 1000)

        # --- 因子 ---
        t0 = time.perf_counter()
        factor_set = compute_factor_set(chart, huangli, as_of, stock_code=stock.stock_code)
        factors_ms = int((time.perf_counter() - t0) * 1000)

        # --- 观点 ---
        bazi_opinion = self.build_opinion(EngineId.BAZI, factor_set, self.bazi.engine_version)
        huangli_opinion = self.build_opinion(EngineId.HUANGLI, factor_set, self.huangli.engine_version)

        # 紫微：Phase 1 未实现 → 明确 unavailable，绝不伪造
        ziwei_opinion = MetaphysicsOpinion(
            engine=EngineId.ZIWEI,
            engine_version="",
            availability=Availability.UNAVAILABLE,
            direction=0, score=None, confidence=0.0,
            note="紫微斗数引擎尚未启用（Phase 2 实现）。本系统不提供任何紫微分析结果，也不以 0 分参与任何聚合。",
        )

        opinions = {
            "bazi": bazi_opinion,
            "huangli": huangli_opinion,
            "ziwei": ziwei_opinion,
        }
        dq = birth_profile.data_quality
        consensus = self.build_display_consensus(opinions, data_quality=ex_value(dq.grade))
        conflict = self.build_display_conflict(opinions)

        versions = VersionStamp(
            engine_version=self.bazi.engine_version,
            rule_version=settings.factor_rule_version,
            config_version=settings.config_version,
            birth_profile_version=birth_profile.birth_profile_version,
            knowledge_version=settings.knowledge_version,
            factor_version=settings.factor_rule_version,
            market_data_version=settings.market_data_version,
            computed_at=datetime.now(),
        )

        chart_ids: dict[str, str] = {}
        if persist:
            self.register_engine_versions(db)
            self.upsert_stock(db, stock)
            self.save_birth_profile(db, birth_profile)

            chart_ids["bazi"] = self.save_chart_artifact(
                db, engine_id="bazi", engine_version=self.bazi.engine_version,
                stock_code=stock.stock_code, as_of=as_of,
                input_payload={
                    "birth_datetime": birth_profile.birth_datetime.isoformat(),
                    "birth_basis": ex_value(birth_profile.birth_basis),
                    "variant_mode": ex_value(birth_profile.variant_mode),
                    "as_of": as_of.isoformat(),
                },
                raw_chart=chart.model_dump(mode="json"),
                assumptions=[a.model_dump(mode="json") for a in chart.assumptions],
                warnings=[w.model_dump(mode="json") for w in chart.warnings],
                birth_profile_version=birth_profile.birth_profile_version,
            )
            chart_ids["huangli"] = self.save_chart_artifact(
                db, engine_id="huangli", engine_version=self.huangli.engine_version,
                stock_code=stock.stock_code, as_of=as_of,
                input_payload={"as_of": as_of.isoformat(), "days": huangli_days},
                raw_chart=huangli.raw_huangli,
                assumptions=huangli.assumptions,
                warnings=[w.model_dump(mode="json") for w in huangli.warnings],
                birth_profile_version=birth_profile.birth_profile_version,
            )
            saved = self.save_factors(db, factor_set)

            self.log_engine_run(db, engine_id="bazi", engine_version=self.bazi.engine_version,
                                stock_code=stock.stock_code, as_of=as_of, status="ok",
                                duration_ms=bazi_ms,
                                warnings=[w.model_dump(mode="json") for w in chart.warnings])
            self.log_engine_run(db, engine_id="huangli", engine_version=self.huangli.engine_version,
                                stock_code=stock.stock_code, as_of=as_of, status="ok",
                                duration_ms=huangli_ms)
            self.log_engine_run(db, engine_id="factors", engine_version=settings.factor_rule_version,
                                stock_code=stock.stock_code, as_of=as_of, status="ok",
                                duration_ms=factors_ms)
        else:
            saved = len(factor_set.observations)

        duration_ms = int((time.perf_counter() - started) * 1000)

        run = AnalysisRun(
            analysis_id=analysis_id,
            stock_code=stock.stock_code,
            as_of=as_of,
            horizon=horizon,
            stock=stock,
            birth_profile=birth_profile,
            engines_requested=[EngineId.CALENDAR, EngineId.HUANGLI, EngineId.BAZI],
            engines_completed=[EngineId.HUANGLI, EngineId.BAZI],
            engines_failed=[],
            chart_artifact_ids=chart_ids,
            factor_set=factor_set,
            opinions=opinions,
            consensus=consensus,
            conflict=conflict,
            versions=versions,
            warnings=warnings,
            duration_ms=duration_ms,
        )

        if persist:
            self.save_analysis_run(db, run, extra={
                "factor_count": saved,
                "huangli": huangli.model_dump(mode="json"),
            })

        return BaziAnalysisResponse(
            analysis_id=analysis_id,
            stock=stock,
            birth_profile=birth_profile,
            chart=chart.model_dump(mode="json"),
            huangli=huangli,
            factors=factor_set,
            opinion=bazi_opinion,
            versions=versions,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # 紫微（Phase 2A）
    # ------------------------------------------------------------------
    @staticmethod
    def ziwei_variants(mode: VariantMode | str) -> list[VariantMode]:
        """把 variant_mode 展开为需要实际计算的 variant 列表。

        ``both`` → [forward, reverse]（**分别计算、分别保存，不得平均**）；
        ``not_applicable`` → []（拒绝排盘，见 ADR-0010）。
        """
        m = VariantMode(ex_value(mode))
        if m == VariantMode.BOTH:
            return [VariantMode.FORWARD, VariantMode.REVERSE]
        if m in (VariantMode.FORWARD, VariantMode.REVERSE):
            return [m]
        return []

    def build_ziwei_charts(
        self,
        db: Session | None,
        *,
        stock: StockMaster,
        birth_profile: StockBirthProfile,
        as_of: datetime,
        variant_mode: VariantMode | str,
        persist: bool,
    ) -> tuple[dict[str, object], dict[str, str], list[Warning_]]:
        """按 variant 排紫微盘；每个 variant 单独落一份 ``raw_chart``。

        Returns:
            ``(variant → ZiweiChart, variant → chart_id, warnings)``

        紫微排盘失败**不影响**八字/黄历：失败只产出 warning，
        调用方据此把紫微标为 unavailable（禁止用 0 分冒充）。
        """
        charts: dict[str, object] = {}
        chart_ids: dict[str, str] = {}
        warnings: list[Warning_] = []
        variants = self.ziwei_variants(variant_mode)
        if not variants:
            return charts, chart_ids, warnings

        for variant in variants:
            key = ex_value(variant)
            started = time.perf_counter()
            try:
                chart = self.ziwei.calculate_chart(
                    EngineContext(stock_code=stock.stock_code, as_of=as_of),
                    birth_datetime=birth_profile.birth_datetime.replace(tzinfo=None),
                    as_of=as_of,
                    variant_mode=variant,
                )
            except ZiweiUnavailableError as exc:
                warnings.append(Warning_(
                    code="ZIWEI_UNAVAILABLE",
                    message=f"紫微（{key}）不可用：{exc}。其余引擎不受影响。",
                    severity="warning",
                    context={"variant": key},
                ))
                if db is not None and persist:
                    self.log_engine_run(
                        db, engine_id="ziwei", engine_version=self.ziwei.engine_version,
                        stock_code=stock.stock_code, as_of=as_of, status="unavailable",
                        duration_ms=int((time.perf_counter() - started) * 1000),
                        error=str(exc),
                    )
                continue

            charts[key] = chart
            for w in chart.warnings:  # type: ignore[attr-defined]
                warnings.append(w)
            if db is not None and persist:
                chart_ids[key] = self.save_chart_artifact(
                    db, engine_id="ziwei", engine_version=self.ziwei.engine_version,
                    stock_code=stock.stock_code, as_of=as_of,
                    input_payload={
                        "birth_datetime": birth_profile.birth_datetime.isoformat(),
                        "variant_mode": key,
                        "gender_parameter": chart.gender_parameter,  # type: ignore[attr-defined]
                        "as_of": as_of.isoformat(),
                    },
                    raw_chart=chart.model_dump(mode="json"),  # type: ignore[attr-defined]
                    assumptions=[a.model_dump(mode="json") for a in chart.assumptions],  # type: ignore[attr-defined]
                    warnings=[w.model_dump(mode="json") for w in chart.warnings],  # type: ignore[attr-defined]
                    birth_profile_version=birth_profile.birth_profile_version,
                )
                self.log_engine_run(
                    db, engine_id="ziwei", engine_version=self.ziwei.engine_version,
                    stock_code=stock.stock_code, as_of=as_of, status="ok",
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    warnings=[w.model_dump(mode="json") for w in chart.warnings],  # type: ignore[attr-defined]
                )
        return charts, chart_ids, warnings

    def _ziwei_opinion_unavailable(self, reason: str) -> MetaphysicsOpinion:
        return MetaphysicsOpinion(
            engine=EngineId.ZIWEI,
            engine_version=self.ziwei.engine_version if self.ziwei.availability == Availability.OK else "",
            availability=Availability.UNAVAILABLE,
            direction=0, score=None, confidence=0.0,
            note=reason,
        )

    def run_multi_analysis(
        self,
        db: Session,
        *,
        stock: StockMaster,
        birth_profile: StockBirthProfile,
        as_of: datetime,
        horizon: str = "20d",
        huangli_days: int = 31,
        persist: bool = True,
    ) -> MultiAnalysisResponse:
        """多模型综合分析：八字 + 紫微 + 黄历 → 三个独立观点 → 共识 / 分歧。

        **故障隔离**：紫微服务不可用时，八字与黄历照常产出；
        紫微观点为 ``availability=unavailable, score=null``，
        共识的可用引擎数相应降低，**绝不把紫微按 0 分计入**。
        """
        warnings: list[Warning_] = []
        analysis_id = f"AN-{as_of.strftime('%Y%m%d%H%M%S')}-{stock.stock_code}-{uuid.uuid4().hex[:6]}"
        variant_mode = VariantMode(ex_value(birth_profile.variant_mode))

        # --- 黄历 ---
        huangli = self.huangli.snapshot(as_of, days=huangli_days)

        # --- 八字 ---
        chart = self.bazi.build_chart(
            birth_datetime=birth_profile.birth_datetime.replace(tzinfo=None),
            as_of=as_of,
            variant_mode=variant_mode,
            stock_code=stock.stock_code,
        )

        # --- 紫微（可失败） ---
        ziwei_charts, ziwei_chart_ids, ziwei_warnings = self.build_ziwei_charts(
            db, stock=stock, birth_profile=birth_profile, as_of=as_of,
            variant_mode=variant_mode, persist=persist,
        )
        warnings.extend(ziwei_warnings)

        # --- 紫微因子：一次只算一个 variant ---
        # `both` 模式下紫微盘有两套。因子/观点层只能取一套作为"主 variant"，
        # 否则同一 factor_id 会出现两个值，语义立刻变得不可解释。
        ziwei_chart = None
        if ziwei_charts:
            primary = "forward" if "forward" in ziwei_charts else next(iter(ziwei_charts))
            ziwei_chart = ziwei_charts[primary]
            if len(ziwei_charts) > 1:
                others = [k for k in ziwei_charts if k != primary]
                warnings.append(Warning_(
                    code="ZIWEI_VARIANT_PRIMARY_SELECTED",
                    message=(
                        f"紫微解析出 {len(ziwei_charts)} 个 variant（{', '.join(ziwei_charts)}）。"
                        f"因子与观点层**只使用 primary={primary}**；"
                        f"其余 variant（{', '.join(others)}）的盘面已分别保存，"
                        "可在变体对比中单独查看。系统不会对两个 variant 取平均。"
                    ),
                    severity="info",
                    context={"primary": primary, "others": others},
                ))

        # --- 因子 ---
        factor_set = compute_factor_set(
            chart, huangli, as_of, stock_code=stock.stock_code, ziwei_chart=ziwei_chart,
        )

        # --- 三个独立观点 ---
        bazi_opinion = self.build_opinion(EngineId.BAZI, factor_set, self.bazi.engine_version)
        huangli_opinion = self.build_opinion(EngineId.HUANGLI, factor_set, self.huangli.engine_version)

        if ziwei_chart is not None:
            ziwei_opinion = self.build_opinion(EngineId.ZIWEI, factor_set, self.ziwei.engine_version)
        else:
            reason = (
                self.ziwei.unavailable_reason()
                if not self.ziwei.availability == Availability.OK
                else (
                    "本次分析未启用紫微：variant_mode="
                    f"{ex_value(variant_mode)}。紫微运限需要显式方向（forward/reverse/both），"
                    "股票无真实性别，系统不提供任何默认性别假设（ADR-0010）。"
                )
            )
            ziwei_opinion = self._ziwei_opinion_unavailable(reason)

        opinions = {
            EngineId.BAZI.value: bazi_opinion,
            EngineId.ZIWEI.value: ziwei_opinion,
            EngineId.HUANGLI.value: huangli_opinion,
        }

        dq = birth_profile.data_quality
        consensus, conflict = self.build_consensus_and_conflict(
            opinions, factor_set=factor_set, data_quality=ex_value(dq.grade),
        )

        versions = VersionStamp(
            engine_version=self.bazi.engine_version,
            rule_version=settings.factor_rule_version,
            config_version=settings.config_version,
            birth_profile_version=birth_profile.birth_profile_version,
            knowledge_version=settings.knowledge_version,
            factor_version=settings.factor_rule_version,
            market_data_version=settings.market_data_version,
            computed_at=datetime.now(),
        )

        if persist:
            self.register_engine_versions(db)
            self.upsert_stock(db, stock)
            self.save_birth_profile(db, birth_profile)
            chart_ids: dict[str, str] = {}
            chart_ids["bazi"] = self.save_chart_artifact(
                db, engine_id="bazi", engine_version=self.bazi.engine_version,
                stock_code=stock.stock_code, as_of=as_of,
                input_payload={
                    "birth_datetime": birth_profile.birth_datetime.isoformat(),
                    "birth_basis": ex_value(birth_profile.birth_basis),
                    "variant_mode": ex_value(birth_profile.variant_mode),
                    "as_of": as_of.isoformat(),
                },
                raw_chart=chart.model_dump(mode="json"),
                assumptions=[a.model_dump(mode="json") for a in chart.assumptions],
                warnings=[w.model_dump(mode="json") for w in chart.warnings],
                birth_profile_version=birth_profile.birth_profile_version,
            )
            chart_ids["huangli"] = self.save_chart_artifact(
                db, engine_id="huangli", engine_version=self.huangli.engine_version,
                stock_code=stock.stock_code, as_of=as_of,
                input_payload={"as_of": as_of.isoformat(), "days": huangli_days},
                raw_chart=huangli.raw_huangli,
                assumptions=huangli.assumptions,
                warnings=[w.model_dump(mode="json") for w in huangli.warnings],
                birth_profile_version=birth_profile.birth_profile_version,
            )
            for variant, cid in ziwei_chart_ids.items():
                chart_ids[f"ziwei:{variant}"] = cid
            self.save_factors(db, factor_set)

            engines_completed = [EngineId.HUANGLI, EngineId.BAZI]
            if ziwei_charts:
                engines_completed.append(EngineId.ZIWEI)
            run = AnalysisRun(
                analysis_id=analysis_id,
                stock_code=stock.stock_code,
                as_of=as_of,
                horizon=horizon,
                stock=stock,
                birth_profile=birth_profile,
                engines_requested=[EngineId.CALENDAR, EngineId.HUANGLI, EngineId.BAZI, EngineId.ZIWEI],
                engines_completed=engines_completed,
                engines_failed=[],
                chart_artifact_ids=chart_ids,
                factor_set=factor_set,
                opinions=opinions,
                consensus=consensus,
                conflict=conflict,
                versions=versions,
                warnings=warnings,
            )
            self.save_analysis_run(db, run, extra={
                "factor_count": len(factor_set.observations),
                "huangli": huangli.model_dump(mode="json"),
                "ziwei_variants": sorted(ziwei_charts.keys()),
            })

        return MultiAnalysisResponse(
            analysis_id=analysis_id,
            stock=stock,
            birth_profile=birth_profile,
            as_of=as_of,
            variant_mode=ex_value(variant_mode),
            horizon=horizon,
            bazi_chart=chart.model_dump(mode="json"),
            ziwei_charts={k: v.model_dump(mode="json") for k, v in ziwei_charts.items()},  # type: ignore[attr-defined]
            huangli=huangli,
            factors=factor_set,
            opinions=opinions,
            consensus=consensus,
            conflict=conflict,
            versions=versions,
            warnings=warnings,
        )

    def save_analysis_run(self, db: Session, run: AnalysisRun, extra: dict | None = None) -> None:
        payload = run.model_dump(mode="json")
        # 附加信息（如黄历快照、因子计数）统一放在 ``_extras`` 下，
        # 这样 AnalysisRun 的严格模型（extra=forbid）不会被污染。
        if extra:
            payload["_extras"] = extra
        db.add(AnalysisRunRow(
            analysis_id=run.analysis_id,
            stock_code=run.stock_code,
            as_of=run.as_of,
            horizon=run.horizon,
            engines_requested_json=[ex_value(e) for e in run.engines_requested],
            engines_completed_json=[ex_value(e) for e in run.engines_completed],
            engines_failed_json=run.engines_failed,
            payload_json=payload,
            versions_json=run.versions.model_dump(mode="json"),
            warnings_json=[w.model_dump(mode="json") for w in run.warnings],
            duration_ms=run.duration_ms,
        ))
        db.flush()

    # ------------------------------------------------------------------
    def load_analysis(self, db: Session, analysis_id: str) -> AnalysisRun | None:
        row = db.get(AnalysisRunRow, analysis_id)
        if row is None:
            return None
        payload = dict(row.payload_json or {})
        payload.pop("_extras", None)
        # 兼容早期写入的平铺字段
        payload.pop("huangli", None)
        payload.pop("factor_count", None)

        # 只保留模型已声明的字段，避免历史 payload 中的新增键导致整体校验失败
        allowed = set(AnalysisRun.model_fields)
        payload = {k: v for k, v in payload.items() if k in allowed}

        try:
            return AnalysisRun.model_validate(payload)
        except Exception:  # noqa: BLE001 - 历史 payload 结构变化时降级
            return AnalysisRun(
                analysis_id=row.analysis_id,
                stock_code=row.stock_code,
                as_of=row.as_of,
                horizon=row.horizon,
                engines_completed=[EngineId(e) for e in (row.engines_completed_json or [])],
                versions=VersionStamp(**(row.versions_json or {})),
                created_at=row.created_at,
                duration_ms=row.duration_ms,
            )

    def load_analysis_extras(self, db: Session, analysis_id: str) -> dict:
        """读取 ``_extras``（黄历快照等附加信息）。"""
        row = db.get(AnalysisRunRow, analysis_id)
        if row is None:
            return {}
        return (row.payload_json or {}).get("_extras", {})

    def load_factor_set(self, db: Session, analysis_id: str) -> FactorSet | None:
        row = db.get(AnalysisRunRow, analysis_id)
        if row is None:
            return None
        obs_rows = db.execute(
            select(FactorObservationRow).where(
                FactorObservationRow.stock_code == row.stock_code,
                FactorObservationRow.as_of == row.as_of,
            ).order_by(FactorObservationRow.factor_id)
        ).scalars().all()
        if not obs_rows:
            return None
        return factor_set_from_rows(row.stock_code, row.as_of, obs_rows)

    def load_raw_chart(self, db: Session, analysis_id: str, engine: str) -> dict | None:
        row = db.get(AnalysisRunRow, analysis_id)
        if row is None:
            return None
        artifact = db.execute(
            select(ChartArtifactRow).where(
                ChartArtifactRow.stock_code == row.stock_code,
                ChartArtifactRow.engine == engine,
                ChartArtifactRow.as_of == row.as_of,
            ).order_by(ChartArtifactRow.calculated_at.desc())
        ).scalars().first()
        return None if artifact is None else {
            "chart_id": artifact.chart_id,
            "engine": artifact.engine,
            "engine_version": artifact.engine_version,
            "config_version": artifact.config_version,
            "birth_profile_version": artifact.birth_profile_version,
            "as_of": artifact.as_of.isoformat(),
            "input": artifact.input_json,
            "raw_chart": artifact.raw_chart,
            "assumptions": artifact.assumptions_json,
            "warnings": artifact.warnings_json,
            "calculated_at": artifact.calculated_at.isoformat(),
        }

    def load_ziwei_charts(self, db: Session, analysis_id: str) -> dict[str, dict]:
        """读取**这一次分析**涉及的紫微盘面（variant → artifact）。

        ``both`` 模式下会有两个变体，**分别返回、绝不平均**（见 ADR-0010）。

        重要：只认本次分析在 ``chart_artifact_ids`` 中登记的 chart_id，
        **不做** (stock_code, as_of, engine) 的模糊匹配 ——
        否则同一天先跑过多模型分析、再跑八字分析时，
        后者会"看到"前者的紫微盘面，从而谎报紫微可用。
        """
        row = db.get(AnalysisRunRow, analysis_id)
        if row is None:
            return {}
        payload = dict(row.payload_json or {})
        ids: dict = payload.get("chart_artifact_ids") or {}
        zw_ids = {
            str(k).split(":", 1)[1]: str(v)
            for k, v in ids.items() if str(k).startswith("ziwei:")
        }
        if not zw_ids:
            return {}

        out: dict[str, dict] = {}
        for variant, chart_id in zw_ids.items():
            a = db.get(ChartArtifactRow, chart_id)
            if a is None:
                continue
            out[variant] = {
                "chart_id": a.chart_id,
                "engine": a.engine,
                "engine_version": a.engine_version,
                "config_version": a.config_version,
                "birth_profile_version": a.birth_profile_version,
                "as_of": a.as_of.isoformat(),
                "input": a.input_json,
                "chart": a.raw_chart,
                "assumptions": a.assumptions_json,
                "warnings": a.warnings_json,
                "calculated_at": a.calculated_at.isoformat(),
            }
        return out

    def load_birth_profile(self, db: Session, stock_code: str,
                           version: str | None = None,
                           birth_basis: str | None = None) -> StockBirthProfile | None:
        stmt = select(StockBirthProfileRow).where(StockBirthProfileRow.stock_code == stock_code)
        if version:
            stmt = stmt.where(StockBirthProfileRow.birth_profile_version == version)
        if birth_basis:
            stmt = stmt.where(StockBirthProfileRow.birth_basis == birth_basis)
        stmt = stmt.order_by(StockBirthProfileRow.updated_at.desc())
        row = db.execute(stmt).scalars().first()
        return None if row is None else bp.from_row(row)

    def load_stock(self, db: Session, stock_code: str) -> StockMaster | None:
        row = db.get(StockMasterRow, stock_code)
        if row is None:
            return None
        return StockMaster(
            stock_code=row.stock_code, wind_code=row.wind_code, name=row.name,
            exchange=row.exchange, board=row.board, industry=row.industry,
            listing_date=row.listing_date,
            total_market_cap=row.total_market_cap,
            circulating_market_cap=row.circulating_market_cap,
            is_active=row.is_active,
            source={"source": row.source},
            data_quality=DataQuality(**(row.data_quality_json or {})),
            updated_at=row.updated_at,
        )


def factor_set_from_rows(stock_code: str, as_of: datetime, rows: list) -> FactorSet:
    """从 ``factor_observation`` 行还原 ``FactorSet``。"""
    from src.core.schemas.factor import FactorObservation

    observations = []
    for r in rows:
        definition = DEFINITION_INDEX.get(r.factor_id)
        raw = (r.raw_value_json or {}).get("value")
        observations.append(FactorObservation(
            factor_id=r.factor_id,
            stock_code=r.stock_code,
            as_of=r.as_of,
            trade_date=r.trade_date,
            engine=r.engine,
            category=r.category,
            name=r.name or (definition.name if definition else ""),
            raw_value=raw,
            normalized_value=r.normalized_value,
            direction=r.direction,
            rule_score=r.rule_score,
            confidence=r.confidence,
            availability=r.availability,
            rule_version=r.rule_version,
            engine_version=r.engine_version,
            config_version=r.config_version,
            evidence=r.evidence_json or [],
            explanation=r.explanation or "",
            warnings=r.warnings_json or [],
            computed_at=r.computed_at,
        ))
    return FactorSet(
        stock_code=stock_code,
        as_of=as_of,
        engine_version=settings.bazi_engine_version,
        rule_version=settings.factor_rule_version,
        config_version=settings.config_version,
        observations=observations,
    )


def default_birth_request(
    basis: str | None = None, variant: str | None = None
) -> BirthProfileCreateRequest:
    from src.core.schemas.common import BirthBasis

    return BirthProfileCreateRequest(
        birth_basis=BirthBasis(basis) if basis else BirthBasis.LISTING_OPEN,
        variant_mode=VariantMode(variant) if variant else VariantMode.NOT_APPLICABLE,
    )


def today_or(value: date | None) -> date:
    return value or date.today()


__all__ = ["AnalysisService", "factor_set_from_rows", "direction_from_score", "DIRECTION_LABEL"]
