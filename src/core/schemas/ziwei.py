"""紫微斗数领域模型（本项目自有；第三方对象不得出现在这里 —— ADR-0001）。

设计纪律
--------
1. **盘面是一等数据**：``ZiweiChart`` 完整保留十二宫 / 星曜 / 四化 / 三方四正 /
   大限小限 / 流年流月流日，落 ``chart_artifact.raw_chart``，未来引擎升级后可逐字段对比。
2. **不与八字混盘**：紫微有自己独立的 ``FiYue``/命身宫/五行局体系，禁止把两套盘
   塞进同一个模型，也禁止用八字的「旺衰」概念解释紫微。
3. **不做业务判断**：本模块只描述盘面。方向、分数、共识一律由因子层与研究层产出。
4. **股票无性别**：见 ``variant_mode`` 与 ``variant_basis``，禁止默认男/女。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from src.core.schemas.common import (
    Assumption,
    SMBaseModel,
    VariantMode,
    Warning_,
)

# ---------------------------------------------------------------------------
# 星曜 / 宫位
# ---------------------------------------------------------------------------


class ZiweiStar(SMBaseModel):
    """一颗星曜。"""

    name: str
    type: str = Field(
        default="",
        description="iztro 分类：major / soft / tough / lucun / tianma / flower / helper / adjective",
    )
    brightness: str = Field(default="", description="庙 / 旺 / 得 / 利 / 平 / 不 / 陷；无庙旺概念时为空")
    mutagen: str = Field(default="", description="生年四化：禄 / 权 / 科 / 忌；无则为空")
    scope: str = Field(default="origin", description="origin / decadal / yearly / monthly / daily / hourly")


class ZiweiPalace(SMBaseModel):
    """十二宫之一。

    ``index`` 固定为**地支顺序**：0 = 寅、1 = 卯 … 11 = 丑（紫微命宫由寅起数，
    因此这是唯一稳定的宫位坐标系）。
    """

    index: int = Field(ge=0, le=11)
    name: str = Field(description="宫名：命宫 / 兄弟 / 夫妻 / 子女 / 财帛 / 疾厄 / 迁移 / 仆役 / 官禄 / 田宅 / 福德 / 父母")
    heavenly_stem: str = ""
    earthly_branch: str = ""
    is_body_palace: bool = False
    is_original_palace: bool = Field(default=False, description="是否为生年命宫（来因宫）")
    major_stars: list[ZiweiStar] = Field(default_factory=list)
    minor_stars: list[ZiweiStar] = Field(default_factory=list)
    adjective_stars: list[ZiweiStar] = Field(default_factory=list)
    changsheng12: str = ""
    boshi12: str = ""
    jiangqian12: str = ""
    suiqian12: str = ""
    decadal_range: list[int] = Field(default_factory=list, description="大限年龄区间 [起, 止]")
    ages: list[int] = Field(default_factory=list, description="小限年龄列表")
    trine_indices: list[int] = Field(
        default_factory=list,
        description="三方四正：本宫 / 对宫 / 财帛位 / 官禄位 的宫位 index",
    )

    def all_stars(self) -> list[ZiweiStar]:
        return [*self.major_stars, *self.minor_stars, *self.adjective_stars]

    def star_names(self) -> set[str]:
        return {s.name for s in self.all_stars()}

    def has_any(self, names: set[str]) -> bool:
        return bool(self.star_names() & names)


class ZiweiDecadal(SMBaseModel):
    """大限一项（按宫位索引）。"""

    palace_index: int = Field(ge=0, le=11)
    palace_name: str = ""
    range: list[int] = Field(default_factory=list)
    heavenly_stem: str = ""
    earthly_branch: str = ""


class ZiweiHoroscopeSection(SMBaseModel):
    """一层运限（大限 / 小限 / 流年 / 流月 / 流日 / 流时）。

    ``palace_names[i]`` 表示**原盘第 i 宫**在该层运限中扮演的宫名；
    ``stars[i]`` 是落在原盘第 i 宫的该层运限星曜（若有该层流曜）。
    这与 iztro 的数组约定一致，也是唯一不歧义的表示法。

    ⚠️ **已知缺失（如实保留，不推算补全）**：``age``（小限）层在 iztro 中
    **不提供 ``stars``**，因此其 ``stars`` 为空列表。下游（因子层）必须把
    "小限无流曜"当作事实处理，不得用其他层的星曜代替。
    """

    scope: str = Field(description="decadal / age / yearly / monthly / daily / hourly")
    index: int = Field(default=-1, description="该层运限命宫落在原盘的宫位 index")
    heavenly_stem: str = ""
    earthly_branch: str = ""
    name: str = ""
    mutagen: list[str] = Field(default_factory=list, description="运限四化，顺序固定 [禄, 权, 科, 忌]")
    palace_names: list[str] = Field(default_factory=list)
    stars: list[list[ZiweiStar]] = Field(
        default_factory=list,
        description="12 项（与 palaces 同序）；小限层为空列表（iztro 不提供该层流曜）",
    )
    nominal_age: int | None = Field(
        default=None, description="小限虚岁（仅 age 层有值，其余层为 null）",
    )

    def palace_of(self, natal_index: int) -> str:
        """原盘第 ``natal_index`` 宫在该层运限中的宫名。"""
        if 0 <= natal_index < len(self.palace_names):
            return self.palace_names[natal_index]
        return ""

    def natal_index_of(self, horoscope_palace_name: str) -> int:
        """该层运限中名为 ``horoscope_palace_name`` 的宫落在原盘哪一宫；找不到返回 -1。"""
        try:
            return self.palace_names.index(horoscope_palace_name)
        except ValueError:
            return -1


class ZiweiHoroscope(SMBaseModel):
    """一次排盘在某个 ``as_of`` 上的运限快照。"""

    solar_date: str = ""
    time_index: int = 0
    decadal: ZiweiHoroscopeSection | None = None
    age: ZiweiHoroscopeSection | None = None
    yearly: ZiweiHoroscopeSection | None = None
    monthly: ZiweiHoroscopeSection | None = None
    daily: ZiweiHoroscopeSection | None = None
    hourly: ZiweiHoroscopeSection | None = None


class ZiweiMutagen(SMBaseModel):
    """生年四化落宫。"""

    mutagen: str = Field(description="禄 / 权 / 科 / 忌")
    star: str
    palace_index: int = Field(ge=0, le=11)
    palace_name: str = ""


# ---------------------------------------------------------------------------
# 主模型
# ---------------------------------------------------------------------------


class ZiweiChart(SMBaseModel):
    """紫微斗数完整盘面（落 ``chart_artifact.raw_chart``）。"""

    stock_code: str = ""
    birth_datetime: datetime | None = None
    as_of: datetime | None = None

    # --- 排盘输入 ---
    solar_date: str = ""
    lunar_date: str = ""
    chinese_date: str = Field(default="", description="出生四柱（由紫微历法给出，仅作对拍用）")
    time_index: int = Field(default=0, ge=0, le=12)
    time_name: str = ""
    time_range: str = ""

    # --- 性别假设（股票无真实性别） ---
    variant_mode: VariantMode = VariantMode.NOT_APPLICABLE
    variant_basis: str = Field(default="", description="variant 语义说明（必须可读）")
    gender_parameter: str = Field(
        default="",
        description="为实现该 variant 实际传入的性别参数——**仅供审计**，不代表股票有性别",
    )

    # --- 命身 ---
    soul: str = Field(default="", description="命主")
    body: str = Field(default="", description="身主")
    five_elements_class: str = Field(default="", description="五行局，如 木三局")
    soul_palace_branch: str = ""
    soul_palace_index: int = Field(default=-1, description="命宫在原盘中的宫位 index")
    body_palace_index: int = Field(default=-1, description="身宫在原盘中的宫位 index")
    sign: str = ""
    zodiac: str = Field(default="", description="生肖（仅展示，不进入因子）")

    # --- 盘面主体 ---
    natal_mutagens: list[ZiweiMutagen] = Field(default_factory=list, description="生年四化，顺序 禄权科忌")
    palaces: list[ZiweiPalace] = Field(default_factory=list, description="固定 12 个，index 0 = 寅")
    decadals: list[ZiweiDecadal] = Field(default_factory=list)
    horoscope: ZiweiHoroscope | None = None

    # --- 元信息 ---
    engine_version: str = ""
    config_version: str = ""
    third_party: str = ""
    calculated_at: datetime = Field(default_factory=datetime.now)
    assumptions: list[Assumption] = Field(default_factory=list)
    warnings: list[Warning_] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # 查询辅助（确定性、纯函数，便于因子层复用）
    # ------------------------------------------------------------------
    def palace_by_name(self, name: str) -> ZiweiPalace | None:
        for p in self.palaces:
            if p.name == name:
                return p
        return None

    def palace_at(self, index: int) -> ZiweiPalace | None:
        if 0 <= index < len(self.palaces):
            return self.palaces[index]
        return None

    def trine_of(self, index: int) -> list[ZiweiPalace]:
        """三方四正：本宫 / 对宫 / 财帛位 / 官禄位。"""
        base = self.palace_at(index)
        if base is None:
            return []
        return [p for p in (self.palace_at(i) for i in base.trine_indices) if p is not None]

    def mutagen_palace_index(self, mutagen: str) -> int:
        """生年四化中某个化（禄/权/科/忌）落在的宫位 index；无则 -1。"""
        for m in self.natal_mutagens:
            if m.mutagen == mutagen:
                return m.palace_index
        return -1

    def palace_names(self) -> list[str]:
        return [p.name for p in self.palaces]


__all__ = [
    "ZiweiStar", "ZiweiPalace", "ZiweiDecadal", "ZiweiHoroscopeSection",
    "ZiweiHoroscope", "ZiweiMutagen", "ZiweiChart",
]
