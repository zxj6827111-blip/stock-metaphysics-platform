"""日期关系扫描的结构化 API Schema（bazi-relation-v3 / relation-matrix-v2）。

这些类型只描述确定性关系计算结果，不把关系转换成收益预测或交易建议。

v3 口径要点（详见 docs/calculation-differences-relation.md）：

* 关系矩阵 = 流年/流月/流日 × 股票年/月/日（3×3），股票时柱不参与；
* 所有列表统计（S/V/U、relation_types、命中说明、筛选、排序）只读
  ``aggregate_scope = "external_day_row"``（流日行三格）；
* 喜用神来源仍是**完整四柱**原局（``yongshen_basis = "full_four_pillars"``），
  因此 ``day_stem_verdict`` 的喜忌部分仍可能间接受出生时辰模型影响；
* 扫描固定标准采样时点 ``evaluation_time = 12:00:00 / Asia/Shanghai``。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import Field

from src.core.config import settings
from src.core.schemas.common import SMBaseModel, Warning_

#: 关系类型目录：矩阵引擎**唯一**允许 emit 的类型全集（契约测试强制不变量）。
RELATION_CATALOG: dict[str, list[str]] = {
    "天干": ["天干五合", "天干相冲", "天干生", "天干受生", "天干克", "天干受克", "天干同五行"],
    "地支": ["六合", "六冲", "三合", "半合", "三会", "相刑", "三刑", "自刑", "相害", "六破", "同支"],
    "组合": ["伏吟", "反吟", "天合地合", "天克地冲"],
}
RELATION_TYPES: tuple[str, ...] = tuple(
    relation for relations in RELATION_CATALOG.values() for relation in relations
)

#: 聚合口径常量（响应中显式回显，UI 不得各自解释）。
AGGREGATE_SCOPE = "external_day_row"
MATRIX_SOURCE_SCOPE: list[str] = ["year", "month", "day"]
MATRIX_TARGET_SCOPE: list[str] = ["year", "month", "day"]
YONGSHEN_BASIS = "full_four_pillars"
#: 日级研究标准采样时刻：节气交界日不同时刻可能影响月柱，产品主动固定正午。
EVALUATION_TIME = "12:00:00"
EVALUATION_TIMEZONE = "Asia/Shanghai"

#: 五行喜忌角色全集（顺序即判定优先级）；不允许"不在喜用"被推断为"忌神"。
WUXING_ROLES: tuple[str, ...] = ("用神", "喜神", "忌神", "仇神", "闲神", "未知")

#: verdict 三态。
VERDICT_MATCH = "匹配"
VERDICT_MISMATCH = "不匹配"
VERDICT_UNKNOWN = "未知"


class RelationEvent(SMBaseModel):
    """一个可追溯的关系命中。"""

    relation_type: str
    source_scope: str = "external_pillar"
    source_pillar: str
    target_pillar: str
    source_stem: str = ""
    source_branch: str = ""
    target_stem: str = ""
    target_branch: str = ""
    element: str = ""
    ten_god: str = ""
    strength: float | None = None
    notes: str = ""
    rule_version: str = ""


class RelationCell(SMBaseModel):
    """日期外部柱与一根股票原局柱（年/月/日）的交叉单元格。"""

    source_pillar: str
    target_pillar: str
    source_ganzhi: str
    target_ganzhi: str
    events: list[RelationEvent] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)


class RelationMatrixRow(SMBaseModel):
    """矩阵的一行（流年 / 流月 / 流日）。

    ``relation_types`` 是该行全部单元格事件类型的去重稳定序列，供 UI 直接展示
    「流年关系 / 流月关系 / 流日关系」，前端不得遍历事件自行重算。
    """

    source_pillar: str
    source_ganzhi: str
    relation_types: list[str] = Field(default_factory=list)
    cells: list[RelationCell] = Field(default_factory=list)


class RelationMatrix(SMBaseModel):
    """严格的「流年/流月/流日 × 股票年/月/日」3×3 矩阵（relation-matrix-v2）。

    股票时柱不参与本矩阵；九格内的 RelationEvent 全部保留，不做隐藏。
    """

    rows: list[RelationMatrixRow] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=lambda: ["year", "month", "day"])
    schema_version: str = settings.relation_matrix_schema_version
    relation_rule_version: str = ""


class DateRelationFingerprint(SMBaseModel):
    """只依赖目标日期的关系模板，一天只计算一次。"""

    date: date
    year: str
    month: str
    day: str
    hour: str | None = None
    stem_targets: dict[str, list[str]] = Field(default_factory=dict)
    branch_targets: dict[str, list[str]] = Field(default_factory=dict)
    candidates: dict[str, list[str]] = Field(default_factory=dict)
    supported_relations: list[str] = Field(default_factory=list)
    unavailable_relations: list[str] = Field(default_factory=list)
    calendar_engine_version: str = ""
    fingerprint_version: str = ""
    relation_rule_version: str = ""


class RelationDayVerdict(SMBaseModel):
    """流日判定：股票日主 × 流日日干的十神，与流日干五行的喜忌角色。

    十神（十神分类维度）与五行角色（喜忌维度）是两套独立坐标，
    ``reason`` 必须分开陈述，禁止出现「正财属于忌神」这类跨维度断言。
    """

    day_stem: str = ""
    day_stem_wuxing: str = ""
    day_master: str = ""
    ten_god: str = ""
    ten_god_group: str = ""
    #: 用神 / 喜神 / 忌神 / 仇神 / 闲神 / 未知
    wuxing_role: str = "未知"
    #: True=在用神/喜神集合；False=在忌/仇/闲集合；None=原局喜忌资料不足
    is_yong_or_xi: bool | None = None
    #: 匹配 / 不匹配 / 未知
    verdict: str = VERDICT_UNKNOWN
    reason: str = ""


class RelationMetrics(SMBaseModel):
    """横截面描述指标（只统计流日行三个单元格）；不是收益预测分。"""

    S_raw: int | None = Field(default=None, alias="s_raw")
    V_raw: int | None = Field(default=None, alias="v_raw")
    U_raw: int | None = Field(default=None, alias="u_raw")
    S_percentile: float | None = Field(default=None, alias="s_percentile")
    V_percentile: float | None = Field(default=None, alias="v_percentile")
    U_percentile: float | None = Field(default=None, alias="u_percentile")
    #: 结构型分组：协同型 / 扰动型 / 混合型 / 弱关系 / 不可用（无阈值定标）
    group: str = "不可用"

    model_config = {"populate_by_name": True}


class DateScanRequest(SMBaseModel):
    """日期优先扫描请求。

    不支持 hour：v3 定义日级标准采样时点（12:00 Asia/Shanghai）；
    版本口径显式进入缓存键和响应，默认值随 settings 同步。
    """

    date: date
    universe: str = "v4-full"
    birth_basis: str = "listing_open"
    birth_profile_version: str = "v2-phase4b-listing_open"
    relation_rule_version: str = Field(
        default_factory=lambda: settings.relation_rule_version,
        description="只接受 settings.relation_rule_version；其他取值返回 422。",
    )
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort: str = Field(default="stock_code", pattern="^(stock_code|s|v|u)$")
    relation_type: str | None = Field(
        default=None, description="只统计流日行（external_day_row）命中的关系类型。",
    )


class RelationStockResult(SMBaseModel):
    stock_code: str
    name: str = ""
    exchange: str = ""
    #: 股票三柱（年/月/日）；时柱不参与择日关系矩阵。
    natal: dict[str, str] = Field(default_factory=dict)
    day_master: str = ""
    yong_shen: list[str] = Field(default_factory=list)
    xi_shen: list[str] = Field(default_factory=list)
    ji_shen: list[str] = Field(default_factory=list)
    chou_shen: list[str] = Field(default_factory=list)
    xian_shen: list[str] = Field(default_factory=list)
    #: 流日行（external_day_row）命中的关系类型，去重稳定序。
    relation_types: list[str] = Field(default_factory=list)
    #: 流日行命中事件的文字说明（供 UI 直接展示，不重新计算）。
    hit_explanations: list[str] = Field(default_factory=list)
    stem_relations: list[str] = Field(default_factory=list)
    branch_relations: list[str] = Field(default_factory=list)
    compound_relations: list[str] = Field(default_factory=list)
    #: 流日十神（恰好一个，来自 day_stem_verdict；不可用时为空列表）。
    ten_gods: list[str] = Field(default_factory=list)
    #: 已废弃（legacy）：流日行事件中 element 落在用神/喜神五行的关系类型列表。
    #: 权威喜忌结论只读 ``day_stem_verdict``；新 UI 不得使用本字段表达"喜用"。
    yong_shen_relations: list[str] = Field(default_factory=list)
    day_stem_verdict: RelationDayVerdict | None = None
    metrics: RelationMetrics
    research_status: str = "NOT_RUN"
    matrix: RelationMatrix | None = None
    availability: str = "ok"
    unavailable: list[str] = Field(default_factory=list)


class DateScanVersions(SMBaseModel):
    calendar_engine_version: str = ""
    bazi_engine_version: str = ""
    relation_rule_version: str = ""
    relation_matrix_schema_version: str = ""
    fingerprint_version: str = ""
    birth_basis: str = ""
    birth_profile_version: str = ""
    universe_version: str = ""
    universe_digest: str = ""


class DateScanQuery(SMBaseModel):
    date: date
    universe: str
    birth_basis: str
    birth_profile_version: str
    relation_rule_version: str
    relation_type: str | None = None
    sort: str = "stock_code"
    offset: int = 0
    limit: int = 100


class RelationScopeDescriptor(SMBaseModel):
    """择日关系扫描的口径自描述（响应与详情端点共用）。"""

    aggregate_scope: str = Field(
        default=AGGREGATE_SCOPE,
        description="external_day_row：所有列表统计只读取 source_pillar=='day'（流日行），"
        "不是 target_pillar=='day'（股票日柱列）。",
    )
    matrix_source_scope: list[str] = Field(default_factory=lambda: list(MATRIX_SOURCE_SCOPE))
    matrix_target_scope: list[str] = Field(default_factory=lambda: list(MATRIX_TARGET_SCOPE))
    yongshen_basis: str = Field(
        default=YONGSHEN_BASIS,
        description="喜用神来源是完整四柱原局；矩阵不再用时柱不等于喜忌与时辰无关。",
    )
    evaluation_time: str = EVALUATION_TIME
    timezone: str = EVALUATION_TIMEZONE


class DateScanResponse(SMBaseModel):
    scan_id: str
    target_date: date
    fingerprint: DateRelationFingerprint
    versions: DateScanVersions
    scope: RelationScopeDescriptor = Field(default_factory=RelationScopeDescriptor)
    stock_total: int = 0
    valid_scan_count: int = 0
    returned_count: int = 0
    filtered_count: int = 0
    offset: int = 0
    limit: int = 100
    group_counts: dict[str, int] = Field(default_factory=dict)
    #: 每个关系类型命中的**股票数**（与 relation_type 过滤后的 filtered_count 一致）。
    relation_type_counts: dict[str, int] = Field(default_factory=dict)
    query: DateScanQuery
    rows: list[RelationStockResult] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    cache: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = (
        "关系分组是确定性术数结构的描述指标，不代表预期收益率、上涨概率或交易建议；"
        "历史有效性必须由独立 Event Study、负对照和样本外研究确认。"
    )


class RelationCatalogGroup(SMBaseModel):
    label: str
    items: list[str]


class RelationCatalogFactorMeta(SMBaseModel):
    """关系研究因子定义摘要（来自 RELATION_DEFINITION_INDEX，随目录一并下发）。"""

    factor_id: str
    name: str
    definition: str = ""
    computation: str = ""
    rule_version: str = ""


class RelationCatalogResponse(SMBaseModel):
    """关系类型目录：前端唯一的术数关系来源，禁止前端再维护第二份清单。"""

    relation_rule_version: str
    relation_matrix_schema_version: str
    aggregate_scope: str = AGGREGATE_SCOPE
    groups: list[RelationCatalogGroup] = Field(default_factory=list)
    factors: dict[str, RelationCatalogFactorMeta] = Field(default_factory=dict)


__all__ = [
    "AGGREGATE_SCOPE",
    "EVALUATION_TIME",
    "EVALUATION_TIMEZONE",
    "MATRIX_SOURCE_SCOPE",
    "MATRIX_TARGET_SCOPE",
    "RELATION_CATALOG",
    "RELATION_TYPES",
    "VERDICT_MATCH",
    "VERDICT_MISMATCH",
    "VERDICT_UNKNOWN",
    "WUXING_ROLES",
    "YONGSHEN_BASIS",
    "DateRelationFingerprint",
    "DateScanQuery",
    "DateScanRequest",
    "DateScanResponse",
    "DateScanVersions",
    "RelationCatalogResponse",
    "RelationCell",
    "RelationDayVerdict",
    "RelationEvent",
    "RelationMatrix",
    "RelationMatrixRow",
    "RelationMetrics",
    "RelationScopeDescriptor",
    "RelationStockResult",
]
