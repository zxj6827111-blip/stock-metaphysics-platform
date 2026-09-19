"""PointInTimeUniverse 单元测试 + 泄漏硬断言（Phase 3A）。

覆盖 GOAL §17 列出的新增 PIT 泄漏场景：
* 当前快照内的"未来上市"股票不得出现在历史中
* 已退市股票在退市日后必须退出
* universe 快照 digest 必须稳定（同样输入 → 同样 digest）
* 生存者偏差告警必须在"delist_date 全为 NULL"时被触发
* 查询接口的排序必须稳定（同一 as_of 两次调用返回一致）
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.research.universe import (
    MembershipRecord,
    PointInTimeUniverse,
    SurvivorshipBiasWarning,
)


def _rec(
    code: str,
    list_date: date,
    delist_date: date | None = None,
    *,
    version: str = "v-phase3-test",
    exchange: str = "SSE",
    board: str = "主板",
    status: str = "active",
    source: str = "tencent_hfq_import",
    delist_source: str = "",
) -> MembershipRecord:
    return MembershipRecord(
        stock_code=code,
        exchange=exchange,
        board=board,
        list_date=list_date,
        delist_date=delist_date,
        status=status,
        source=source,
        universe_version=version,
        delist_source=delist_source,
    )


# ---------------------------------------------------------------------------
# 基本 as_of 语义
# ---------------------------------------------------------------------------


class TestAsOfMembership:
    def test_stock_listed_before_or_on_asof_is_included(self):
        u = PointInTimeUniverse(
            [_rec("600519", date(2001, 8, 27))],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        snap = u.at(date(2010, 1, 4))
        assert "600519" in snap.member_codes
        assert u.is_member("600519", date(2010, 1, 4))

    def test_stock_listed_after_asof_is_excluded(self):
        u = PointInTimeUniverse(
            [_rec("600519", date(2001, 8, 27))],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        snap = u.at(date(2000, 1, 1))
        assert "600519" not in snap.member_codes
        assert not u.is_member("600519", date(2000, 1, 1))

    def test_stock_listed_exactly_on_asof_is_included(self):
        u = PointInTimeUniverse(
            [_rec("600519", date(2001, 8, 27))],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        snap = u.at(date(2001, 8, 27))
        assert "600519" in snap.member_codes

    def test_delisted_stock_excluded_after_delist_date(self):
        u = PointInTimeUniverse(
            [_rec("000003", date(1991, 1, 1), date(2002, 5, 30))],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        assert "000003" in u.at(date(2002, 5, 30)).member_codes
        assert "000003" not in u.at(date(2002, 6, 1)).member_codes
        assert not u.is_member("000003", date(2002, 6, 1))

    def test_active_stock_visible_after_listing(self):
        u = PointInTimeUniverse(
            [_rec("600519", date(2001, 8, 27))],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        assert "600519" in u.at(date(2026, 9, 18)).member_codes


# ---------------------------------------------------------------------------
# 泄漏防护（§17 要求的硬断言）
# ---------------------------------------------------------------------------


class TestLeakageGuard:
    def test_future_listing_does_not_appear_in_past(self):
        """不管多晚上市的股票，都不准出现在比它上市日更早的 as_of 快照里。"""
        u = PointInTimeUniverse(
            [
                _rec("688981", date(2020, 7, 16)),
                _rec("600519", date(2001, 8, 27)),
                _rec("000001", date(1991, 1, 2)),
            ],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        assert "688981" not in u.at(date(2015, 1, 1)).member_codes
        assert "688981" not in u.at(date(2020, 7, 15)).member_codes
        assert "688981" in u.at(date(2020, 7, 16)).member_codes

    def test_iter_daily_range_consistency(self):
        """iter_daily_range 与逐个 at() 必须一致。"""
        u = PointInTimeUniverse(
            [_rec("600519", date(2001, 8, 27))],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        start, end = date(2000, 12, 30), date(2001, 9, 1)
        for cur, snap in u.iter_daily_range(start, end):
            assert cur >= start and cur <= end
            assert snap.as_of == cur
            # "600519 上市前查不到，上市后查得到"
            expect_member = cur >= date(2001, 8, 27)
            assert ("600519" in snap.member_codes) == expect_member

    def test_snapshot_digest_is_deterministic(self):
        """同一 universe、同一 as_of → digest 必须稳定（实验可追溯）。"""
        u = PointInTimeUniverse(
            [
                _rec("600519", date(2001, 8, 27)),
                _rec("000001", date(1991, 1, 2)),
            ],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        a = u.at(date(2010, 1, 4))
        b = u.at(date(2010, 1, 4))
        assert a.digest == b.digest
        assert len(a.digest) >= 12

    def test_digest_changes_with_membership(self):
        u = PointInTimeUniverse(
            [_rec("600519", date(2001, 8, 27))],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        snap_a = u.at(date(2000, 1, 1))  # 空
        snap_b = u.at(date(2010, 1, 4))  # {600519}
        assert snap_a.digest != snap_b.digest

    def test_member_order_is_stable(self):
        """输出按 stock_code 升序：多次调用结果必须完全一致。"""
        u = PointInTimeUniverse(
            [
                _rec("600887", date(1996, 3, 12)),
                _rec("000001", date(1991, 1, 2)),
                _rec("600519", date(2001, 8, 27)),
                _rec("000858", date(1998, 4, 27)),
            ],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        a = u.at(date(2020, 1, 1)).member_codes
        b = u.at(date(2020, 1, 1)).member_codes
        assert a == b
        assert a == tuple(sorted(a))


# ---------------------------------------------------------------------------
# 生存者偏差告警
# ---------------------------------------------------------------------------


class TestSurvivorshipBiasWarning:
    def test_warning_fired_when_delist_source_unavailable(self):
        """delist_date 为 NULL 且 delist_source 为空 → 结构性未知 → 必须警告。"""
        u = PointInTimeUniverse(
            [
                _rec("600519", date(2001, 8, 27), None, delist_source=""),
                _rec("000001", date(1991, 1, 2), None, delist_source=""),
            ],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        snap = u.at(date(2020, 1, 1))
        kinds = {w.kind for w in snap.warnings}
        assert "SURVIVORSHIP_BIAS_WARNING" in kinds

    def test_warning_fired_when_source_is_not_available_marker(self):
        u = PointInTimeUniverse(
            [
                _rec("600519", date(2001, 8, 27), None,
                     delist_source="NOT_AVAILABLE_FROM_PROVIDER"),
            ],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        snap = u.at(date(2020, 1, 1))
        kinds = {w.kind for w in snap.warnings}
        assert "SURVIVORSHIP_BIAS_WARNING" in kinds

    def test_no_warning_when_delisted_have_date_and_actives_have_known_source(self):
        """v2-phase3a 的目标形态：
        - 退市股：delist_date != NULL + delist_source='tushare_pit_universe'
        - 在市股：delist_date = NULL + delist_source='tushare_pit_universe'（语义：截至快照未退市）
        这两种都视为"已知" → 不应触发 SURVIVORSHIP_BIAS_WARNING。
        """
        u = PointInTimeUniverse(
            [
                _rec("600519", date(2001, 8, 27), None,
                     delist_source="tushare_pit_universe"),
                _rec("000003", date(1991, 7, 3), date(2002, 6, 14),
                     delist_source="tushare_pit_universe", status="delisted"),
            ],
            universe_version="v2-phase3a",
            snapshot_at=date(2026, 9, 19),
        )
        snap = u.at(date(2020, 1, 1))
        kinds = {w.kind for w in snap.warnings}
        assert "SURVIVORSHIP_BIAS_WARNING" not in kinds

    def test_warning_when_partial_records_unknown(self):
        """部分未知 → 仍要 warning。"""
        u = PointInTimeUniverse(
            [
                _rec("600519", date(2001, 8, 27), None,
                     delist_source="tushare_pit_universe"),
                _rec("000001", date(1991, 1, 2), None, delist_source=""),
            ],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        snap = u.at(date(2020, 1, 1))
        kinds = {w.kind for w in snap.warnings}
        assert "SURVIVORSHIP_BIAS_WARNING" in kinds
        w = next(w for w in snap.warnings if w.kind == "SURVIVORSHIP_BIAS_WARNING")
        assert w.member_count_with_delist_known == 1
        assert w.member_count_total == 2

    def test_empty_universe_warns(self):
        u = PointInTimeUniverse(
            [],
            universe_version="v1",
            snapshot_at=date(2026, 9, 19),
        )
        snap = u.at(date(2020, 1, 1))
        kinds = {w.kind for w in snap.warnings}
        assert "SURVIVORSHIP_BIAS_WARNING" in kinds
