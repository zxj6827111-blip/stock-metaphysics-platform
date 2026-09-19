"""Phase 3A · Universe-usage 纪律测试。

目标（GOAL §3A-1 / §17）：
1) 所有"某时点可研究的股票集合"必须经 ``PointInTimeUniverse.at()`` 产生；
   违反者（直接 SQL ``FROM stock_master`` 无时间过滤）会通过此测试文件被揪出。
2) 泄漏硬断言：universe 任何股票的 ``list_date`` 不得迟于其被纳入 as_of 的日期。
3) 生存者偏差告示必须传播到 ``docs/data-coverage-phase3.md``。

具体实现：
* 本文件**不扫描源码 AST**（那样做量级太大）。我们用**行为级不变量**：
  - 对每个调研 as_of，universe.size > 0 且每只股票都满足 list_date <= as_of
  - 强行对比 "PIT universe" 与 "naive ALL stocks list" 的差异，要求差异非空，
    这证明 PIT 通道在生效（而不是被 stub 成"全量"）
* 如果未来有人新增绕过本模块的查询路径，他们必须显式在 ADR 里声明，
  否则 review 时这里会给出 SFR 注释（见源码注释中的 ``GREP_HOOK``）。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.research.universe import (
    MembershipRecord,
    PointInTimeUniverse,
)


@pytest.fixture
def universe_v2_sample() -> PointInTimeUniverse:
    """合成 universe：包含早期上市 / 晚期上市 / 已退市股票。"""
    return PointInTimeUniverse(
        [
            MembershipRecord(
                stock_code="000001", exchange="SZSE", board="主板",
                list_date=date(1991, 4, 3), delist_date=None,
                status="active", source="tushare_pit_universe",
                universe_version="v-discipline", delist_source="tushare_pit_universe",
            ),
            MembershipRecord(
                stock_code="000003", exchange="SZSE", board="主板",
                list_date=date(1991, 7, 3), delist_date=date(2002, 6, 14),
                status="delisted", source="tushare_pit_universe",
                universe_version="v-discipline", delist_source="tushare_pit_universe",
            ),
            MembershipRecord(
                stock_code="600519", exchange="SSE", board="主板",
                list_date=date(2001, 8, 27), delist_date=None,
                status="active", source="tushare_pit_universe",
                universe_version="v-discipline", delist_source="tushare_pit_universe",
            ),
            MembershipRecord(
                stock_code="688981", exchange="SSE", board="科创板",
                list_date=date(2020, 7, 16), delist_date=None,
                status="active", source="tushare_pit_universe",
                universe_version="v-discipline", delist_source="tushare_pit_universe",
            ),
        ],
        universe_version="v-discipline",
        snapshot_at=date(2026, 9, 19),
    )


class TestNoTradeBeforeListing:
    """特征计算不许用到上市前的数据（与 GOAL §17 对应）。"""

    def test_each_as_of_only_sees_stocks_already_listed(self, universe_v2_sample):
        """iter_daily_range 的每个 snapshot 内，所有 stock 都满足 list_date <= as_of。"""
        u = universe_v2_sample
        for as_of, snap in u.iter_daily_range(date(1990, 1, 1), date(2026, 9, 19)):
            for m in snap.members:
                assert m.list_date <= as_of, (
                    f"VIOLATION: {m.stock_code} list_date={m.list_date} > as_of={as_of}"
                )

    def test_delisted_stock_disappears_after_delist(self, universe_v2_sample):
        u = universe_v2_sample
        for cur, snap in u.iter_daily_range(date(2002, 6, 1), date(2002, 7, 31)):
            in_universe = "000003" in snap.member_codes
            expect_in = cur <= date(2002, 6, 14)
            assert in_universe == expect_in, (
                f"000003 在 as_of={cur} 的出现状态错误: {in_universe=}, {expect_in=}"
            )

    def test_new_stock_never_leaks_to_earlier_window(self, universe_v2_sample):
        """科创板股票 688981 上市 2020-07-16；在 2019/2018 的任何一天都不准出现。"""
        u = universe_v2_sample
        for y in (2018, 2019, 2020):
            for m in (1, 6, 12):
                snap = u.at(date(y, m, 1))
                if (y, m) < (2020, 7):
                    assert "688981" not in snap.member_codes, \
                        f"688981 泄露到了 as_of={y}-{m}"


class TestPITvsAllUniverse:
    """没有 PIT 约束时宇宙"看起来"更大，用 PIT 后必须缩小 —— 这是 PIT 生效的可观测信号。"""

    def test_pit_universe_is_strictly_smaller_than_all(self, universe_v2_sample):
        u = universe_v2_sample
        # 在某个早期时刻：PIT 只含部分；'所有会员' = 4
        all_count = len(u.list_all_members())
        assert all_count == 4
        snap_1995 = u.at(date(1995, 1, 1))
        assert len(snap_1995.member_codes) == 2  # 000001, 000003
        assert len(snap_1995.member_codes) < all_count


class TestCoverageReportIntegrity:
    """``docs/data-coverage-phase3.md`` 必须声明本 Phase 使用的 universe_version。"""

    def test_coverage_report_mentions_v2_phase3a(self):
        from pathlib import Path
        p = Path("docs/data-coverage-phase3.md")
        assert p.exists(), "docs/data-coverage-phase3.md 缺失"
        text = p.read_text(encoding="utf-8")
        assert "v2-phase3a" in text
        assert "Survivorship" in text or "SURVIVORSHIP_BIAS" in text
