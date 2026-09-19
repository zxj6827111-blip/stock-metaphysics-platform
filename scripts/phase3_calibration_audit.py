"""Phase 3C Factor / Opinion distribution audit and TRAIN-only calibration.

The script never writes research tables. It can either create a raw-cache shard for a
PIT-universe slice or merge raw-cache shards and publish the 3C reports.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pickle
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.core.orchestration.analysis_service import AnalysisService  # noqa: E402
from src.core.schemas.common import EngineId, VariantMode  # noqa: E402
from src.db.base import get_session_factory  # noqa: E402
from src.db.models import StockBirthProfileRow, UniverseMembershipRow  # noqa: E402
from src.engines.base import EngineContext  # noqa: E402
from src.engines.bazi.bazi_engine import BaziEngine  # noqa: E402
from src.engines.huangli.huangli_engine import HuangliEngine  # noqa: E402
from src.engines.ziwei.ziwei_engine import ZiweiEngine, ZiweiUnavailableError  # noqa: E402
from src.factors.registry.compute import compute_factor_set  # noqa: E402
from src.research.calibration import CALIBRATION_VERSION, ResearchCalibrationLayer  # noqa: E402

UNIVERSE_VERSION = "v2-phase3a"
MARKET_DATA_VERSION = "phase3a_astockdata_cutoff_20260814"
CUTOFF_DATE = date(2026, 8, 14)
TRAIN_START = date(2010, 1, 1)
TRAIN_END = date(2018, 12, 31)
VALIDATION_START = date(2019, 1, 1)
VALIDATION_END = date(2022, 12, 31)
OOS_START = date(2023, 1, 1)
MODEL_VERSIONS = {
    "listing_open_v1": "v1-phase3b-listing_open",
    "listing_close_v1": "v1-phase3b-listing_close",
    "ipo_approx_v1": "v1-phase3b-ipo_approx",
}
OUT_FACTOR_CSV = ROOT / "data" / "phase3_universe" / "phase3c_factor_distribution.csv"
OUT_OPINION_CSV = ROOT / "data" / "phase3_universe" / "phase3c_opinion_distribution.csv"
OUT_BIAS_MD = ROOT / "docs" / "bazi-opinion-bias-analysis.md"
OUT_METHOD_MD = ROOT / "docs" / "factor-calibration-methodology.md"
OUT_META = ROOT / "data" / "phase3_universe" / "phase3c_calibration_metadata.json"

PHASES = (
    (date(2010, 1, 1), date(2014, 12, 31), "2010_2014"),
    (date(2015, 1, 1), date(2019, 12, 31), "2015_2019"),
    (date(2020, 1, 1), date(2021, 12, 31), "2020_2021"),
    (date(2022, 1, 1), CUTOFF_DATE, "2022_2026"),
)


@dataclass(frozen=True)
class Profile:
    stock_code: str
    list_date: date
    model: str
    birth_datetime: datetime


@dataclass
class MetricAccumulator:
    total: int = 0
    available: int = 0
    null_count: int = 0
    values: list[float] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    raw_directions: Counter = field(default_factory=Counter)
    calibrated_directions: Counter = field(default_factory=Counter)
    rank_scores: list[float] = field(default_factory=list)
    statuses: Counter = field(default_factory=Counter)

    def add(self, row, *, value_name: str) -> None:  # type: ignore[no-untyped-def]
        self.total += 1
        value = getattr(row, value_name, None)
        if _finite(value):
            self.available += 1
            self.values.append(float(value))
            raw_name = "direction" if value_name == "normalized_value" else "raw_direction"
            self.raw_directions[int(getattr(row, raw_name, 0) or 0)] += 1
        else:
            self.null_count += 1
        score = getattr(row, "rule_score", None)
        if _finite(score):
            self.scores.append(float(score))
        calibrated = getattr(row, "calibrated_direction", None)
        if _finite(calibrated):
            self.calibrated_directions[int(float(calibrated))] += 1
        rank = getattr(row, "rank_score", None)
        if _finite(rank):
            self.rank_scores.append(float(rank))
        self.statuses[str(getattr(row, "calibration_status", "unavailable"))] += 1


def _finite(value: object) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _mean(values: list[float]) -> float | None:
    return round(float(np.mean(values)), 6) if values else None


def _std(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(np.std(values, ddof=1)), 6) if len(values) > 1 else 0.0


def _quantile(values: list[float], q: float) -> float | None:
    return round(float(np.quantile(values, q)), 6) if values else None


def _dominant_share(values: list[float]) -> float | None:
    if not values:
        return None
    counts = Counter(round(v, 10) for v in values)
    return round(max(counts.values()) / len(values), 6)


def _entropy(values: Counter) -> float | None:
    total = sum(values.values())
    if not total:
        return None
    return round(-sum((n / total) * math.log2(n / total) for n in values.values() if n), 6)


def partition_for(value: date) -> str:
    if TRAIN_START <= value <= TRAIN_END:
        return "TRAIN"
    if VALIDATION_START <= value <= VALIDATION_END:
        return "VALIDATION"
    if OOS_START <= value <= CUTOFF_DATE:
        return "OOS"
    return "OUT_OF_SCOPE"


def phase_for(value: date) -> str:
    for start, end, name in PHASES:
        if start <= value <= end:
            return name
    return "OUT_OF_SCOPE"


def sample_dates(date_from: date, date_to: date, step_months: int) -> list[date]:
    if not 1 <= step_months <= 12:
        raise ValueError("step_months 必须在 1..12")
    cur = date(date_from.year, date_from.month, 1)
    out: list[date] = []
    while cur <= date_to:
        if TRAIN_START <= cur <= CUTOFF_DATE:
            out.append(cur)
        month_index = cur.month - 1 + step_months
        cur = date(cur.year + month_index // 12, month_index % 12 + 1, 1)
    if TRAIN_START <= date_to <= CUTOFF_DATE:
        out.append(date_to)
    return sorted(set(out))


def load_profiles(limit: int = 0, offset: int = 0) -> tuple[list[str], dict[tuple[str, str], Profile]]:
    factory = get_session_factory()
    with factory() as db:
        members = db.execute(
            select(UniverseMembershipRow).where(
                UniverseMembershipRow.universe_version == UNIVERSE_VERSION,
            ).order_by(UniverseMembershipRow.stock_code)
        ).scalars().all()
        members = members[offset:]
        if limit:
            members = members[:limit]
        codes = [row.stock_code for row in members]
        list_dates = {row.stock_code: row.list_date for row in members}
        rows = db.execute(
            select(StockBirthProfileRow).where(
                StockBirthProfileRow.stock_code.in_(codes),
                StockBirthProfileRow.birth_profile_version.in_(list(MODEL_VERSIONS.values())),
            )
        ).scalars().all()
    profiles: dict[tuple[str, str], Profile] = {}
    for row in rows:
        model = next((m for m, v in MODEL_VERSIONS.items() if row.birth_profile_version == v), None)
        if model and row.stock_code in list_dates and row.birth_datetime is not None:
            profiles[(row.stock_code, model)] = Profile(
                row.stock_code, list_dates[row.stock_code], model, row.birth_datetime.replace(tzinfo=None),
            )
    return codes, profiles


class AuditRunner:
    def __init__(self, codes: list[str], profiles: dict[tuple[str, str], Profile], skip_ziwei: bool):
        self.codes = codes
        self.profiles = profiles
        self.bazi = BaziEngine()
        self.huangli = HuangliEngine()
        self.ziwei = None if skip_ziwei else ZiweiEngine()
        self.huangli_cache: dict[date, object] = {}
        self.failures: Counter = Counter()
        self.ziwei_unavailable_reason = ""
        if self.ziwei is not None and self.ziwei.availability != "ok":
            self.ziwei_unavailable_reason = self.ziwei.unavailable_reason()

    def _huangli(self, as_of: datetime):
        key = as_of.date()
        if key not in self.huangli_cache:
            self.huangli_cache[key] = self.huangli.snapshot(as_of, days=31)
        return self.huangli_cache[key]

    def compute_date(self, as_of_date: date) -> tuple[list[dict], list[dict]]:
        as_of = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 15, 0, 0)
        partition, phase = partition_for(as_of_date), phase_for(as_of_date)
        work: list[tuple[str, str, Profile, object]] = []
        for code in self.codes:
            for model in MODEL_VERSIONS:
                profile = self.profiles.get((code, model))
                if profile is None or as_of_date < profile.birth_datetime.date():
                    continue
                try:
                    chart = self.bazi.build_chart(
                        birth_datetime=profile.birth_datetime, as_of=as_of,
                        variant_mode=VariantMode.NOT_APPLICABLE, stock_code=code,
                    )
                    work.append((code, model, profile, chart))
                except Exception:  # noqa: BLE001
                    self.failures["bazi"] += 1
        ziwei_by_key: dict[tuple[str, str], object] = {}
        if self.ziwei is not None and self.ziwei.availability == "ok":
            for start in range(0, len(work), 100):
                chunk = work[start:start + 100]
                requests = [{
                    "context": EngineContext(stock_code=code, as_of=as_of),
                    "birth_datetime": profile.birth_datetime, "as_of": as_of,
                    "variant_mode": VariantMode.FORWARD, "stock_code": code,
                } for code, _model, profile, _chart in chunk]
                try:
                    charts = self.ziwei.calculate_charts(requests)
                    for item, chart in zip(chunk, charts, strict=True):
                        ziwei_by_key[(item[0], item[1])] = chart
                except ZiweiUnavailableError as exc:
                    self.failures["ziwei_batch"] += 1
                    self.ziwei_unavailable_reason = str(exc)
                    for code, model, profile, _chart in chunk:
                        try:
                            ziwei_by_key[(code, model)] = self.ziwei.calculate_chart(
                                EngineContext(stock_code=code, as_of=as_of),
                                birth_datetime=profile.birth_datetime, as_of=as_of,
                                variant_mode=VariantMode.FORWARD,
                            )
                        except ZiweiUnavailableError as item_exc:
                            self.failures["ziwei"] += 1
                            self.ziwei_unavailable_reason = str(item_exc)
        factors: list[dict] = []
        opinions: list[dict] = []
        for code, model, _profile, chart in work:
            try:
                fset = compute_factor_set(
                    chart, self._huangli(as_of), as_of, stock_code=code,
                    ziwei_chart=ziwei_by_key.get((code, model)),
                )
            except Exception:  # noqa: BLE001
                self.failures["factor"] += 1
                continue
            for obs in fset.observations:
                factors.append({
                    "engine": _enum_value(obs.engine), "category": _enum_value(obs.category),
                    "factor_id": obs.factor_id, "stock_code": code, "birth_model": model,
                    "as_of": as_of_date, "year": as_of_date.year, "market_phase": phase,
                    "partition": partition, "normalized_value": obs.normalized_value,
                    "direction": int(obs.direction), "rule_score": obs.rule_score,
                    "availability": _enum_value(obs.availability),
                })
            opinions_map = {
                "bazi": AnalysisService.build_opinion(EngineId.BAZI, fset, self.bazi.engine_version),
                "huangli": AnalysisService.build_opinion(EngineId.HUANGLI, fset, self.huangli.engine_version),
            }
            if self.ziwei is not None:
                opinions_map["ziwei"] = AnalysisService.build_opinion(
                    EngineId.ZIWEI, fset, self.ziwei.engine_version,
                    unavailable_reason=self.ziwei_unavailable_reason or "紫微本次未产出可用因子",
                )
            for engine, opinion in opinions_map.items():
                opinions.append({
                    "engine": engine, "stock_code": code, "birth_model": model,
                    "as_of": as_of_date, "year": as_of_date.year, "market_phase": phase,
                    "partition": partition, "opinion_score": opinion.score,
                    "raw_direction": int(opinion.direction), "confidence": opinion.confidence,
                    "availability": _enum_value(opinion.availability),
                    "engine_version": opinion.engine_version,
                })
        return factors, opinions


def _fit_layers(factors: list[dict], opinions: list[dict]):
    ff = pd.DataFrame([r for r in factors if r["partition"] == "TRAIN"])
    of = pd.DataFrame([r for r in opinions if r["partition"] == "TRAIN"])
    if ff.empty or of.empty:
        raise RuntimeError("TRAIN 没有可用 Factor/Opinion 原始值，不能拟合 Calibration")
    ff = ff[ff["availability"] == "ok"].dropna(subset=["normalized_value"])
    of = of[of["availability"] == "ok"].dropna(subset=["opinion_score"])
    return (
        ResearchCalibrationLayer("normalized_value", ("engine", "birth_model", "factor_id"), fit_max_as_of=TRAIN_END).fit(ff),
        ResearchCalibrationLayer("opinion_score", ("engine", "birth_model"), fit_max_as_of=TRAIN_END).fit(of),
    )


def _apply_factor(frame: pd.DataFrame, layer: ResearchCalibrationLayer) -> pd.DataFrame:
    out = layer.transform(frame)
    for column in ("normalized_value", "direction", "rule_score"):
        if not frame[column].equals(out[column]):
            raise AssertionError(f"Calibration 修改了原始因子字段: {column}")
    return out


def _apply_opinion(frame: pd.DataFrame, layer: ResearchCalibrationLayer) -> pd.DataFrame:
    out = layer.transform(frame)
    for column in ("opinion_score", "raw_direction"):
        if not frame[column].equals(out[column]):
            raise AssertionError(f"Calibration 修改了原始 Opinion 字段: {column}")
    return out


def _factor_row(key: tuple, acc: MetricAccumulator) -> dict:
    engine, model, fid, partition, year, phase = key
    values = acc.values
    unique = len(set(round(v, 10) for v in values))
    activation = sum(v != 0 for v in values) / len(values) if values else None
    flags: list[str] = []
    if not values:
        flags.append("ALL_NULL_FACTOR")
    elif unique <= 1:
        flags += ["CONSTANT_FACTOR", "LOW_DISCRIMINATION_FACTOR"]
    elif (_dominant_share(values) or 0) >= 0.995:
        flags.append("NEAR_CONSTANT_FACTOR")
    if activation is not None and activation > 0.95:
        flags.append("LOW_DISCRIMINATION_FACTOR(>95%)")
    if activation is not None and activation < 0.005 and len(values) >= 100:
        flags.append("LOW_DISCRIMINATION_FACTOR(<0.5%)")
    return {
        "engine": engine, "birth_model": model, "factor_id": fid, "partition": partition,
        "year": year, "market_phase": phase, "sample_count": acc.total,
        "available_count": acc.available, "null_count": acc.null_count,
        "null_rate": round(acc.null_count / acc.total, 6) if acc.total else None,
        "activation_rate": round(activation, 6) if activation is not None else None,
        "raw_direction_positive": acc.raw_directions.get(1, 0),
        "raw_direction_neutral": acc.raw_directions.get(0, 0),
        "raw_direction_negative": acc.raw_directions.get(-1, 0),
        "mean_normalized": _mean(values), "std_normalized": _std(values),
        "p25_normalized": _quantile(values, .25), "p50_normalized": _quantile(values, .5),
        "p75_normalized": _quantile(values, .75), "p95_normalized": _quantile(values, .95),
        "mean_rule_score": _mean(acc.scores), "std_rule_score": _std(acc.scores),
        "unique_value_count": unique, "dominant_share": _dominant_share(values),
        "calibrated_positive": acc.calibrated_directions.get(1, 0),
        "calibrated_neutral": acc.calibrated_directions.get(0, 0),
        "calibrated_negative": acc.calibrated_directions.get(-1, 0),
        "mean_rank_score": _mean(acc.rank_scores),
        "calibration_status": json.dumps(dict(acc.statuses), ensure_ascii=False, sort_keys=True),
        "flags": ";".join(flags),
    }


def _opinion_row(key: tuple, acc: MetricAccumulator) -> dict:
    engine, model, partition, year, phase = key
    values = acc.values
    return {
        "engine": engine, "birth_model": model, "partition": partition, "year": year,
        "market_phase": phase, "sample_count": acc.total, "available_count": acc.available,
        "unavailable_count": acc.null_count,
        "availability_rate": round(acc.available / acc.total, 6) if acc.total else None,
        "raw_direction_positive": acc.raw_directions.get(1, 0),
        "raw_direction_neutral": acc.raw_directions.get(0, 0),
        "raw_direction_negative": acc.raw_directions.get(-1, 0),
        "mean_opinion_score": _mean(values), "std_opinion_score": _std(values),
        "min_opinion_score": min(values) if values else None,
        "max_opinion_score": max(values) if values else None,
        "p25_opinion_score": _quantile(values, .25), "p50_opinion_score": _quantile(values, .5),
        "p75_opinion_score": _quantile(values, .75), "p95_opinion_score": _quantile(values, .95),
        "calibrated_positive": acc.calibrated_directions.get(1, 0),
        "calibrated_neutral": acc.calibrated_directions.get(0, 0),
        "calibrated_negative": acc.calibrated_directions.get(-1, 0),
        "calibrated_direction_entropy_bits": _entropy(acc.calibrated_directions),
        "mean_rank_score": _mean(acc.rank_scores),
        "calibration_status": json.dumps(dict(acc.statuses), ensure_ascii=False, sort_keys=True),
    }


def _write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        if not rows:
            return
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _write_docs(meta: dict, factor_rows: list[dict], opinion_rows: list[dict], bias_rows: list[dict], fl, ol, failures: dict):
    _write_methodology(meta)
    lines = [
        "# Phase 3C · BAZI_POS 偏置诊断与 Factor / Opinion 分布审计", "",
        f"> 生成时间：{meta['generated_at']}",
        f"> Universe：`{UNIVERSE_VERSION}`（{meta['universe_size']} 只）",
        f"> 采样：{meta['sample_dates']} 个日历点，{meta['date_from']}..{meta['date_to']}，步长 {meta['step_months']} 个月",
        f"> Calibration：`{CALIBRATION_VERSION}`；fit 仅使用 TRAIN `{TRAIN_START}..{TRAIN_END}`", "",
        "## 结论先行", "",
        "- `BAZI_POS` 正向率是八字 Opinion 的方向分布，不是上涨概率、预期收益率或有效性证据。",
        "- 原始 Opinion score/direction 和 Factor 原值未被修改；Calibration 只追加研究派生列。",
        "- Validation/OOS 只使用全体 TRAIN 冻结的 P25/P75 阈值；正式 OOS Pipeline 留到 Phase 3D。",
        "- 行业切片状态：`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`；Phase 3E 尚未提供 PIT 行业。", "",
        "## BAZI_POS 总体诊断", "",
        "| birth model | n | raw +1 | raw 0 | raw -1 | raw +1 rate | cal +1 | cal 0 | cal -1 | cal +1 rate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model in MODEL_VERSIONS:
        rows = [r for r in bias_rows if r["birth_model"] == model]
        n = sum(r["available_count"] for r in rows)
        raw = {k: sum(r[k] for r in rows) for k in ("raw_positive", "raw_neutral", "raw_negative")}
        cal = {k: sum(r[k] for r in rows) for k in ("calibrated_positive", "calibrated_neutral", "calibrated_negative")}
        lines.append(
            f"| `{model}` | {n} | {raw['raw_positive']} | {raw['raw_neutral']} | {raw['raw_negative']} | "
            f"{raw['raw_positive'] / n:.1%} | {cal['calibrated_positive']} | {cal['calibrated_neutral']} | "
            f"{cal['calibrated_negative']} | {cal['calibrated_positive'] / max(sum(cal.values()), 1):.1%} |"
        )
    lines += [
        "", "## 时间切片与完整审计", "",
        "运行时方向阈值仍为 score >= 58 / <= 42；完整 year/market_phase/partition 统计在 `phase3c_opinion_distribution.csv`。",
        f"Factor 摘要行：**{len(factor_rows)}**；Opinion 摘要行：**{len(opinion_rows)}**。",
        f"单点失败：`{failures or {}}`。",
        "", "## Calibration 审计", "",
        f"Factor fit groups={fl.metadata()['group_count']}，Opinion fit groups={ol.metadata()['group_count']}；fit_max_as_of={TRAIN_END}。",
        "常量 TRAIN 参考分布显式返回 unavailable/null，不用 0 冒充。",
        "", "## 研究边界", "",
        "本报告只回答分布偏置与 TRAIN-only 校准纪律，不回答术数是否有效；未读取未来收益标签，也没有用 OOS 调阈值。",
    ]
    OUT_BIAS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_methodology(meta: dict) -> None:
    OUT_METHOD_MD.write_text(f"""# Phase 3C · Factor / Opinion Calibration 方法学

- Calibration version: `{CALIBRATION_VERSION}`；原始 `opinion.score` 不变。
- Universe: `{UNIVERSE_VERSION}`，本次 `{meta['universe_size']}` 只；快照截止 `{CUTOFF_DATE}`。
- TRAIN: `{TRAIN_START}..{TRAIN_END}`；Validation: `{VALIDATION_START}..{VALIDATION_END}`；OOS: `{OOS_START}..{CUTOFF_DATE}`。
- 分区和 market phase 只由日历确定，不使用未来收益/benchmark。
- fit 只接受全体 TRAIN 原始 Factor/Opinion，冻结均值、标准差、经验分布和 P25/P75；Validation/OOS 只能 transform。
- `research_percentile`/`historical_percentile` 使用 TRAIN 参考分布；`cross_sectional_percentile` 只描述当前横截面；`z_score` 在常量参考分布时为 null；`rank_score` 是 0-100 研究刻度，不是收益概率。
- 行业状态：`POINT_IN_TIME_INDUSTRY_UNAVAILABLE`，Phase 3E 前不使用当前行业资料替代 PIT 行业。
- 常量/近常量只报告，不删除；正式 walk-forward 和 OOS gate 留到 Phase 3D。
""", encoding="utf-8")


def _bias_rows(opinion_frame: pd.DataFrame) -> list[dict]:
    if opinion_frame.empty:
        return []
    rows: list[dict] = []
    sub = opinion_frame[opinion_frame["engine"] == "bazi"]
    for key, group in sub.groupby(["birth_model", "partition", "year", "market_phase"], sort=True):
        valid = group[group["opinion_score"].notna()]
        raw = valid["raw_direction"].astype(int)
        cal = group[group["calibrated_direction"].notna()]["calibrated_direction"].astype(int)
        scores = valid["opinion_score"].astype(float).to_numpy()
        rows.append({
            "birth_model": key[0], "partition": key[1], "year": key[2], "market_phase": key[3],
            "available_count": len(valid), "raw_positive": int((raw == 1).sum()),
            "raw_neutral": int((raw == 0).sum()), "raw_negative": int((raw == -1).sum()),
            "raw_positive_rate": float((raw == 1).mean()) if len(raw) else None,
            "score_ge_58_rate": float((scores >= 58).mean()) if len(scores) else None,
            "score_le_42_rate": float((scores <= 42).mean()) if len(scores) else None,
            "score_p25": _quantile(scores.tolist(), .25), "score_p50": _quantile(scores.tolist(), .5),
            "score_p75": _quantile(scores.tolist(), .75), "score_p95": _quantile(scores.tolist(), .95),
            "calibrated_positive": int((cal == 1).sum()), "calibrated_neutral": int((cal == 0).sum()),
            "calibrated_negative": int((cal == -1).sum()),
            "calibrated_positive_rate": float((cal == 1).mean()) if len(cal) else None,
        })
    return rows


def _collect_raw(args: argparse.Namespace) -> int:
    dates = sample_dates(date.fromisoformat(args.date_from), date.fromisoformat(args.date_to), args.step_months)
    codes, profiles = load_profiles(args.limit, args.offset)
    if not codes:
        raise RuntimeError("raw cache 分片没有股票")
    runner = AuditRunner(codes, profiles, skip_ziwei=args.skip_ziwei)
    raw_cache: dict[date, tuple[list[dict], list[dict]]] = {}
    for as_of in dates:
        raw_cache[as_of] = runner.compute_date(as_of)
    payload = {
        "universe_version": UNIVERSE_VERSION,
        "codes": codes,
        "dates": dates,
        "raw_cache": raw_cache,
        "failures": dict(runner.failures),
        "ziwei_unavailable_reason": runner.ziwei_unavailable_reason,
        "meta": {"step_months": args.step_months, "skip_ziwei": args.skip_ziwei},
    }
    with open(args.raw_cache_out, "wb") as fh:
        pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"raw cache: {args.raw_cache_out}", flush=True)
    return 0


def _merge_payloads(paths: list[str]) -> dict:
    payloads = []
    for path in paths:
        with open(path, "rb") as fh:
            payloads.append(pickle.load(fh))
    if not payloads:
        raise ValueError("raw cache 为空")
    base = payloads[0]
    codes: list[str] = []
    raw_cache: dict[date, tuple[list[dict], list[dict]]] = {}
    failures: Counter = Counter()
    for payload in payloads:
        if payload.get("universe_version") != UNIVERSE_VERSION:
            raise ValueError("raw cache universe_version 不一致")
        if payload.get("dates") != base.get("dates"):
            raise ValueError("raw cache sample dates 不一致")
        overlap = set(codes) & set(payload["codes"])
        if overlap:
            raise ValueError(f"raw cache 股票分片重叠: {sorted(overlap)[:5]}")
        codes.extend(payload["codes"])
        failures.update(payload.get("failures", {}))
        for as_of, (factors, opinions) in payload["raw_cache"].items():
            existing = raw_cache.setdefault(as_of, ([], []))
            existing[0].extend(factors)
            existing[1].extend(opinions)
    return {
        "universe_version": UNIVERSE_VERSION, "codes": codes,
        "profiles": {}, "dates": base["dates"], "raw_cache": raw_cache,
        "failures": dict(failures),
        "ziwei_unavailable_reason": "; ".join(p.get("ziwei_unavailable_reason", "") for p in payloads if p.get("ziwei_unavailable_reason")),
        "meta": base.get("meta", {}),
    }


def _run_from_payload(payload: dict, args: argparse.Namespace) -> int:
    codes = payload["codes"]
    dates = payload["dates"]
    raw_cache = payload["raw_cache"]
    all_factors = [row for rows in raw_cache.values() for row in rows[0]]
    all_opinions = [row for rows in raw_cache.values() for row in rows[1]]
    factor_layer, opinion_layer = _fit_layers(all_factors, all_opinions)
    factor_acc: dict[tuple, MetricAccumulator] = defaultdict(MetricAccumulator)
    opinion_acc: dict[tuple, MetricAccumulator] = defaultdict(MetricAccumulator)
    opinion_frames: list[pd.DataFrame] = []
    factor_keys: set[tuple] = set()
    opinion_keys: set[tuple] = set()
    for as_of in dates:
        factors, opinions = raw_cache[as_of]
        if factors:
            ff = _apply_factor(pd.DataFrame(factors), factor_layer)
            for row in ff.itertuples(index=False):
                key = (row.engine, row.birth_model, row.factor_id, row.partition, int(row.year), row.market_phase)
                factor_keys.add(key)
                factor_acc[key].add(row, value_name="normalized_value")
        if opinions:
            of = _apply_opinion(pd.DataFrame(opinions), opinion_layer)
            opinion_frames.append(of[["engine", "birth_model", "as_of", "partition", "year", "market_phase", "opinion_score", "raw_direction", "calibrated_direction", "rank_score"]].copy())
            for row in of.itertuples(index=False):
                key = (row.engine, row.birth_model, row.partition, int(row.year), row.market_phase)
                opinion_keys.add(key)
                opinion_acc[key].add(row, value_name="opinion_score")
    factor_rows = [_factor_row(k, factor_acc[k]) for k in sorted(factor_keys, key=lambda x: tuple(str(v) for v in x))]
    opinion_rows = [_opinion_row(k, opinion_acc[k]) for k in sorted(opinion_keys, key=lambda x: tuple(str(v) for v in x))]
    _write_csv(OUT_FACTOR_CSV, factor_rows)
    _write_csv(OUT_OPINION_CSV, opinion_rows)
    opinion_frame = pd.concat(opinion_frames, ignore_index=True) if opinion_frames else pd.DataFrame()
    meta = {
        "generated_at": datetime.now().isoformat(timespec="seconds"), "universe_size": len(codes),
        "profile_count": len(codes) * 3, "sample_dates": len(dates),
        "date_from": min(dates).isoformat() if dates else None, "date_to": max(dates).isoformat() if dates else None,
        "step_months": payload.get("meta", {}).get("step_months", args.step_months), "cutoff": CUTOFF_DATE.isoformat(),
        "factor_rows": len(factor_rows), "opinion_rows": len(opinion_rows),
        "raw_opinion_observations": len(opinion_frame), "industry_status": "POINT_IN_TIME_INDUSTRY_UNAVAILABLE",
        "market_data_version": MARKET_DATA_VERSION, "bazi_engine_version": settings.bazi_engine_version,
        "factor_rule_version": settings.factor_rule_version, "calibration_version": CALIBRATION_VERSION,
        "ziwei_status": "skipped" if payload.get("meta", {}).get("skip_ziwei") else "attempted",
        "ziwei_unavailable_reason": payload.get("ziwei_unavailable_reason", ""),
        "failures": payload.get("failures", {}),
    }
    bias_rows = _bias_rows(opinion_frame)
    _write_docs(meta, factor_rows, opinion_rows, bias_rows, factor_layer, opinion_layer, payload.get("failures", {}))
    OUT_META.write_text(json.dumps({"audit": meta, "factor_calibration": factor_layer.metadata(), "opinion_calibration": opinion_layer.metadata()}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"factor csv: {OUT_FACTOR_CSV}", flush=True)
    print(f"opinion csv: {OUT_OPINION_CSV}", flush=True)
    print(f"bias report: {OUT_BIAS_MD}", flush=True)
    return 0


def run(args: argparse.Namespace) -> int:
    if args.raw_cache_out:
        return _collect_raw(args)
    if args.raw_cache_input:
        payload = _merge_payloads(args.raw_cache_input.split(";"))
        return _run_from_payload(payload, args)
    dates = sample_dates(date.fromisoformat(args.date_from), date.fromisoformat(args.date_to), args.step_months)
    codes, profiles = load_profiles(args.limit, args.offset)
    runner = AuditRunner(codes, profiles, skip_ziwei=args.skip_ziwei)
    raw_cache: dict[date, tuple[list[dict], list[dict]]] = {}
    for as_of in dates:
        raw_cache[as_of] = runner.compute_date(as_of)
    return _run_from_payload({
        "universe_version": UNIVERSE_VERSION, "codes": codes, "dates": dates,
        "raw_cache": raw_cache, "failures": dict(runner.failures),
        "ziwei_unavailable_reason": runner.ziwei_unavailable_reason,
        "meta": {"step_months": args.step_months, "skip_ziwei": args.skip_ziwei},
    }, args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3C Factor / Opinion 分布审计")
    parser.add_argument("--limit", type=int, default=0, help="审计 N 只股票；与 --offset 组合用于分片")
    parser.add_argument("--offset", type=int, default=0, help="跳过排序后的前 N 只股票，用于分片")
    parser.add_argument("--date-from", default=TRAIN_START.isoformat())
    parser.add_argument("--date-to", default=CUTOFF_DATE.isoformat())
    parser.add_argument("--step-months", type=int, default=12)
    parser.add_argument("--skip-ziwei", action="store_true", help="仅用于诊断；正式 3C 不应使用")
    parser.add_argument("--raw-cache-out", default="", help="只生成原始分片缓存")
    parser.add_argument("--raw-cache-input", default="", help="以分号分隔的 raw cache，合并后统一 fit")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
