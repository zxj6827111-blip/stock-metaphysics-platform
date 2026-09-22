"""术数基础常量表（干支 / 五行 / 十神 / 藏干 / 刑冲合害）。

设计原则
--------
1. 本模块只放**静态查表数据**与**纯函数**，不依赖任何第三方库，便于单元测试。
2. 排盘本身（历法换算、节气、纳音）不在这里实现 —— 那由 CalendarEngine 经
   lunar-python adapter 提供。这里只提供干支之间的**关系运算**，
   这类关系（如十神、六冲）属于命理定义，不是历法，必须由本项目自己保证一致。
3. 所有表项均为传统命理通行定义，流派差异处显式标注。
"""

from __future__ import annotations

from enum import Enum

# ---------------------------------------------------------------------------
# 天干 / 地支
# ---------------------------------------------------------------------------

HEAVENLY_STEMS: tuple[str, ...] = ("甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸")
EARTHLY_BRANCHES: tuple[str, ...] = (
    "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥",
)

STEM_INDEX: dict[str, int] = {s: i for i, s in enumerate(HEAVENLY_STEMS)}
BRANCH_INDEX: dict[str, int] = {b: i for i, b in enumerate(EARTHLY_BRANCHES)}

# 天干阴阳：甲丙戊庚壬为阳，乙丁己辛癸为阴
STEM_YANG: dict[str, bool] = {s: (i % 2 == 0) for i, s in enumerate(HEAVENLY_STEMS)}

# 地支阴阳：子寅辰午申戌为阳，丑卯巳未酉亥为阴
BRANCH_YANG: dict[str, bool] = {b: (i % 2 == 0) for i, b in enumerate(EARTHLY_BRANCHES)}

# 地支生肖
BRANCH_ZODIAC: dict[str, str] = dict(
    zip(EARTHLY_BRANCHES, ("鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"), strict=True)
)

# 地支对应时辰范围（用于校验与展示）
BRANCH_HOUR_RANGE: dict[str, tuple[int, int]] = {
    "子": (23, 1), "丑": (1, 3), "寅": (3, 5), "卯": (5, 7),
    "辰": (7, 9), "巳": (9, 11), "午": (11, 13), "未": (13, 15),
    "申": (15, 17), "酉": (17, 19), "戌": (19, 21), "亥": (21, 23),
}


class WuXing(str, Enum):
    """五行。"""

    WOOD = "木"
    FIRE = "火"
    EARTH = "土"
    METAL = "金"
    WATER = "水"


WU_XING_ORDER: tuple[str, ...] = ("木", "火", "土", "金", "水")

# 天干五行
STEM_WUXING: dict[str, str] = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# 地支五行（本气）
BRANCH_WUXING: dict[str, str] = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 五行相生：生我者为母，我生者为子
WUXING_GENERATES: dict[str, str] = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
WUXING_GENERATED_BY: dict[str, str] = {v: k for k, v in WUXING_GENERATES.items()}

# 五行相克
WUXING_OVERCOMES: dict[str, str] = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
WUXING_OVERCOME_BY: dict[str, str] = {v: k for k, v in WUXING_OVERCOMES.items()}

# 五行颜色（前端使用，Token 语义，不做吉凶染色）
WUXING_COLOR_KEY: dict[str, str] = {
    "木": "wood", "火": "fire", "土": "earth", "金": "metal", "水": "water",
}


# ---------------------------------------------------------------------------
# 地支藏干（本气 / 中气 / 余气）
#   顺序即传统权重顺序：index 0 为本气。
# ---------------------------------------------------------------------------

BRANCH_HIDDEN_STEMS: dict[str, tuple[str, ...]] = {
    "子": ("癸",),
    "丑": ("己", "癸", "辛"),
    "寅": ("甲", "丙", "戊"),
    "卯": ("乙",),
    "辰": ("戊", "乙", "癸"),
    "巳": ("丙", "庚", "戊"),
    "午": ("丁", "己"),
    "未": ("己", "丁", "乙"),
    "申": ("庚", "壬", "戊"),
    "酉": ("辛",),
    "戌": ("戊", "辛", "丁"),
    "亥": ("壬", "甲"),
}

# 藏干权重（本气 0.6 / 中气 0.3 / 余气 0.1；单一藏干取 1.0）
# 说明：这是本项目用于"五行力量估算"的工程近似，不是传统定论，
# 因子层会以 rule_version 标记，并接受历史数据检验。
HIDDEN_STEM_WEIGHTS: tuple[float, ...] = (0.6, 0.3, 0.1)


def hidden_stem_weight(pos: int, total: int) -> float:
    """返回第 pos 个藏干的权重（本气/中气/余气）。"""
    if total == 1:
        return 1.0
    if total == 2:
        return (0.7, 0.3)[pos]
    return HIDDEN_STEM_WEIGHTS[pos] if pos < 3 else 0.0


# ---------------------------------------------------------------------------
# 十神
# ---------------------------------------------------------------------------

# 十神分类
TEN_GOD_GROUP: dict[str, str] = {
    "比肩": "比劫", "劫财": "比劫",
    "食神": "食伤", "伤官": "食伤",
    "偏财": "财星", "正财": "财星",
    "七杀": "官杀", "正官": "官杀",
    "偏印": "印星", "正印": "印星",
}

TEN_GODS: tuple[str, ...] = (
    "比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印",
)


def ten_god(day_stem: str, other_stem: str) -> str:
    """计算 ``other_stem`` 相对日主 ``day_stem`` 的十神。

    规则（子平通行）：
      - 同我五行：同性 = 比肩，异性 = 劫财
      - 我生五行：同性 = 食神，异性 = 伤官
      - 我克五行：同性 = 偏财，异性 = 正财
      - 克我五行：同性 = 七杀，异性 = 正官
      - 生我五行：同性 = 偏印，异性 = 正印
    """
    if day_stem not in STEM_WUXING or other_stem not in STEM_WUXING:
        raise ValueError(f"非法天干: {day_stem!r} / {other_stem!r}")

    dw, ow = STEM_WUXING[day_stem], STEM_WUXING[other_stem]
    same_polarity = STEM_YANG[day_stem] == STEM_YANG[other_stem]

    if dw == ow:
        return "比肩" if same_polarity else "劫财"
    if WUXING_GENERATES[dw] == ow:
        return "食神" if same_polarity else "伤官"
    if WUXING_OVERCOMES[dw] == ow:
        return "偏财" if same_polarity else "正财"
    if WUXING_OVERCOME_BY[dw] == ow:
        return "七杀" if same_polarity else "正官"
    if WUXING_GENERATED_BY[dw] == ow:
        return "偏印" if same_polarity else "正印"
    raise ValueError(f"无法判定十神: 日主 {day_stem} / 对象 {other_stem}")


# ---------------------------------------------------------------------------
# 刑冲合害
# ---------------------------------------------------------------------------

# 地支六冲
BRANCH_SIX_CLASH: tuple[tuple[str, str], ...] = (
    ("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
)

# 地支六合（附化气五行，传统说法，仅作为结构标签使用）
BRANCH_SIX_HARMONY: dict[tuple[str, str], str] = {
    ("子", "丑"): "土", ("寅", "亥"): "木", ("卯", "戌"): "火",
    ("辰", "酉"): "金", ("巳", "申"): "水", ("午", "未"): "土",
}

# 地支三合局
BRANCH_TRIPLE_HARMONY: dict[tuple[str, str, str], str] = {
    ("申", "子", "辰"): "水",
    ("亥", "卯", "未"): "木",
    ("寅", "午", "戌"): "火",
    ("巳", "酉", "丑"): "金",
}

# 地支三会方局
BRANCH_TRIPLE_MEETING: dict[tuple[str, str, str], str] = {
    ("寅", "卯", "辰"): "木",
    ("巳", "午", "未"): "火",
    ("申", "酉", "戌"): "金",
    ("亥", "子", "丑"): "水",
}

# 地支相刑（子平通行分组；含自刑）
BRANCH_PUNISHMENTS: tuple[tuple[str, ...], ...] = (
    ("寅", "巳", "申"),   # 无恩之刑
    ("丑", "戌", "未"),   # 恃势之刑
    ("子", "卯"),         # 无礼之刑
    ("辰", "辰"), ("午", "午"), ("酉", "酉"), ("亥", "亥"),  # 自刑
)

# 地支相害（六害）
BRANCH_SIX_HARM: tuple[tuple[str, str], ...] = (
    ("子", "未"), ("丑", "午"), ("寅", "巳"),
    ("卯", "辰"), ("申", "亥"), ("酉", "戌"),
)

# 地支六破。
#
# 六破存在流派差异；本项目固定采用这一组关系，并由
# ``relation_rule_version`` 记录口径。它只作为结构标签，不推导涨跌。
BRANCH_SIX_BREAK: tuple[tuple[str, str], ...] = (
    ("子", "酉"), ("丑", "辰"), ("寅", "亥"),
    ("卯", "午"), ("巳", "申"), ("未", "戌"),
)

# 天干五合（附化气五行）
STEM_FIVE_HARMONY: dict[tuple[str, str], str] = {
    ("甲", "己"): "土", ("乙", "庚"): "金", ("丙", "辛"): "水",
    ("丁", "壬"): "木", ("戊", "癸"): "火",
}

# 天干相冲
STEM_CLASH: tuple[tuple[str, str], ...] = (
    ("甲", "庚"), ("乙", "辛"), ("丙", "壬"), ("丁", "癸"),
)

# 十二长生序（阳干顺行，阴干逆行）
TWELVE_STAGES: tuple[str, ...] = (
    "长生", "沐浴", "冠带", "临官", "帝旺", "衰",
    "病", "死", "墓", "绝", "胎", "养",
)

# 阳干长生起点（阴干按通行规则另表给出）
STEM_CHANGSHENG_START: dict[str, str] = {
    "甲": "亥", "丙": "寅", "戊": "寅", "庚": "巳", "壬": "申",
    "乙": "午", "丁": "酉", "己": "酉", "辛": "子", "癸": "卯",
}


def _build_six_clash_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for a, b in BRANCH_SIX_CLASH:
        idx[a] = b
        idx[b] = a
    return idx


def _build_six_harmony_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for (a, b), _ in BRANCH_SIX_HARMONY.items():
        idx[a] = b
        idx[b] = a
    return idx


def _build_six_harm_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for a, b in BRANCH_SIX_HARM:
        idx[a] = b
        idx[b] = a
    return idx


def _build_six_break_index() -> dict[str, str]:
    idx: dict[str, str] = {}
    for a, b in BRANCH_SIX_BREAK:
        idx[a] = b
        idx[b] = a
    return idx


BRANCH_CLASH_OF: dict[str, str] = _build_six_clash_index()
BRANCH_HARMONY_OF: dict[str, str] = _build_six_harmony_index()
BRANCH_HARM_OF: dict[str, str] = _build_six_harm_index()
BRANCH_BREAK_OF: dict[str, str] = _build_six_break_index()


def twelve_stage(day_stem: str, branch: str) -> str:
    """计算 ``branch`` 相对日干 ``day_stem`` 的十二长生（旺衰）阶段。

    规则：阳干顺行、阴干逆行，从各自长生位起算。
    """
    if day_stem not in STEM_CHANGSHENG_START:
        raise ValueError(f"非法天干: {day_stem!r}")
    if branch not in BRANCH_INDEX:
        raise ValueError(f"非法地支: {branch!r}")

    start = STEM_CHANGSHENG_START[day_stem]
    start_idx = BRANCH_INDEX[start]
    cur = BRANCH_INDEX[branch]
    forward = STEM_YANG[day_stem]
    step = (cur - start_idx) % 12 if forward else (start_idx - cur) % 12
    return TWELVE_STAGES[step]


# 建除十二值（黄历，按日支相对月支确定；顺序固定）
TWELVE_DUTY_OFFICERS: tuple[str, ...] = (
    "建", "除", "满", "平", "定", "执", "破", "危", "成", "收", "开", "闭",
)

# 黄道 / 黑道 十二神（青龙起例）
DAY_TIAN_SHEN_LUCK: dict[str, str] = {
    "青龙": "黄道", "明堂": "黄道", "金匮": "黄道", "天德": "黄道",
    "玉堂": "黄道", "司命": "黄道",
    "天刑": "黑道", "朱雀": "黑道", "白虎": "黑道", "天牢": "黑道",
    "玄武": "黑道", "勾陈": "黑道",
}


# ---------------------------------------------------------------------------
# 六十甲子纳音（传统固定映射，无流派分歧）
# ---------------------------------------------------------------------------
#
# 为什么放在这里：lunar-python 的 ``getYearNaYin`` 等接口与
# ``getYearInGanZhiExact`` 存在口径差（见 docs/calculation-differences-phase1.md），
# 会导致同一柱"干支是甲辰、纳音却是癸卯的金箔金"这种内部矛盾。
# 纳音是干支的纯函数，本项目自掌，保证"柱与纳音永不冲突"。

_NAYIN_SEQUENCE = (
    "海中金", "炉中火", "大林木", "路旁土", "剑锋金", "山头火",
    "涧下水", "城头土", "白蜡金", "杨柳木", "泉中水", "屋上土",
    "霹雳火", "松柏木", "长流水", "沙中金", "山下火", "平地木",
    "壁上土", "金箔金", "覆灯火", "天河水", "大驿土", "钗钏金",
    "桑柘木", "大溪水", "沙中土", "天上火", "石榴木", "大海水",
)

_SIXTY_JIAZI = tuple(
    HEAVENLY_STEMS[i % 10] + EARTHLY_BRANCHES[i % 12] for i in range(60)
)

#: 六十甲子 → 纳音（如 甲辰 → 覆灯火）
NAYIN_OF: dict[str, str] = {
    jiazi: _NAYIN_SEQUENCE[i // 2] for i, jiazi in enumerate(_SIXTY_JIAZI)
}


def nayin_of(ganzhi_text: str) -> str:
    """由干支文本查纳音；无法识别返回空串（不猜测）。"""
    return NAYIN_OF.get(ganzhi_text, "")


__all__ = [
    "HEAVENLY_STEMS", "EARTHLY_BRANCHES", "STEM_INDEX", "BRANCH_INDEX",
    "STEM_YANG", "BRANCH_YANG", "BRANCH_ZODIAC", "BRANCH_HOUR_RANGE",
    "WuXing", "WU_XING_ORDER", "STEM_WUXING", "BRANCH_WUXING", "WUXING_COLOR_KEY",
    "WUXING_GENERATES", "WUXING_GENERATED_BY", "WUXING_OVERCOMES", "WUXING_OVERCOME_BY",
    "BRANCH_HIDDEN_STEMS", "HIDDEN_STEM_WEIGHTS", "hidden_stem_weight",
    "TEN_GODS", "TEN_GOD_GROUP", "ten_god",
    "BRANCH_SIX_CLASH", "BRANCH_SIX_HARMONY", "BRANCH_TRIPLE_HARMONY",
    "BRANCH_TRIPLE_MEETING", "BRANCH_PUNISHMENTS", "BRANCH_SIX_HARM", "BRANCH_SIX_BREAK",
    "STEM_FIVE_HARMONY", "STEM_CLASH",
    "BRANCH_CLASH_OF", "BRANCH_HARMONY_OF", "BRANCH_HARM_OF", "BRANCH_BREAK_OF",
    "TWELVE_STAGES", "twelve_stage", "STEM_CHANGSHENG_START",
    "TWELVE_DUTY_OFFICERS", "DAY_TIAN_SHEN_LUCK",
    "NAYIN_OF", "nayin_of",
]
