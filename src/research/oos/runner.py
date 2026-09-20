"""Phase 3D 研究执行器：固定 holdout 的 OOS 实验 + 负对照 + 状态门。

数据流
------
    raw panel（采集器产物：opinion 观测）
      → calibration.transform（只用 TRAIN 冻结阈值；只追加研究列）
      → 方向矩阵（raw_direction / calibrated_direction → 假设命中掩码）
      → 与标签 join（``src/research/labels/horizon_returns.py``）
      → 分区统计 + 年份稳定性 + 重叠/单一股票诊断
      → 负对照（随机事件位置 / 随机出生指派 / 出生日期 ±7 天平移）
      → ``evaluate_oos_gate``（GOAL §15 十项条件）

硬性纪律
--------
* 事件定义只来自**预注册假设**（``hypothesis_registry.yaml``），不支持自由组合搜索。
* 负对照的置换分布规模固定（``PERMUTATION_DRAWS``），种子由
  ``settings.negative_control_seed`` + 假设 + 出生模型派生，可复现。
* ``ipo_approx_v1`` 的所有结果都携带 ``IPO_APPROXIMATION_WARNING``。
* OOS 只评估一次；评估后 ``oos_used=True`` 写进实验登记。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from src.core.config import settings
from src.research.oos import diagnostics as diag
from src.research.oos.gates import OOSGateResult, evaluate_oos_gate, gate_thresholds
from src.research.oos.registry import HypothesisSpec
from src.research.oos.splits import OOS, TRAIN, VALIDATION, ResearchSplit

#: 随机对照的置换分布规模
PERMUTATION_DRAWS = 200
#: 出生日期平移对照的平移天数（± 两个方向）
SHIFT_DAYS = (-7, 7)
#: ipo_approx 出生模型的强制告警
IPO_APPROXIMATION_WARNING = (
    "IPO_APPROXIMATION_WARNING：本结果的出生时间使用 ipo_approx_v1 近似口径"
    "（TuShare ipo_date 近似），**不是真实公司成立时间**，"
    "不得描述为『真实 IPO 出生时间』。"
)
#: 对照类型常量
CONTROL_RANDOM_POSITION = "random_event_position"
CONTROL_RANDOM_BIRTH_ASSIGNMENT = "random_birth_assignment"
CONTROL_SHIFT_MINUS_7 = "shifted_birth_date_minus_7d"
CONTROL_SHIFT_PLUS_7 = "shifted_birth_date_plus_7d"


class PanelError(RuntimeError):
    """面板数据不满足研究前提（缺列、分区越界等）。"""


# ---------------------------------------------------------------------------
# 面板
# ---------------------------------------------------------------------------


REQUIRED_PANEL_COLUMNS = (
    "stock_code", "birth_model", "as_of", "engine", "opinion_score", "raw_direction",
)


def build_observation_panel(rows: list[dict], split: ResearchSplit) -> pd.DataFrame:
    """把采集器行集合转成研究面板，并按日历打上 holdout 分区（只用日历，不看收益）。"""
    if not rows:
        return pd.DataFrame(columns=[*REQUIRED_PANEL_COLUMNS, "partition", "year"])
    frame = pd.DataFrame(rows)
    missing = [c for c in REQUIRED_PANEL_COLUMNS if c not in frame.columns]
    if missing:
        raise PanelError(f"观测面板缺少字段：{missing}")
    frame["as_of"] = pd.to_datetime(frame["as_of"]).dt.date
    frame["partition"] = [split.partition_of(value) for value in frame["as_of"]]
    frame["year"] = [value.year for value in frame["as_of"]]
    frame["raw_direction"] = pd.to_numeric(frame["raw_direction"], errors="coerce")
    frame["opinion_score"] = pd.to_numeric(frame["opinion_score"], errors="coerce")
    return frame


def assert_no_out_of_scope(panel: pd.DataFrame, split: ResearchSplit) -> None:
    """面板里不允许出现研究区间之外的样本（例如早于 2010 的数据被误采）。"""
    out = panel[panel["partition"] == "OUT_OF_SCOPE"]
    if not out.empty:
        raise PanelError(
            f"面板包含 OUT_OF_SCOPE 样本 {len(out)} 行"
            f"（{out['as_of'].min()}..{out['as_of'].max()}）"
        )


def attach_calibration(panel: pd.DataFrame, layer) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    """把校准层 transform 到整块面板上，并校验原始字段未被改动。"""
    out = layer.transform(panel.copy())
    for column in ("opinion_score", "raw_direction"):
        if not panel[column].reset_index(drop=True).equals(
            pd.to_numeric(out[column], errors="coerce").reset_index(drop=True)
        ):
            raise AssertionError(f"Calibration 修改了原始字段 {column}（研究层不得回写）")
    return out


# ---------------------------------------------------------------------------
# 命中掩码
# ---------------------------------------------------------------------------


def _hit_from_wide(pivot: pd.DataFrame, spec: HypothesisSpec) -> pd.Series:
    """由 (stock, as_of) × engine 的方向宽表计算命中布尔。

    缺失引擎一律**不命中**（缺数据不得当 0、也不得当命中）。
    """
    if pivot.empty or any(engine not in pivot.columns for engine in spec.engines):
        return pd.Series(dtype=bool)
    if spec.logic == "single":
        hit = pd.to_numeric(pivot[spec.engines[0]], errors="coerce") > 0
    elif spec.logic == "all_positive":
        hit = pd.Series(True, index=pivot.index)
        for engine in spec.engines:
            hit &= pd.to_numeric(pivot[engine], errors="coerce") > 0
    else:  # conflict：正引擎为正、负引擎为负
        conflict = spec.conflict or {}
        hit = pd.Series(True, index=pivot.index)
        for engine in conflict.get("positive", ()):
            hit &= pd.to_numeric(pivot[engine], errors="coerce") > 0
        for engine in conflict.get("negative", ()):
            hit &= pd.to_numeric(pivot[engine], errors="coerce") < 0
    return hit.fillna(False).astype(bool)


def direction_wide(
    panel: pd.DataFrame,
    spec: HypothesisSpec,
    *,
    birth_model: str,
    source: str,
) -> pd.DataFrame:
    """``(stock_code, as_of) × engine`` 的方向宽表。"""
    value_col = "raw_direction" if source == "raw" else "calibrated_direction"
    if value_col not in panel.columns:
        raise PanelError(f"面板缺少 {value_col} 列")
    sub = panel[(panel["birth_model"] == birth_model) & (panel["engine"].isin(spec.engines))]
    if sub.empty:
        return pd.DataFrame()
    return sub.pivot_table(
        index=["stock_code", "as_of"], columns="engine", values=value_col, aggfunc="first",
    )


def direction_matrix(
    panel: pd.DataFrame,
    spec: HypothesisSpec,
    *,
    birth_model: str,
    source: str,
) -> pd.DataFrame:
    """命中掩码：``stock_code`` / ``as_of`` / ``hit``。"""
    pivot = direction_wide(panel, spec, birth_model=birth_model, source=source)
    hit = _hit_from_wide(pivot, spec)
    if hit.empty:
        return pd.DataFrame(columns=["stock_code", "as_of", "hit"])
    return hit.rename("hit").reset_index()


def event_frame(
    mask: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    stock_col: str = "stock_code",
) -> pd.DataFrame:
    """把命中掩码与未来收益标签 join 成事件表（无标签的命中不出现在事件里）。"""
    if mask.empty or labels.empty:
        return pd.DataFrame(columns=["stock_code", "as_of", "trade_date", "trade_index"])
    merged = mask[mask["hit"]].merge(labels, on=[stock_col, "as_of"], how="inner")
    return merged.drop(columns=["hit"], errors="ignore")


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


def _numeric(frame: pd.DataFrame, column: str) -> np.ndarray:
    if frame is None or len(frame) == 0 or column not in frame.columns:
        return np.asarray([], dtype=float)
    values = pd.to_numeric(frame[column], errors="coerce").to_numpy(dtype=float)
    return values[np.isfinite(values)]


def horizon_stats(frame: pd.DataFrame, horizon: int) -> dict:
    ret = _numeric(frame, f"ret_{horizon}d")
    excess = _numeric(frame, f"excess_return_{horizon}d")
    bench = _numeric(frame, f"bench_ret_{horizon}d")
    n = int(len(ret))
    if n == 0:
        return {
            "horizon": horizon, "sample_count": 0, "mean_return": None,
            "median_return": None, "std_return": None, "up_rate": None,
            "mean_excess_return": None, "excess_up_rate": None, "mean_bench_return": None,
        }
    return {
        "horizon": horizon,
        "sample_count": n,
        "mean_return": round(float(ret.mean()), 6),
        "median_return": round(float(np.median(ret)), 6),
        "std_return": round(float(ret.std(ddof=1)), 6) if n > 1 else None,
        "up_rate": round(float((ret > 0).mean()), 6),
        "mean_excess_return": round(float(excess.mean()), 6) if len(excess) else None,
        "excess_up_rate": round(float((excess > 0).mean()), 6) if len(excess) else None,
        "mean_bench_return": round(float(bench.mean()), 6) if len(bench) else None,
    }


def partition_stats(
    frame: pd.DataFrame, partition: str, horizons: tuple[int, ...], primary_horizon: int,
) -> dict:
    by_horizon = {h: horizon_stats(frame, h) for h in horizons}
    primary = by_horizon.get(primary_horizon, {})
    mean_excess = primary.get("mean_excess_return")
    return {
        "partition": partition,
        "event_count": int(len(frame)),
        "sample_count": int(primary.get("sample_count") or 0),
        "eligible_stock_count": int(frame["stock_code"].nunique()) if len(frame) else 0,
        "coverage_start": str(pd.to_datetime(frame["trade_date"]).dt.date.min())
        if len(frame) else None,
        "coverage_end": str(pd.to_datetime(frame["trade_date"]).dt.date.max())
        if len(frame) else None,
        "mean_return": primary.get("mean_return"),
        "mean_excess_return": mean_excess,
        "up_rate": primary.get("up_rate"),
        "excess_up_rate": primary.get("excess_up_rate"),
        "median_return": primary.get("median_return"),
        "std_return": primary.get("std_return"),
        "sign": 0 if mean_excess is None else int(np.sign(mean_excess)),
        "by_horizon": by_horizon,
    }


# ---------------------------------------------------------------------------
# 负对照
# ---------------------------------------------------------------------------


@dataclass
class ControlOutcome:
    kind: str
    description: str
    event_count: int = 0
    jaccard_with_real: float | None = None
    overlap_with_real: int | None = None
    expected_overlap_fraction: float | None = None
    mean_return: float | None = None
    mean_excess_return: float | None = None
    up_rate: float | None = None
    delta_mean_excess: float | None = None
    p_value: float | None = None
    p_value_lower: float | None = None
    p_value_upper: float | None = None
    p_value_method: str = ""
    draws: int | None = None
    control_mean_std: float | None = None
    decisive: bool = False
    verdict: str = "inconclusive"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "control_kind": self.kind,
            "control_description": self.description,
            "event_count": self.event_count,
            "jaccard_with_real": self.jaccard_with_real,
            "overlap_with_real": self.overlap_with_real,
            "expected_overlap_fraction": self.expected_overlap_fraction,
            "mean_return": self.mean_return,
            "mean_excess_return": self.mean_excess_return,
            "up_rate": self.up_rate,
            "delta_mean_excess_vs_real": self.delta_mean_excess,
            "p_value": self.p_value,
            "p_value_lower": self.p_value_lower,
            "p_value_upper": self.p_value_upper,
            "p_value_method": self.p_value_method,
            "draws": self.draws,
            "control_mean_std": self.control_mean_std,
            "decisive": self.decisive,
            "verdict": self.verdict,
            "warnings": list(self.warnings),
        }


def _jaccard(left: set, right: set) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _event_keys(frame: pd.DataFrame) -> set[tuple[str, object]]:
    if frame is None or len(frame) == 0:
        return set()
    return {(str(r.stock_code), r.as_of) for r in frame.itertuples()}


def _seed_for(hypothesis_id: str, birth_model: str, salt: str) -> int:
    payload = f"{settings.negative_control_seed}:{hypothesis_id}:{birth_model}:{salt}"
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8], 16)


def random_event_position_control(
    real_events: pd.DataFrame,
    pool: pd.DataFrame,
    *,
    horizon: int,
    seed: int,
    draws: int = PERMUTATION_DRAWS,
    description: str = "",
) -> ControlOutcome:
    """随机事件位置对照：从同分区可用池里随机抽"同样多"的事件（置换分布）。

    对照值取置换分布均值；``p`` 值取置换分布上的单侧经验概率
    ``(#{draw >= real} + 1) / (draws + 1)``。事件集合的 Jaccard 用第 0 次
    置换作为代表样本 —— 因为"随机事件位置"本身是一个分布，不是一个集合。
    """
    real_values = _numeric(real_events, f"excess_return_{horizon}d")
    pool_values = _numeric(pool, f"excess_return_{horizon}d")
    outcome = ControlOutcome(
        kind=CONTROL_RANDOM_POSITION,
        description=description or (
            f"从同一分区的可用 (股票, as_of) 池中随机抽取与真实事件相同数量的事件"
            f"（{draws} 次置换），检验真实事件位置是否优于随机位置。"
        ),
        event_count=int(len(real_values)),
        draws=draws,
        p_value_method="permutation_one_sided",
    )
    if len(real_values) == 0 or len(pool_values) == 0:
        outcome.warnings.append("真实事件或候选池为空，对照不可判定")
        return outcome

    rng = np.random.default_rng(seed)
    size = min(len(real_values), len(pool_values))
    means = np.empty(draws, dtype=float)
    for i in range(draws):
        idx = rng.choice(len(pool_values), size=size, replace=False)
        means[i] = float(pool_values[idx].mean())
    real_mean = float(real_values.mean())
    outcome.mean_excess_return = round(float(means.mean()), 6)
    outcome.mean_return = outcome.mean_excess_return
    outcome.control_mean_std = round(float(means.std(ddof=1)), 6) if draws > 1 else None
    outcome.delta_mean_excess = round(real_mean - float(means.mean()), 6)
    outcome.p_value_upper = float((np.sum(means >= real_mean) + 1) / (draws + 1))
    outcome.p_value_lower = float((np.sum(means <= real_mean) + 1) / (draws + 1))
    outcome.p_value = outcome.p_value_upper
    outcome.up_rate = round(float((pool_values > 0).mean()), 6)
    outcome.decisive = True
    outcome.verdict = _verdict_from_delta(outcome.delta_mean_excess)

    idx0 = rng.choice(len(pool_values), size=size, replace=False)
    representative = pool.iloc[np.sort(idx0)]
    real_keys, control_keys = _event_keys(real_events), _event_keys(representative)
    outcome.jaccard_with_real = round(_jaccard(real_keys, control_keys), 6)
    outcome.overlap_with_real = len(real_keys & control_keys)
    outcome.expected_overlap_fraction = round(size / len(pool_values), 6)
    return outcome


def _verdict_from_delta(delta: float | None) -> str:
    if delta is None:
        return "inconclusive"
    if delta > 0:
        return "outperform"
    if delta < 0:
        return "underperform"
    return "tie"


@dataclass
class _DateBlock:
    """同一 as_of 下的股票块（用于逐日置换）。"""

    key: object
    values: np.ndarray          # (n_stocks, n_engines) 方向值
    excess_primary: np.ndarray  # (n_stocks,) 主持有期超额收益
    stocks: list[str]


def _build_date_blocks(
    panel: pd.DataFrame,
    spec: HypothesisSpec,
    *,
    birth_model: str,
    source: str,
    labels: pd.DataFrame,
    partitions: tuple[str, ...],
    horizon: int,
) -> list[_DateBlock]:
    """把面板切成"每日股票块"，供置换对照使用（向量化，避免逐次建 DataFrame）。"""
    pivot = direction_wide(panel, spec, birth_model=birth_model, source=source)
    if pivot.empty:
        return []
    pivot = pivot.reset_index()
    sub_partition = panel[
        (panel["birth_model"] == birth_model) & (panel["partition"].isin(partitions))
    ]
    allowed = set(zip(sub_partition["stock_code"], sub_partition["as_of"], strict=True))
    pivot = pivot[[(row.stock_code, row.as_of) in allowed for row in pivot.itertuples()]]
    if pivot.empty:
        return []
    label_lookup = labels.set_index(["stock_code", "as_of"])
    column = f"excess_return_{horizon}d"
    blocks: list[_DateBlock] = []
    for as_of, group in pivot.groupby("as_of", sort=True):
        stocks = group["stock_code"].tolist()
        values = group[list(spec.engines)].to_numpy(dtype=float)
        excess_primary = np.full(len(stocks), np.nan, dtype=float)
        for i, code in enumerate(stocks):
            try:
                row = label_lookup.loc[(code, as_of)]
            except KeyError:
                continue
            if isinstance(row, pd.DataFrame):
                if row.empty:
                    continue
                row = row.iloc[0]
            value = row[column]
            if value is not None and np.isfinite(float(value)):
                excess_primary[i] = float(value)
        # 没有主持有期标签的 (股票, as_of) 不是"事件"：事件研究里它根本进不来。
        # 因此候选池只保留标签订阅成功且有限的行，保证对照命中数与真实事件数同口径。
        valid = np.isfinite(excess_primary)
        if not valid.any():
            continue
        blocks.append(_DateBlock(
            key=as_of,
            values=values[valid],
            excess_primary=excess_primary[valid],
            stocks=[code for code, keep in zip(stocks, valid, strict=True) if keep],
        ))
    return blocks


def _hit_mask(values: np.ndarray, spec: HypothesisSpec) -> np.ndarray:
    """由 (n_stocks, n_engines) 方向矩阵计算命中布尔。"""
    engines = list(spec.engines)
    columns = {engine: values[:, i] for i, engine in enumerate(engines)}
    if spec.logic == "single":
        return columns[engines[0]] > 0
    if spec.logic == "all_positive":
        hit = np.ones(values.shape[0], dtype=bool)
        for engine in engines:
            hit &= columns[engine] > 0
        return hit
    conflict = spec.conflict or {}
    hit = np.ones(values.shape[0], dtype=bool)
    for engine in conflict.get("positive", ()):
        hit &= columns[engine] > 0
    for engine in conflict.get("negative", ()):
        hit &= columns[engine] < 0
    return hit


def random_birth_assignment_control(
    panel: pd.DataFrame,
    spec: HypothesisSpec,
    *,
    birth_model: str,
    source: str,
    labels: pd.DataFrame,
    partitions: tuple[str, ...],
    horizon: int,
    seed: int,
    real_events: pd.DataFrame,
    draws: int = PERMUTATION_DRAWS,
) -> ControlOutcome:
    """随机出生指派对照：在同一 as_of 内把命盘指派随机置换到其它股票。

    同一股票的**所有引擎一起置换**（因为 bazi / ziwei 盘面同源于一个出生时间），
    因此保持每日横截面分布不变，只破坏"股票 ↔ 命盘"的对应关系。
    """
    outcome = ControlOutcome(
        kind=CONTROL_RANDOM_BIRTH_ASSIGNMENT,
        description=(
            "在同一 as_of 内把命盘（引擎方向向量）随机置换到池内其它股票，"
            "保持每日横截面分布不变，破坏「股票↔命盘」对应关系。"
        ),
        draws=draws,
        p_value_method="permutation_one_sided",
    )
    blocks = _build_date_blocks(
        panel, spec, birth_model=birth_model, source=source, labels=labels,
        partitions=partitions, horizon=horizon,
    )
    if not blocks:
        outcome.warnings.append("面板在该分区为空，对照不可判定")
        return outcome
    real_values = _numeric(real_events, f"excess_return_{horizon}d")
    if len(real_values) == 0:
        outcome.warnings.append("真实事件没有有效标签，对照不可判定")
        return outcome
    real_mean = float(real_values.mean())

    rng = np.random.default_rng(seed)
    means = np.full(draws, np.nan, dtype=float)
    counts = np.zeros(draws, dtype=int)
    for i in range(draws):
        total = 0.0
        n = 0
        for block in blocks:
            permutation = rng.permutation(len(block.stocks))
            hit = _hit_mask(block.values[permutation], spec)
            values = block.excess_primary[hit]
            finite = values[np.isfinite(values)]
            total += float(finite.sum())
            n += int(len(finite))
        counts[i] = n
        if n:
            means[i] = total / n
    finite = means[np.isfinite(means)]
    if len(finite) == 0:
        outcome.warnings.append("置换分布全部为空")
        return outcome
    outcome.mean_excess_return = round(float(finite.mean()), 6)
    outcome.mean_return = outcome.mean_excess_return
    outcome.control_mean_std = round(float(finite.std(ddof=1)), 6) if len(finite) > 1 else None
    outcome.event_count = int(round(float(np.mean(counts))))
    outcome.delta_mean_excess = round(real_mean - float(finite.mean()), 6)
    outcome.p_value_upper = float((np.sum(finite >= real_mean) + 1) / (len(finite) + 1))
    outcome.p_value_lower = float((np.sum(finite <= real_mean) + 1) / (len(finite) + 1))
    outcome.p_value = outcome.p_value_upper
    outcome.decisive = True
    outcome.verdict = _verdict_from_delta(outcome.delta_mean_excess)
    outcome.warnings.append(
        "随机出生指派只检验『股票↔命盘对应关系』是否携带信息，"
        "不能检验「同一命盘在不同日期是否有效」；后者由随机事件位置对照承担。"
    )
    return outcome


def random_direction_control(
    panel: pd.DataFrame,
    spec: HypothesisSpec,
    *,
    birth_model: str,
    source: str,
    labels: pd.DataFrame,
    partitions: tuple[str, ...],
    horizon: int,
    seed: int,
    real_events: pd.DataFrame,
    draws: int = PERMUTATION_DRAWS,
) -> ControlOutcome:
    """随机模型方向对照：保持命中数量，随机选择命中位置。

    与随机出生指派的区别：这里**不保留命盘结构**，只保留"每天命中多少只股票"，
    检验的是"具体哪些股票命中"是否携带信息。
    """
    outcome = ControlOutcome(
        kind="random_model_direction",
        description=(
            "在每个 as_of 内保持命中数量不变，把命中位置随机重新指派给池内股票，"
            "检验「具体哪些股票命中」是否携带信息。"
        ),
        draws=draws,
        p_value_method="permutation_one_sided",
    )
    blocks = _build_date_blocks(
        panel, spec, birth_model=birth_model, source=source, labels=labels,
        partitions=partitions, horizon=horizon,
    )
    if not blocks:
        outcome.warnings.append("面板在该分区为空，对照不可判定")
        return outcome
    real_values = _numeric(real_events, f"excess_return_{horizon}d")
    if len(real_values) == 0:
        outcome.warnings.append("真实事件没有有效标签，对照不可判定")
        return outcome
    real_mean = float(real_values.mean())

    rng = np.random.default_rng(seed)
    means = np.full(draws, np.nan, dtype=float)
    counts = np.zeros(draws, dtype=int)
    for i in range(draws):
        total = 0.0
        n = 0
        for block in blocks:
            hit = _hit_mask(block.values, spec)
            k = int(hit.sum())
            counts[i] += k
            if k == 0:
                continue
            chosen = rng.choice(len(block.stocks), size=k, replace=False)
            values = block.excess_primary[chosen]
            finite = values[np.isfinite(values)]
            total += float(finite.sum())
            n += int(len(finite))
        if n:
            means[i] = total / n
    finite = means[np.isfinite(means)]
    if len(finite) == 0:
        outcome.warnings.append("置换分布全部为空")
        return outcome
    outcome.mean_excess_return = round(float(finite.mean()), 6)
    outcome.mean_return = outcome.mean_excess_return
    outcome.control_mean_std = round(float(finite.std(ddof=1)), 6) if len(finite) > 1 else None
    outcome.event_count = int(round(float(np.mean(counts))))
    outcome.delta_mean_excess = round(real_mean - float(finite.mean()), 6)
    outcome.p_value_upper = float((np.sum(finite >= real_mean) + 1) / (len(finite) + 1))
    outcome.p_value_lower = float((np.sum(finite <= real_mean) + 1) / (len(finite) + 1))
    outcome.p_value = outcome.p_value_upper
    outcome.decisive = True
    outcome.verdict = _verdict_from_delta(outcome.delta_mean_excess)
    outcome.warnings.append(
        "本对照只随机化命中位置，保留每日命中数量；"
        "若真实事件集合接近整个池（如原始 BAZI_POS 正向率 96%），本对照会退化。"
    )
    return outcome


def shifted_birth_control(
    shifted_events: pd.DataFrame,
    *,
    kind: str,
    days: int,
    real_events: pd.DataFrame,
    horizon: int,
) -> ControlOutcome:
    """出生日期平移对照（用 ±N 天重排盘的 panel 计算）。

    该对照使用**真实 TRAIN 冻结阈值**（平移 panel 只采集 Validation/OOS 区间），
    因此它是"同一阈值语义下的反事实"，这一点必须写进方法学文档。
    """
    outcome = ControlOutcome(
        kind=kind,
        description=(
            f"把出生时间平移 {days:+d} 天后重新排盘、重算因子，"
            "在真实 TRAIN 冻结阈值下重新求解事件集合。"
        ),
        event_count=int(len(shifted_events)) if shifted_events is not None else 0,
        p_value_method="welch_normal_approx",
    )
    if shifted_events is None or shifted_events.empty:
        outcome.warnings.append("平移 panel 没有事件")
        return outcome
    values = _numeric(shifted_events, f"excess_return_{horizon}d")
    if len(values) == 0:
        outcome.warnings.append("平移 panel 的事件没有有效标签")
        return outcome
    outcome.mean_excess_return = round(float(values.mean()), 6)
    outcome.mean_return = outcome.mean_excess_return
    outcome.up_rate = round(float((values > 0).mean()), 6)
    real_values = _numeric(real_events, f"excess_return_{horizon}d")
    if len(real_values):
        outcome.delta_mean_excess = round(float(real_values.mean()) - float(values.mean()), 6)
        _t, p = diag.welch_ttest(real_values, values)
        outcome.p_value = p
    real_keys, control_keys = _event_keys(real_events), _event_keys(shifted_events)
    outcome.jaccard_with_real = round(_jaccard(real_keys, control_keys), 6)
    outcome.overlap_with_real = len(real_keys & control_keys)
    outcome.decisive = True
    outcome.verdict = _verdict_from_delta(outcome.delta_mean_excess)
    return outcome


# ---------------------------------------------------------------------------
# 单个假设 × 单个出生模型
# ---------------------------------------------------------------------------


@dataclass
class HypothesisOutcome:
    hypothesis_id: str
    object_id: str
    birth_model: str
    direction_source: str
    partitioned: dict = field(default_factory=dict)
    calibration_audit: dict = field(default_factory=dict)
    controls: list[dict] = field(default_factory=list)
    year_stability: dict = field(default_factory=dict)
    stock_dependency: dict = field(default_factory=dict)
    overlap: dict = field(default_factory=dict)
    non_overlapping: dict = field(default_factory=dict)
    gate: OOSGateResult | None = None
    warnings: list[str] = field(default_factory=list)
    data_is_real: bool = True

    def to_dict(self) -> dict:
        return {
            "hypothesis_id": self.hypothesis_id,
            "object_id": self.object_id,
            "birth_model": self.birth_model,
            "direction_source": self.direction_source,
            "partitioned": self.partitioned,
            "calibration_audit": self.calibration_audit,
            "controls": self.controls,
            "year_stability": self.year_stability,
            "stock_dependency": {
                k: v for k, v in self.stock_dependency.items()
                if k != "stock_contribution_distribution"
            },
            "overlap": self.overlap,
            "non_overlapping": self.non_overlapping,
            "gate": None if self.gate is None else self.gate.to_dict(),
            "warnings": self.warnings,
            "data_is_real": self.data_is_real,
        }


def _mean_or_none(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric(frame, column)
    return None if len(values) == 0 else round(float(values.mean()), 6)


def _rate_or_none(frame: pd.DataFrame, column: str) -> float | None:
    values = _numeric(frame, column)
    return None if len(values) == 0 else round(float((values > 0).mean()), 6)


def overlap_block(frame: pd.DataFrame, horizon: int) -> dict:
    """重叠比例 + 全样本 / 非重叠子样本的对照。"""
    subset = diag.non_overlapping_subset(frame, horizon)
    return {
        "horizon": horizon,
        "overlap_ratio": diag.overlap_ratio(frame, horizon),
        "all_events": {
            "event_count": int(len(frame)),
            "mean_excess_return": _mean_or_none(frame, f"excess_return_{horizon}d"),
            "up_rate": _rate_or_none(frame, f"ret_{horizon}d"),
        },
        "non_overlapping_events": {
            "event_count": int(len(subset)),
            "mean_excess_return": _mean_or_none(subset, f"excess_return_{horizon}d"),
            "up_rate": _rate_or_none(subset, f"ret_{horizon}d"),
        },
    }


def run_hypothesis(
    *,
    calibrated_panel: pd.DataFrame,
    labels: pd.DataFrame,
    split: ResearchSplit,
    spec: HypothesisSpec,
    birth_model: str,
    calibration_audit: dict,
    shifted_panels: dict[str, pd.DataFrame] | None = None,
    data_is_real: bool = True,
    data_problems: list[str] | None = None,
    permutation_draws: int = PERMUTATION_DRAWS,
    include_extra_controls: bool = True,
) -> HypothesisOutcome:
    """执行一个假设 × 一个出生模型的固定 holdout 研究。"""
    horizon = spec.primary_horizon
    outcome = HypothesisOutcome(
        hypothesis_id=spec.hypothesis_id,
        object_id=spec.object_id,
        birth_model=birth_model,
        direction_source=spec.direction_source,
        calibration_audit=dict(calibration_audit),
        data_is_real=data_is_real,
    )
    if birth_model.startswith("ipo_approx"):
        outcome.warnings.append(IPO_APPROXIMATION_WARNING)

    mask = direction_matrix(
        calibrated_panel, spec, birth_model=birth_model, source=spec.direction_source
    )
    events = event_frame(mask, labels)
    if not events.empty:
        events = events.copy()
        events["partition"] = [split.partition_of(v) for v in events["as_of"]]

    frames: dict[str, pd.DataFrame] = {
        partition: events[events["partition"] == partition].copy()
        for partition in (TRAIN, VALIDATION, OOS)
    }
    for partition, frame in frames.items():
        outcome.partitioned[partition] = partition_stats(
            frame, partition, spec.horizons, horizon
        )

    oos_frame = frames[OOS]
    pool = pd.DataFrame()
    if not mask.empty:
        pool = mask[["stock_code", "as_of"]].merge(labels, on=["stock_code", "as_of"], how="inner")
        pool = pool.copy()
        pool["partition"] = [split.partition_of(v) for v in pool["as_of"]]
    oos_pool = pool[pool["partition"] == OOS].copy() if not pool.empty else pool

    # 资格分母（eligible）：该分区内"有标签的可用 (股票, as_of)"数量。
    # 正向率 = 事件数 / 资格数；缺了分母就无法回答 GOAL §19 Q1（raw 是否仍近乎恒正）。
    for partition in (TRAIN, VALIDATION, OOS):
        pool_count = (
            int((pool["partition"] == partition).sum()) if not pool.empty else 0
        )
        event_count = outcome.partitioned[partition]["event_count"]
        outcome.partitioned[partition]["pool_count"] = pool_count
        outcome.partitioned[partition]["positive_rate"] = (
            None if pool_count == 0 else round(event_count / pool_count, 6)
        )
        partition_pool = pool[pool["partition"] == partition] if not pool.empty else pool
        outcome.partitioned[partition]["hit_concentration"] = diag.hit_concentration(
            frames[partition], partition_pool
        )

    controls: list[ControlOutcome] = [
        random_event_position_control(
            oos_frame, oos_pool, horizon=horizon,
            seed=_seed_for(spec.hypothesis_id, birth_model, "random_position"),
            draws=permutation_draws,
        )
    ]
    if include_extra_controls:
        controls.append(random_birth_assignment_control(
            calibrated_panel, spec, birth_model=birth_model,
            source=spec.direction_source, labels=labels, partitions=(OOS,),
            horizon=horizon, real_events=oos_frame,
            seed=_seed_for(spec.hypothesis_id, birth_model, "birth_assignment"),
            draws=permutation_draws,
        ))
        controls.append(random_direction_control(
            calibrated_panel, spec, birth_model=birth_model,
            source=spec.direction_source, labels=labels, partitions=(OOS,),
            horizon=horizon, real_events=oos_frame,
            seed=_seed_for(spec.hypothesis_id, birth_model, "random_direction"),
            draws=permutation_draws,
        ))
    if shifted_panels:
        for days in SHIFT_DAYS:
            kind = CONTROL_SHIFT_MINUS_7 if days < 0 else CONTROL_SHIFT_PLUS_7
            shifted_panel = shifted_panels.get(str(days))
            if shifted_panel is None:
                continue
            shifted_mask = direction_matrix(
                shifted_panel, spec, birth_model=birth_model,
                source=spec.direction_source,
            )
            shifted_events = event_frame(shifted_mask, labels)
            if not shifted_events.empty:
                shifted_events = shifted_events.copy()
                shifted_events["partition"] = [
                    split.partition_of(v) for v in shifted_events["as_of"]
                ]
                shifted_events = shifted_events[shifted_events["partition"] == OOS]
            controls.append(shifted_birth_control(
                shifted_events, kind=kind, days=days, real_events=oos_frame, horizon=horizon,
            ))
    outcome.controls = [c.to_dict() for c in controls]

    outcome.year_stability = diag.year_stability(oos_frame, horizon)
    outcome.stock_dependency = diag.stock_dependency(oos_frame, horizon)
    outcome.overlap = overlap_block(oos_frame, horizon)
    outcome.non_overlapping = outcome.overlap["non_overlapping_events"]

    oos_stats = dict(outcome.partitioned[OOS])
    oos_stats["cohen_d"] = diag.cohens_d(
        _numeric(oos_frame, f"excess_return_{horizon}d"),
        _numeric(oos_pool, f"excess_return_{horizon}d"),
    )
    if spec.expected_direction == "exploratory":
        # 探索性对象（冲突组合）没有单向预注册，不套用单向 gate：
        # 结果以双侧描述统计给出，状态记为 EXPLORATORY_NOT_GATED。
        outcome.gate = None
        outcome.warnings.append(
            "EXPLORATORY_NOT_GATED：该对象在预注册中为探索性（无方向性预测），"
            "因此不套用 OOS 单向状态门；请阅读双侧 p 值与效应量，不得据此解锁候选状态。"
        )
    else:
        outcome.gate = evaluate_oos_gate(
            split=split,
            hypothesis_id=f"{spec.hypothesis_id}::{birth_model}",
            oos_stats=oos_stats,
            validation_stats=outcome.partitioned[VALIDATION],
            controls=outcome.controls,
            year_stability=outcome.year_stability,
            stock_dependency=outcome.stock_dependency,
            calibration_audit=calibration_audit,
            data_is_real=data_is_real,
            data_problems=data_problems or [],
            primary_horizon=horizon,
        )
    return outcome


__all__ = [
    "CONTROL_RANDOM_BIRTH_ASSIGNMENT",
    "CONTROL_RANDOM_POSITION",
    "CONTROL_SHIFT_MINUS_7",
    "CONTROL_SHIFT_PLUS_7",
    "IPO_APPROXIMATION_WARNING",
    "PERMUTATION_DRAWS",
    "PanelError",
    "REQUIRED_PANEL_COLUMNS",
    "SHIFT_DAYS",
    "ControlOutcome",
    "HypothesisOutcome",
    "assert_no_out_of_scope",
    "attach_calibration",
    "build_observation_panel",
    "direction_matrix",
    "direction_wide",
    "event_frame",
    "gate_thresholds",
    "horizon_stats",
    "overlap_block",
    "partition_stats",
    "random_birth_assignment_control",
    "random_direction_control",
    "random_event_position_control",
    "run_hypothesis",
    "shifted_birth_control",
]
