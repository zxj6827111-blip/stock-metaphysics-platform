"""紫微第二实现源（REFERENCE ONLY）。

**硬约束（GOAL §3G-2）**：本包只能用于验证 iztro 的排盘实现差异：

* 不进入 ``ConsensusEngine``；
* 不与 iztro 一起构成"双重确认"；
* 不被业务层依赖（业务层只依赖 ``MetaphysicsEngine`` 接口）。

模块划分
--------
* ``client``    —— Node 客户端（``services/ziwei-reference-service``）+ 可用性状态
* ``normalize`` —— 简繁/别名归一（只做字形与别名等价，不做语义近似）
* ``compare``   —— 案例集加载与字段级差异登记
"""

from src.engines.ziwei.reference.client import (
    CROSSCHECK_UNAVAILABLE,
    REFERENCE_AVAILABLE,
    REFERENCE_LIBRARY,
    REFERENCE_LICENSE,
    REFERENCE_REPOSITORY,
    REFERENCE_SCHOOL,
    REFERENCE_UNAVAILABLE,
    REFERENCE_VERSION_PINNED,
    ReferenceChart,
    ReferenceStatus,
    ReferenceUnavailableError,
    fetch_charts,
    reference_status,
)
from src.engines.ziwei.reference.compare import (
    CaseComparison,
    CrossEngineCase,
    Difference,
    compare_case,
    load_cases,
)

__all__ = [
    "CROSSCHECK_UNAVAILABLE",
    "REFERENCE_AVAILABLE",
    "REFERENCE_LIBRARY",
    "REFERENCE_LICENSE",
    "REFERENCE_REPOSITORY",
    "REFERENCE_SCHOOL",
    "REFERENCE_UNAVAILABLE",
    "REFERENCE_VERSION_PINNED",
    "CaseComparison",
    "CrossEngineCase",
    "Difference",
    "ReferenceChart",
    "ReferenceStatus",
    "ReferenceUnavailableError",
    "compare_case",
    "fetch_charts",
    "load_cases",
    "reference_status",
]
