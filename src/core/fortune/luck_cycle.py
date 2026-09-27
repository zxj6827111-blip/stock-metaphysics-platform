"""股票大运方向的显式研究约定，不表示股票具有传统命理性别。"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from src.core.constants import STEM_YANG
from src.core.fortune.market_sessions import AShareMarketSessionAdapter
from src.core.fortune.ports import MarketSessionAdapter
from src.core.schemas.common import Assumption, Exchange, SourceRef, VariantMode
from src.core.schemas.fortune import (
    CompatibilityGender,
    FortuneAvailability,
    FortuneLuckCycleContext,
    FortunePolarity,
    FORTUNE_MARKET_SESSION_POLICY_VERSION,
    LuckCycleDirection,
)


def resolve_first_day_yinyang_luck_cycle(
    *,
    first_day_yinyang: str | None,
    polarity_observation_date: date | None,
    polarity_is_trading_day: bool | None,
    source: SourceRef | None,
    source_version: str,
    market_session_version: str,
    exchange: Exchange,
    birth_year_stem: str | None,
    as_of: datetime,
    market_session_adapter: MarketSessionAdapter | None = None,
) -> FortuneLuckCycleContext:
    """按首日阴阳研究约定推导极性、兼容输入与实际顺逆。

    首日阴阳来自首个交易日收盘结果，故只在该 session 收盘后可用。
    本函数不接收价格或收益序列，也不对规则做历史收益优化。
    """

    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("luck-cycle as_of 必须带时区")
    if (
        first_day_yinyang not in {"阳", "阴"}
        or polarity_observation_date is None
        or polarity_is_trading_day is not True
        or source is None
        or source.source.strip().lower() in {"", "unavailable"}
        or source.source.strip().lower().startswith("synthetic")
        or source_version.strip().lower() in {"", "unknown"}
        or market_session_version.strip().lower() in {"", "unknown"}
        or exchange not in {Exchange.SSE, Exchange.SZSE, Exchange.BSE}
        or birth_year_stem not in STEM_YANG
    ):
        return _unavailable(
            "缺少有效首日阴阳、极性观测日期/交易日证据、来源版本、A 股交易所或出生年干",
            source=source,
            source_version=source_version,
            polarity_observation_date=polarity_observation_date,
            market_session_version=market_session_version,
        )

    if polarity_observation_date.weekday() >= 5:
        return _unavailable(
            "周末日期与首日阴阳的交易日证据冲突",
            source=source,
            source_version=source_version,
            polarity_observation_date=polarity_observation_date,
            market_session_version=market_session_version,
        )

    try:
        session_adapter = market_session_adapter or AShareMarketSessionAdapter()
        session, matched_key = session_adapter.resolve_open_session(
            exchange, polarity_observation_date
        )
        session_tz = ZoneInfo(session.timezone)
    except (FileNotFoundError, LookupError, ValueError, KeyError):
        return _unavailable(
            "无法解析极性观测日适用的市场 session，不能证明首日阴阳的可用时点",
            source=source,
            source_version=source_version,
            polarity_observation_date=polarity_observation_date,
            market_session_version=market_session_version,
        )

    observed_at = datetime.combine(
        polarity_observation_date, session.close_time, tzinfo=session_tz
    )
    if as_of.astimezone(session_tz) < observed_at:
        return _unavailable(
            "首日阴阳只能在其观测交易日收盘后使用；当前 as_of 早于可观测时点",
            source=source,
            source_version=source_version,
            polarity_observation_date=polarity_observation_date,
            market_session_version=market_session_version,
            observed_at=observed_at,
        )

    polarity = FortunePolarity.YANG if first_day_yinyang == "阳" else FortunePolarity.YIN
    compatibility_gender = (
        CompatibilityGender.MALE if polarity == FortunePolarity.YANG else CompatibilityGender.FEMALE
    )
    year_is_yang = STEM_YANG[birth_year_stem]
    proxy_is_yang = polarity == FortunePolarity.YANG
    direction = (
        LuckCycleDirection.FORWARD
        if year_is_yang == proxy_is_yang
        else LuckCycleDirection.REVERSE
    )
    assumptions = [
        Assumption(
            key="fortune.luck_cycle.stock_polarity",
            value=(
                f"first_day_yinyang:{first_day_yinyang};"
                f"observation_date:{polarity_observation_date.isoformat()}"
            ),
            reason="首日收涨/收跌仅作为项目研究约定的 polarity proxy，不是股票的生理性别或传统定论",
            impact="该字段只在首个交易日收盘后可用，缺失时大运保持 unavailable",
        ),
        Assumption(
            key="fortune.luck_cycle.direction",
            value=f"{compatibility_gender.value}+birth_year_stem:{birth_year_stem}->{direction.value}",
            reason="按 ADR-0014 候选兼容映射输入算法，再依年干阴阳判定实际方向；同阴阳顺、异阴阳逆",
            impact="研究约定版本化，不进入正式财富因子，也不表达未来收益",
        ),
    ]
    resolved_market_session_version = (
        f"{FORTUNE_MARKET_SESSION_POLICY_VERSION}:{market_session_version}"
    )
    enriched_source = source.model_copy(
        update={
            "extra": {
                **source.extra,
                "polarity_observation_date": polarity_observation_date.isoformat(),
                "observed_at": observed_at.isoformat(),
                "session_source": session.source,
                "session_lookup_key": matched_key,
                "market_session_version": resolved_market_session_version,
            }
        }
    )
    return FortuneLuckCycleContext(
        polarity=polarity,
        direction=direction,
        compatibility_gender=compatibility_gender,
        availability=FortuneAvailability.AVAILABLE,
        direction_basis="first_day_yinyang_proxy+birth_year_stem_polarity",
        polarity_source=enriched_source,
        polarity_source_version=source_version,
        market_session_version=resolved_market_session_version,
        polarity_observation_date=polarity_observation_date,
        polarity_observed_at=observed_at,
        assumptions=assumptions,
    )


def compatibility_variant_mode(context: FortuneLuckCycleContext) -> VariantMode:
    """映射到旧 BaziEngine 的兼容参数；该枚举值不是实际顺逆方向。"""

    if context.availability != FortuneAvailability.AVAILABLE:
        return VariantMode.NOT_APPLICABLE
    if context.compatibility_gender == CompatibilityGender.MALE:
        return VariantMode.FORWARD
    if context.compatibility_gender == CompatibilityGender.FEMALE:
        return VariantMode.REVERSE
    return VariantMode.NOT_APPLICABLE


def _unavailable(
    reason: str,
    *,
    source: SourceRef | None,
    source_version: str,
    market_session_version: str = "",
    polarity_observation_date: date | None = None,
    observed_at: datetime | None = None,
) -> FortuneLuckCycleContext:
    return FortuneLuckCycleContext(
        availability=FortuneAvailability.UNAVAILABLE,
        direction_basis="first_day_yinyang_proxy+birth_year_stem_polarity",
        polarity_source=source or SourceRef(source="unavailable"),
        polarity_source_version=source_version or "unknown",
        market_session_version=market_session_version,
        polarity_observation_date=polarity_observation_date,
        polarity_observed_at=observed_at,
        unavailability_reason=reason,
        assumptions=[
            Assumption(
                key="fortune.luck_cycle.unavailable",
                value=reason,
                reason="排运约定必须 fail closed",
                impact="不生成 polarity、实际方向或大运周期",
            )
        ],
    )
