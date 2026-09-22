"""关系因子历史研究运行器。

通过既有 ResearchPipeline / Event Study / Negative Controls 计算，不在 UI 层
重新计算关系，也不把关系类型映射成正负方向。
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
from src.research.event_study.engine import apply_activation, apply_request_filters, extract_event_keys
from src.research.multipletesting.fdr import benjamini_hochberg
from src.research.oos.diagnostics import welch_ttest
from src.research.pipeline import ResearchPipeline, month_starts, new_experiment_id
from src.research.relation_study import build_relation_observations, relation_factor_id
from src.research.status import assess_research_status
from src.research.universe.point_in_time import PointInTimeUniverse


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
    label_frame = labels.copy()
    label_frame["trade_date"] = pd.to_datetime(label_frame["trade_date"]).dt.strftime("%Y-%m-%d")
    label_frame["stock_code"] = label_frame["stock_code"].astype(str)
    col = f"ret_{horizon}d"
    if col not in label_frame.columns:
        return []
    values = []
    for row in label_frame.itertuples():
        key = (str(row.stock_code), row.trade_date)
        if key in {(str(code), pd.to_datetime(day).strftime("%Y-%m-%d")) for code, day in keys}:
            value = getattr(row, col, None)
            if value is not None and pd.notna(value):
                values.append(float(value))
    return values


def _split_ranges(start: date, end: date) -> list[tuple[str, date, date]]:
    ranges = [
        ("TRAIN", start, min(end, date(2018, 12, 31))),
        ("VALIDATION", max(start, date(2019, 1, 1)), min(end, date(2022, 12, 31))),
        ("OOS", max(start, date(2023, 1, 1)), end),
    ]
    return [(name, left, right) for name, left, right in ranges if left <= right]


def run_relation_study(db, market, payload: RelationStudyRequest) -> RelationStudyRun:
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
    all_codes = list(payload.stock_codes) if payload.stock_codes else [r.stock_code for r in universe.list_all_members()]
    all_codes = sorted(set(all_codes))
    profiles = _load_profiles(db, tuple(all_codes), scan_request)
    static_cache = _load_static_natal_cache()
    bazi = __import__("src.engines.bazi.bazi_engine", fromlist=["BaziEngine"]).BaziEngine()
    calendar = __import__("src.engines.calendar.calendar_engine", fromlist=["CalendarEngine"]).CalendarEngine()
    pipeline = ResearchPipeline()
    warnings: list[Any] = []

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
            controls[str(kind)] = pipeline.build_panel(
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
    splits: list[RelationStudySplit] = []
    p_values: list[float | None] = []
    p_slots: list[tuple[int, int]] = []
    for split_name, split_from, split_to in _split_ranges(date_from, date_to):
        request = base_request.model_copy(update={"date_from": split_from, "date_to": split_to})
        result = pipeline.run_event_study(observations, labels, request)
        control_report = None
        if payload.run_negative_controls:
            split_controls = {
                key: (obs, ctrl_labels)
                for key, (obs, ctrl_labels) in controls.items()
            }
            control_report = pipeline.run_negative_controls(
                result, control_panels=split_controls, observations=observations,
                labels=labels, request=request,
            )
        assessment = assess_research_status(result, control_report, data_is_real=data_is_real)
        control_by_horizon: dict[int, Any] = {}
        if control_report:
            for control in control_report.results:
                if str(control.kind).endswith("RANDOM_FACTOR"):
                    control_by_horizon = {h.horizon: h for h in control.horizon_stats}
                    break
        split_horizons: list[RelationStudyHorizon] = []
        for horizon_stat in result.horizons:
            real_values = _return_values(observations, labels, request, horizon_stat.horizon)
            control_values = []
            if controls:
                random_obs, random_labels = next(iter(controls.values()))
                control_values = _return_values(random_obs, random_labels, request, horizon_stat.horizon)
            _t, p_value = welch_ttest(real_values, control_values)
            p_values.append(p_value)
            p_slots.append((len(splits), len(split_horizons)))
            control_stat = control_by_horizon.get(horizon_stat.horizon)
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
                control_mean_return=getattr(control_stat, "mean_return", None),
                control_up_rate=getattr(control_stat, "up_rate", None),
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
            negative_controls={str(r.kind): {"verdict": r.verdict, "jaccard_with_real": r.jaccard_with_real} for r in (control_report.results if control_report else [])},
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
        methodology=(
            "关系命中次数作为 normalized_value；direction 固定为 0；"
            "按日期顺序切分 TRAIN / VALIDATION / OOS；事件研究使用已有未来收益标签，"
            "并以随机出生日、±7 天和随机因子作为负对照；p-value 为 Welch 正态近似，"
            "q-value 为全关系研究结果的 Benjamini–Hochberg 校正。"
        ),
        warnings=[str(item) for item in warnings[:20]],
    )
    full_result = pipeline.run_event_study(observations, labels, base_request)
    full_controls = pipeline.run_negative_controls(
        full_result, control_panels=controls, observations=observations,
        labels=labels, request=base_request,
    ) if payload.run_negative_controls else None
    return RelationStudyRun(response, full_result, full_controls, observations, labels, warnings, data_source)


__all__ = ["RelationStudyRun", "run_relation_study"]
