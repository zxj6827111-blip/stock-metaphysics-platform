"""时间窗口编排（Phase 2D）：未来 12 个月 / 12 周。

周度不是独立的术数概念
----------------------
**传统术数没有"流周"。** 因此周度窗口必须由该周内**交易日**的流日结果聚合而来，
而不是发明一层新的运限。聚合口径版本化在 ``AGGREGATION_VERSION``。

所有窗口一律落在**实际交易日**上
--------------------------------
用 ``TradingCalendarProvider`` 判定与枚举交易日；如果交易日历超出覆盖范围，
**如实降级并给出 warning**，绝不用"周末规则"假装肯定
（这与 Phase 1.1 对 `is_trading_day()` 的要求一致）。

每个窗口独立携带三模型观点
--------------------------
月度窗口不是一个"综合数字"：每个月都有独立的
`bazi / ziwei / huangli / consensus / conflict / research_status / data_quality`。
"""

from __future__ import annotations

import statistics
from datetime import date, datetime, timedelta

from src.core.config import settings
from src.core.orchestration.analysis_service import AnalysisService, direction_from_score
from src.core.schemas.analysis import MetaphysicsOpinion
from src.core.schemas.common import Availability, EngineId, VariantMode, Warning_
from src.core.schemas.timeline import (
    AGGREGATION_VERSION,
    DayResult,
    MonthWindow,
    TimeWindowResponse,
    WeekWindow,
)
from src.engines.base import EngineContext
from src.engines.ziwei.ziwei_engine import ZiweiUnavailableError
from src.factors.registry.compute import compute_factor_set

#: 每周的交易日数量（A 股一周最多 5 个交易日）
TRADING_DAYS_PER_WEEK = 5


class TimelineBuilder:
    """构建未来时间窗口（月 / 周）。"""

    def __init__(self, service: AnalysisService | None = None) -> None:
        self.service = service or AnalysisService()
        self._calendar = self.service.calendar

    # ------------------------------------------------------------------
    # 交易日工具
    # ------------------------------------------------------------------
    @staticmethod
    def _trading_calendar(exchange: str = "SSE"):
        from src.core.stock.trading_calendar import get_trading_calendar_provider

        return get_trading_calendar_provider().for_exchange(exchange)

    def _is_trading_day(self, d: date, exchange: str) -> bool | None:
        """``True`` / ``False`` / ``None``（超出日历覆盖范围）。

        **返回 None 时绝不猜测** —— 调用方必须把它当作"不知道"处理。
        这正是 Phase 1.1 对 ``is_trading_day()`` 的要求：
        日历越界时不得用周末规则假装肯定。
        """
        cal = self._trading_calendar(exchange)
        try:
            q = cal.is_trading_day(d)
        except Exception:  # noqa: BLE001 - 日历不可用时如实降级
            return None
        if q.value is None:
            return None
        return bool(q.value)

    def trading_days_in(self, start: date, end: date, exchange: str) -> tuple[list[date], list[str]]:
        """枚举区间内的交易日；返回 ``(交易日, warnings)``。"""
        warnings: list[str] = []
        out: list[date] = []
        cur = start
        unknown = 0
        while cur <= end:
            flag = self._is_trading_day(cur, exchange)
            if flag is True:
                out.append(cur)
            elif flag is None:
                unknown += 1
            cur += timedelta(days=1)
        if unknown:
            warnings.append(
                f"{start}~{end} 中有 {unknown} 天的交易日历覆盖缺失，"
                "这些日期未计入交易日（日历优先，不使用周末规则假装肯定）。"
            )
        return out, warnings

    # ------------------------------------------------------------------
    # 月度窗口
    # ------------------------------------------------------------------
    def build_months(
        self,
        *,
        stock_code: str,
        as_of: datetime,
        months: int = 12,
        variant_mode: VariantMode = VariantMode.FORWARD,
        exchange: str = "SSE",
        birth_datetime: datetime | None = None,
    ) -> tuple[list[MonthWindow], list[Warning_]]:
        warnings: list[Warning_] = []
        out: list[MonthWindow] = []

        for i in range(1, months + 1):
            year, month = _add_months(as_of.year, as_of.month, i)
            start = date(year, month, 1)
            end = date(year, month, _days_in_month(year, month))
            trading_days, cal_warnings = self.trading_days_in(start, end, exchange)
            for w in cal_warnings:
                warnings.append(Warning_(
                    code="TIMELINE_CALENDAR_PARTIAL", message=w, severity="info",
                ))

            window = MonthWindow(
                month=f"{year:04d}-{month:02d}",
                month_index=i,
                start_date=start,
                end_date=end,
                trading_days=len(trading_days),
                sample_dates=[d.isoformat() for d in _sample_days(trading_days)],
            )

            if not trading_days:
                window.research_status = "NOT_RUN"
                window.warnings.append(Warning_(
                    code="TIMELINE_NO_TRADING_DAY",
                    message=f"{window.month} 在该交易所没有交易日，无法产出窗口评分。",
                    severity="warning",
                ))
                out.append(window)
                continue

            # 取该月最后一个交易日作为打分时点（月内信息最完整）
            score_day = trading_days[-1]
            as_of_month = datetime(score_day.year, score_day.month, score_day.day, 15, 0, 0)
            opinions, fset, w = self._score_at(
                stock_code=stock_code, as_of=as_of_month,
                variant_mode=variant_mode, birth_datetime=birth_datetime,
            )
            warnings.extend(w)
            window.bazi = opinions.get("bazi")
            window.ziwei = opinions.get("ziwei")
            window.huangli = opinions.get("huangli")
            consensus, conflict = self.service.build_consensus_and_conflict(
                opinions, factor_set=fset,
                data_quality="B",
                research_status="NOT_RUN",
            )
            window.consensus = consensus
            window.conflict = conflict
            window.research_status = consensus.research_status
            window.data_quality = {
                "grade": consensus.data_quality,
                "note": "本窗口的分数是**规则强度**，其历史有效性必须由研究流水线回答。",
            }
            out.append(window)

        return out, warnings

    # ------------------------------------------------------------------
    # 周度窗口（交易日聚合）
    # ------------------------------------------------------------------
    def build_weeks(
        self,
        *,
        stock_code: str,
        as_of: datetime,
        weeks: int = 12,
        variant_mode: VariantMode = VariantMode.FORWARD,
        exchange: str = "SSE",
        birth_datetime: datetime | None = None,
    ) -> tuple[list[WeekWindow], list[Warning_]]:
        """由**交易日流日结果**聚合出周度窗口。

        周的定义 = 从 as_of 之后的第一个交易日开始，每 ``TRADING_DAYS_PER_WEEK``
        个交易日为一周。这与"自然周"不同，是刻意的：市场只在交易日运行，
        用自然周会把周末/节假日算成空窗口。
        """
        warnings: list[Warning_] = []
        out: list[WeekWindow] = []

        start = as_of.date() + timedelta(days=1)
        # 覆盖 weeks 周所需的自然日上界（交易日 ≤ 自然日；留 2 倍余量）
        span_end = start + timedelta(days=weeks * 7 * 2 + 30)
        all_days, cal_warnings = self.trading_days_in(start, span_end, exchange)
        for w in cal_warnings:
            warnings.append(Warning_(
                code="TIMELINE_CALENDAR_PARTIAL", message=w, severity="info",
            ))

        if not all_days:
            return [], [*warnings, Warning_(
                code="TIMELINE_NO_TRADING_DAY",
                message="as_of 之后没有任何已知交易日，无法构建周度窗口。",
                severity="warning",
            )]

        for i in range(weeks):
            chunk = all_days[i * TRADING_DAYS_PER_WEEK:(i + 1) * TRADING_DAYS_PER_WEEK]
            if not chunk:
                break
            week = WeekWindow(
                week_index=i + 1,
                week_start=chunk[0],
                week_end=chunk[-1],
                trading_days=len(chunk),
                aggregation_method=(
                    f"由该周 {len(chunk)} 个**交易日**的流日评分聚合"
                    f"（每 {TRADING_DAYS_PER_WEEK} 个交易日为一周；不使用自然周，"
                    "也不存在『流周』这一传统概念）"
                ),
                aggregation_version=AGGREGATION_VERSION,
            )
            daily: list[DayResult] = []
            for d in chunk:
                as_of_day = datetime(d.year, d.month, d.day, 15, 0, 0)
                opinions, _, w = self._score_at(
                    stock_code=stock_code, as_of=as_of_day,
                    variant_mode=variant_mode, birth_datetime=birth_datetime,
                )
                warnings.extend(w)
                daily.append(_day_result(d, opinions))
            week.daily_results = daily

            combined = [float(x.combined_direction) for x in daily]
            week.mean = round(statistics.fmean(combined), 6) if combined else None
            week.median = round(statistics.median(combined), 6) if combined else None
            week.min = round(min(combined), 6) if combined else None
            week.max = round(max(combined), 6) if combined else None
            week.positive_day_ratio = (
                round(sum(1 for v in combined if v > 0) / len(combined), 6) if combined else None
            )
            week.weighted_mean = _weighted_mean(daily)

            # 周度共识：用周内代表性交易日的观点（取中位数那一天）
            mid = daily[len(daily) // 2].trade_date
            opinions, fset, _w = self._score_at(
                stock_code=stock_code,
                as_of=datetime(mid.year, mid.month, mid.day, 15, 0, 0),
                variant_mode=variant_mode, birth_datetime=birth_datetime,
            )
            consensus, _conflict = self.service.build_consensus_and_conflict(
                opinions, factor_set=fset, data_quality="B", research_status="NOT_RUN",
            )
            week.consensus = consensus
            week.research_status = consensus.research_status
            out.append(week)

        return out, warnings

    # ------------------------------------------------------------------
    def _score_at(
        self,
        *,
        stock_code: str,
        as_of: datetime,
        variant_mode: VariantMode,
        birth_datetime: datetime | None,
    ) -> tuple[dict[str, MetaphysicsOpinion], object, list[Warning_]]:
        """计算某时刻的三模型观点。不落库（时间窗口是只读视图）。"""
        warnings: list[Warning_] = []
        huangli = self.service.huangli.snapshot(as_of, days=31)

        if birth_datetime is None:
            raise ValueError("时间窗口需要 birth_datetime（请先构造出生档案）")
        chart = self.service.bazi.build_chart(
            birth_datetime=birth_datetime.replace(tzinfo=None),
            as_of=as_of,
            variant_mode=variant_mode,
            stock_code=stock_code,
        )

        ziwei_chart = None
        if variant_mode in (VariantMode.FORWARD, VariantMode.REVERSE):
            try:
                ziwei_chart = self.service.ziwei.calculate_chart(
                    EngineContext(stock_code=stock_code, as_of=as_of),
                    birth_datetime=birth_datetime.replace(tzinfo=None),
                    as_of=as_of,
                    variant_mode=variant_mode,
                    stock_code=stock_code,
                )
            except ZiweiUnavailableError as exc:
                warnings.append(Warning_(
                    code="TIMELINE_ZIWEI_UNAVAILABLE",
                    message=f"{as_of.date()} 紫微不可用：{exc}",
                    severity="warning",
                ))

        fset = compute_factor_set(
            chart, huangli, as_of, stock_code=stock_code, ziwei_chart=ziwei_chart,
        )

        opinions = {
            "bazi": self.service.build_opinion(
                EngineId.BAZI, fset, self.service.bazi.engine_version),
            "huangli": self.service.build_opinion(
                EngineId.HUANGLI, fset, self.service.huangli.engine_version),
        }
        if ziwei_chart is not None:
            opinions["ziwei"] = self.service.build_opinion(
                EngineId.ZIWEI, fset, self.service.ziwei.engine_version)
        else:
            opinions["ziwei"] = MetaphysicsOpinion(
                engine=EngineId.ZIWEI, availability=Availability.UNAVAILABLE,
                direction=0, score=None, confidence=0.0,
                note="该时刻紫微不可用（服务不可用或未指定方向 variant），不以 0 分替代。",
            )
        return opinions, fset, warnings


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    m = month + delta
    return year + (m - 1) // 12, (m - 1) % 12 + 1


def _days_in_month(year: int, month: int) -> int:
    import calendar as _cal

    return _cal.monthrange(year, month)[1]


def _sample_days(trading_days: list[date]) -> list[date]:
    """在一个月的交易日中取采样点：首、中、末（控制计算量，同时保留边界信息）。"""
    if len(trading_days) <= 3:
        return list(trading_days)
    return [trading_days[0], trading_days[len(trading_days) // 2], trading_days[-1]]


def _day_result(d: date, opinions: dict[str, MetaphysicsOpinion]) -> DayResult:
    def g(key: str) -> tuple[int, float | None]:
        o = opinions.get(key)
        if o is None or o.availability != Availability.OK:
            return 0, None
        return int(o.direction), o.score

    b_d, b_s = g("bazi")
    z_d, z_s = g("ziwei")
    h_d, h_s = g("huangli")
    # 只对**可用**引擎取方向均值；不可用引擎不参与，也不当成 0。
    used = [d for d, s in ((b_d, b_s), (z_d, z_s), (h_d, h_s)) if s is not None]
    combined = 0
    if used:
        mean = sum(used) / len(used)
        combined = direction_from_score(50.0 + mean * 50.0)
    return DayResult(
        trade_date=d, is_trading_day=True,
        bazi_direction=b_d, ziwei_direction=z_d, huangli_direction=h_d,
        combined_direction=combined,
        bazi_score=b_s, ziwei_score=z_s, huangli_score=h_s,
    )


def _weighted_mean(daily: list[DayResult]) -> float | None:
    """按引擎可用性加权 —— 不可用引擎不参与，**不用 0 占位**。

    权重 = 该日**可用引擎个数**。若某天所有引擎都不可用，该日被排除，
    因为把"不知道"当成 0 会系统性地把均值拉向中性。
    """
    num = 0.0
    den = 0.0
    for x in daily:
        n = sum(1 for s in (x.bazi_score, x.ziwei_score, x.huangli_score) if s is not None)
        if n == 0:
            continue
        num += x.combined_direction * n
        den += n
    if den == 0:
        return None
    return round(num / den, 6)


def build_time_windows(
    *,
    stock_code: str,
    as_of: datetime,
    birth_datetime: datetime,
    months: int = 12,
    weeks: int = 12,
    variant_mode: VariantMode = VariantMode.FORWARD,
    exchange: str = "SSE",
    service: AnalysisService | None = None,
) -> TimeWindowResponse:
    """一次构建月 + 周窗口。"""
    builder = TimelineBuilder(service)
    month_windows, w1 = builder.build_months(
        stock_code=stock_code, as_of=as_of, months=months,
        variant_mode=variant_mode, exchange=exchange, birth_datetime=birth_datetime,
    )
    week_windows, w2 = builder.build_weeks(
        stock_code=stock_code, as_of=as_of, weeks=weeks,
        variant_mode=variant_mode, exchange=exchange, birth_datetime=birth_datetime,
    )
    warnings = [*w1, *w2]
    return TimeWindowResponse(
        stock_code=stock_code,
        as_of=as_of,
        variant_mode=str(variant_mode.value if hasattr(variant_mode, "value") else variant_mode),
        months=month_windows,
        weeks=week_windows,
        research_status="NOT_RUN",
        research_status_reasons=[
            "时间窗口给出的是**传统规则强度**在未来的分布，"
            "没有任何历史统计支持其预测能力。"
            "历史有效性必须由研究流水线（事件研究 + 负对照）回答。"
        ],
        methodology=(
            f"月度：每个自然月的**实际交易日**（{settings.timezone}）中取末个交易日打分，"
            "逐月独立计算三模型观点与共识。"
            f"周度：由每 {TRADING_DAYS_PER_WEEK} 个**交易日**的流日结果聚合，"
            f"聚合版本 {AGGREGATION_VERSION}。"
            "传统术数**没有『流周』这一层**，周度是聚合结果而非独立运限。"
        ),
        warnings=warnings,
    )


__all__ = [
    "TimelineBuilder", "build_time_windows", "TRADING_DAYS_PER_WEEK",
]
