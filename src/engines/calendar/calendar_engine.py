"""CalendarEngine —— 历法与黄历基础设施（lunar-python adapter）。

职责（architecture §8 / two_session_plan §5）：

    公历 / 农历 / 干支 / 节气 / 生肖 / 纳音 / 建除十二值 / 十二神 /
    黄黑道 / 冲煞 / 彭祖百忌 / 吉神方位

严格约束
--------
1. **禁止 LLM 计算这些内容** —— 全部来自确定性代码。
2. lunar-python 对象**不得**离开本模块；对外只返回 ``CalendarSnapshot``。
3. 本模块是唯一允许 ``import lunar_python`` 的地方之一（另一个是 HuangliEngine）。
   `tests/test_third_party_isolation.py` 会校验这一约束。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from lunar_python import Solar

from src.core.config import settings
from src.core.constants import EARTHLY_BRANCHES, HEAVENLY_STEMS
from src.core.schemas.calendar import (
    CalendarSnapshot,
    GanZhi,
    JieQiInfo,
    LunarDate,
    SolarDate,
)
from src.core.schemas.common import Assumption, Availability, SourceRef, Warning_
from src.engines.base import EngineContext, EngineMetadata, MetaphysicsEngine

WEEKDAY_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")


class CalendarCalculationError(RuntimeError):
    """核心历法字段无法计算；调用方必须将本次历法结果标记为不可用。"""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"{field} 计算失败：{reason}")


def _safe(fn: Any, default: Any = "") -> Any:
    """调用 lunar-python 方法并吞掉异常 —— 单字段失败不应导致整盘失败。"""
    try:
        value = fn()
        return default if value is None else value
    except Exception:  # noqa: BLE001 - 第三方字段缺失属于预期情况
        return default


def _required(fn: Any, field: str, *, allow_none: bool = False) -> Any:
    """读取核心历法结果；失败或缺失时终止本次计算，不能合成合法外观的值。"""
    try:
        value = fn()
    except Exception as exc:  # noqa: BLE001 - 转为可识别的引擎不可用状态
        raise CalendarCalculationError(field, f"{type(exc).__name__}: {exc}") from exc
    if value is None and not allow_none:
        raise CalendarCalculationError(field, "第三方返回空值")
    if isinstance(value, str) and not value.strip() and not allow_none:
        raise CalendarCalculationError(field, "第三方返回空文本")
    return value


_VALID_GANZHI = frozenset(
    HEAVENLY_STEMS[index % 10] + EARTHLY_BRANCHES[index % 12]
    for index in range(60)
)


class CalendarEngine(MetaphysicsEngine[CalendarSnapshot]):
    """历法引擎。无状态、可并发调用。"""

    metadata = EngineMetadata(
        engine_id="calendar",
        display_name="历法引擎",
        engine_version=settings.calendar_engine_version,
        config_version=settings.config_version,
        third_party="6tail/lunar-python",
        third_party_commit="v1.4.8 (PyPI release)",
        notes="公历/农历/干支/节气/黄历基础字段；年柱按立春换年，月柱按节气换月",
    )

    # ------------------------------------------------------------------
    def calculate_chart(  # type: ignore[override]
        self,
        context: EngineContext,
        *,
        when: datetime | None = None,
        **_: Any,
    ) -> CalendarSnapshot:
        """计算 ``when`` 时刻的历法快照。``when`` 缺省取 context.as_of。"""
        target = when or context.as_of
        if target is None:
            raise ValueError("CalendarEngine.calculate_chart 需要 when 或 context.as_of")
        return self.snapshot(target)

    # ------------------------------------------------------------------
    def snapshot(self, when: datetime) -> CalendarSnapshot:
        """核心实现：把 lunar-python 转成本项目自己的 Schema。"""
        warnings: list[Warning_] = []

        try:
            solar = Solar.fromYmdHms(
                when.year, when.month, when.day, when.hour, when.minute, when.second or 0
            )
            lunar = solar.getLunar()
            eight_char = lunar.getEightChar()
        except Exception as exc:  # noqa: BLE001 - 核心转换失败时不返回部分伪盘
            raise CalendarCalculationError(
                "solar_lunar_conversion", f"{type(exc).__name__}: {exc}"
            ) from exc

        # --- 公历 ---
        solar_date = SolarDate(
            date=when.date(),
            timestamp=when,
            year=when.year,
            month=when.month,
            day=when.day,
            hour=when.hour,
            minute=when.minute,
            weekday_cn=WEEKDAY_CN[when.weekday()],
            zodiac_western=_safe(solar.getXingZuo),
        )

        # --- 农历 ---
        try:
            lunar_year = int(_required(lunar.getYear, "lunar.year"))
            lunar_month = int(_required(lunar.getMonth, "lunar.month"))
            lunar_day = int(_required(lunar.getDay, "lunar.day"))
        except (TypeError, ValueError) as exc:
            raise CalendarCalculationError("lunar_date", f"非法日期字段：{exc}") from exc
        if lunar_year < 1 or not 1 <= abs(lunar_month) <= 12 or not 1 <= lunar_day <= 30:
            raise CalendarCalculationError(
                "lunar_date", f"第三方返回超出范围的日期：{lunar_year}-{lunar_month}-{lunar_day}"
            )
        lunar_date = LunarDate(
            year=lunar_year,
            month=abs(lunar_month),
            day=lunar_day,
            is_leap_month=lunar_month < 0,
            text=_safe(lunar.toString),
            month_cn=_safe(lunar.getMonthInChinese),
            day_cn=_safe(lunar.getDayInChinese),
            zodiac=_safe(lunar.getYearShengXiao),
        )

        # --- 干支 ---
        # 年柱/月柱按节气换柱（getYearInGanZhiExact / getMonthInGanZhiExact 对应
        # 立春换年、节气换月，八字标准口径）
        #
        # 纳音（Phase 1.1 口径修正）：
        # lunar-python 的 getYearNaYin()/getMonthNaYin() 与 Exact 版干支口径
        # 不一致（立春/节气当日会出现"柱是甲辰、纳音是癸卯的金箔金"这种内部矛盾）。
        # 纳音是六十甲子的纯函数，由本项目常量表供给，保证柱与纳音永不冲突。
        # 见 docs/calculation-differences-phase1.md。
        from src.core.constants import nayin_of

        def _ganzhi(fn: Any, field: str) -> GanZhi:
            text = _required(fn, field)
            if not isinstance(text, str) or text not in _VALID_GANZHI:
                raise CalendarCalculationError(field, f"第三方返回非法干支：{text!r}")
            return GanZhi.from_text(text, nayin=nayin_of(text))

        year_gz = _ganzhi(lunar.getYearInGanZhiExact, "year_ganzhi")
        month_gz = _ganzhi(lunar.getMonthInGanZhiExact, "month_ganzhi")
        day_gz = _ganzhi(lunar.getDayInGanZhiExact, "day_ganzhi")
        hour_gz = _ganzhi(eight_char.getTime, "hour_ganzhi")

        # --- 节气 ---
        jieqi = self._build_jieqi(lunar, when)

        # --- 黄历基础字段 ---
        tian_shen = _safe(lunar.getDayTianShen)
        tian_shen_type = _safe(lunar.getDayTianShenType)
        if not tian_shen_type and tian_shen:
            from src.core.constants import DAY_TIAN_SHEN_LUCK

            tian_shen_type = DAY_TIAN_SHEN_LUCK.get(tian_shen, "")

        snapshot = CalendarSnapshot(
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            availability=Availability.OK,
            solar=solar_date,
            lunar=lunar_date,
            year_ganzhi=year_gz,
            month_ganzhi=month_gz,
            day_ganzhi=day_gz,
            hour_ganzhi=hour_gz,
            jieqi=jieqi,
            duty_officer=_safe(lunar.getZhiXing),
            day_tian_shen=tian_shen,
            day_tian_shen_type=tian_shen_type,
            day_tian_shen_luck=_safe(lunar.getDayTianShenLuck),
            xiu=_safe(lunar.getXiu),
            xiu_luck=_safe(lunar.getXiuLuck),
            chong_desc=_safe(lunar.getDayChongDesc),
            sha_direction=_safe(lunar.getDaySha),
            pengzu_gan=_safe(lunar.getPengZuGan),
            pengzu_zhi=_safe(lunar.getPengZuZhi),
            cai_shen_direction=_safe(lunar.getDayPositionCaiDesc),
            xi_shen_direction=_safe(lunar.getDayPositionXiDesc),
            fu_shen_direction=_safe(lunar.getDayPositionFuDesc),
            tai_shen=_safe(lunar.getDayPositionTai),
            day_yi=list(_safe(lunar.getDayYi, []) or []),
            day_ji=list(_safe(lunar.getDayJi, []) or []),
            assumptions=[
                "年柱以立春换年、月柱以节气换月（八字标准口径，非农历正月初一换年）",
                "时区固定为 Asia/Shanghai，按传入的 naive 本地时间解释",
            ],
            warnings=warnings,
            source=SourceRef(source="lunar-python", extra={"version": "1.4.8"}),
            raw_source=self._raw_snapshot(solar, lunar, eight_char),
        )
        return snapshot

    # ------------------------------------------------------------------
    def _build_jieqi(self, lunar: Any, when: datetime) -> JieQiInfo:
        """构造节气信息，包含"距上一个节的天数"（用于月令深浅分析）。"""
        prev = _required(lunar.getPrevJieQi, "jieqi.previous")
        nxt = _required(lunar.getNextJieQi, "jieqi.next")
        cur = _required(lunar.getCurrentJieQi, "jieqi.current", allow_none=True)

        prev_name = _required(prev.getName, "jieqi.previous.name")
        next_name = _required(nxt.getName, "jieqi.next.name")
        prev_at = _to_datetime(prev, "jieqi.previous.time")
        next_at = _to_datetime(nxt, "jieqi.next.time")
        if not prev_name or not next_name or prev_at is None or next_at is None:
            raise CalendarCalculationError("jieqi", "前后节气名称或时刻缺失")
        if not prev_at <= when <= next_at:
            raise CalendarCalculationError("jieqi", "前后节气时刻未覆盖目标时间")

        cur_name = _required(cur.getName, "jieqi.current.name") if cur is not None else ""
        cur_at = _to_datetime(cur, "jieqi.current.time") if cur is not None else None
        days_from_prev = round((when - prev_at).total_seconds() / 86400.0, 4)

        return JieQiInfo(
            name=_required(lunar.getJieQi, "jieqi.name", allow_none=True) or "",
            prev_name=prev_name,
            prev_at=prev_at,
            next_name=next_name,
            next_at=next_at,
            current_name=cur_name,
            current_at=cur_at,
            days_from_prev_jie=days_from_prev,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _raw_snapshot(solar: Any, lunar: Any, eight_char: Any) -> dict:
        """原始第三方输出 —— 仅用于审计/调试，业务层禁止读取。"""
        return {
            "solar_full": _safe(solar.toFullString),
            "lunar_full": _safe(lunar.toFullString),
            "lunar_short": _safe(lunar.toString),
            "eight_char": _safe(eight_char.toString),
            "jieqi": _safe(lunar.getJieQi),
            "prev_jieqi": _safe(lambda: lunar.getPrevJieQi().getName()),
            "next_jieqi": _safe(lambda: lunar.getNextJieQi().getName()),
            "zhi_xing": _safe(lunar.getZhiXing),
            "tian_shen": _safe(lunar.getDayTianShen),
            "xiu": _safe(lambda: f"{lunar.getXiu()}{lunar.getZheng()}{lunar.getAnimal()}"),
            "chong": _safe(lunar.getDayChongDesc),
            "sha": _safe(lunar.getDaySha),
            "pengzu": [_safe(lunar.getPengZuGan), _safe(lunar.getPengZuZhi)],
        }

    # ------------------------------------------------------------------
    def collect_assumptions(self) -> list[Assumption]:
        return [
            Assumption(
                key="calendar.year_boundary",
                value="立春",
                reason="八字年柱以立春为界，与农历新年不同",
                impact="1-2 月出生/上市的样本年柱可能与农历口径不同",
            ),
            Assumption(
                key="calendar.month_boundary",
                value="节（十二节）",
                reason="月柱以节气中的『节』换月",
                impact="交节当日的月柱存在边界风险，Golden Case 已覆盖",
            ),
        ]


def _to_datetime(jieqi_obj: Any, field: str) -> datetime | None:
    """把 lunar-python 的 JieQi 对象转成 datetime。"""
    try:
        solar = jieqi_obj.getSolar()
        return datetime(
            solar.getYear(), solar.getMonth(), solar.getDay(),
            solar.getHour(), solar.getMinute(), solar.getSecond(),
        )
    except Exception as exc:  # noqa: BLE001 - 节气时刻是核心边界信息
        raise CalendarCalculationError(field, f"{type(exc).__name__}: {exc}") from exc


def get_calendar_engine() -> CalendarEngine:
    return CalendarEngine()
