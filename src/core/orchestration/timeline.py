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
from typing import NamedTuple

from src.core.config import settings
from src.core.orchestration.analysis_service import AnalysisService, direction_from_score
from src.core.schemas.analysis import MetaphysicsOpinion
from src.core.schemas.common import Availability, EngineId, VariantMode, Warning_
from src.core.schemas.timeline import (
    AGGREGATION_VERSION,
    DailyWindowResponse,
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

#: 逐日视图默认与最大交易日数量。
#: 上限 60 是因为逐日结果要按天算八字节律 + 紫微流日，60 天足以覆盖"近 3 个月"，
#: 再长就该用月/周窗口而不是逐日列表。
DEFAULT_DAILY_WINDOW = 20
MAX_DAILY_WINDOW = 60


class DayEvaluation(NamedTuple):
    """某一天的三模型观点 + 该天的因子集（共识/冲突需要它）。"""

    opinions: dict[str, MetaphysicsOpinion]
    factor_set: object
    as_of: datetime


class TimelineBuilder:
    """构建未来时间窗口（月 / 周 / 日）。"""

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
        """``True`` / ``False`` / ``None``（无可靠日历依据 → 未知）。

        **返回 None 时绝不猜测** —— 调用方必须把它当作"不知道"处理。
        这正是 Phase 1.1 对 ``is_trading_day()`` 的要求：
        日历越界时不得用周末规则假装肯定。

        这里显式检查 ``source``：只有**实测成交日**（观测事实）与
        **官方已公布日历**（交易所公告）才算依据；``weekend_rule_fallback``
        是"日历文件缺失时的近似"，识别不了长假 —— 若接受它，
        时间窗口会把春节连休当成交易日且毫无提示。
        """
        from src.core.stock.trading_calendar import KNOWN_SOURCES

        cal = self._trading_calendar(exchange)
        try:
            q = cal.is_trading_day(d)
        except Exception:  # noqa: BLE001 - 日历不可用时如实降级
            return None
        if q.source not in KNOWN_SOURCES:
            return None
        if q.value is None:
            return None
        return bool(q.value)

    def calendar_coverage(self, exchange: str) -> dict:
        """交易日历覆盖元数据（实测层 / 官方公布层分开报告）。"""
        try:
            return self._trading_calendar(exchange).coverage_descriptor()
        except Exception as exc:  # noqa: BLE001 - 元数据拿不到不该让整页失败
            return {"exchange": exchange, "error": f"{type(exc).__name__}: {exc}"}

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
    # 批量逐日求值（性能关键路径）
    # ------------------------------------------------------------------
    def evaluate_days(
        self,
        *,
        stock_code: str,
        target_days: list[date],
        variant_mode: VariantMode,
        birth_datetime: datetime | None,
        hour: int = 15,
    ) -> tuple[dict[date, DayEvaluation], list[Warning_]]:
        """批量求多天的三模型观点（含该天的因子集，供共识/冲突使用）。

        为什么不能逐日调用 ``_score_at``：那条路径每天都要重建 31 天黄历
        （0.28s）并单独启动一次 Node 子进程排紫微（0.23s），
        20 个交易日就要 17 秒。这里把两处可批量的部分批起来：

        * 黄历：一次构造覆盖整个区间的连续日历，再按天切片
          （``HuangliEngine.snapshots_for_window``，结果与逐日调用逐字段相同）；
        * 紫微：一次 ``calculate_charts`` 批量请求（``services/ziwei-service`` 的
          批量入口本来就是为此设计的）。

        **不改变任何分数**：每个交易日的观点仍由同一个 ``compute_factor_set`` +
        ``build_opinion`` 产出，只是把重复的构造摊掉了。
        ``tests/core/test_timeline_batch_equivalence.py`` 断言两条路径结果一致。
        """
        if not target_days:
            return {}, []
        warnings: list[Warning_] = []
        ordered = sorted(set(target_days))
        if birth_datetime is None:
            raise ValueError("时间窗口需要 birth_datetime（请先构造出生档案）")

        start_dt = datetime(ordered[0].year, ordered[0].month, ordered[0].day, hour, 0, 0)
        offsets = [(d - ordered[0]).days for d in ordered]
        offset_by_day = dict(zip(ordered, offsets, strict=True))
        huangli_map = self.service.huangli.snapshots_for_window(
            start=start_dt, offsets=offsets, window_days=31,
        )

        charts = {
            d: self.service.bazi.build_chart(
                birth_datetime=birth_datetime.replace(tzinfo=None),
                as_of=datetime(d.year, d.month, d.day, hour, 0, 0),
                variant_mode=variant_mode,
                stock_code=stock_code,
            )
            for d in ordered
        }

        ziwei_charts: dict[date, object] = {}
        if variant_mode in (VariantMode.FORWARD, VariantMode.REVERSE):
            from src.engines.base import EngineContext  # 局部导入避免循环依赖

            requests = [
                {
                    "context": EngineContext(
                        stock_code=stock_code,
                        as_of=datetime(d.year, d.month, d.day, hour, 0, 0),
                    ),
                    "birth_datetime": birth_datetime.replace(tzinfo=None),
                    "as_of": datetime(d.year, d.month, d.day, hour, 0, 0),
                    "variant_mode": variant_mode,
                    "stock_code": stock_code,
                }
                for d in ordered
            ]
            try:
                built = self.service.ziwei.calculate_charts(requests)
                ziwei_charts = dict(zip(ordered, built, strict=True))
            except ZiweiUnavailableError as exc:
                # 单个引擎不可用不影响其它引擎（AGENTS.md §9.7）
                warnings.append(Warning_(
                    code="TIMELINE_ZIWEI_UNAVAILABLE",
                    message=f"紫微批量排盘不可用：{exc}",
                    severity="warning",
                ))

        out: dict[date, DayEvaluation] = {}
        for d in ordered:
            as_of_day = datetime(d.year, d.month, d.day, hour, 0, 0)
            fset = compute_factor_set(
                charts[d], huangli_map[offset_by_day[d]], as_of_day,
                stock_code=stock_code, ziwei_chart=ziwei_charts.get(d),
            )
            opinions = {
                "bazi": self.service.build_opinion(
                    EngineId.BAZI, fset, self.service.bazi.engine_version),
                "huangli": self.service.build_opinion(
                    EngineId.HUANGLI, fset, self.service.huangli.engine_version),
            }
            if d in ziwei_charts:
                opinions["ziwei"] = self.service.build_opinion(
                    EngineId.ZIWEI, fset, self.service.ziwei.engine_version)
            else:
                opinions["ziwei"] = MetaphysicsOpinion(
                    engine=EngineId.ZIWEI, availability=Availability.UNAVAILABLE,
                    direction=0, score=None, confidence=0.0,
                    note="该时刻紫微不可用（服务不可用或未指定方向 variant），不以 0 分替代。",
                )
            out[d] = DayEvaluation(opinions=opinions, factor_set=fset, as_of=as_of_day)
        return out, warnings

    # ------------------------------------------------------------------
    # 逐日窗口（主时间视图的真实粒度）
    # ------------------------------------------------------------------
    def build_days(
        self,
        *,
        stock_code: str,
        as_of: datetime,
        days: int = DEFAULT_DAILY_WINDOW,
        variant_mode: VariantMode = VariantMode.FORWARD,
        exchange: str = "SSE",
        birth_datetime: datetime | None = None,
    ) -> tuple[list[DayResult], list[Warning_]]:
        """as_of 之后连续的 ``days`` 个**实际交易日**的逐日结果。

        粒度说明：这是**逐日**粒度，来自流日（流日 = 该日期的日柱 + 当日黄历），
        不是把月度分数插值出来的"每日预测"。
        """
        warnings: list[Warning_] = []
        days = max(1, min(int(days), MAX_DAILY_WINDOW))
        start = as_of.date() + timedelta(days=1)
        span_end = start + timedelta(days=days * 7 + 60)
        all_days, cal_warnings = self.trading_days_in(start, span_end, exchange)
        for w in cal_warnings:
            warnings.append(Warning_(
                code="TIMELINE_CALENDAR_PARTIAL", message=w, severity="info",
            ))
        target = all_days[:days]
        if not target:
            return [], [*warnings, Warning_(
                code="TIMELINE_NO_TRADING_DAY",
                message="as_of 之后没有任何已知交易日，无法产出逐日窗口。",
                severity="warning",
            )]
        if len(target) < days:
            warnings.append(Warning_(
                code="TIMELINE_DAILY_PARTIAL",
                message=(
                    f"请求 {days} 个交易日，实际只取到 {len(target)} 个："
                    "交易日历在区间内覆盖不足（不补造日期）。"
                ),
                severity="warning",
            ))
        opinions_by_day, w = self.evaluate_days(
            stock_code=stock_code, target_days=target,
            variant_mode=variant_mode, birth_datetime=birth_datetime,
        )
        warnings.extend(w)
        return [_day_result(d, opinions_by_day[d].opinions) for d in target], warnings

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
        # 先把每个月的"打分日"收集起来一次性求值，再逐月装配窗口。
        # 打分日 = 该月最后一个交易日（月内信息最完整）。
        planned: list[tuple[int, MonthWindow, list[date]]] = []
        score_days: list[date] = []

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
            planned.append((i, window, trading_days))
            score_days.append(trading_days[-1])

        opinions_by_day, eval_warnings = self.evaluate_days(
            stock_code=stock_code,
            target_days=score_days,
            variant_mode=variant_mode,
            birth_datetime=birth_datetime,
        )
        warnings.extend(eval_warnings)

        for _i, window, trading_days in planned:
            evaluation = opinions_by_day[trading_days[-1]]
            opinions = evaluation.opinions
            window.bazi = opinions.get("bazi")
            window.ziwei = opinions.get("ziwei")
            window.huangli = opinions.get("huangli")
            consensus, conflict = self.service.build_consensus_and_conflict(
                opinions, factor_set=evaluation.factor_set,
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

        # 先把所有周的交易日并成一批求值（每 5 个交易日一周），再逐周聚合。
        # 逐日调用 _score_at 时，12 周要 32 秒；批量后是同一份结果的摊薄。
        chunks: list[list[date]] = []
        for i in range(weeks):
            chunk = all_days[i * TRADING_DAYS_PER_WEEK:(i + 1) * TRADING_DAYS_PER_WEEK]
            if not chunk:
                break
            chunks.append(chunk)
        all_target = [d for chunk in chunks for d in chunk]
        evaluations, eval_warnings = self.evaluate_days(
            stock_code=stock_code,
            target_days=all_target,
            variant_mode=variant_mode,
            birth_datetime=birth_datetime,
        )
        warnings.extend(eval_warnings)

        for i, chunk in enumerate(chunks):
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
            daily: list[DayResult] = [
                _day_result(d, evaluations[d].opinions) for d in chunk
            ]
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
            evaluation = evaluations[mid]
            consensus, _conflict = self.service.build_consensus_and_conflict(
                evaluation.opinions, factor_set=evaluation.factor_set,
                data_quality="B", research_status="NOT_RUN",
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


def build_daily_windows(
    *,
    stock_code: str,
    as_of: datetime,
    birth_datetime: datetime,
    days: int = DEFAULT_DAILY_WINDOW,
    variant_mode: VariantMode = VariantMode.FORWARD,
    exchange: str = "SSE",
    service: AnalysisService | None = None,
) -> DailyWindowResponse:
    """构建逐日窗口（主时间视图的真实粒度）。"""
    builder = TimelineBuilder(service)
    requested = max(1, min(int(days), MAX_DAILY_WINDOW))
    day_results, warnings = builder.build_days(
        stock_code=stock_code, as_of=as_of, days=requested,
        variant_mode=variant_mode, exchange=exchange, birth_datetime=birth_datetime,
    )
    present = sorted({
        name
        for d in day_results
        for name, score in (
            ("bazi", d.bazi_score), ("ziwei", d.ziwei_score), ("huangli", d.huangli_score),
        )
        if score is not None
    })
    return DailyWindowResponse(
        stock_code=stock_code,
        as_of=as_of,
        variant_mode=str(variant_mode.value if hasattr(variant_mode, "value") else variant_mode),
        calendar_coverage=builder.calendar_coverage(exchange),
        requested_days=requested,
        returned_days=len(day_results),
        days=day_results,
        research_status="NOT_RUN",
        research_status_reasons=[
            "逐日结果给出的是**该交易日流日的传统规则强度**，"
            "不是价格预测，也没有历史统计支持其预测能力。"
            "历史有效性必须由研究流水线（事件研究 + 负对照）回答。"
        ],
        methodology=(
            f"每个点都是独立求值的**流日**结果（as_of 之后连续的实际交易日），"
            "交易日优先取实测成交日历，其覆盖之外取交易所**已公布**的开市/休市安排"
            f"（{exchange}；两层覆盖见 calendar_coverage），"
            "不是把月度分数插值到每一天。"
            f"本批数据中可用的引擎：{'、'.join(present) if present else '（无）'}；"
            "不可用引擎的分数字段为 null，不参与方向合成、也不以 0 替代。"
        ),
        warnings=warnings,
    )


__all__ = [
    "TimelineBuilder", "build_time_windows", "build_daily_windows",
    "TRADING_DAYS_PER_WEEK", "DEFAULT_DAILY_WINDOW", "MAX_DAILY_WINDOW",
]
