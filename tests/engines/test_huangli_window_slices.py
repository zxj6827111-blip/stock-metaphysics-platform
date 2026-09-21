"""``HuangliEngine.snapshots_for_window`` 与逐日 ``snapshot(days=31)`` 等价性。

为什么必须有这个测试
--------------------
逐日视图为了性能把"每天各构造 31 天"改成"一次构造整段、按天切片"。
这是一个**纯性能优化**，一旦切片口径（长度、起止、时刻分量）有偏差，
H_MONTH_* 月度聚合因子就会跟着变 —— 而那种偏差表现为"分数悄悄变了 0.3 分"，
肉眼看不出、事后无法追溯。

所以这里逐字段比对两条路径的结果，把"性能优化"和"口径变化"彻底分开。
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.engines.huangli.huangli_engine import HuangliEngine


@pytest.fixture()
def engine() -> HuangliEngine:
    return HuangliEngine()


@pytest.mark.parametrize("hour", [0, 15])
def test_slices_equal_per_day_snapshots(engine, hour):
    start = datetime(2024, 11, 15, hour, 0, 0)
    offsets = [0, 1, 4, 7, 11, 18]
    sliced = engine.snapshots_for_window(start=start, offsets=offsets, window_days=31)

    assert set(sliced) == set(offsets)
    for offset in offsets:
        expected = engine.snapshot(start + timedelta(days=offset), days=31)
        got = sliced[offset]
        # primary 逐字段相同（含 hour_ganzhi —— 时刻分量必须一致）
        assert got.primary.model_dump(mode="json") == expected.primary.model_dump(mode="json")
        # days 同时长、逐字段相同
        assert len(got.days) == len(expected.days) == 31
        assert [d.model_dump(mode="json") for d in got.days] == [
            d.model_dump(mode="json") for d in expected.days
        ]
        assert got.engine_version == expected.engine_version
        assert got.availability == expected.availability


def test_day_payload_of_slices_is_decision_equivalent(engine):
    """因子真正消费的字段（day_ganzhi / 建除 / 十二神 / 黄黑道）必须完全一致。"""
    start = datetime(2024, 11, 15, 15, 0, 0)
    offsets = list(range(0, 12))
    sliced = engine.snapshots_for_window(start=start, offsets=offsets, window_days=31)
    fields = (
        "date", "day_ganzhi", "duty_officer", "day_tian_shen",
        "day_tian_shen_type", "day_tian_shen_luck", "xiu", "xiu_luck",
    )
    for offset in offsets:
        expected = engine.snapshot(start + timedelta(days=offset), days=31)
        got = sliced[offset]
        for field in fields:
            assert getattr(got.primary, field) == getattr(expected.primary, field)
        assert [getattr(d, "day_ganzhi") for d in got.days] == [
            getattr(d, "day_ganzhi") for d in expected.days
        ]


def test_empty_offsets_returns_empty(engine):
    assert engine.snapshots_for_window(start=datetime(2024, 11, 15, 15), offsets=[]) == {}


def test_duplicate_offsets_deduplicated(engine):
    out = engine.snapshots_for_window(
        start=datetime(2024, 11, 15, 15), offsets=[0, 0, 3, 3, 3], window_days=31,
    )
    assert sorted(out) == [0, 3]
