"""黄历日课分类（版本化规则层）。

为什么单独一个模块
------------------
参考设计把日期卡分成「吉 / 平 / 凶」三级。**本项目后端只有两级**：
``HuangliDay.day_tian_shen_luck`` 来自 lunar-python 的 ``getDayTianShenLuck()``，
取值集合实测为 {吉, 凶}（十二神所属黄黑道的派生结论），不存在「平」。

按 AGENTS.md §13「不得编造」与用户要求「不能为匹配图片随意补出『平』」，
本模块**只产出两级**，并把"确实没有第三类"这件事写进响应
（``third_category_supported=False`` + 差异说明），由前端如实展示。

规则的三条纪律
--------------
1. **只做映射，不做再判断**：分类直接来自引擎字段，本模块不引入新的术数判断；
2. **不可用时返回 None**，绝不用「吉」或「平」占位（AGENTS.md §2.4）；
3. **口径版本化**：改动映射必须提升 ``HUANGLI_DAY_CLASS_VERSION``，
   否则"为什么同一天的类别变了"无法追溯。
"""

from __future__ import annotations

from typing import Any

from src.core.schemas.calendar import HuangliDay

#: 分类口径版本。**改动映射规则必须提升它。**
HUANGLI_DAY_CLASS_VERSION = "huangli-day-class-v1"

#: 引擎字段 → 分类码。只映射已存在的取值，不新增类别。
_LUCK_TO_CLASS: dict[str, tuple[str, str]] = {
    "吉": ("auspicious", "吉"),
    "凶": ("inauspicious", "凶"),
}

#: 分类依据（写入响应，便于追溯这条分类是从哪个字段推出来的）
CLASS_BASIS_FIELD = "HuangliDay.day_tian_shen_luck"
CLASS_BASIS_SOURCE = "lunar-python getDayTianShenLuck()"


def classify_day(day: HuangliDay) -> dict[str, Any]:
    """把一天的传统黄历结果映射成版本化的研究分类。

    Returns:
        ``{class_code, class_label_cn, class_basis_cn, class_available}``；
        引擎未给出吉凶时 ``class_code`` / ``class_label_cn`` 为 ``None``
        且 ``class_available=False`` —— **不猜测、不用「平」补位**。
    """
    luck = (day.day_tian_shen_luck or "").strip()
    mapped = _LUCK_TO_CLASS.get(luck)
    tian_shen = day.day_tian_shen or "（未给出）"
    shen_type = day.day_tian_shen_type or "（未给出）"
    if mapped is None:
        return {
            "class_code": None,
            "class_label_cn": None,
            "class_available": False,
            "class_basis_cn": (
                f"十二神「{tian_shen}」的吉凶字段为空或不在此口径的取值范围内，"
                "本次不给出分类（不以「平」或「吉」占位）。"
            ),
        }
    code, label = mapped
    return {
        "class_code": code,
        "class_label_cn": label,
        # 依据里带上原始字段值，读者可以自己核对分类是怎么来的
        "class_available": True,
        "class_basis_cn": f"十二神「{tian_shen}」属{shen_type}，通书口径为「{luck}」。",
    }


def class_rule_descriptor() -> dict[str, Any]:
    """分类口径说明（随每次响应返回，供页面与审计引用）。"""
    return {
        "rule_id": HUANGLI_DAY_CLASS_VERSION,
        "basis_field": CLASS_BASIS_FIELD,
        "basis_source": CLASS_BASIS_SOURCE,
        "categories": [
            {"code": "auspicious", "label_cn": "吉"},
            {"code": "inauspicious", "label_cn": "凶"},
        ],
        "third_category_supported": False,
        "difference_note_cn": (
            "视觉稿的日期卡使用「吉 / 平 / 凶」三级。本系统沿用后端通书口径，"
            "该口径只给出「吉 / 凶」两级；没有可解释、可版本化的第三类规则，"
            "因此不产出「平」。分类缺失时显式标注「未给出分类」，不以「平」补位。"
        ),
        "not_a_recommendation_cn": (
            "分类描述的是传统择日观念，不是买入/卖出建议；"
            "它也不是对股票收益的判断，历史表现属于研究统计，见对应分区。"
        ),
    }


def day_payload(day: HuangliDay, *, weekday_cn: str) -> dict[str, Any]:
    """日期卡的完整序列化（传统字段 + 分类）。

    ``day_yi`` / ``day_ji`` 原样保留通书条目 —— 页面展示它们时**不加任何
    "宜交易 / 忌追涨"式的行情改写**（见用户要求 §四.7）。
    """
    return {
        "date": day.date.isoformat(),
        "weekday_cn": weekday_cn,
        "lunar_text": day.lunar_text,
        "year_ganzhi": day.year_ganzhi,
        "month_ganzhi": day.month_ganzhi,
        "day_ganzhi": day.day_ganzhi,
        "jieqi": day.jieqi,
        "zodiac": day.zodiac,
        "duty_officer": day.duty_officer,
        "day_tian_shen": day.day_tian_shen,
        "day_tian_shen_type": day.day_tian_shen_type,
        "day_tian_shen_luck": day.day_tian_shen_luck,
        "xiu": day.xiu,
        "xiu_luck": day.xiu_luck,
        "day_nayin": day.day_nayin,
        "chong_desc": day.chong_desc,
        "sha_direction": day.sha_direction,
        "pengzu_gan": day.pengzu_gan,
        "pengzu_zhi": day.pengzu_zhi,
        "cai_shen_direction": day.cai_shen_direction,
        "xi_shen_direction": day.xi_shen_direction,
        "fu_shen_direction": day.fu_shen_direction,
        "day_yi": list(day.day_yi),
        "day_ji": list(day.day_ji),
        **classify_day(day),
    }


__all__ = [
    "HUANGLI_DAY_CLASS_VERSION",
    "CLASS_BASIS_FIELD",
    "CLASS_BASIS_SOURCE",
    "classify_day",
    "class_rule_descriptor",
    "day_payload",
]
