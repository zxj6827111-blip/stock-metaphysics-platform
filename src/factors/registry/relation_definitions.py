"""关系研究因子定义。

这些因子只表示关系事件的发生次数，不预设正负方向。
"""

from src.core.config import settings
from src.core.schemas.common import Direction, EngineId
from src.core.schemas.factor import FactorCategory, FactorDefinition
from src.research.relation_study import RELATION_FACTOR_IDS, RELATION_NAMES


def relation_definitions() -> list[FactorDefinition]:
    return [
        FactorDefinition(
            factor_id=factor_id,
            name=RELATION_NAMES[relation_type],
            engine=EngineId.BAZI,
            category=FactorCategory.CROSS,
            definition=(
                f"指定 as_of 的「流日柱」与股票年/月/日三柱，在 3×3 关系矩阵的流日行中"
                f"命中「{relation_type}」的事件次数。"
            ),
            computation=(
                "normalized_value = 该 as_of 流日行（aggregate_scope=external_day_row）中"
                f"「{relation_type}」的事件命中数；未命中为 0。"
            ),
            raw_unit="count",
            normalized_hint="0 表示未命中，正数表示命中次数；不赋予涨跌方向。",
            default_direction=Direction.NEUTRAL,
            rule_score_meaning="关系事件计数，不代表预期收益率，也不代表上涨概率。",
            rule_version=settings.relation_rule_version,
            enabled=True,
            requires=["date_relation_matrix"],
            tags=["关系研究", relation_type],
        )
        for relation_type, factor_id in RELATION_FACTOR_IDS.items()
    ]
