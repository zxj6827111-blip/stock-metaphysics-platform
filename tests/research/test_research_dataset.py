"""Phase 3E/3F · 研究数据集组装测试（对象宽表命中逻辑）。

为什么单独测这一层
------------------
3E（中性化）与 3F（多重检验）都建立在"对象命中布尔"之上。命中定义一旦写错，
后面所有统计都错，而且错得很安静（数字照样漂亮）。因此这里用**构造的方向矩阵**
逐条核对 single / all_positive / conflict 三种预注册逻辑，并确认：

* 缺失引擎一律**不命中**（既不当 0 也不当命中）；
* 冲突组合要求"正引擎为正、负引擎为负"；
* 多引擎对象不生成自造的连续分数（RankIC 只能走事件命中）。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from src.research.neutralization.dataset import build_object_wide
from src.research.oos.registry import HypothesisRegistry, HypothesisSpec


def _registry() -> HypothesisRegistry:
    return HypothesisRegistry(
        version="test-registry",
        frozen_at="2026-09-20",
        oos_labels_seen_at_registration=False,
        hypotheses=(
            HypothesisSpec(
                hypothesis_id="H-SINGLE", title="single", object_id="bazi_raw",
                engines=("bazi",), direction_source="raw", logic="single",
            ),
            HypothesisSpec(
                hypothesis_id="H-ALL", title="all", object_id="bazi_ziwei_raw",
                engines=("bazi", "ziwei"), direction_source="raw", logic="all_positive",
            ),
            HypothesisSpec(
                hypothesis_id="H-ALL-CAL", title="all cal", object_id="all_cal",
                engines=("bazi", "ziwei", "huangli"), direction_source="calibrated",
                logic="all_positive",
            ),
            HypothesisSpec(
                hypothesis_id="H-CONFLICT", title="conflict", object_id="conflict_x",
                engines=("bazi", "ziwei"), direction_source="calibrated", logic="conflict",
                conflict={"positive": ["bazi"], "negative": ["ziwei"]},
                expected_direction="exploratory",
            ),
        ),
    )


def _panel() -> pd.DataFrame:
    """三只股票 × 一个 as_of 的方向矩阵（raw 与 calibrated 故意取不同值）。"""
    day = date(2023, 1, 3)
    rows = []
    spec = [
        # (stock, bazi_raw, ziwei_raw, huangli_raw, bazi_cal, ziwei_cal, huangli_cal)
        ("A", 1, 1, 1, 1, 1, 1),
        ("B", 1, 1, 1, 1, -1, 1),
        ("C", 1, -1, 0, 0, 1, 0),
    ]
    for stock, bazi_raw, ziwei_raw, huangli_raw, bazi_cal, ziwei_cal, huangli_cal in spec:
        for engine, raw_direction, cal_direction in (
            ("bazi", bazi_raw, bazi_cal),
            ("ziwei", ziwei_raw, ziwei_cal),
            ("huangli", huangli_raw, huangli_cal),
        ):
            rows.append({
                "stock_code": stock,
                "birth_model": "listing_open_v1",
                "as_of": day,
                "engine": engine,
                "opinion_score": 60.0,
                "raw_direction": raw_direction,
                "calibrated_direction": cal_direction,
                "research_percentile": 0.9,
                "partition": "OOS",
            })
    return pd.DataFrame(rows)


def test_single_logic_uses_engine_direction() -> None:
    wide = build_object_wide(_panel(), _registry(), birth_models=("listing_open_v1",))
    hits = dict(zip(wide["stock_code"], wide["hit__bazi_raw"], strict=True))
    assert hits == {"A": True, "B": True, "C": True}


def test_all_positive_requires_every_engine_positive() -> None:
    wide = build_object_wide(_panel(), _registry(), birth_models=("listing_open_v1",))
    hits = dict(zip(wide["stock_code"], wide["hit__bazi_ziwei_raw"], strict=True))
    assert hits == {"A": True, "B": True, "C": False}


def test_all_positive_calibrated_uses_calibrated_directions() -> None:
    wide = build_object_wide(_panel(), _registry(), birth_models=("listing_open_v1",))
    hits = dict(zip(wide["stock_code"], wide["hit__all_cal"], strict=True))
    # A: 1,1,1 → 命中；B: 1,-1,1 → 紫微校准为负，不命中；C: 0,1,0 → 零方向不命中
    assert hits == {"A": True, "B": False, "C": False}


def test_conflict_requires_positive_and_negative() -> None:
    wide = build_object_wide(_panel(), _registry(), birth_models=("listing_open_v1",))
    hits = dict(zip(wide["stock_code"], wide["hit__conflict_x"], strict=True))
    # 八字校准为正、紫微校准为负
    assert hits == {"A": False, "B": True, "C": False}


def test_zero_direction_is_not_a_hit() -> None:
    """本项目的 0 = 中性/不可用，绝不能被当成正向。"""
    wide = build_object_wide(_panel(), _registry(), birth_models=("listing_open_v1",))
    row_c = wide[wide["stock_code"] == "C"].iloc[0]
    assert row_c["raw_huangli"] == 0
    assert bool(row_c["hit__bazi_raw"]) is True  # 八字 raw 为 1
    assert bool(row_c["hit__all_cal"]) is False  # 含 0 的组合不命中


def test_missing_engine_never_hits_and_is_recorded() -> None:
    """面板缺某引擎时，包含该引擎的组合一律不命中（不得当 0 也不得当命中），
    并且"整列缺失"必须被记录 —— 否则一个坏面板会悄悄退化成"0 个事件"。"""
    panel = _panel()
    panel = panel[panel["engine"] != "ziwei"]
    missing: list[dict] = []
    wide = build_object_wide(
        panel, _registry(), birth_models=("listing_open_v1",), missing_out=missing,
    )
    assert not wide["hit__bazi_ziwei_raw"].any()
    assert not wide["hit__all_cal"].any()
    assert not wide["hit__conflict_x"].any()
    assert wide["hit__bazi_raw"].all(), "单引擎对象不受其它引擎缺失影响"
    recorded = {(item["object_id"], item["missing_direction_column"]) for item in missing}
    assert ("bazi_ziwei_raw", "raw_ziwei") in recorded
    assert ("all_cal", "cal_ziwei") in recorded
    assert ("conflict_x", "cal_ziwei") in recorded


def test_engine_scores_are_exposed_for_rank_ic() -> None:
    wide = build_object_wide(_panel(), _registry(), birth_models=("listing_open_v1",))
    for column in ("score_bazi", "pct_bazi", "score_ziwei", "pct_huangli"):
        assert column in wide.columns
    assert wide["score_bazi"].notna().all()
    assert wide["pct_bazi"].notna().all()


def test_birth_models_are_not_mixed() -> None:
    panel = pd.concat([
        _panel(),
        _panel().assign(birth_model="listing_close_v1"),
    ], ignore_index=True)
    wide = build_object_wide(
        panel, _registry(), birth_models=("listing_open_v1", "listing_close_v1"),
    )
    assert set(wide["birth_model"]) == {"listing_open_v1", "listing_close_v1"}
    assert len(wide) == 6, "每个出生模型各 3 只股票，不得合并"
    assert wide.groupby("birth_model").size().tolist() == [3, 3]


def test_unregistered_engine_yields_no_hits_not_a_crash() -> None:
    """未实现的术数（例如六爻）在面板里不存在 → 该对象 0 命中，并留下缺失记录。"""
    registry = HypothesisRegistry(
        version="test", frozen_at="2026-09-20", oos_labels_seen_at_registration=False,
        hypotheses=(
            HypothesisSpec(
                hypothesis_id="H-X", title="x", object_id="x",
                engines=("liuyao",), direction_source="raw", logic="single",
            ),
        ),
    )
    missing: list[dict] = []
    wide = build_object_wide(
        _panel(), registry, birth_models=("listing_open_v1",), missing_out=missing,
    )
    assert not wide["hit__x"].any()
    assert missing[0]["missing_direction_column"] == "raw_liuyao"
