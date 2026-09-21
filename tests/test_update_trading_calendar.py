"""交易日历更新脚本的纯逻辑（不联网）。

这一批测试锁的是"更新链路可以放心重复跑"这件事：

* 只增不删 —— 数据源异常不得截断历史日历；
* 公告解析 —— 只认明示的休市表述，不推断；
* 幂等 —— 同样的上游数据必须产出同样的字节。
"""

from __future__ import annotations

from datetime import date

import pytest

from scripts.update_trading_calendar import (
    EV_SSE_CLOSURE,
    EV_SSE_WEEKDAY,
    EV_WEEKEND,
    expand_closure_ranges,
    load_observed_csv,
    merge_observed,
)


class TestMergeObserved:
    def test_union_is_sorted_and_deduplicated(self):
        old = [date(2026, 9, 17), date(2026, 9, 18)]
        fresh = [date(2026, 9, 18), date(2026, 9, 21)]
        m = merge_observed("SSE", old, fresh, allow_shrink=False)
        assert m.days == [date(2026, 9, 17), date(2026, 9, 18), date(2026, 9, 21)]
        assert m.added == [date(2026, 9, 21)]
        assert m.dropped == []
        assert m.source_truncated is False

    def test_repeated_run_adds_nothing(self):
        old = [date(2026, 9, 18), date(2026, 9, 21)]
        m = merge_observed("SSE", old, list(old), allow_shrink=False)
        assert m.days == old and m.added == [] and m.dropped == []

    def test_truncated_source_aborts_instead_of_shrinking(self):
        """数据源回得比本地已有覆盖还短：必须中断，不能让历史日历被截断。"""
        old = [date(2026, 9, 18), date(2026, 9, 21)]
        with pytest.raises(RuntimeError, match="疑似抓取被截断"):
            merge_observed("SSE", old, [date(2026, 8, 1)], allow_shrink=False)

    def test_union_never_drops_even_when_source_has_holes(self):
        """源在中间缺几天（但末日没退）时，旧数据必须原样保留。"""
        old = [date(2026, 9, 17), date(2026, 9, 18), date(2026, 9, 21)]
        fresh = [date(2026, 9, 17), date(2026, 9, 21)]  # 缺 9-18
        m = merge_observed("SSE", old, fresh, allow_shrink=False)
        assert date(2026, 9, 18) in m.days
        assert m.dropped == []

    def test_explicit_shrink_flag_accepts_source_and_records_dropped(self):
        old = [date(2026, 9, 18), date(2026, 9, 21)]
        m = merge_observed("SSE", old, [date(2026, 9, 18)], allow_shrink=True)
        assert m.days == [date(2026, 9, 18)]
        assert m.dropped == [date(2026, 9, 21)]
        assert m.source_truncated is True


class TestClosureParsing:
    def test_range_is_expanded_inclusively(self):
        text = "一、休市安排：9月25日（星期五）至9月27日（星期日）休市，9月28日（星期一）起照常开市。"
        days = expand_closure_ranges(text, publish_date=date(2026, 9, 17))
        assert days == [date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27)]

    def test_multiple_ranges_in_one_announcement(self):
        text = (
            "9月25日（星期五）至9月27日（星期日）休市，9月28日（星期一）起照常开市。"
            "10月1日（星期四）至10月7日（星期三）休市，10月8日（星期四）起照常开市。"
        )
        days = expand_closure_ranges(text, publish_date=date(2026, 9, 17))
        assert days[0] == date(2026, 9, 25)
        assert days[-1] == date(2026, 10, 7)
        assert len(days) == 10  # 3 + 7

    def test_single_day_closure(self):
        text = "6月22日（星期一）休市，6月23日（星期二）起照常开市。"
        assert expand_closure_ranges(text, publish_date=date(2026, 6, 11)) == [date(2026, 6, 22)]

    def test_weekend_restatement_is_not_a_closure_range(self):
        """「另外，9月20日（星期日）…为周末休市」是周末复述，不是假日区间。"""
        text = "10月1日（星期四）至10月7日（星期三）休市。另外，9月20日（星期日）、10月10日（星期六）为周末休市。"
        days = expand_closure_ranges(text, publish_date=date(2026, 9, 17))
        assert date(2026, 9, 20) not in days
        assert date(2026, 10, 10) not in days
        assert days == [d for d in days if date(2026, 10, 1) <= d <= date(2026, 10, 7)]

    def test_december_announcement_rolls_into_next_year(self):
        text = "1月1日（星期四）至1月3日（星期六）休市，1月5日（星期一）起照常开市。"
        days = expand_closure_ranges(text, publish_date=date(2025, 12, 18))
        assert days[0] == date(2026, 1, 1)
        assert days[-1] == date(2026, 1, 3)

    def test_no_closure_means_empty_not_guess(self):
        assert expand_closure_ranges("关于交易安排的其他说明。", publish_date=date(2026, 1, 1)) == []


class TestEvidenceLabels:
    def test_evidence_labels_are_distinct(self):
        assert len({EV_SSE_CLOSURE, EV_SSE_WEEKDAY, EV_WEEKEND}) == 3


class TestObservedCsvRoundTrip:
    def test_load_missing_file_returns_empty(self, tmp_path):
        assert load_observed_csv(tmp_path / "nope.csv") == []

    def test_load_reads_and_sorts(self, tmp_path):
        path = tmp_path / "SSE.csv"
        path.write_text("trade_date\n2026-09-21\n2026-09-18\n", encoding="utf-8")
        assert load_observed_csv(path) == [date(2026, 9, 18), date(2026, 9, 21)]


class TestRealDataInvariants:
    """对真实入库文件的结构性断言（不联网）。"""

    def test_published_csv_covers_every_calendar_day(self):
        """公布层必须逐日给出标志 —— 有空洞就意味着某些日期又变回"未知"。"""
        import csv
        from datetime import timedelta

        from src.core.stock.trading_calendar import PUBLISHED_DIR

        path = PUBLISHED_DIR / "SSE.csv"
        if not path.exists():
            pytest.skip("尚未生成官方公布日历")
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        days = [date.fromisoformat(r["trade_date"]) for r in rows]
        assert days == sorted(set(days)), "公布层日期必须严格递增且去重"
        # 逐日无空洞
        for prev, cur in zip(days, days[1:]):
            assert cur - prev == timedelta(days=1), f"{prev} → {cur} 之间有空洞"
        assert all(r["is_open"] in ("0", "1") for r in rows)
        assert all(r["evidence"] for r in rows), "每行都要有判定依据"

    def test_published_meta_records_sources_and_verification(self):
        import json

        from src.core.stock.trading_calendar import PUBLISHED_DIR

        meta_path = PUBLISHED_DIR / "_meta.json"
        if not meta_path.exists():
            pytest.skip("尚未生成官方公布日历元数据")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert meta["cross_validation"]["verified"] is True
        assert meta["cross_validation"]["mismatches"] == []
        assert meta["sources"], "必须记录来源 URL"
        assert meta["generated_at"]
        assert "2027" in meta["boundary_cn"] or meta["boundary_cn"]
