"""紫微第二实现源（REFERENCE ONLY）—— 名称归一化。

为什么需要归一化
----------------
两个实现源的**字形与命名**不同，直接比字符串会得到一堆假差异：

* 中州派库（``fortel-ziweidoushu``）输出**繁体**（貪狼 / 命宮 / 財帛）；
  生产引擎（iztro）输出**简体**（贪狼 / 命宫 / 财帛）；
* 宫位别名：中州派用「交友 / 事業」，iztro 用「仆役 / 官禄」——
  同一宫位的不同习惯名，不是排盘差异。

归一化只做**字形与别名**的等价映射，**不做**语义近似（例如不会把「截路」与
「截空」视为同一神煞 —— 那属于命名约定差异，必须作为差异登记而不是抹平）。
"""

from __future__ import annotations

#: 繁体 → 简体（只覆盖本项目比较会用到的字，逐字可审计）
TRADITIONAL_TO_SIMPLIFIED: dict[str, str] = {
    "宮": "宫", "貞": "贞", "門": "门", "祿": "禄", "貪": "贪", "機": "机",
    "陽": "阳", "陰": "阴", "殺": "杀", "輔": "辅", "鈴": "铃", "羅": "罗",
    "馬": "马", "鉞": "钺", "軍": "军", "業": "业", "遷": "迁", "財": "财",
    "僕": "仆", "驛": "驿", "將": "将", "歲": "岁", "弔": "吊", "權": "权",
    "貴": "贵", "華": "华", "蓋": "盖", "壽": "寿", "虛": "虚",
    "鳳": "凤", "閣": "阁", "臺": "台", "剛": "刚", "劍": "剑",
    "龍": "龙", "紅": "红", "鸞": "鸾", "養": "养",
    "長": "长", "絕": "绝", "臨": "临", "衰": "衰", "旺": "旺", "墓": "墓",
    "死": "死", "病": "病", "胎": "胎", "帯": "带", "帶": "带", "冠": "冠",
    "沐": "沐", "浴": "浴", "帝": "帝",
}

#: 宫位别名 → 项目内标准宫名（与 ``ZiweiPalace.name`` 对齐）
PALACE_ALIASES: dict[str, str] = {
    "交友": "仆役",
    "奴仆": "仆役",
    "事業": "官禄",
    "事业": "官禄",
    "官祿": "官禄",
    "命宮": "命宫",
    "身宮": "身宫",
    "夫婦": "夫妻",
    "子女": "子女",
    "財帛": "财帛",
    "遷移": "迁移",
    "田宅": "田宅",
    "福德": "福德",
    "父母": "父母",
    "兄弟": "兄弟",
    "疾厄": "疾厄",
}

#: 地支/天干（字形一致，保留显式表以便测试断言）
BRANCHES: tuple[str, ...] = ("子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥")
STEMS: tuple[str, ...] = (
    "甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸",
)

#: 四化名（简体/繁体统一）
MUTAGEN_ALIASES: dict[str, str] = {"祿": "禄", "權": "权", "科": "科", "忌": "忌"}


def to_simplified(text: str) -> str:
    """逐字转换繁体 → 简体（未收录的字原样保留）。"""
    return "".join(TRADITIONAL_TO_SIMPLIFIED.get(ch, ch) for ch in str(text))


def normalize_name(text: str) -> str:
    """星曜 / 五行局 / 命主 等名称归一化（先简繁、去空白）。"""
    return to_simplified(str(text)).strip()


def normalize_palace(text: str) -> str:
    """宫名归一化：先简繁，再套别名表。"""
    simplified = normalize_name(text)
    return PALACE_ALIASES.get(simplified, simplified)


def normalize_mutagen(text: str) -> str:
    simplified = normalize_name(text)
    return MUTAGEN_ALIASES.get(simplified, simplified)


def branch_index_from_zi(branch: str) -> int:
    """地支 → ``子=0`` 索引。"""
    value = normalize_name(branch)
    if value not in BRANCHES:
        raise ValueError(f"未知地支：{branch}")
    return BRANCHES.index(value)


def project_index_from_branch(branch: str) -> int:
    """地支 → 项目内宫位索引（**index 0 = 寅**，与 ``ZiweiPalace.index`` 一致）。"""
    return (branch_index_from_zi(branch) - 2) % 12


__all__ = [
    "BRANCHES",
    "MUTAGEN_ALIASES",
    "PALACE_ALIASES",
    "STEMS",
    "TRADITIONAL_TO_SIMPLIFIED",
    "branch_index_from_zi",
    "normalize_mutagen",
    "normalize_name",
    "normalize_palace",
    "project_index_from_branch",
    "to_simplified",
]
