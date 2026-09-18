"""八字（BaziEngine）输出 Schema。

原始盘面是一等数据：``BaziChart`` 必须完整落库到 ``chart_artifact.raw_chart``，
不允许只保存一个分数。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from src.core.schemas.calendar import GanZhi
from src.core.schemas.common import (
    Assumption,
    Availability,
    SMBaseModel,
    SourceRef,
    VariantMode,
    Warning_,
)


class HiddenStem(SMBaseModel):
    """藏干及其十神。"""

    stem: str
    ten_god: str
    wuxing: str
    weight: float = 1.0
    rank: str = Field(default="本气", description="本气 / 中气 / 余气")


class Pillar(SMBaseModel):
    """一柱（年/月/日/时）。"""

    position: str = Field(description="year | month | day | hour")
    ganzhi: GanZhi
    stem_ten_god: str = Field(default="", description="天干十神；日柱为'日主'")
    hidden_stems: list[HiddenStem] = Field(default_factory=list)
    hidden_ten_gods: list[str] = Field(default_factory=list)
    nayin: str = ""
    di_shi: str = Field(default="", description="十二长生（以日干为主）")
    xun: str = ""
    xun_kong: str = ""


class WuxingStrength(SMBaseModel):
    """五行力量估算。"""

    scores: dict[str, float] = Field(default_factory=dict, description="五行 → 加权力量分")
    percentages: dict[str, float] = Field(default_factory=dict)
    dominant: str = ""
    weakest: str = ""
    missing: list[str] = Field(default_factory=list, description="四柱天干地支中未出现的五行")


class DayMasterAnalysis(SMBaseModel):
    """日主旺衰分析。"""

    day_master: str
    day_master_wuxing: str
    day_master_yang: bool
    month_branch: str = ""
    month_season: str = Field(default="", description="月令司权季节，如 申月(金旺)")
    # 三个维度
    de_ling: bool = Field(default=False, description="得令：日主五行在月令处于旺相")
    de_di: bool = Field(default=False, description="得地：日主在支中有强根")
    de_shi: bool = Field(default=False, description="得势：比劫印星帮扶数量占优")
    support_score: float = Field(default=0.0, description="帮扶力量（比劫 + 印）")
    drain_score: float = Field(default=0.0, description="耗泄力量（食伤 + 财 + 官杀）")
    balance_ratio: float = Field(default=0.5, description="support / (support + drain)")
    strength_level: str = Field(default="中和", description="身强 / 偏强 / 中和 / 偏弱 / 身弱")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class PatternCandidate(SMBaseModel):
    """格局候选。"""

    name: str
    basis: str = Field(description="判定依据")
    score: float = 0.0
    is_primary: bool = False


class PatternAnalysis(SMBaseModel):
    """格局分析。

    传统格局判定流派众多（子平 / 盲派 / 新派），Phase 1 使用**月令司权 + 透干**的
    通行子平法，并显式给出 confidence 与候选列表。若无法可靠判定则返回 unavailable。
    """

    primary: str = Field(default="", description="主格局，如 食神生财格")
    category: str = Field(default="", description="格局大类：财格 / 官格 / 印格 / 食伤格 / 比劫格 / 特殊格")
    candidates: list[PatternCandidate] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    availability: Availability = Availability.OK
    method: str = Field(default="月令本气/透干取格（子平通行法）")


class YongShenAnalysis(SMBaseModel):
    """喜用忌神分析。

    采用**扶抑为主 + 调候为辅**的通行方法；同时给出调候参考。
    Phase 1 输出结构化结果并标 confidence，不宣称唯一正确。
    """

    method: str = Field(default="扶抑法（主）+ 调候法（辅）")
    yong_shen: list[str] = Field(default_factory=list, description="用神（五行）")
    xi_shen: list[str] = Field(default_factory=list, description="喜神（五行）")
    ji_shen: list[str] = Field(default_factory=list, description="忌神（五行）")
    chou_shen: list[str] = Field(default_factory=list, description="仇神（五行）")
    xian_shen: list[str] = Field(default_factory=list, description="闲神（五行）")
    tiaohou_note: str = Field(default="", description="调候说明")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    availability: Availability = Availability.OK
    rationale: list[str] = Field(default_factory=list, description="判定理由，可追溯")


class RelationHit(SMBaseModel):
    """刑冲合害等结构命中。"""

    relation_type: str = Field(description="六合 / 三合 / 三会 / 六冲 / 相刑 / 相害 / 天干五合 / 天干相冲")
    positions: list[str] = Field(default_factory=list, description="参与的位置，如 ['year','day']")
    branches_or_stems: list[str] = Field(default_factory=list)
    transform_element: str = Field(default="", description="合化五行（若为合类）")
    note: str = ""


class TemporalPillar(SMBaseModel):
    """时间流（流年 / 流月 / 流日）的一柱结构。"""

    kind: str = Field(description="year | month | day")
    label: str = Field(description="如 2024 甲辰")
    ganzhi: GanZhi
    start_date: date | None = None
    end_date: date | None = None

    stem_ten_god: str = Field(default="", description="流年/月天干相对日主的十神")
    branch_ten_gods: list[str] = Field(default_factory=list)
    di_shi: str = ""

    # 与原局的相互作用
    clashes_with_natal: list[str] = Field(default_factory=list, description="冲到的原局位置")
    harmonies_with_natal: list[str] = Field(default_factory=list, description="六合到的原局位置")
    triple_harmonies: list[str] = Field(default_factory=list, description="构成的三合局")
    punishments_with_natal: list[str] = Field(default_factory=list)
    harms_with_natal: list[str] = Field(default_factory=list)

    # 与喜用忌的关系
    stem_is: str = Field(default="", description="喜神 / 用神 / 忌神 / 仇神 / 闲神 / 未知")
    branch_is: str = Field(default="")

    note: str = ""


class BaziChart(SMBaseModel):
    """八字原始盘面（一等数据）。"""

    chart_id: str = ""
    stock_code: str | None = None
    birth_datetime: datetime | None = None

    # 四柱
    year_pillar: Pillar
    month_pillar: Pillar
    day_pillar: Pillar
    hour_pillar: Pillar

    # 基础
    day_master: str
    day_master_wuxing: str
    wuxing: WuxingStrength
    day_master_analysis: DayMasterAnalysis
    pattern: PatternAnalysis
    yong_shen: YongShenAnalysis

    # 十神统计
    ten_god_counts: dict[str, int] = Field(default_factory=dict)
    ten_god_group_counts: dict[str, int] = Field(default_factory=dict)
    visible_ten_gods: list[str] = Field(default_factory=list, description="天干透出的十神")

    relations: list[RelationHit] = Field(default_factory=list)

    # 辅助盘
    tai_yuan: str = ""
    ming_gong: str = ""
    shen_gong: str = ""
    tai_xi: str = ""

    # 时间流
    current_year_pillar: TemporalPillar | None = None
    current_month_pillar: TemporalPillar | None = None
    current_day_pillar: TemporalPillar | None = None

    # 运限（受"股票无性别"影响）
    variant_mode: VariantMode = VariantMode.NOT_APPLICABLE
    da_yun: list[dict] = Field(default_factory=list, description="大运列表（Phase1 不进入因子）")
    da_yun_note: str = Field(
        default="",
        description="大运顺逆依赖性别，股票无性别 → Phase1 标记 not_applicable，不参与因子",
    )

    # 元信息
    engine_id: str = "bazi"
    engine_version: str = ""
    config_version: str = ""
    calculated_at: datetime = Field(default_factory=datetime.now)
    availability: Availability = Availability.OK

    assumptions: list[Assumption] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    source: SourceRef = Field(default_factory=lambda: SourceRef(source="smx-bazi-native"))

    def pillar_by_position(self, position: str) -> Pillar:
        return {
            "year": self.year_pillar,
            "month": self.month_pillar,
            "day": self.day_pillar,
            "hour": self.hour_pillar,
        }[position]

    def all_pillars(self) -> list[Pillar]:
        return [self.year_pillar, self.month_pillar, self.day_pillar, self.hour_pillar]


class BaziEngineResult(SMBaseModel):
    """BaziEngine 统一返回包（对应 architecture §19 的 MetaphysicsEngine 契约）。"""

    engine: str = "bazi"
    engine_version: str = ""
    config_version: str = ""
    chart: BaziChart
    factors: list[dict] = Field(default_factory=list, description="由 BaziEngine 直接产出的因子（可选）")
    opinion: dict = Field(default_factory=dict, description="Phase 2 使用；Phase 1 为空结构")
    evidence_queries: list[str] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
