"""历法（CalendarEngine）与黄历（HuangliEngine）的输出 Schema。

业务层只消费这里定义的类型，**不得**直接使用 lunar-python 对象。
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from src.core.schemas.common import Availability, SMBaseModel, SourceRef, Warning_


class GanZhi(SMBaseModel):
    """一对干支。"""

    stem: str = Field(description="天干")
    branch: str = Field(description="地支")
    text: str = Field(description="干支合写，如 辛巳")
    stem_wuxing: str = Field(description="天干五行")
    branch_wuxing: str = Field(description="地支五行")
    nayin: str = Field(default="", description="纳音")

    @classmethod
    def from_text(cls, text: str, nayin: str = "") -> GanZhi:
        from src.core.constants import BRANCH_WUXING, STEM_WUXING

        if len(text) != 2:
            raise ValueError(f"非法干支: {text!r}")
        stem, branch = text[0], text[1]
        return cls(
            stem=stem,
            branch=branch,
            text=text,
            stem_wuxing=STEM_WUXING.get(stem, "未知"),
            branch_wuxing=BRANCH_WUXING.get(branch, "未知"),
            nayin=nayin,
        )


class SolarDate(SMBaseModel):
    """公历日期信息。"""

    date: date
    timestamp: datetime
    year: int
    month: int
    day: int
    hour: int = 0
    minute: int = 0
    weekday_cn: str = ""
    zodiac_western: str = ""


class LunarDate(SMBaseModel):
    """农历日期信息。"""

    year: int
    month: int
    day: int
    is_leap_month: bool = False
    text: str = Field(description="如 二〇〇一年七月初九")
    month_cn: str = ""
    day_cn: str = ""
    zodiac: str = Field(default="", description="生肖")


class JieQiInfo(SMBaseModel):
    """节气信息。"""

    name: str
    prev_name: str = ""
    prev_at: datetime | None = None
    next_name: str = ""
    next_at: datetime | None = None
    current_name: str = ""
    current_at: datetime | None = None
    # 距离上一个"节"的天数（用于月柱边界与节令深浅分析）
    days_from_prev_jie: float | None = None


class CalendarSnapshot(SMBaseModel):
    """CalendarEngine 的完整输出（某一时刻的历法快照）。

    注意：``raw_source`` 保存第三方原始文本，仅用于审计与调试；
    业务逻辑必须只读上面的结构化字段。
    """

    engine_id: str = "calendar"
    engine_version: str = ""
    availability: Availability = Availability.OK

    solar: SolarDate
    lunar: LunarDate

    year_ganzhi: GanZhi = Field(description="年柱干支（立春换年）")
    month_ganzhi: GanZhi = Field(description="月柱干支（节气换月）")
    day_ganzhi: GanZhi
    hour_ganzhi: GanZhi

    jieqi: JieQiInfo = Field(default_factory=lambda: JieQiInfo(name=""))

    # 黄历类字段
    duty_officer: str = Field(default="", description="建除十二值")
    day_tian_shen: str = Field(default="", description="十二神（青龙/明堂/…）")
    day_tian_shen_type: str = Field(default="", description="黄道 / 黑道")
    day_tian_shen_luck: str = Field(default="", description="吉 / 凶")
    xiu: str = Field(default="", description="二十八宿")
    xiu_luck: str = Field(default="")
    chong_desc: str = Field(default="", description="冲煞描述，如 (丙辰)龙")
    sha_direction: str = Field(default="", description="煞方")
    pengzu_gan: str = Field(default="")
    pengzu_zhi: str = Field(default="")
    cai_shen_direction: str = Field(default="")
    xi_shen_direction: str = Field(default="")
    fu_shen_direction: str = Field(default="")
    tai_shen: str = Field(default="")
    day_yi: list[str] = Field(default_factory=list, description="宜")
    day_ji: list[str] = Field(default_factory=list, description="忌")

    assumptions: list[str] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    source: SourceRef = Field(default_factory=lambda: SourceRef(source="lunar-python"))

    raw_source: dict = Field(default_factory=dict, description="第三方引擎原始输出（审计用）")


class HuangliDay(SMBaseModel):
    """单日黄历（HuangliEngine 输出）。"""

    date: date
    solar_text: str = ""
    lunar_text: str = ""
    year_ganzhi: str = ""
    month_ganzhi: str = ""
    day_ganzhi: str = ""
    hour_ganzhi: str = ""
    jieqi: str = ""
    zodiac: str = ""
    day_nayin: str = ""
    month_nayin: str = ""
    year_nayin: str = ""

    duty_officer: str = ""
    day_tian_shen: str = ""
    day_tian_shen_type: str = ""
    day_tian_shen_luck: str = ""
    xiu: str = ""
    xiu_luck: str = ""
    chong_desc: str = ""
    sha_direction: str = ""
    pengzu_gan: str = ""
    pengzu_zhi: str = ""
    cai_shen_direction: str = ""
    xi_shen_direction: str = ""
    fu_shen_direction: str = ""
    tai_shen: str = ""
    day_yi: list[str] = Field(default_factory=list)
    day_ji: list[str] = Field(default_factory=list)
    is_trading_day: bool | None = None


class HuangliSnapshot(SMBaseModel):
    """HuangliEngine 的完整输出（含原始盘面与版本信息）。"""

    engine_id: str = "huangli"
    engine_version: str = ""
    config_version: str = ""
    availability: Availability = Availability.OK
    calculated_at: datetime = Field(default_factory=datetime.now)

    primary: HuangliDay
    days: list[HuangliDay] = Field(default_factory=list, description="查询窗口内的日历")

    assumptions: list[str] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)
    source: SourceRef = Field(default_factory=lambda: SourceRef(source="lunar-python"))

    raw_huangli: dict = Field(default_factory=dict, description="原始黄历数据（一等数据，必须落库）")
