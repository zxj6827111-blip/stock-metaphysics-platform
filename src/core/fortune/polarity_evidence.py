"""验证 stock_master 中首日阴阳字段级证据并构造运限输入。"""

from __future__ import annotations

import math
from datetime import date, datetime

from src.core.schemas.common import SourceRef
from src.core.schemas.fortune import FirstDayPolarityEvidence, FortuneLuckCycleEvidence


def read_first_day_polarity_evidence(stock) -> tuple[FirstDayPolarityEvidence, FortuneLuckCycleEvidence | None]:
    """只有字段、日期、交易日、版本和可见时点彼此一致时才向运限传证据。"""

    raw_value = getattr(stock, "first_day_yinyang", None)
    raw_pct = getattr(stock, "first_day_pct_chg", None)
    raw_listing_date = getattr(stock, "listing_date", None)
    metadata = getattr(stock, "first_day_evidence_json", None) or {}
    status = "unavailable"
    reason = "数据库没有首日阴阳的字段级来源证据；股票主档的整体 source 不能代替字段来源。"
    evidence: FortuneLuckCycleEvidence | None = None

    if isinstance(metadata, dict) and metadata:
        source = str(metadata.get("source") or "")
        source_version = str(metadata.get("source_version") or "")
        flag = metadata.get("first_day_yinyang")
        observation_date = _date(metadata.get("observation_date"))
        visible_at = _datetime(metadata.get("visible_at"))
        trading = metadata.get("trading_day_evidence") or {}
        market_session_version = str(metadata.get("market_session_version") or "")
        reasons: list[str] = []
        if metadata.get("status") == "conflict":
            reasons.extend(str(item) for item in metadata.get("unavailability_reasons", []) if item)
            if not reasons:
                reasons.append("来源元数据已登记为冲突")
            status = "conflict"
        elif metadata.get("status") != "available":
            reasons.append("来源元数据未标记为可用")
        if flag not in {"阳", "阴"} or raw_value != flag:
            reasons.append("数据库阴阳字段与来源证据不一致")
        if not isinstance(raw_pct, (int, float)) or not math.isfinite(float(raw_pct)):
            reasons.append("数据库缺少有效的首日涨跌幅字段")
        elif not isinstance(metadata.get("first_day_pct_chg"), (int, float)) or not math.isclose(
            float(raw_pct), float(metadata["first_day_pct_chg"]), rel_tol=0.0, abs_tol=1e-12
        ):
            reasons.append("数据库首日涨跌幅与来源证据不一致")
        if observation_date is None or raw_listing_date is None or observation_date != raw_listing_date:
            reasons.append("阴阳观测日期与股票主档上市日期不一致或缺失")
        if not source or not source_version:
            reasons.append("字段级来源或来源版本缺失")
        if trading.get("is_trading_day") is not True or not trading.get("source"):
            reasons.append("缺少可核验的首日交易日证据")
        if not market_session_version or visible_at is None:
            reasons.append("市场时段版本或收盘可见时点缺失")

        if not reasons:
            status = "available"
            reason = "首日阴阳来源、主档日期、交易日证据、市场时段版本及收盘可见时点一致。"
            evidence = FortuneLuckCycleEvidence(
                first_day_yinyang=flag,
                observation_date=observation_date,
                is_trading_day=True,
                source=SourceRef(
                    source=source,
                    extra={
                        "price_basis": metadata.get("price_basis", ""),
                        "trading_day_evidence": trading,
                        "market_session": metadata.get("market_session", {}),
                    },
                ),
                source_version=source_version,
                market_session_version=market_session_version,
                visible_at=visible_at,
            )
        else:
            status = "conflict" if metadata.get("status") == "conflict" or any(
                "不一致" in item or "冲突" in item for item in reasons
            ) else "unavailable"
            reason = "；".join(dict.fromkeys(reasons))

    record = FirstDayPolarityEvidence(
        status=status,
        first_day_yinyang=raw_value if raw_value in {"阳", "阴"} else None,
        first_day_pct_chg=float(raw_pct) if isinstance(raw_pct, (int, float)) and math.isfinite(float(raw_pct)) else None,
        price_basis=str(metadata.get("price_basis") or "") if isinstance(metadata, dict) else "",
        observation_date=(
            _date(metadata.get("observation_date")) if isinstance(metadata, dict) else None
        ),
        is_trading_day=(
            (metadata.get("trading_day_evidence") or {}).get("is_trading_day")
            if isinstance(metadata, dict) else None
        ),
        trading_day_source=(
            str((metadata.get("trading_day_evidence") or {}).get("source") or "")
            if isinstance(metadata, dict) else ""
        ),
        source=str(metadata.get("source") or "") if isinstance(metadata, dict) else "",
        source_version=str(metadata.get("source_version") or "") if isinstance(metadata, dict) else "",
        market_session_version=str(metadata.get("market_session_version") or "") if isinstance(metadata, dict) else "",
        visible_at=_datetime(metadata.get("visible_at")) if isinstance(metadata, dict) else None,
        reason=reason,
    )
    return record, evidence


def _date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed
