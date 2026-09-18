"""HuangliEngine 测试。

重点：
* 黄历字段结构化正确；
* ``raw_huangli`` 完整保留（一等数据）；
* 业务层只消费本引擎输出的 Schema，不直接碰 lunar-python。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.core.schemas.common import Availability


class TestHuangliSnapshot:
    def test_primary_day_fields(self, huangli_engine):
        snap = huangli_engine.snapshot(datetime(2001, 8, 27, 9, 30))
        p = snap.primary
        assert p.date == date(2001, 8, 27)
        assert p.year_ganzhi == "辛巳"
        assert p.month_ganzhi == "丙申"
        assert p.day_ganzhi == "壬戌"
        assert p.zodiac == "蛇"
        assert p.day_nayin == "大海水"
        assert p.duty_officer == "满"
        assert p.day_tian_shen_type == "黄道"
        assert p.chong_desc == "(丙辰)龙"

    def test_yi_ji_lists(self, huangli_engine):
        snap = huangli_engine.snapshot(datetime(2001, 8, 27, 9, 30))
        assert isinstance(snap.primary.day_yi, list)
        assert isinstance(snap.primary.day_ji, list)
        assert len(snap.primary.day_yi) > 0

    def test_engine_metadata(self, huangli_engine):
        snap = huangli_engine.snapshot(datetime(2024, 11, 15, 14, 32))
        assert snap.engine_id == "huangli"
        assert snap.engine_version
        assert snap.config_version
        assert snap.availability == Availability.OK
        assert snap.calculated_at is not None

    def test_raw_huangli_is_persisted_payload(self, huangli_engine):
        """原始黄历必须完整落库（可审计），且含版本与生成时间。"""
        snap = huangli_engine.snapshot(datetime(2024, 11, 15, 14, 32), days=1)
        raw = snap.raw_huangli
        assert raw["engine_version"] == snap.engine_version
        assert "generated_at" in raw
        assert raw["primary"]["day_ganzhi"] == "癸未"

    def test_multi_day_window(self, huangli_engine):
        snap = huangli_engine.snapshot(datetime(2024, 11, 15, 14, 32), days=31)
        assert len(snap.days) == 31
        assert snap.days[0].date == date(2024, 11, 15)
        assert snap.days[-1].date == date(2024, 12, 15)
        # 多日查询时 raw 中也应包含 days 明细
        assert len(snap.raw_huangli["days"]) == 31

    def test_days_are_consecutive(self, huangli_engine):
        snap = huangli_engine.snapshot(datetime(2024, 11, 15, 14, 32), days=10)
        dates = [d.date for d in snap.days]
        for i in range(1, len(dates)):
            assert (dates[i] - dates[i - 1]).days == 1

    def test_day_for_helper(self, huangli_engine):
        d = huangli_engine.day_for(date(2024, 11, 15))
        assert d.day_ganzhi == "癸未"

    def test_days_clamped(self, huangli_engine):
        """days 参数被限制在 1..400，防止误用导致超大扫描。"""
        snap = huangli_engine.snapshot(datetime(2024, 1, 1, 12, 0), days=9999)
        assert len(snap.days) == 400

    def test_assumptions_recorded(self, huangli_engine):
        snap = huangli_engine.snapshot(datetime(2024, 1, 1, 12, 0))
        assert snap.assumptions
        assert any("流派" in a or "通书" in a for a in snap.assumptions)

    def test_requires_when_or_context(self, huangli_engine):
        from src.engines.base import EngineContext

        with pytest.raises(ValueError):
            huangli_engine.calculate_chart(EngineContext())
