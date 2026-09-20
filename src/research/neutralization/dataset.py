"""Phase 3E/3F 共用的研究数据集组装。

为什么要有这一层
----------------
Phase 3D 把"面板 + 校准 + 标签 + 事件掩码"的逻辑写在管线脚本里。3E（中性化）
与 3F（多重检验 / 稳健性）需要**完全相同的**数据集，否则两阶段的数字无法对齐。
本模块把组装过程固化成一个可测试的函数：给定同一份缓存分片，
必然得到同一份研究数据集。

数据流
------
    phase3d_cache/main_*.pkl（观测面板：opinion 级）
      → build_observation_panel（打分区）
      → attach_calibration（cal-v1：只 fit TRAIN，只追加研究列）
      → 展开为"对象宽表"：每个 (股票, as_of, 出生模型) 一行，
                            每个预注册对象一列命中布尔
      → join 未来收益标签（4 个持有期）
      → join 风格暴露 + 板块
      → 最终研究数据集（3E / 3F 的唯一输入）

纪律
----
* 事件定义**只能**来自 ``config/phase3d_hypothesis_registry.yaml``；
  本模块不提供"自定义条件"的入口，避免事后自由搜索组合。
* 校准版本固定为 ``cal-v1``；本模块不接受其它版本号参数。
* 标签与暴露都按 ``(stock_code, as_of)`` 对齐；缺标签的命中保留在表中
  （``hit`` 为 True 但收益为 NaN），以便统计时如实体现"命中但无收益"。
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from src.research.neutralization.exposures import (
    STYLE_EXPOSURE_COLUMNS,
    build_exposure_panel,
    zscore_cross_section,
)
from src.research.neutralization.industry import attach_segment, load_board_map
from src.research.oos.calibration_freeze import CALIBRATION_VERSION
from src.research.oos.registry import HypothesisRegistry, HypothesisSpec
from src.research.oos.runner import (
    PanelError,
    assert_no_out_of_scope,
    attach_calibration,
    build_observation_panel,
)
from src.research.oos.splits import UNIVERSE_VERSION, ResearchSplit, default_split

#: 允许的研究分区
PARTITIONS: tuple[str, ...] = ("TRAIN", "VALIDATION", "OOS")


@dataclass
class ResearchDataset:
    """3E / 3F 的唯一输入容器。"""

    frame: pd.DataFrame
    panel_raw: pd.DataFrame
    calibrated_panel: pd.DataFrame
    labels: pd.DataFrame
    split: ResearchSplit
    registry: HypothesisRegistry
    calibration_audit: dict
    label_meta: dict
    exposure_meta: dict
    object_ids: tuple[str, ...]
    birth_models: tuple[str, ...]
    universe_composition: dict

    def object_frame(self, object_id: str, birth_model: str, partition: str) -> pd.DataFrame:
        """取某对象 × 出生模型 × 分区的横截面（含标签、暴露与命中列）。"""
        if object_id not in self.object_ids:
            raise KeyError(f"未注册对象 {object_id}；已注册：{list(self.object_ids)}")
        hit_col = f"hit__{object_id}"
        sub = self.frame[
            (self.frame["birth_model"] == birth_model)
            & (self.frame["partition"] == partition)
        ]
        out = sub.copy()
        out["hit"] = sub[hit_col].astype(bool)
        return out


# ---------------------------------------------------------------------------
# 从缓存分片读面板
# ---------------------------------------------------------------------------


def discover_shards(cache_dir: Path, label: str) -> list[Path]:
    """发现 ``<label>_shard*.pkl``（按名称排序，保证确定性）。"""
    return sorted(cache_dir.glob(f"{label}_shard[0-9][0-9].pkl"))


def merge_shards(paths: list[Path]) -> dict:
    """合并分片（分片之间股票集合不重叠，合并是纯拼接）。"""
    if not paths:
        raise PanelError(f"没有可用的面板分片：{paths}")
    merged_rows: list[dict] = []
    codes: list[str] = []
    dates: list[str] = []
    failures: dict[str, int] = {}
    skipped_pit: dict[str, int] = {}
    engine_versions: dict = {}
    universe_version = UNIVERSE_VERSION
    birth_shift_days = 0
    for path in paths:
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        merged_rows.extend(payload["rows"])
        codes.extend(payload["codes"])
        dates.extend(payload["dates"])
        for key, value in (payload.get("failures") or {}).items():
            failures[key] = failures.get(key, 0) + int(value)
        for key, value in (payload.get("skipped_pit") or {}).items():
            skipped_pit[key] = skipped_pit.get(key, 0) + int(value)
        if payload.get("engine_versions"):
            engine_versions = payload["engine_versions"]
        assert payload.get("universe_version") == UNIVERSE_VERSION, (
            f"分片 {path.name} 的 universe_version="
            f"{payload.get('universe_version')} != {UNIVERSE_VERSION}"
        )
        universe_version = str(payload["universe_version"])
        birth_shift_days = int(payload.get("birth_shift_days", 0) or 0)
    return {
        "universe_version": universe_version,
        "birth_shift_days": birth_shift_days,
        "rows": merged_rows,
        "codes": sorted(set(codes)),
        "dates": sorted(set(dates)),
        "failures": failures,
        "skipped_pit": skipped_pit,
        "engine_versions": engine_versions,
        "shard_count": len(paths),
    }


# ---------------------------------------------------------------------------
# 对象宽表
# ---------------------------------------------------------------------------


def _hit_series(
    wide: pd.DataFrame,
    spec: HypothesisSpec,
    *,
    missing_out: list[dict] | None = None,
    birth_model: str = "",
) -> pd.Series:
    """按预注册逻辑计算命中布尔。

    缺失引擎的语义与 Phase 3D 完全一致：**一律不命中**（既不当 0，也不当命中）。
    但"整列都不存在"（该出生模型下该引擎没有任何观测）与"个别行缺值"是两件事，
    前者会被记入 ``missing_out``，避免一个坏掉的面板悄悄退化成"0 个事件"。
    """
    prefix = "raw" if spec.direction_source == "raw" else "cal"
    columns = [f"{prefix}_{engine}" for engine in spec.engines]
    missing = [column for column in columns if column not in wide.columns]
    if missing:
        if missing_out is not None:
            for column in missing:
                missing_out.append({
                    "birth_model": birth_model,
                    "object_id": spec.object_id,
                    "missing_direction_column": column,
                })
        wide = wide.assign(**{column: pd.NA for column in missing})
    if spec.logic == "single":
        hit = pd.to_numeric(wide[columns[0]], errors="coerce") > 0
    elif spec.logic == "all_positive":
        hit = pd.Series(True, index=wide.index)
        for column in columns:
            hit &= pd.to_numeric(wide[column], errors="coerce") > 0
    elif spec.logic == "conflict":
        conflict = spec.conflict or {}
        hit = pd.Series(True, index=wide.index)
        for engine in conflict.get("positive", ()):
            hit &= pd.to_numeric(wide[f"{prefix}_{engine}"], errors="coerce") > 0
        for engine in conflict.get("negative", ()):
            hit &= pd.to_numeric(wide[f"{prefix}_{engine}"], errors="coerce") < 0
    else:  # pragma: no cover - 注册表加载时已校验
        raise PanelError(f"未知 logic：{spec.logic}")
    return hit.fillna(False).astype(bool)


def build_object_wide(
    panel: pd.DataFrame,
    registry: HypothesisRegistry,
    *,
    birth_models: tuple[str, ...],
    missing_out: list[dict] | None = None,
) -> pd.DataFrame:
    """把长表面板展开为 ``(股票, as_of, 出生模型) × 对象命中`` 宽表。

    同时保留每个引擎的原始分数与校准分位，供 RankIC 使用（仅单引擎对象）。
    ``missing_out`` 会收集"整列缺失"的 (出生模型, 对象, 方向列)，供报告披露。
    """
    collector: list[dict] = missing_out if missing_out is not None else []
    frames: list[pd.DataFrame] = []
    for birth_model in birth_models:
        sub = panel[panel["birth_model"] == birth_model]
        if sub.empty:
            continue
        raw = sub.pivot_table(
            index=["stock_code", "as_of"], columns="engine",
            values="raw_direction", aggfunc="first",
        )
        cal = sub.pivot_table(
            index=["stock_code", "as_of"], columns="engine",
            values="calibrated_direction", aggfunc="first",
        )
        score = sub.pivot_table(
            index=["stock_code", "as_of"], columns="engine",
            values="opinion_score", aggfunc="first",
        )
        pct = sub.pivot_table(
            index=["stock_code", "as_of"], columns="engine",
            values="research_percentile", aggfunc="first",
        )
        raw.columns = [f"raw_{column}" for column in raw.columns]
        cal.columns = [f"cal_{column}" for column in cal.columns]
        score.columns = [f"score_{column}" for column in score.columns]
        pct.columns = [f"pct_{column}" for column in pct.columns]
        wide = raw.join([cal, score, pct], how="outer")
        wide["birth_model"] = birth_model
        wide = wide.reset_index()
        for spec in registry.hypotheses:
            wide[f"hit__{spec.object_id}"] = _hit_series(
                wide, spec, missing_out=collector, birth_model=str(birth_model),
            ).to_numpy()
        frames.append(wide)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined["as_of"] = pd.to_datetime(combined["as_of"]).dt.date
    return combined


# ---------------------------------------------------------------------------
# 组装
# ---------------------------------------------------------------------------


def build_research_dataset(
    *,
    cache_dir: Path,
    registry: HypothesisRegistry,
    split: ResearchSplit | None = None,
    bars: dict[str, pd.DataFrame] | None = None,
    labels: pd.DataFrame | None = None,
    label_meta: dict | None = None,
    with_exposures: bool = True,
    progress=None,  # type: ignore[no-untyped-def]
) -> ResearchDataset:
    """组装 3E/3F 的研究数据集。

    ``bars`` / ``labels`` 可显式注入（测试与复用场景）；不注入时从 canonical DB 读取。
    """
    from src.research.labels import panel as label_panel

    split = split or default_split(calibration_version=CALIBRATION_VERSION)
    shards = discover_shards(cache_dir, "main")
    payload = merge_shards(shards)
    panel_raw = build_observation_panel(payload["rows"], split)
    assert_no_out_of_scope(panel_raw, split)

    registry_models = sorted({
        model for spec in registry.hypotheses for model in spec.birth_models
    })
    available_models = tuple(
        model for model in registry_models
        if model in set(panel_raw["birth_model"].unique())
    )
    if not available_models:
        raise PanelError("面板里没有任何注册表中声明的出生模型")

    from src.research.oos.calibration_freeze import fit_holdout_calibration

    calibration, calibration_audit = fit_holdout_calibration(panel_raw, split)
    calibrated_panel = attach_calibration(panel_raw, calibration)

    if labels is None:
        codes = payload["codes"]
        if progress:
            progress(f"读取行情（{len(codes)} 只）并计算标签 …")
        bars = label_panel.load_bars_by_code(codes)
        sample_dates = sorted({date.fromisoformat(value) for value in payload["dates"]})
        labels, label_meta = label_panel.build_label_panel(bars, sample_dates)
    if label_meta is None:
        label_meta = {}

    if progress:
        progress("展开对象宽表 …")
    wide = build_object_wide(calibrated_panel, registry, birth_models=available_models)
    wide["partition"] = [split.partition_of(value) for value in wide["as_of"]]
    wide = wide[wide["partition"].isin(PARTITIONS)].reset_index(drop=True)

    if progress:
        progress("join 未来收益标签 …")
    label_cols = [
        "stock_code", "as_of",
        *[f"ret_{h}d" for h in split.horizons],
        *[f"bench_ret_{h}d" for h in split.horizons],
        *[f"excess_return_{h}d" for h in split.horizons],
        "label_version",
    ]
    merged = wide.merge(labels[label_cols], on=["stock_code", "as_of"], how="left")

    exposure_meta: dict = {}
    if with_exposures:
        if bars is None:
            bars = label_panel.load_bars_by_code(sorted(merged["stock_code"].unique()))
        if progress:
            progress("计算风格暴露（动量 / 波动 / 规模代理）…")
        as_ofs = sorted(set(merged["as_of"]))
        exposures, exposure_meta = build_exposure_panel(bars, as_ofs)
        merged = merged.merge(
            exposures[[
                "stock_code", "as_of", *STYLE_EXPOSURE_COLUMNS,
            ]],
            on=["stock_code", "as_of"], how="left",
        )
        merged = zscore_cross_section(merged, STYLE_EXPOSURE_COLUMNS)
        board_map = load_board_map(UNIVERSE_VERSION, limit_codes=sorted(merged["stock_code"].unique()))
        merged = attach_segment(merged, board_map)

    from src.research.neutralization.benchmark import attach_market_excess

    merged = attach_market_excess(merged, split.horizons)

    object_ids = tuple(spec.object_id for spec in registry.hypotheses)
    return ResearchDataset(
        frame=merged,
        panel_raw=panel_raw,
        calibrated_panel=calibrated_panel,
        labels=labels,
        split=split,
        registry=registry,
        calibration_audit=calibration_audit,
        label_meta=label_meta,
        exposure_meta=exposure_meta,
        object_ids=object_ids,
        birth_models=available_models,
        universe_composition={},
    )


__all__ = [
    "PARTITIONS",
    "ResearchDataset",
    "build_object_wide",
    "build_research_dataset",
    "discover_shards",
    "merge_shards",
]
