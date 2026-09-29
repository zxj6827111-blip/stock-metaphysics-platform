"""统一出生档案下的股票公历月/日期十神与 Fortune 结构结果。"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.config import settings
from src.core.fortune.birth import resolve_market_first_trade_profile
from src.core.fortune.polarity_evidence import read_first_day_polarity_evidence
from src.core.orchestration.stock_fortune import (
    DatabaseFortuneChartArtifactWriter,
    StockFortuneEngine,
)
from src.core.orchestration.stock_fortune_timeline import StockFortuneTimelineEngine
from src.core.orchestration.ten_god_calendar import (
    TenGodCalendarError,
    build_stock_ten_god_calendar,
    load_birth_profile,
)
from src.core.schemas.common import (
    Assumption,
    BirthBasis,
    DataQuality,
    Exchange,
    SourceRef,
    VariantMode,
)
from src.core.schemas.fortune import (
    BirthTimePrecision,
    FirstTradeObservation,
    FirstTradeObservationResolution,
    FirstTradeObservationStatus,
    FortuneAvailability,
    FortuneBirthBasis,
    FortuneContextKind,
    FortuneRelationScope,
    FortuneTimelineAnchorMode,
    FortuneTimelineDateMode,
    StockFortuneBirthProfile,
    StockFortuneIdentity,
    StockFortuneTimelineRequest,
)
from src.core.schemas.research_v2 import (
    FortuneMonthCalendarV2Request,
    FortuneMonthCalendarV2Response,
    FortuneMonthSegmentInterpretation,
)
from src.core.schemas.stock import BirthProfileEvidence, StockBirthProfile
from src.core.stock.codes import normalize_code
from src.core.stock.exchange_sessions import ex_value
from src.db.models import StockMasterRow
from src.market.providers.fortune_first_trade import DailyBarFirstTradeProvider

_WEALTH_GODS = {"正财", "偏财"}


class StockFortuneMonthCalendarEngine:
    """在单一出生档案上分别运行既有十神日历与 Fortune 时间轴。"""

    def build(self, db: Session, payload: FortuneMonthCalendarV2Request, market) -> FortuneMonthCalendarV2Response:
        if payload.config_version != settings.config_version:
            raise ValueError(
                "请求 config_version 与当前实例配置不一致："
                f"requested={payload.config_version}; active={settings.config_version}"
            )
        code = normalize_code(payload.stock_code)
        master = db.execute(
            select(StockMasterRow).where(StockMasterRow.stock_code == code)
        ).scalars().first()
        if master is None:
            raise LookupError(f"本地股票主档不存在：{code}")

        profile, calendar_profile, calendar_reason, market_version = self._birth_profile(
            db, master, payload, market
        )
        try:
            exchange = Exchange(master.exchange)
        except ValueError:
            exchange = Exchange.UNKNOWN
        if exchange == Exchange.UNKNOWN and profile.exchange != Exchange.UNKNOWN:
            exchange = profile.exchange
        identity = StockFortuneIdentity(
            symbol=code,
            exchange=exchange,
            name=master.name,
            source=SourceRef(
                source="stock_master",
                extra={"source_row_source": master.source, "listing_date": master.listing_date.isoformat() if master.listing_date else None},
            ),
            source_version=master.source or "stock-master-record",
        )
        polarity_summary, luck_cycle_evidence = read_first_day_polarity_evidence(master)

        timeline = None
        timeline_reason = ""
        try:
            timeline_request = StockFortuneTimelineRequest(
                stock_identity=identity,
                birth_profile=profile,
                start_date=payload.start_date,
                end_date=payload.end_date,
                date_mode=FortuneTimelineDateMode.ALL_CALENDAR_DAYS,
                anchor_mode=FortuneTimelineAnchorMode.EXACT_LOCAL_TIME,
                evaluation_time=payload.evaluation_time,
                timezone=payload.timezone,
                luck_cycle_evidence=luck_cycle_evidence,
                evaluation_source=SourceRef(source="stock_fortune_month_calendar_v2"),
                evaluation_source_version="research-api-v2-month-calendar-v1",
                market_session_version=payload.market_session_version,
                config_version=payload.config_version,
                include_relation_events=True,
                include_month_segments=True,
                include_ten_god_index=True,
            )
            timeline = StockFortuneTimelineEngine(
                StockFortuneEngine(DatabaseFortuneChartArtifactWriter(db))
            ).build(timeline_request)
        except Exception as exc:  # noqa: BLE001 - 时间轴失败不阻断独立的十神日历
            db.rollback()
            timeline_reason = f"Fortune 时间轴不可用：{type(exc).__name__}: {exc}"

        calendar = None
        if calendar_profile is not None:
            try:
                calendar = build_stock_ten_god_calendar(
                    db,
                    code,
                    start_date=payload.start_date,
                    years=0,
                    months=30,
                    days=(payload.end_date - payload.start_date).days + 1,
                    view="all",
                    birth_basis=ex_value(calendar_profile.birth_basis),
                    birth_profile_version=calendar_profile.birth_profile_version,
                    resolved_profile=calendar_profile,
                )
                calendar_reason = ""
            except Exception as exc:  # noqa: BLE001 - 日历失败不清除可用的 Fortune 结果
                calendar_reason = f"十神日历不可用：{type(exc).__name__}: {exc}"
        elif not calendar_reason:
            calendar_reason = "所选出生口径没有可用于股票日主十神的完整出生时刻。"

        if timeline is not None:
            db.commit()
        month_interpretations = self._month_interpretations(calendar, timeline)
        return FortuneMonthCalendarV2Response(
            request=payload,
            stock_identity=identity,
            resolved_versions={
                "stock_master_source_version": master.source,
                "market_data_version": market_version,
                "birth_profile_version": profile.birth_profile_version,
                "birth_rule_version": profile.rule_version,
                "market_session_version": profile.market_session_version or payload.market_session_version,
                "config_version": payload.config_version,
                "calendar_engine_version": settings.calendar_engine_version,
                "bazi_engine_version": settings.bazi_engine_version,
                "ten_god_rule_version": settings.ten_god_rule_version,
                "luck_cycle_rule_version": "stock-luck-cycle-first-day-yinyang-v1",
            },
            birth_profile=profile,
            first_day_polarity=polarity_summary,
            calendar=calendar,
            calendar_unavailability_reason=calendar_reason,
            timeline=timeline,
            timeline_unavailability_reason=timeline_reason,
            month_interpretations=month_interpretations,
        )

    def _birth_profile(self, db, master, payload, market):
        code = master.stock_code
        try:
            exchange = Exchange(master.exchange)
        except ValueError:
            exchange = Exchange.UNKNOWN

        if payload.birth_basis == "listing_open":
            try:
                legacy, _ = load_birth_profile(
                    db, code, "listing_open", payload.birth_profile_version
                )
                if master.listing_date is None or legacy.birth_datetime.date() != master.listing_date:
                    raise TenGodCalendarError(
                        "listing_open 档案出生日期与 stock_master 上市日期不一致；不自动校正"
                    )
                assumptions = list(legacy.assumptions)
                if not assumptions:
                    assumptions.append(Assumption(
                        key="fortune.birth.listing_open",
                        value=legacy.birth_datetime.isoformat(),
                        reason="上市开盘时刻是明确的研究假设，不是首笔真实成交时刻",
                        impact="首笔成交时间仍保持 unavailable；更换档案版本会使排盘结果变化",
                    ))
                profile = StockFortuneBirthProfile(
                    symbol=code,
                    exchange=legacy.exchange,
                    listing_date=master.listing_date,
                    birth_basis=FortuneBirthBasis.LISTING_OPEN,
                    birth_datetime=legacy.birth_datetime,
                    first_trade_datetime=None,
                    first_trade_date=None,
                    first_trade_resolution=FirstTradeObservationResolution.UNKNOWN,
                    timezone=legacy.timezone,
                    birth_time_precision=BirthTimePrecision.INFERRED,
                    source=legacy.source,
                    source_version=legacy.birth_profile_version,
                    confidence=legacy.data_quality.score,
                    birth_profile_version=legacy.birth_profile_version,
                    rule_version=f"listing-open-profile:{legacy.birth_profile_version}",
                    config_version=payload.config_version,
                    market_session_version=payload.market_session_version,
                    assumptions=assumptions,
                    data_quality=legacy.data_quality,
                )
                return profile, legacy, "", None
            except (TenGodCalendarError, ValueError) as exc:
                reason = str(exc)
                profile = self._unavailable_profile(
                    code, exchange, master.listing_date, FortuneBirthBasis.LISTING_OPEN,
                    payload.birth_profile_version, payload, reason,
                )
                return profile, None, reason, None

        market_version = _market_version(market)
        provider_id = str(getattr(market, "provider_id", "unknown") or "unknown")
        try:
            observation = DailyBarFirstTradeProvider(
                market, source_version=market_version
            ).observe_first_trade(code)
        except Exception as exc:  # noqa: BLE001 - provider failure is section-level unavailability
            observation = FirstTradeObservation(
                status=FirstTradeObservationStatus.UNAVAILABLE,
                source=SourceRef(source=f"market-provider:{provider_id}"),
                source_version=market_version,
                reason=f"行情首日证据读取失败：{type(exc).__name__}",
            )
        if observation.status == FirstTradeObservationStatus.OBSERVED_TRADING_DATE:
            if master.listing_date is None or observation.first_trade_date != master.listing_date:
                observation = FirstTradeObservation(
                    status=FirstTradeObservationStatus.UNAVAILABLE,
                    source=observation.source,
                    source_version=observation.source_version,
                    reason=(
                        "行情最早可见日与已核实上市日期不一致或主档上市日期缺失；"
                        "不能把受覆盖范围截断的第一条行情认作上市首日"
                    ),
                )
        profile = resolve_market_first_trade_profile(
            symbol=code,
            exchange=exchange,
            observation=observation,
            listing_date=master.listing_date,
            config_version=payload.config_version,
            market_session_version=payload.market_session_version,
        )
        legacy = self._legacy_market_profile(profile, master) if profile.birth_datetime else None
        reason = "" if legacy else (
            profile.assumptions[0].value if profile.assumptions else "没有可用的 MARKET_FIRST_TRADE 出生时刻。"
        )
        return profile, legacy, reason, market_version

    @staticmethod
    def _unavailable_profile(code, exchange, listing_date, basis, version, payload, reason):
        fortune_basis = (
            FortuneBirthBasis.LISTING_OPEN if basis == FortuneBirthBasis.LISTING_OPEN
            else FortuneBirthBasis.MARKET_FIRST_TRADE
        )
        return StockFortuneBirthProfile(
            symbol=code,
            exchange=exchange,
            listing_date=listing_date,
            birth_basis=fortune_basis,
            birth_datetime=None,
            birth_time_precision=BirthTimePrecision.UNKNOWN,
            source=SourceRef(source="unavailable"),
            source_version="unknown",
            birth_profile_version=version,
            rule_version="stock-fortune-birth-unavailable-v1",
            config_version=payload.config_version,
            market_session_version=payload.market_session_version,
            assumptions=[Assumption(
                key="fortune.birth.unavailable",
                value=reason,
                reason="所选出生口径缺少一致且可追溯的时刻证据",
                impact="不回退到另一出生口径；日历日期柱可独立计算，股票日主十神与运限保持不可用",
            )],
        )

    @staticmethod
    def _legacy_market_profile(profile: StockFortuneBirthProfile, master) -> StockBirthProfile:
        return StockBirthProfile(
            stock_code=profile.symbol,
            exchange=profile.exchange,
            birth_basis=BirthBasis.FIRST_TRADE,
            birth_datetime=profile.birth_datetime,
            timezone=profile.timezone,
            source=profile.source,
            birth_profile_version=profile.birth_profile_version,
            evidence=BirthProfileEvidence(
                listing_date=master.listing_date,
                first_trading_day=profile.first_trade_date,
                timezone=profile.timezone,
                derivation=(
                    "使用已解析的 MARKET_FIRST_TRADE 档案；日线仅表示最早观测交易日期，"
                    "session 开盘时刻仍是明确的推定，不是首笔真实成交时间。"
                ),
            ),
            assumptions=profile.assumptions,
            data_quality=profile.data_quality or DataQuality(),
            variant_mode=VariantMode.NOT_APPLICABLE,
            variant_note="股票无真实性别；此原局日历不使用运限兼容性别。",
        )

    @staticmethod
    def _month_interpretations(calendar, timeline):
        if calendar is None:
            return []
        interpretations = []
        day_master = calendar.natal.day_master
        for segment in calendar.months:
            if segment.kind != "month":
                continue
            wealth_locations = []
            if segment.stem_ten_god in _WEALTH_GODS:
                wealth_locations.append(f"月干 {segment.stem}：{segment.stem_ten_god}")
            for hidden in segment.branch_hidden_stems:
                if hidden.ten_god in _WEALTH_GODS:
                    wealth_locations.append(f"月支藏干 {hidden.stem}：{hidden.ten_god}")

            related = []
            relation_context_available = bool(
                timeline
                and timeline.stable_context.natal_context.availability == FortuneAvailability.AVAILABLE
            )
            if relation_context_available:
                seen: set[str] = set()
                for point in timeline.points:
                    if not (segment.start_at <= point.evaluation_datetime < segment.end_at):
                        continue
                    for event in point.relation_events:
                        context = getattr(event.source.context, "value", event.source.context)
                        scope = getattr(event.scope, "value", event.scope)
                        if context != FortuneContextKind.MONTH.value or scope != FortuneRelationScope.TEMPORAL_TO_NATAL.value:
                            continue
                        if event.source.pillar != "month":
                            continue
                        key = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
                        if key not in seen:
                            seen.add(key)
                            related.append(event)

            if day_master:
                wealth_text = "、".join(wealth_locations) if wealth_locations else "该月柱天干及当前返回的地支藏干中未见正财/偏财类别"
                if related:
                    relation_text = "；结构关系：" + "；".join(event.explanation for event in related)
                elif relation_context_available:
                    relation_text = "；在当前流月及原局上下文中未检测到合冲刑害事件"
                else:
                    relation_text = "；流月与原局的合冲刑害关系不可用，不能判定有无相关事件"
                explanation = (
                    f"以该股票日主 {day_master} 分类：月柱 {segment.ganzhi.text} 的月干 {segment.stem} 为"
                    f"{segment.stem_ten_god}，地支藏干按同一日主分别标注；{wealth_text}。"
                    f"五行喜忌状态为「{segment.verdict}」：{segment.reason}{relation_text}。"
                    "以上是传统结构标签，不表示财富结果、股价方向或预期收益。"
                )
            else:
                explanation = "日主资料不可用，不能将该月干或藏干映射为股票十神；不作通用五行替代解释。"
            interpretations.append(FortuneMonthSegmentInterpretation(
                segment=segment,
                wealth_star_locations=wealth_locations,
                related_events=related,
                explanation=explanation,
            ))
        return interpretations


def _market_version(market) -> str:
    try:
        descriptor = market.status_descriptor()
    except Exception:  # noqa: BLE001 - provider status is optional provenance
        descriptor = {}
    version = descriptor.get("data_version") if isinstance(descriptor, dict) else None
    return str(version or settings.market_data_version or "unknown").strip()


__all__ = ["StockFortuneMonthCalendarEngine"]
