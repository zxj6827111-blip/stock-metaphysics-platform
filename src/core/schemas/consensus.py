"""多模型共识 / 冲突 / 共振研究 Schema（Phase 2C）。"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from src.core.schemas.common import SMBaseModel, Warning_

#: 同向共振组合：combo_id → 必须**全部为正**的引擎集合
CONSENSUS_COMBO_SPECS: dict[str, tuple[str, ...]] = {
    "BAZI_POS": ("bazi",),
    "ZIWEI_POS": ("ziwei",),
    "HUANGLI_POS": ("huangli",),
    "BAZI_ZIWEI_POS": ("bazi", "ziwei"),
    "BAZI_HUANGLI_POS": ("bazi", "huangli"),
    "ZIWEI_HUANGLI_POS": ("ziwei", "huangli"),
    "ALL_THREE_POS": ("bazi", "ziwei", "huangli"),
}


#: 冲突组合的完整定义：combo_id → (正引擎, 负引擎)。
#: 冲突组合**必须与同向组合一起研究** —— 否则无法回答"共振是否真的比冲突更有信息量"。
CONFLICT_COMBO_SPECS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "BAZI_POS_ZIWEI_NEG": (("bazi",), ("ziwei",)),
    "BAZI_NEG_ZIWEI_POS": (("ziwei",), ("bazi",)),
    "BAZI_POS_HUANGLI_NEG": (("bazi",), ("huangli",)),
    "ZIWEI_POS_HUANGLI_NEG": (("ziwei",), ("huangli",)),
}

#: 组合的**预定义**全集（同向 + 冲突）。研究只允许在这套预定义组合上进行，
#: 不支持自由搜索 —— 这是数据挖掘防护的第一道闸门。
ALL_COMBO_IDS: tuple[str, ...] = tuple(CONSENSUS_COMBO_SPECS) + tuple(CONFLICT_COMBO_SPECS)


class ConsensusComboStats(SMBaseModel):
    """单个共振/冲突组合的历史统计。

    **必须与随机对照同时给出** —— 三个模型都看多并不能证明更有效。
    """

    combo_id: str
    description: str = ""
    engines: list[str] = Field(default_factory=list)
    logic: str = Field(default="", description="组合逻辑说明（同向 / 冲突）")

    sample_count: int = 0
    event_count: int = 0
    event_rate: float = Field(default=0.0, description="event_count / sample_count")

    up_rate: float | None = None
    mean_return: float | None = None
    median_return: float | None = None
    excess_return: float | None = None
    std_return: float | None = None

    # --- 负对照 ---
    control_kind: str = ""
    control_event_count: int = 0
    control_up_rate: float | None = None
    control_mean_return: float | None = None
    jaccard_with_real: float | None = Field(
        default=None, description="对照事件集合与真实事件集合的 Jaccard；>0.9 视为对照失效",
    )
    control_result: str = Field(default="not_run", description="outperform / underperform / tie / invalid")
    #: Welch t 检验（真实组 vs 对照组）。**未做多重比较校正**，
    #: 因此单个组合的 p 值不能直接当作"有效"证据；校正参考见 multiple_testing。
    t_stat: float | None = None
    p_value: float | None = None
    test_method: str = "welch_t_test_two_sided"

    horizon: int = 20
    research_status: str = "NOT_RUN"
    research_status_reasons: list[str] = Field(default_factory=list)


class MultipleTestingWarning(SMBaseModel):
    """多重比较警告（数据挖掘防护）。"""

    experiment_count: int = Field(default=0, description="本次研究实际执行的组合数")
    parameter_count: int = Field(default=0, description="可调参数个数（持有期 × 组合 × 股票池…）")
    selection_method: str = Field(default="exhaustive_over_predefined_combos")
    warning_level: str = Field(default="none", description="none / caution / high")
    bonferroni_alpha: float | None = Field(
        default=None, description="Bonferroni 校正后的单次检验阈值（参考值）",
    )
    message: str = ""


class ConsensusResearchResult(SMBaseModel):
    """共振研究总结果。"""

    experiment_id: str
    universe_size: int = 0
    sample_dates: int = 0
    horizon: int = 20
    benchmark_code: str = ""
    data_source: dict = Field(default_factory=dict)

    combos: list[ConsensusComboStats] = Field(default_factory=list)
    multiple_testing: MultipleTestingWarning = Field(default_factory=MultipleTestingWarning)

    overall_research_status: str = "NOT_RUN"
    overall_reasons: list[str] = Field(default_factory=list)
    conclusion: str = ""
    methodology: str = ""
    warnings: list[Warning_] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=datetime.now)


class ConsensusResearchRequest(SMBaseModel):
    """共振研究请求。"""

    universe: list[str] = Field(default_factory=list)
    combos: list[str] = Field(
        default_factory=list, description="留空表示使用全部预定义组合；不支持自由搜索以避免数据挖掘",
    )
    horizon: int = Field(default=20, ge=1, le=60)
    date_from: str = "2021-01-01"
    date_to: str = "2026-09-01"
    sample_step_months: int = Field(default=3, ge=1, le=12)
    variant_mode: str = Field(default="forward", description="紫微运限方向（forward/reverse）")
    run_negative_controls: bool = True
    persist: bool = False


__all__ = [
    "CONSENSUS_COMBO_SPECS", "CONFLICT_COMBO_SPECS", "ALL_COMBO_IDS",
    "ConsensusComboStats", "ConsensusResearchResult",
    "ConsensusResearchRequest", "MultipleTestingWarning",
]
