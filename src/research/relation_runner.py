"""关系因子历史研究运行器（bazi-relation-v3）。

通过既有 ResearchPipeline / Event Study / Negative Controls 计算，不在 UI 层
重新计算关系，也不把关系类型映射成正负方向。

口径与安全边界：

* 观测与 Date Scan 共用 3×3 矩阵 + 流日行（external_day_row）聚合；
* CalendarSnapshot 按样本日期缓存，每日期只排历一次；
* ``stock_codes`` 为空时必须显式 ``allow_full_universe=True``，否则 422，
  避免一次点击无提示启动全市场十年同步运算；
* p-value 与页面展示的 control 均值/上涨率来自**同一个**对照面板
  （``p_value_control_kind`` 回显），不允许"一种对照算 p、另一种对照显示均值"；
* BH 校正范围是"当前 relation_type 本次运行内的 split × horizon"，
  不宣称跨全部关系类型联合校正（``multiplicity_scope`` 回显）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from src.core.config import settings
from src.core.orchestration.date_relation_scan import _load_profiles, _load_static_natal_cache
from src.core.schemas.market import EventStudyRequest, NegativeControlKind
from src.core.schemas.relation import DateScanRequest
from src.core.schemas.relation_study import (
    RelationStudyHorizon,
    RelationStudyRequest,
    RelationStudyResponse,
    RelationStudySplit,
)
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine
from src.research.event_study.engine import apply_activation, apply_request_filters, extract_event_keys
from src.research.multipletesting.fdr import benjamini_hochberg
from src.research.oos.diagnostics import welch_ttest
from src.research.pipeline import ResearchPipeline, month_starts, new_experiment_id
from src.research.relation_study import build_relation_observations, relation_factor_id, relation_snapshot
from src.research.status import assess_research_status
from src.research.universe.point_in_time import PointInTimeUniverse

#: p-value 使用的对照类型（写死并回显；control 均值/上涨率必须来自同一面板）。
P_VALUE_CONTROL_KIND = NegativeControlKind.RANDOM_BIRTH_DATE

#: BH 校正范围（写进响应与文档，禁止夸大为"全关系联合校正"）。
MULTIPLICITY_SCOPE = "within_relation_split_horizon"


def _kind_key(kind: Any) -> str:
    """对照类型的稳定键（枚举取 value，避免出现 ``NegativeControlKind.X`` 这类字符串）。"""
    return getattr(kind, "value", None) or str(kind)


@dataclass
class RelationStudyRun:
    response: RelationStudyResponse
    real_result: Any
    control_report: Any
    observations: pd.DataFrame
    labels: pd.DataFrame
    warnings: list[Any]
    data_source: dict[str, Any]


def _return_values(observations: pd.DataFrame, labels: pd.DataFrame, request: EventStudyRequest, horizon: int) -> list[float]:
    filtered = apply_activation(apply_request_filters(observations, request), request.activation)
    if filtered.empty:
        return []
    keys = extract_event_keys(observations, request)
    if not keys:
        return []
    # 键集合在循环外构建一次：原实现每行标签都重建集合，是 O(n·m) 的主要来源。
    key_set = {(str(code), pd.to_datetime(day).strftime("%Y-%m-%d")) for code, day in keys}
    label_frame = labels.copy()
    label_frame["trade_date"] = pd.to_datetime(label_frame["trade_date"]).dt.strftime("%Y-%m-%d")
    label_frame["stock_code"] = label_frame["stock_code"].astype(str)
    col = f"ret_{horizon}d"
    if col not in label_frame.columns:
        return []
    values = []
    for row in label_frame.itertuples():
        if (str(row.stock_code), row.trade_date) in key_set:
            value = getattr(row, col, None)
            if value is not None and pd.notna(value):
                values.append(float(value))
    return values


def _up_rate(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value > 0) / len(values)


def _split_ranges(start: date, end: date) -> list[tuple[str, date, date]]:
    ranges = [
        ("TRAIN", start, min(end, date(2018, 12, 31))),
        ("VALIDATION", max(start, date(2019, 1, 1)), min(end, date(2022, 12, 31))),
        ("OOS", max(start, date(2023, 1, 1)), end),
    ]
    return [(name, left, right) for name, left, right in ranges if left <= right]


def run_relation_study(db, market, payload: RelationStudyRequest) -> RelationStudyRun:
    if not payload.stock_codes and not payload.allow_full_universe:
        raise ValueError(
            "未指定 stock_codes 时不会自动跑全市场。请显式设置 allow_full_universe=true "
            "确认在指定区间上运行全市场关系研究（全市场 × 样本日期 × 4 个面板是重同步任务）。"
        )
    factor_id = relation_factor_id(payload.relation_type)
    date_from = payload.date_from or date.fromisoformat(settings.market_history_start)
    date_to = payload.date_to or date.today()
    if date_from > date_to:
        raise ValueError("date_from 不能晚于 date_to")
    sample_dates = month_starts(date_from, date_to, step_months=payload.sample_step_months)
    if not sample_dates:
        raise ValueError("关系研究采样日期为空")

    scan_request = DateScanRequest(
        date=date_to,
        universe=payload.universe,
        birth_basis=settings.canonical_birth_basis,
        birth_profile_version=settings.canonical_birth_profile_version,
        relation_rule_version=settings.relation_rule_version,
    )
    universe = PointInTimeUniverse.load(db, payload.universe, snapshot_at=date_to)
    full_universe = not payload.stock_codes
    all_codes = list(payload.stock_codes) if payload.stock_codes else [r.stock_code for r in universe.list_all_members()]
    all_codes = sorted(set(all_codes))
    profiles = _load_profiles(db, tuple(all_codes), scan_request)
    static_cache = _load_static_natal_cache()
    bazi = BaziEngine()
    calendar = CalendarEngine()
    pipeline = ResearchPipeline()
    warnings: list[Any] = []
    if full_universe:
        warnings.append(
            f"全市场研究：{len(all_codes)} 只 × {len(sample_dates)} 个样本日期 × "
            f"{1 + (3 if payload.run_negative_controls else 0)} 个面板，为同步重任务。"
        )

    # 同一 as_of 日期对所有股票是同一个日历快照：按日期缓存，避免 stock×date 次排历。
    snapshot_cache: dict[date, Any] = {}

    def snapshot_for(as_of_date: date):
        cached = snapshot_cache.get(as_of_date)
        if cached is None:
            cached = relation_snapshot(calendar, as_of_date)
            snapshot_cache[as_of_date] = cached
        return cached

    series_cache: dict[str, Any] = {}
    series_meta: dict[str, dict[str, Any]] = {}
    benchmark = None
    try:
        benchmark = market.get_benchmark_bars(settings.benchmark_index_code, date_from, date_to)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"基准指数不可用：{type(exc).__name__}: {exc}")

    def label_builder(code: str, as_of_date: date):
        if code not in series_cache:
            series_cache[code] = market.get_daily_bars(code, date_from, date_to)
            series_meta[code] = {
                "is_degraded": bool(getattr(series_cache[code], "is_degraded", False)),
                "source": str(getattr(getattr(series_cache[code], "source_ref", None), "source", "") or ""),
            }
        from src.research.labels.forward_returns import compute_labels
        return compute_labels(
            series_cache[code], as_of_date, benchmark_series=benchmark,
            benchmark_code=settings.benchmark_index_code,
        )

    def birth_provider(code: str, _variant: str | None):
        profile = profiles.get(code)
        if profile is None:
            raise ValueError(f"股票 {code} 缺少 canonical 出生档案")
        return profile

    def factor_builder(code: str, as_of_date: date, profile):
        if not universe.is_member(code, as_of_date):
            return []
        source = str(getattr(getattr(profile, "source", None), "source", ""))
        static = None if source.startswith("negative_control:") else static_cache.get(code)
        return build_relation_observations(
            stock_code=code,
            profile=profile,
            as_of_date=as_of_date,
            relation_type=payload.relation_type,
            bazi=bazi,
            calendar=calendar,
            use_static_natal=static,
            snapshot=snapshot_for(as_of_date),
        )

    observations, labels, panel_warnings = pipeline.build_panel(
        stocks=all_codes,
        sample_dates=sample_dates,
        factor_builder=factor_builder,
        label_builder=label_builder,
        birth_profile_provider=birth_provider,
    )
    warnings.extend(panel_warnings)

    controls: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}
    if payload.run_negative_controls:
        for kind in (
            NegativeControlKind.RANDOM_BIRTH_DATE,
            NegativeControlKind.SHIFT_PLUS_7D,
            NegativeControlKind.SHIFT_MINUS_7D,
        ):
            controls[_kind_key(kind)] = pipeline.build_panel(
                stocks=all_codes,
                sample_dates=sample_dates,
                factor_builder=factor_builder,
                label_builder=label_builder,
                birth_profile_provider=birth_provider,
                birth_transform=ResearchPipeline.make_birth_transform(kind),
                variant=kind.value,
            )[:2]

    data_is_real = not any(meta["is_degraded"] for meta in series_meta.values())
    if benchmark is not None and bool(getattr(benchmark, "is_degraded", False)):
        data_is_real = False
    experiment_id = new_experiment_id("REL")
    horizons = payload.horizons or [1, 5, 20]
    base_request = EventStudyRequest(
        factor_ids=[factor_id], horizons=horizons, activation="nonzero",
        benchmark_code=settings.benchmark_index_code,
    )
    # p-value 与展示的 control 统计必须来自同一个对照面板（写死并回显）。
    p_control_key = _kind_key(P_VALUE_CONTROL_KIND)
    p_control_panel = controls.get(p_control_key)
    splits: list[RelationStudySplit] = []
    p_values: list[float | None] = []
    p_slots: list[tuple[int, int]] = []
    for split_name, split_from, split_to in _split_ranges(date_from, date_to):
        request = base_request.model_copy(update={"date_from": split_from, "date_to": split_to})
        result = pipeline.run_event_study(observations, labels, request)
        control_report = None
        if payload.run_negative_controls:
            control_report = pipeline.run_negative_controls(
                result, control_panels=dict(controls), observations=observations,
                labels=labels, request=request,
            )
        assessment = assess_research_status(result, control_report, data_is_real=data_is_real)
        split_horizons: list[RelationStudyHorizon] = []
        for horizon_stat in result.horizons:
            real_values = _return_values(observations, labels, request, horizon_stat.horizon)
            control_values: list[float] = []
            if p_control_panel is not None:
                control_values = _return_values(
                    p_control_panel[0], p_control_panel[1], request, horizon_stat.horizon,
                )
            _t, p_value = welch_ttest(real_values, control_values)
            p_values.append(p_value)
            p_slots.append((len(splits), len(split_horizons)))
            split_horizons.append(RelationStudyHorizon(
                horizon=horizon_stat.horizon,
                sample_count=horizon_stat.sample_count,
                activation_rate=(result.activation_stats or {}).get(factor_id, {}).get("activation_rate"),
                mean_return=horizon_stat.mean_return,
                median_return=horizon_stat.median_return,
                mean_excess_return=horizon_stat.mean_excess_return,
                up_rate=horizon_stat.up_rate,
                max_drawdown=horizon_stat.max_drawdown,
                p_value=p_value,
                p_value_control_kind=p_control_key if p_control_panel is not None else None,
                control_mean_return=(
                    sum(control_values) / len(control_values) if control_values else None
                ),
                control_up_rate=_up_rate(control_values),
            ))
        split_date_from = result.date_from or split_from
        split_date_to = result.date_to or split_to
        splits.append(RelationStudySplit(
            name=split_name, date_from=split_date_from, date_to=split_date_to,
            event_count=result.event_count,
            observation_count=int(len(observations)),
            sample_count=sum(h.sample_count for h in result.horizons),
            activation_rate=(result.activation_stats or {}).get(factor_id, {}).get("activation_rate"),
            horizons=split_horizons,
            research_status=assessment.status.value,
            research_status_reasons=assessment.reasons,
            negative_controls={_kind_key(r.kind): {"verdict": r.verdict, "jaccard_with_real": r.jaccard_with_real} for r in (control_report.results if control_report else [])},
        ))

    q_values = benjamini_hochberg(p_values, alpha=0.05)
    for (split_index, horizon_index), q_value in zip(p_slots, q_values, strict=True):
        splits[split_index].horizons[horizon_index].q_value = q_value

    data_source = {
        "is_real": data_is_real,
        "provider": getattr(market, "provider_id", ""),
        "degraded_codes": sorted(code for code, meta in series_meta.items() if meta["is_degraded"]),
        "universe_version": payload.universe,
        "universe_digest": universe.at(date_to).digest,
        "stock_scope": "full_universe" if full_universe else "explicit_stock_codes",
        "stock_count": len(all_codes),
        "sample_date_count": len(sample_dates),
    }
    response = RelationStudyResponse(
        experiment_id=experiment_id,
        relation_type=payload.relation_type,
        factor_id=factor_id,
        direction=0,
        universe=payload.universe,
        universe_size=len(all_codes),
        date_from=date_from,
        date_to=date_to,
        horizons=horizons,
        splits=splits,
        data_source=data_source,
        multiplicity_scope=MULTIPLICITY_SCOPE,
        p_value_control_kind=p_control_key if p_control_panel is not None else None,
        methodology=(
            "关系命中次数作为 normalized_value（3×3 矩阵、aggregate_scope=external_day_row，"
            "与择日关系扫描同一口径）；direction 固定为 0；按日期顺序切分 TRAIN / VALIDATION / OOS；"
            "事件研究使用已有未来收益标签，并以随机出生日、±7 天和随机因子作为负对照；"
            f"p-value 为 Welch 正态近似，对照类型固定为 {p_control_key}（页面展示的对照均值/上涨率同源）；"
            f"q-value 仅在当前 relation_type 本次运行的 split × horizon 内做 Benjamini–Hochberg 校正"
            f"（multiplicity_scope={MULTIPLICITY_SCOPE}），不代表跨关系类型联合校正。"
        ),
        warnings=[str(item) for item in warnings[:20]],
        relation_rule_version=settings.relation_rule_version,
        relation_matrix_schema_version=settings.relation_matrix_schema_version,
    )
    full_result = pipeline.run_event_study(observations, labels, base_request)
    full_controls = pipeline.run_negative_controls(
        full_result, control_panels=controls, observations=observations,
        labels=labels, request=base_request,
    ) if payload.run_negative_controls else None
    return RelationStudyRun(response, full_result, full_controls, observations, labels, warnings, data_source)


__all__ = [
    "MULTIPLICITY_SCOPE",
    "P_VALUE_CONTROL_KIND",
    "RelationStudyRun",
    "run_relation_study",
]
