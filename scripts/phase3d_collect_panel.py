"""Phase 3D 观测面板采集器（可并行分片）。

职责
----
对 PIT universe 的每一只股票 × 出生模型 × 采样 as_of，重新排盘（八字/紫微/黄历）
并聚合出三个引擎观点（``opinion_score`` / ``raw_direction``），写成 pickle 分片。
**只落原始观测与元数据**：不做任何收益计算、不做校准、不做统计。

为什么要分片
------------
500 股 × 3 模型 × 1 个 as_of ≈ 1500 次排盘 ≈ 3 分钟（紫微 Node 子进程占 78%）。
季度采样 68 个点单进程要 3.4 小时，因此管线脚本用 ``N`` 个子进程按股票分片并行，
再由主进程合并。分片之间股票集合不重叠，合并是纯拼接。

用法（单分片）::

    python scripts/phase3d_collect_panel.py \\
        --shard-index 0 --shard-count 8 \\
        --date-from 2010-01-01 --date-to 2026-08-14 --step-months 3 \\
        --out data/phase3_universe/phase3d_cache/main_shard00.pkl

出生平移对照::

    ... --birth-shift-days -7 --out .../shift_minus7_shard00.pkl
"""

from __future__ import annotations

import argparse
import pickle
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

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
from src.research.oos.splits import UNIVERSE_VERSION  # noqa: E402

CUTOFF_DATE = date(2026, 8, 14)
#: 出生模型 → stock_birth_profile.birth_profile_version
MODEL_VERSIONS: dict[str, str] = {
    "listing_open_v1": "v1-phase3b-listing_open",
    "listing_close_v1": "v1-phase3b-listing_close",
    "ipo_approx_v1": "v1-phase3b-ipo_approx",
}


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def sample_dates(date_from: date, date_to: date, step_months: int) -> list[date]:
    """生成采样 as_of（每月 1 日，收盘后时刻；与 Phase 3C 口径一致）。"""
    if not 1 <= step_months <= 12:
        raise ValueError("step_months 必须在 1..12")
    out: list[date] = []
    current = date(date_from.year, date_from.month, 1)
    while current <= date_to:
        out.append(current)
        index = current.month - 1 + step_months
        current = date(current.year + index // 12, index % 12 + 1, 1)
    if date_to not in out:
        out.append(date_to)
    return sorted(set(v for v in out if date_from <= v <= date_to))


def load_universe(limit: int = 0, offset: int = 0) -> tuple[list[str], dict[str, tuple[date, date | None]]]:
    """返回 ``(codes, {code: (list_date, delist_date)})``。

    PIT 资格窗口 ``[list_date, delist_date]`` 是**事件能不能存在**的前提：
    退市后的 (股票, as_of) 不是"收益缺失"，而是"当时不可投资"，
    必须从面板中排除 —— 否则负对照的候选池会被不存在的股票-日期对撑大。
    """
    factory = get_session_factory()
    with factory() as db:
        rows = db.execute(
            select(UniverseMembershipRow).where(
                UniverseMembershipRow.universe_version == UNIVERSE_VERSION
            ).order_by(UniverseMembershipRow.stock_code)
        ).scalars().all()
    rows = rows[offset:]
    if limit:
        rows = rows[:limit]
    return (
        [r.stock_code for r in rows],
        {r.stock_code: (r.list_date, r.delist_date) for r in rows},
    )


def load_profiles(codes: list[str]) -> dict[tuple[str, str], datetime]:
    factory = get_session_factory()
    with factory() as db:
        rows = db.execute(
            select(StockBirthProfileRow).where(
                StockBirthProfileRow.stock_code.in_(codes),
                StockBirthProfileRow.birth_profile_version.in_(list(MODEL_VERSIONS.values())),
            )
        ).scalars().all()
    profiles: dict[tuple[str, str], datetime] = {}
    for row in rows:
        model = next(
            (m for m, v in MODEL_VERSIONS.items() if row.birth_profile_version == v), None
        )
        if model and row.birth_datetime is not None:
            profiles[(row.stock_code, model)] = row.birth_datetime.replace(tzinfo=None)
    return profiles


class PanelCollector:
    """按 as_of 逐点排盘并聚合引擎观点（不落分数以外的任何东西）。"""

    def __init__(
        self,
        codes: list[str],
        profiles: dict[tuple[str, str], datetime],
        *,
        eligibility: dict[str, tuple[date, date | None]] | None = None,
        birth_shift_days: int = 0,
        skip_ziwei: bool = False,
        ziwei_batch_size: int = 100,
    ) -> None:
        self.codes = codes
        self.profiles = profiles
        self.eligibility = eligibility or {}
        self.birth_shift_days = int(birth_shift_days)
        self.bazi = BaziEngine()
        self.huangli = HuangliEngine()
        self.ziwei = None if skip_ziwei else ZiweiEngine()
        self.ziwei_batch_size = ziwei_batch_size
        self.huangli_cache: dict[date, object] = {}
        self.failures: Counter = Counter()
        self.skipped_pit: Counter = Counter()
        self.ziwei_unavailable_reason = ""
        if self.ziwei is not None and self.ziwei.availability != "ok":
            self.ziwei_unavailable_reason = self.ziwei.unavailable_reason()

    # ------------------------------------------------------------------
    def pit_eligible(self, code: str, as_of_date: date) -> bool:
        """PIT 资格：``list_date <= as_of <= delist_date``（无退市日视为仍在市）。"""
        window = self.eligibility.get(code)
        if window is None:
            return True
        list_date, delist_date = window
        if as_of_date < list_date:
            self.skipped_pit["before_list"] += 1
            return False
        if delist_date is not None and as_of_date > delist_date:
            self.skipped_pit["after_delist"] += 1
            return False
        return True

    def birth_datetime_for(self, code: str, model: str) -> datetime | None:
        value = self.profiles.get((code, model))
        if value is None:
            return None
        if self.birth_shift_days:
            return value + timedelta(days=self.birth_shift_days)
        return value

    def _huangli(self, as_of: datetime):  # type: ignore[no-untyped-def]
        key = as_of.date()
        if key not in self.huangli_cache:
            self.huangli_cache[key] = self.huangli.snapshot(as_of, days=31)
        return self.huangli_cache[key]

    def compute_date(self, as_of_date: date) -> list[dict]:
        """返回该 as_of 的观测行（``opinion`` 级别，仅三个引擎）。"""
        as_of = datetime(as_of_date.year, as_of_date.month, as_of_date.day, 15, 0, 0)
        work: list[tuple[str, str, datetime, object]] = []
        for code in self.codes:
            if not self.pit_eligible(code, as_of_date):
                continue
            for model in MODEL_VERSIONS:
                birth = self.birth_datetime_for(code, model)
                if birth is None or as_of_date < birth.date():
                    continue
                try:
                    chart = self.bazi.build_chart(
                        birth_datetime=birth, as_of=as_of,
                        variant_mode=VariantMode.NOT_APPLICABLE, stock_code=code,
                    )
                except Exception:  # noqa: BLE001 - 单点失败只计数，不静默改写
                    self.failures["bazi"] += 1
                    continue
                work.append((code, model, birth, chart))

        ziwei_by_key: dict[tuple[str, str], object] = {}
        if self.ziwei is not None and self.ziwei.availability == "ok":
            for start in range(0, len(work), self.ziwei_batch_size):
                chunk = work[start:start + self.ziwei_batch_size]
                requests = [{
                    "context": EngineContext(stock_code=code, as_of=as_of),
                    "birth_datetime": birth, "as_of": as_of,
                    "variant_mode": VariantMode.FORWARD, "stock_code": code,
                } for code, _model, birth, _chart in chunk]
                try:
                    charts = self.ziwei.calculate_charts(requests)
                    for item, chart in zip(chunk, charts, strict=True):
                        ziwei_by_key[(item[0], item[1])] = chart
                except ZiweiUnavailableError as exc:
                    self.failures["ziwei_batch"] += 1
                    self.ziwei_unavailable_reason = str(exc)
                    for code, model, birth, _chart in chunk:
                        try:
                            ziwei_by_key[(code, model)] = self.ziwei.calculate_chart(
                                EngineContext(stock_code=code, as_of=as_of),
                                birth_datetime=birth, as_of=as_of,
                                variant_mode=VariantMode.FORWARD,
                            )
                        except ZiweiUnavailableError as item_exc:
                            self.failures["ziwei"] += 1
                            self.ziwei_unavailable_reason = str(item_exc)

        rows: list[dict] = []
        for code, model, _birth, chart in work:
            try:
                factor_set = compute_factor_set(
                    chart, self._huangli(as_of), as_of, stock_code=code,
                    ziwei_chart=ziwei_by_key.get((code, model)),
                )
            except Exception:  # noqa: BLE001
                self.failures["factor"] += 1
                continue
            opinions = {
                "bazi": AnalysisService.build_opinion(
                    EngineId.BAZI, factor_set, self.bazi.engine_version
                ),
                "huangli": AnalysisService.build_opinion(
                    EngineId.HUANGLI, factor_set, self.huangli.engine_version
                ),
            }
            if self.ziwei is not None:
                opinions["ziwei"] = AnalysisService.build_opinion(
                    EngineId.ZIWEI, factor_set, self.ziwei.engine_version,
                    unavailable_reason=(
                        self.ziwei_unavailable_reason or "紫微本次未产出可用因子"
                    ),
                )
            for engine, opinion in opinions.items():
                rows.append({
                    "stock_code": code,
                    "birth_model": model,
                    "as_of": as_of_date,
                    "engine": engine,
                    "opinion_score": opinion.score,
                    "raw_direction": int(opinion.direction),
                    "confidence": opinion.confidence,
                    "availability": _enum_value(opinion.availability),
                    "engine_version": opinion.engine_version,
                })
        return rows


def run(args: argparse.Namespace) -> int:
    started = time.time()
    date_from = date.fromisoformat(args.date_from)
    date_to = date.fromisoformat(args.date_to)
    dates = sample_dates(date_from, date_to, args.step_months)
    codes, eligibility = load_universe(args.limit, args.offset)
    if args.shard_count > 1:
        codes = codes[args.shard_index::args.shard_count]
    if not codes:
        raise RuntimeError("分片没有股票")
    eligibility = {code: eligibility[code] for code in codes if code in eligibility}
    profiles = load_profiles(codes)
    missing = [
        (code, model) for code in codes for model in MODEL_VERSIONS
        if (code, model) not in profiles
    ]
    collector = PanelCollector(
        codes, profiles,
        eligibility=eligibility,
        birth_shift_days=args.birth_shift_days,
        skip_ziwei=args.skip_ziwei,
    )
    collector = PanelCollector(
        codes, profiles,
        eligibility=eligibility,
        birth_shift_days=args.birth_shift_days,
        skip_ziwei=args.skip_ziwei,
    )
    rows: list[dict] = []
    per_date: dict[str, int] = {}
    for as_of in dates:
        chunk = collector.compute_date(as_of)
        per_date[as_of.isoformat()] = len(chunk)
        rows.extend(chunk)
        print(
            f"[{args.birth_shift_days:+d}d shard {args.shard_index}/{args.shard_count}] "
            f"{as_of} rows={len(chunk)} elapsed={time.time() - started:.0f}s",
            flush=True,
        )
    payload = {
        "universe_version": UNIVERSE_VERSION,
        "codes": codes,
        "dates": [v.isoformat() for v in dates],
        "rows": rows,
        "birth_shift_days": int(args.birth_shift_days),
        "step_months": int(args.step_months),
        "date_from": args.date_from,
        "date_to": args.date_to,
        "skip_ziwei": bool(args.skip_ziwei),
        "failures": dict(collector.failures),
        "skipped_pit": dict(collector.skipped_pit),
        "ziwei_unavailable_reason": collector.ziwei_unavailable_reason,
        "missing_profiles": len(missing),
        "engine_versions": {
            "bazi": collector.bazi.engine_version,
            "huangli": collector.huangli.engine_version,
            "ziwei": None if collector.ziwei is None else collector.ziwei.engine_version,
            "factor_rule_version": settings.factor_rule_version,
        },
        "per_date_row_count": per_date,
        "elapsed_seconds": round(time.time() - started, 1),
        "collector": "scripts/phase3d_collect_panel.py",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
    print(
        f"wrote {out} rows={len(rows)} dates={len(dates)} codes={len(codes)} "
        f"elapsed={time.time() - started:.0f}s failures={dict(collector.failures)}",
        flush=True,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3D 观测面板采集器")
    parser.add_argument("--date-from", default="2010-01-01")
    parser.add_argument("--date-to", default=CUTOFF_DATE.isoformat())
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="只取前 N 只股票")
    parser.add_argument("--offset", type=int, default=0, help="跳过前 N 只股票")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--birth-shift-days", type=int, default=0,
                        help="出生平移对照：把出生时间平移 N 天（0 = 真实 panel）")
    parser.add_argument("--skip-ziwei", action="store_true", help="仅用于诊断")
    parser.add_argument("--out", required=True)
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
