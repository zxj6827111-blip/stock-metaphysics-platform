"""黄历日课分类（版本化规则层）的契约测试。

锁定三条不可退让的语义：
1. **只有后端已有的类别**：吉 / 凶；**不得**为了贴合视觉稿补出「平」。
2. 引擎未给出吉凶时必须显式「未给出分类」，**不得用 0 / 「平」/「吉」占位**。
3. 分类依据必须可追溯（带原始十二神与黄黑道）。
"""

from __future__ import annotations

from datetime import date

from src.core.orchestration.huangli_day_class import (
    HUANGLI_DAY_CLASS_VERSION,
    class_rule_descriptor,
    classify_day,
    day_payload,
)
from src.core.schemas.calendar import HuangliDay


def _day(**kwargs) -> HuangliDay:
    base = {
        "date": date(2024, 11, 15),
        "day_ganzhi": "癸未",
        "day_tian_shen": "明堂",
        "day_tian_shen_type": "黄道",
        "day_tian_shen_luck": "吉",
    }
    base.update(kwargs)
    return HuangliDay(**base)


def test_classify_maps_engine_field_without_rejudging():
    info = classify_day(_day(day_tian_shen="明堂", day_tian_shen_type="黄道", day_tian_shen_luck="吉"))
    assert info["class_code"] == "auspicious"
    assert info["class_label_cn"] == "吉"
    assert info["class_available"] is True
    # 依据必须带原始字段值，读者能自己核对
    assert "明堂" in info["class_basis_cn"]
    assert "黄道" in info["class_basis_cn"]

    info = classify_day(_day(day_tian_shen="白虎", day_tian_shen_type="黑道", day_tian_shen_luck="凶"))
    assert info["class_code"] == "inauspicious"
    assert info["class_label_cn"] == "凶"


def test_missing_luck_never_invents_a_category():
    """引擎没给吉凶时不得猜测 —— 尤其不得补「平」。"""
    info = classify_day(_day(day_tian_shen_luck=""))
    assert info["class_code"] is None
    assert info["class_label_cn"] is None
    assert info["class_available"] is False
    assert info["class_label_cn"] != "平"


def test_unknown_luck_value_is_not_silently_reclassified():
    """出现未登记取值时按"未给出分类"处理，而不是就近归到吉或凶。"""
    info = classify_day(_day(day_tian_shen_luck="大吉"))
    assert info["class_code"] is None
    assert info["class_available"] is False


def test_rule_descriptor_declares_two_categories_and_the_difference():
    rule = class_rule_descriptor()
    assert rule["rule_id"] == HUANGLI_DAY_CLASS_VERSION
    labels = [c["label_cn"] for c in rule["categories"]]
    assert labels == ["吉", "凶"]
    assert rule["third_category_supported"] is False
    # 必须显式说明与视觉稿的差异，而不是悄悄少一类
    assert "平" in rule["difference_note_cn"]
    # 分类不是买卖建议
    assert "建议" in rule["not_a_recommendation_cn"]


def test_day_payload_keeps_traditional_yi_ji_verbatim():
    """通书宜忌原样保留，不得改写成"宜交易/忌追涨"之类的行情语。"""
    day = _day(day_yi=["祭祀", "祈福", "开光"], day_ji=["入宅", "词讼"])
    payload = day_payload(day, weekday_cn="星期五")
    assert payload["day_yi"] == ["祭祀", "祈福", "开光"]
    assert payload["day_ji"] == ["入宅", "词讼"]
    joined = " ".join(payload["day_yi"] + payload["day_ji"])
    for forbidden in ("买", "卖", "追涨", "抄底", "建仓"):
        assert forbidden not in joined
    assert payload["class_code"] == "auspicious"


def test_payload_is_json_safe():
    payload = day_payload(_day(), weekday_cn="星期五")
    assert payload["date"] == "2024-11-15"
    assert payload["weekday_cn"] == "星期五"
    assert isinstance(payload["day_yi"], list)
