"""StockBirthProfile 构造器 —— 本项目第一重要的研究变量。

默认模型 ``listing_open``：

    上市首个正式交易日 + 该交易所对应交易 session 的正式开盘时刻 + Asia/Shanghai

关键纪律
--------
1. **禁止硬编码 09:30** —— 开盘时刻必须来自 ``exchange_session_calendar``。
2. 每次构造都产出 ``birth_profile_version``，并且**不覆盖**历史版本。
3. 股票**无性别**：``variant_mode`` 默认 ``not_applicable``，
   禁止偷偷填"男命/女命"以启用顺逆大运。
4. 所有假设写入 ``assumptions``，可服务于未来的方案对比回测。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.schemas.common import (
    Assumption,
    BirthBasis,
    DataQuality,
    DataQualityGrade,
    Exchange,
    SourceRef,
    VariantMode,
)
from src.core.schemas.stock import (
    BirthProfileCreateRequest,
    BirthProfileEvidence,
    ExchangeSession,
    StockBirthProfile,
    StockMaster,
)
from src.core.stock import exchange_sessions
from src.core.stock.exchange_sessions import ex_value

DEFAULT_TZ = "Asia/Shanghai"
#: 上市日若非交易日，向后最多查找多少个自然日
MAX_LOOKAHEAD_DAYS = 30


class BirthProfileError(ValueError):
    """出生档案无法构造（关键输入缺失）。"""


def _ensure_trading_day(
    candidate: date,
    *,
    is_trading_day: callable | None = None,
) -> tuple[date, bool, str]:
    """把"上市日"对齐到首个正式交易日。

    由于 Phase 1 没有独立的交易日历表，这里采用保守策略：

    * 周末 → 顺延到下一个工作日；
    * 若调用方提供了 ``is_trading_day`` 回调（例如用行情数据判断），则用其校验；
    * 若无法校验，则在 ``data_quality`` 中降级并记录假设。
    """
    cursor = candidate
    shifted = False
    for _ in range(MAX_LOOKAHEAD_DAYS):
        is_weekend = cursor.weekday() >= 5
        known = None
        if is_trading_day is not None:
            try:
                known = bool(is_trading_day(cursor))
            except Exception:  # noqa: BLE001 - 校验失败不阻塞
                known = None
        if not is_weekend and (known is None or known):
            note = ""
            if shifted:
                note = f"上市日 {candidate} 非交易日，已顺延至 {cursor}"
            return cursor, shifted, note
        shifted = True
        cursor += timedelta(days=1)
    raise BirthProfileError(f"无法在 {MAX_LOOKAHEAD_DAYS} 天内找到交易日（起点 {candidate}）")


def build_birth_profile(
    stock: StockMaster,
    request: BirthProfileCreateRequest | None = None,
    *,
    is_trading_day: callable | None = None,
    db_sessions: list[ExchangeSession] | None = None,
    session_open_time: str | None = None,
) -> StockBirthProfile:
    """构造股票出生档案。

    Args:
        stock: 股票基础资料（需含 listing_date）。
        request: 出生基准请求，缺省 ``listing_open``。
        is_trading_day: 可选回调，用于校验某日是否交易日（例如用行情数据）。
        db_sessions: 可选的数据库时段配置（优先于配置文件）。
        session_open_time: 测试/覆盖用；正常路径应为 None。
    """
    req = request or BirthProfileCreateRequest()
    basis = req.birth_basis
    exchange = req.exchange_override or stock.exchange or Exchange.UNKNOWN
    tz = ZoneInfo(DEFAULT_TZ)

    assumptions: list[Assumption] = []
    notes: list[str] = []
    grade = DataQualityGrade.A
    score = 1.0

    # ---------------- 解析出生时间 ----------------
    if basis == BirthBasis.LISTING_OPEN:
        if stock.listing_date is None:
            raise BirthProfileError(
                f"{stock.stock_code} 缺少上市日期，无法构造 listing_open 出生档案"
            )
        trading_day, shifted, shift_note = _ensure_trading_day(
            stock.listing_date, is_trading_day=is_trading_day
        )
        if shift_note:
            notes.append(shift_note)
        if shifted:
            grade = DataQualityGrade.B
            score = min(score, 0.85)

        session, matched_key = exchange_sessions.resolve_session(
            exchange, stock.board or "DEFAULT", trading_day, db_sessions=db_sessions
        )
        open_time = session.open_time
        if session_open_time:
            open_time = datetime.strptime(session_open_time, "%H:%M:%S").time()
            notes.append(f"开盘时刻被显式覆盖为 {session_open_time}（测试/研究用途）")

        birth_dt = datetime(
            trading_day.year, trading_day.month, trading_day.day,
            open_time.hour, open_time.minute, open_time.second,
            tzinfo=tz,
        )

        if matched_key.startswith("UNKNOWN"):
            grade = DataQualityGrade.C
            score = min(score, 0.6)
            notes.append("交易所未知，已使用兜底交易时段配置")
        elif (
            matched_key.endswith("/DEFAULT")
            and (stock.board or "DEFAULT") not in ("DEFAULT", "主板", "")
        ):
            # 主板本身即对应 DEFAULT 配置，只有创业板/科创板/北交所等
            # 板块专属时段缺失时才算降级
            grade = DataQualityGrade.B
            score = min(score, 0.85)
            notes.append(f"未命中板块专属时段，回退到 {matched_key}")

        if is_trading_day is None:
            score = min(score, 0.9)
            notes.append("Phase 1 未接入独立交易日历表，交易日仅按周末规则校验")

        evidence = BirthProfileEvidence(
            listing_date=stock.listing_date,
            first_trading_day=trading_day,
            session_name=session.session_name,
            session_open_time=open_time.strftime("%H:%M:%S"),
            timezone=session.timezone,
            derivation=(
                f"listing_open = 上市首个正式交易日({trading_day}) "
                f"+ {matched_key} 正式开盘({open_time.strftime('%H:%M')}) + {session.timezone}"
            ),
            lookup_key=matched_key,
        )
        assumptions.append(Assumption(
            key="birth.listing_open",
            value=f"{trading_day.isoformat()}T{open_time.strftime('%H:%M:%S')}+08:00",
            reason="股票不存在传统意义的出生时间；本系统以『上市首日正式开盘时刻』作为默认研究假设",
            impact="该假设本身是需要被历史回测检验的对象，而非既定事实",
        ))
        source = SourceRef(
            source="derived:listing_open",
            extra={"session_source": session.source, "matched_key": matched_key},
        )

    elif basis == BirthBasis.CUSTOM:
        if req.override_datetime is None:
            raise BirthProfileError("birth_basis=custom 时必须提供 override_datetime")
        birth_dt = req.override_datetime
        if birth_dt.tzinfo is None:
            birth_dt = birth_dt.replace(tzinfo=tz)
        trading_day = birth_dt.date()
        evidence = BirthProfileEvidence(
            listing_date=stock.listing_date,
            first_trading_day=trading_day,
            derivation=f"custom = 用户指定的 {birth_dt.isoformat()}",
            lookup_key="custom",
        )
        grade = DataQualityGrade.B
        score = 0.7
        notes.append("使用自定义出生时间，非默认研究基准")
        assumptions.append(Assumption(
            key="birth.custom",
            value=birth_dt.isoformat(),
            reason="用户显式指定出生时刻",
            impact="与其他股票不可直接比较",
        ))
        source = SourceRef(source="user:custom")

    elif basis == BirthBasis.IPO_DATE:
        if stock.listing_date is None:
            raise BirthProfileError(f"{stock.stock_code} 缺少上市/发行日期")
        # IPO 发行日暂以 listing_date 近似，并标记为不可用字段
        birth_dt = datetime(
            stock.listing_date.year, stock.listing_date.month, stock.listing_date.day,
            tzinfo=tz,
        )
        trading_day = stock.listing_date
        evidence = BirthProfileEvidence(
            listing_date=stock.listing_date,
            derivation="ipo_date 基准：Phase 1 暂无独立发行日数据源，使用 listing_date 近似",
            lookup_key="ipo_date",
        )
        grade = DataQualityGrade.C
        score = 0.5
        notes.append("ipo_date 数据源缺失，使用 listing_date 近似（不可用于正式结论）")
        assumptions.append(Assumption(
            key="birth.ipo_date",
            value="approximated_by_listing_date",
            reason="Phase 1 未接入独立 IPO 发行日数据源",
            impact="该基准的出生时刻精度不足，仅供参考",
        ))
        source = SourceRef(source="derived:ipo_date_approx")

    elif basis == BirthBasis.COMPANY_FOUNDATION:
        if stock.listing_date is None:
            raise BirthProfileError(f"{stock.stock_code} 无任何可用于推导的日期")
        raise BirthProfileError(
            "company_foundation 需要公司成立日期数据源，Phase 1 尚未接入（按契约返回错误，不猜测）"
        )

    elif basis == BirthBasis.FIRST_TRADE:
        raise BirthProfileError(
            "first_trade 需要历史逐笔成交数据，Phase 1 尚未接入（按契约返回错误，不猜测）"
        )
    else:  # pragma: no cover - 枚举已穷尽
        raise BirthProfileError(f"不支持的 birth_basis: {basis}")

    # ---------------- 股票无性别 ----------------
    variant_mode = req.variant_mode
    variant_note = ""
    if variant_mode == VariantMode.NOT_APPLICABLE:
        variant_note = (
            "股票不存在真实性别。运限顺逆依赖性别，因此 Phase 1 不启用大运，"
            "variant_mode=not_applicable；如需研究可显式切换为 forward/reverse/both。"
        )
    else:
        variant_note = (
            f"当前使用 {ex_value(variant_mode)} 假设计算运限，仅用于研究对比，"
            "不得解读为股票的真实性别。"
        )
        assumptions.append(Assumption(
            key="birth.variant_mode",
            value=ex_value(variant_mode),
            reason="传统运限算法需要性别/顺逆，股票无性别",
            impact="不同 variant 结果必须分别回测，Phase 1 不纳入正式因子",
        ))

    # ---------------- 记录候选基准（预留） ----------------
    ipo = None
    foundation = None
    first_trade = None

    return StockBirthProfile(
        stock_code=stock.stock_code,
        exchange=exchange,
        birth_basis=basis,
        birth_datetime=birth_dt,
        timezone=DEFAULT_TZ,
        source=source,
        birth_profile_version=settings.birth_profile_version,
        evidence=evidence,
        assumptions=assumptions,
        data_quality=DataQuality(
            grade=grade,
            score=round(score, 3),
            notes=notes or ["出生时间来源明确、无降级"],
        ),
        variant_mode=variant_mode,
        variant_note=variant_note,
        ipo_date=ipo,
        company_foundation=foundation,
        first_trade=first_trade,
        custom_datetime=birth_dt if basis == BirthBasis.CUSTOM else None,
    )


def to_row(profile: StockBirthProfile) -> dict:
    """转成 ``stock_birth_profile`` 表行。"""
    return {
        "stock_code": profile.stock_code,
        "exchange": ex_value(profile.exchange),
        "birth_basis": ex_value(profile.birth_basis),
        "birth_datetime": profile.birth_datetime.replace(tzinfo=None),
        "timezone": profile.timezone,
        "source": profile.source.source,
        "birth_profile_version": profile.birth_profile_version,
        "evidence_json": profile.evidence.model_dump(mode="json"),
        "assumptions_json": [a.model_dump(mode="json") for a in profile.assumptions],
        "data_quality_json": profile.data_quality.model_dump(mode="json"),
        "variant_mode": ex_value(profile.variant_mode),
        "variant_note": profile.variant_note,
        "ipo_date": profile.ipo_date,
        "company_foundation": profile.company_foundation,
        "first_trade": profile.first_trade.replace(tzinfo=None) if profile.first_trade else None,
        "custom_datetime": profile.custom_datetime.replace(tzinfo=None) if profile.custom_datetime else None,
    }


def from_row(row: object) -> StockBirthProfile:
    """从 ORM 行还原 Schema 对象。"""
    return StockBirthProfile(
        stock_code=row.stock_code,  # type: ignore[attr-defined]
        exchange=Exchange(row.exchange),  # type: ignore[attr-defined]
        birth_basis=BirthBasis(row.birth_basis),  # type: ignore[attr-defined]
        birth_datetime=row.birth_datetime.replace(tzinfo=ZoneInfo(DEFAULT_TZ)),  # type: ignore[attr-defined]
        timezone=row.timezone,  # type: ignore[attr-defined]
        source=SourceRef(source=row.source),  # type: ignore[attr-defined]
        birth_profile_version=row.birth_profile_version,  # type: ignore[attr-defined]
        evidence=BirthProfileEvidence(**(row.evidence_json or {})),  # type: ignore[attr-defined]
        assumptions=[Assumption(**a) for a in (row.assumptions_json or [])],  # type: ignore[attr-defined]
        data_quality=DataQuality(**(row.data_quality_json or {})),  # type: ignore[attr-defined]
        variant_mode=VariantMode(row.variant_mode),  # type: ignore[attr-defined]
        variant_note=row.variant_note,  # type: ignore[attr-defined]
        ipo_date=row.ipo_date,  # type: ignore[attr-defined]
        company_foundation=row.company_foundation,  # type: ignore[attr-defined]
        first_trade=row.first_trade,  # type: ignore[attr-defined]
        custom_datetime=row.custom_datetime,  # type: ignore[attr-defined]
    )
