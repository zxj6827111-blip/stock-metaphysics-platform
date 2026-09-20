"""Phase 3D：样本外（OOS）/ Walk-forward 研究管线。

模块地图
--------
    splits.py             固定 holdout 切分契约（``phase3-oos-v1``）
    calibration_freeze.py ``cal-v1`` 冻结声明与断言
    gates.py              OOS 状态门（GOAL §15 十项条件）
    walk_forward.py       扩窗 walk-forward，逐 fold 重拟合（P0 规则）
    diagnostics.py        年份稳定性 / 重叠窗口 / 单一股票依赖 / 效应量
    registry.py           假设预注册 + 实验登记（复用 backtest_experiment）
    runner.py             固定 holdout 的实验执行器与负对照

配套标签计算在 ``src/research/labels/horizon_returns.py``（未来收益只能由
labels 模块计算，见 AGENTS.md §6）。
"""

from src.research.oos.calibration_freeze import (
    CALIBRATION_VERSION,
    FREEZE_V1,
    CalibrationFreeze,
    CalibrationFreezeError,
    freeze_for,
)
from src.research.oos.diagnostics import (
    cohens_d,
    effect_size_summary,
    non_overlapping_subset,
    overlap_ratio,
    stock_dependency,
    year_stability,
)
from src.research.oos.gates import (
    GATE_VERSION,
    GateCheck,
    OOSGateResult,
    evaluate_oos_gate,
    gate_thresholds,
)
from src.research.oos.registry import (
    HYPOTHESIS_REGISTRY_VERSION,
    RESEARCH_REUSE_WARNING,
    ExperimentRecord,
    HypothesisRegistry,
    HypothesisSpec,
    load_hypothesis_registry,
    new_experiment_id,
    persist_experiments,
    write_experiment_registry_csv,
)
from src.research.oos.runner import (
    HypothesisOutcome,
    build_observation_panel,
    run_hypothesis,
)
from src.research.oos.splits import (
    HORIZONS,
    PRIMARY_HORIZON,
    SPLIT_VERSION,
    ResearchSplit,
    SplitContractError,
    default_split,
)
from src.research.oos.walk_forward import (
    WalkForwardFold,
    WalkForwardLeakError,
    expanding_folds,
    run_walk_forward,
)

__all__ = [
    "CALIBRATION_VERSION",
    "FREEZE_V1",
    "GATE_VERSION",
    "HORIZONS",
    "HYPOTHESIS_REGISTRY_VERSION",
    "PRIMARY_HORIZON",
    "RESEARCH_REUSE_WARNING",
    "SPLIT_VERSION",
    "CalibrationFreeze",
    "CalibrationFreezeError",
    "ExperimentRecord",
    "GateCheck",
    "HypothesisOutcome",
    "HypothesisRegistry",
    "HypothesisSpec",
    "OOSGateResult",
    "ResearchSplit",
    "SplitContractError",
    "WalkForwardFold",
    "WalkForwardLeakError",
    "build_observation_panel",
    "cohens_d",
    "default_split",
    "effect_size_summary",
    "evaluate_oos_gate",
    "expanding_folds",
    "freeze_for",
    "gate_thresholds",
    "load_hypothesis_registry",
    "new_experiment_id",
    "non_overlapping_subset",
    "overlap_ratio",
    "persist_experiments",
    "run_hypothesis",
    "run_walk_forward",
    "stock_dependency",
    "write_experiment_registry_csv",
    "year_stability",
]
