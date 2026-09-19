"""紫微斗数静态查表与映射（**本项目自持**，不依赖 iztro 的类型系统）。

为什么自持
---------
iztro 给出的是 `type: "major" | "soft" | "tough" | "lucun" | ...` 这样的工程分类，
而研究需要的分类是**术数语义**分类（主星 / 六吉 / 六煞 / 桃花 / 禄马）。

两者不能互相替代：iztro 的分类会随版本变化，而因子定义必须稳定。
因此本项目在 Adapter 输出之后，用本文件里的表做二次归类 ——
这样 iztro 升级不会静默改变因子语义。

**注意**：本文件只做"分类"，不做"吉凶判断"。哪一类偏正向是先验的**研究假设**
（`direction`），必须经历史回测检验，且写入 `research_mapping` 版本号。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 宫位坐标系
# ---------------------------------------------------------------------------

#: 十二宫地支顺序（index 0 = 寅）。紫微命宫由寅起数，这是唯一稳定的宫位坐标。
ZIWEI_PALACE_BRANCHES: tuple[str, ...] = (
    "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑",
)

#: 十二宫名（紫微固定宫名，用于校验）
ZIWEI_PALACE_NAMES: tuple[str, ...] = (
    "命宫", "兄弟", "夫妻", "子女", "财帛", "疾厄",
    "迁移", "仆役", "官禄", "田宅", "福德", "父母",
)

#: 十二宫名 → 统一别名（iztro 使用「仆役/交友」等异名，统一到本项目口径）
PALACE_ALIASES: dict[str, str] = {
    "仆役": "仆役", "交友": "仆役", "奴仆": "仆役",
    "官禄": "官禄", "事业": "官禄",
    "财帛": "财帛", "财": "财帛",
}


def canonical_palace_name(name: str) -> str:
    return PALACE_ALIASES.get(name, name)


def trine_indices(index: int) -> list[int]:
    """三方四正：本宫 / 对宫(+6) / 财帛位(+8) / 官禄位(+4)，对 12 取模。

    该映射由紫微宫位结构决定（命-迁-财-官 构成三方四正），与 iztro 的
    ``surroundedPalaces`` 输出在 Golden Case 中逐宫对拍。
    """
    return [index, (index + 6) % 12, (index + 8) % 12, (index + 4) % 12]


# ---------------------------------------------------------------------------
# 星曜语义分类
# ---------------------------------------------------------------------------

#: 十四主星
MAJOR_STARS: frozenset[str] = frozenset({
    "紫微", "天机", "太阳", "武曲", "天同", "廉贞",
    "天府", "太阴", "贪狼", "巨门", "天相", "天梁", "七杀", "破军",
})

#: 六吉星（含禄存/天马常被并入"助曜"）
LUCKY_STARS: frozenset[str] = frozenset({
    "左辅", "右弼", "文昌", "文曲", "天魁", "天钺",
})

#: 禄马（财禄与驿动，传统视为助力）
WEALTH_MOVE_STARS: frozenset[str] = frozenset({"禄存", "天马"})

#: 六煞星
MALEFIC_STARS: frozenset[str] = frozenset({
    "擎羊", "陀罗", "火星", "铃星", "地空", "地劫",
})

#: 桃花星（传统视为情感/人际，股票研究里作为"波动/题材"的弱代理）
FLOWER_STARS: frozenset[str] = frozenset({
    "红鸾", "天喜", "咸池", "大耗", "天姚", "沐浴",
})

#: 四化顺序（固定）：化禄 / 化权 / 化科 / 化忌
MUTAGEN_ORDER: tuple[str, ...] = ("禄", "权", "科", "忌")

MUTAGEN_CN: dict[str, str] = {
    "禄": "化禄", "权": "化权", "科": "化科", "忌": "化忌",
}

#: 庙旺等级 → 序数（用于确定性数值化；"无"概念时用 0）
BRIGHTNESS_SCORE: dict[str, float] = {
    "庙": 1.0, "旺": 0.85, "得": 0.65, "利": 0.5,
    "平": 0.3, "不": 0.05, "陷": -0.2, "": 0.0,
}

#: 长生十二神顺序（阳男阴女顺行、阴男阳女逆行 —— 方向由 variant 决定）
TWELVE_STAGES_ZIWEI: tuple[str, ...] = (
    "长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养",
)

#: 五行局 → (局数, 纳音五行)，用于起运岁数
FIVE_ELEMENTS_CLASS: dict[str, tuple[int, str]] = {
    "水二局": (2, "水"), "木三局": (3, "木"), "金四局": (4, "金"),
    "土五局": (5, "土"), "火六局": (6, "火"),
}


def star_category(name: str) -> str:
    """把星名归类为本项目的语义类别（确定性查表，无第三方依赖）。

    返回：major / lucky / wealth_move / malefic / flower / adjective
    """
    if name in MAJOR_STARS:
        return "major"
    if name in LUCKY_STARS:
        return "lucky"
    if name in WEALTH_MOVE_STARS:
        return "wealth_move"
    if name in MALEFIC_STARS:
        return "malefic"
    if name in FLOWER_STARS:
        return "flower"
    return "adjective"


def brightness_score(name: str) -> float:
    return BRIGHTNESS_SCORE.get(name, 0.0)


__all__ = [
    "ZIWEI_PALACE_BRANCHES", "ZIWEI_PALACE_NAMES", "PALACE_ALIASES",
    "canonical_palace_name", "trine_indices",
    "MAJOR_STARS", "LUCKY_STARS", "WEALTH_MOVE_STARS", "MALEFIC_STARS", "FLOWER_STARS",
    "MUTAGEN_ORDER", "MUTAGEN_CN", "BRIGHTNESS_SCORE", "TWELVE_STAGES_ZIWEI",
    "FIVE_ELEMENTS_CLASS", "star_category", "brightness_score",
]
