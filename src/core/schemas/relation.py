"""日期关系扫描的结构化 API Schema。

这些类型只描述确定性关系计算结果，不把关系转换成收益预测或交易建议。
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import Field

from src.core.schemas.common import SMBaseModel, Warning_

RELATION_CATALOG: dict[str, list[str]] = {
    "天干": ["天干五合", "天干相冲", "天干生", "天干克", "天干同五行"],
    "地支": ["六合", "六冲", "三合", "半合", "三会", "相刑", "三刑", "自刑", "相害", "六破", "同支"],
    "组合": ["伏吟", "反吟", "天合地合", "天克地冲"],
}
RELATION_TYPES: tuple[str, ...] = tuple(
    relation for relations in RELATION_CATALOG.values() for relation in relations
)


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
    """日期外部柱与一根股票原局柱的交叉单元格。"""

    source_pillar: str
    target_pillar: str
    source_ganzhi: str
    target_ganzhi: str
    events: list[RelationEvent] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    unavailable: list[str] = Field(default_factory=list)


class RelationMatrixRow(SMBaseModel):
    source_pillar: str
    source_ganzhi: str
    cells: list[RelationCell] = Field(default_factory=list)


class RelationMatrix(SMBaseModel):
    """严格的「流年/流月/流日 × 股票年/月/日/时」3×4 矩阵。"""

    rows: list[RelationMatrixRow] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=lambda: ["year", "month", "day", "hour"])
    schema_version: str = "relation-matrix-v1"
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


class RelationMetrics(SMBaseModel):
    """横截面描述指标；不是收益预测分。"""

    S_raw: int | None = Field(default=None, alias="s_raw")
    V_raw: int | None = Field(default=None, alias="v_raw")
    U_raw: int | None = Field(default=None, alias="u_raw")
    S_percentile: float | None = Field(default=None, alias="s_percentile")
    V_percentile: float | None = Field(default=None, alias="v_percentile")
    U_percentile: float | None = Field(default=None, alias="u_percentile")
    group: str = "不可用"

    model_config = {"populate_by_name": True}


class DateScanRequest(SMBaseModel):
    """日期优先扫描请求；版本口径显式进入缓存键和响应。"""

    date: date
    hour: int | None = Field(default=None, ge=0, le=23)
    universe: str = "v4-full"
    birth_basis: str = "listing_open"
    birth_profile_version: str = "v2-phase4b-listing_open"
    relation_rule_version: str = "bazi-relation-v2"
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    sort: str = Field(default="stock_code", pattern="^(stock_code|s|v|u)$")
    relation_type: str | None = None


class RelationStockResult(SMBaseModel):
    stock_code: str
    name: str = ""
    exchange: str = ""
    natal: dict[str, str] = Field(default_factory=dict)
    day_master: str = ""
    yong_shen: list[str] = Field(default_factory=list)
    xi_shen: list[str] = Field(default_factory=list)
    ji_shen: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    hit_explanations: list[str] = Field(default_factory=list)
    stem_relations: list[str] = Field(default_factory=list)
    branch_relations: list[str] = Field(default_factory=list)
    compound_relations: list[str] = Field(default_factory=list)
    ten_gods: list[str] = Field(default_factory=list)
    yong_shen_relations: list[str] = Field(default_factory=list)
    metrics: RelationMetrics
    research_status: str = "NOT_RUN"
    matrix: RelationMatrix | None = None
    availability: str = "ok"
    unavailable: list[str] = Field(default_factory=list)


class DateScanVersions(SMBaseModel):
    calendar_engine_version: str = ""
    bazi_engine_version: str = ""
    relation_rule_version: str = ""
    fingerprint_version: str = ""
    birth_basis: str = ""
    birth_profile_version: str = ""
    universe_version: str = ""
    universe_digest: str = ""


class DateScanQuery(SMBaseModel):
    date: date
    hour: int | None = None
    universe: str
    birth_basis: str
    birth_profile_version: str
    relation_rule_version: str
    relation_type: str | None = None
    sort: str = "stock_code"
    offset: int = 0
    limit: int = 100


class DateScanResponse(SMBaseModel):
    scan_id: str
    target_date: date
    fingerprint: DateRelationFingerprint
    versions: DateScanVersions
    stock_total: int = 0
    valid_scan_count: int = 0
    returned_count: int = 0
    filtered_count: int = 0
    offset: int = 0
    limit: int = 100
    group_counts: dict[str, int] = Field(default_factory=dict)
    relation_type_counts: dict[str, int] = Field(default_factory=dict)
    query: DateScanQuery
    rows: list[RelationStockResult] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    cache: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = (
        "关系分组是确定性术数结构的描述指标，不代表预期收益率、上涨概率或交易建议；"
        "历史有效性必须由独立 Event Study、负对照和样本外研究确认。"
    )
