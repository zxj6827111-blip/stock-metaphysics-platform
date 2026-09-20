"""Phase 3F · 多重检验、重采样与稳健性。

模块划分
--------
* ``families``   —— 假设族冻结定义（``mt-v1``）：BH 在族内校正
* ``fdr``        —— Benjamini-Hochberg FDR + Bonferroni
* ``resample``   —— 日期分层置换检验 + date-block bootstrap
* ``robustness`` —— 九个预注册稳健性维度
* ``gate_v2``    —— A–L 十二项条件；唯一允许解锁 SUPPORTED_OUT_OF_SAMPLE 的路径
* ``runner``     —— 执行器：对 3D 的 54 个实验逐条 3F 分析
"""

from src.research.multipletesting.families import (
    MT_VERSION,
    FamilyRegistry,
    FamilySpec,
    load_family_registry,
)
from src.research.multipletesting.fdr import (
    MultipleTestingResult,
    apply_family_correction,
    benjamini_hochberg,
)
from src.research.multipletesting.gate_v2 import (
    GATE_V2_VERSION,
    GateV2Result,
    evaluate_gate_v2,
    gate_v2_thresholds,
)
from src.research.multipletesting.resample import (
    BOOTSTRAP_VERSION,
    PERMUTATION_VERSION,
    BootstrapResult,
    PermutationResult,
    date_block_bootstrap,
    permutation_test,
)

__all__ = [
    "BOOTSTRAP_VERSION",
    "GATE_V2_VERSION",
    "MT_VERSION",
    "PERMUTATION_VERSION",
    "BootstrapResult",
    "FamilyRegistry",
    "FamilySpec",
    "GateV2Result",
    "MultipleTestingResult",
    "PermutationResult",
    "apply_family_correction",
    "benjamini_hochberg",
    "date_block_bootstrap",
    "evaluate_gate_v2",
    "gate_v2_thresholds",
    "load_family_registry",
    "permutation_test",
]
