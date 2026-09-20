"""拼合脚本的 PIT 口径验算单元测试（铁律 17）。

`expected_row_count` 是拼合校验的唯一把关逻辑：它决定"重算结果是否可信"。
判据是 PIT 资格 —— ``list_date <= as_of <= delist_date``，与
``scripts/phase4_collect_panel.py`` 的 ``load_universe`` 保持一致。
"""

from __future__ import annotations

from datetime import date

from scripts.phase4d_splice_panel import (
    ROWS_PER_ELIGIBLE_DATE,
    as_date,
    expected_row_count,
)

AS_OFS = [
    date(2010, 1, 1), date(2010, 4, 1), date(2010, 7, 1), date(2010, 10, 1),
    date(2011, 1, 1),
]


class TestAsDate:
    def test_string_from_sqlite(self) -> None:
        """SQLite 的 Date 列经 raw 查询会以字符串返回。"""
        assert as_date("2010-04-01") == date(2010, 4, 1)

    def test_date_passthrough(self) -> None:
        assert as_date(date(2010, 4, 1)) == date(2010, 4, 1)


class TestExpectedRowCount:
    def test_listed_before_all_dates(self) -> None:
        """全程在市 → 每个时点都可用。"""
        assert expected_row_count("1991-04-03", None, AS_OFS) == ROWS_PER_ELIGIBLE_DATE * 5

    def test_listed_midway(self) -> None:
        """上市日在中间 → 只算其后的时点。"""
        assert expected_row_count("2010-06-15", None, AS_OFS) == ROWS_PER_ELIGIBLE_DATE * 3

    def test_listed_boundary_inclusive(self) -> None:
        """边界是闭区间：恰好等于 as_of 也算可用。"""
        assert expected_row_count("2010-04-01", None, AS_OFS) == ROWS_PER_ELIGIBLE_DATE * 4

    def test_listed_after_last_date(self) -> None:
        """晚于最后一个时点 → 0 行（这正是北交所那批被改晚后的情形）。"""
        assert expected_row_count("2023-05-31", None, AS_OFS) == 0

    def test_delisted_excludes_later_dates(self) -> None:
        """退市日之后不再可用；退市当天仍可用。"""
        assert expected_row_count("2010-01-01", "2010-04-01", AS_OFS) == ROWS_PER_ELIGIBLE_DATE * 2

    def test_delisted_before_all_dates(self) -> None:
        assert expected_row_count("2001-01-01", "2009-12-31", AS_OFS) == 0

    def test_monotonic_in_listing_date(self) -> None:
        """上市日越晚，可用时点数只能不增（防止边界写反）。"""
        counts = [
            expected_row_count(listed, None, AS_OFS)
            for listed in ("1990-01-01", "2010-04-01", "2010-07-01", "2015-01-01")
        ]
        assert counts == sorted(counts, reverse=True)
