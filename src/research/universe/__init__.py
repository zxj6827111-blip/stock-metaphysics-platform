"""Point-in-Time Universe 查询（Phase 3A）。

合约（对应 GOAL §3A-1 / §17 泄漏测试）：

* 任何"t日可研究的股票集合"必须由本模块回答，**不允许**绕过本模块直接
  ``SELECT stock_code FROM stock_master``。
* 判定规则（严格闭区间）：
    ``list_date <= as_of AND (delist_date IS NULL OR as_of <= delist_date)``
* ``delist_date IS NULL`` **不代表"永不退市"**，只代表"当前数据源无法告诉我"。
  本模块通过 ``SurvivorshipBiasWarning`` 显式暴露该语义，
  研究报告必须传播该告警（见 ``docs/data-coverage-phase3.md`` §生存者偏差）。

泄露防护（§17 要求）：

* ``PointInTimeUniverse.at(as_of)`` 与 ``PointInTimeUniverse.iter_daily_range`` 必须
  保证："``as_of`` 之后"的 ``list_date`` 不会让股票出现在结果中；
  "``as_of`` 之前"的 ``delist_date`` 必须排除对应股票。
* 泄漏硬断言由 ``tests/research/test_point_in_time_universe.py`` 覆盖；
  新增绕过本模块的查询会触发 ``tests/research/test_universe_query_discipline.py``。
"""

from src.research.universe.point_in_time import (
    MembershipRecord,
    PointInTimeUniverse,
    SurvivorshipBiasWarning,
    UniverseSnapshot,
)

__all__ = [
    "MembershipRecord",
    "PointInTimeUniverse",
    "SurvivorshipBiasWarning",
    "UniverseSnapshot",
]
