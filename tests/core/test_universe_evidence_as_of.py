"""Universe 证据截止日解析器测试（R1 P0）。

被锁死的错误语义：**用「最后一只 IPO 的上市日期」当作数据快照日期**。
本文件只测解析器本身（纯 DB + 数据工件），不需要十神服务。
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import select

from src.db.models import UniverseMembershipRow
from src.research.universe.snapshot_metadata import (
    UNIVERSE_EVIDENCE_METADATA_VERSION,
    UniverseEvidenceAsOf,
    resolve_universe_evidence_as_of,
)

_SNAPSHOT_DATE = date(2026, 9, 20)
_VENDOR_LABEL = "phase4-vendor-hfq-v1"
_REPORT_NAME = "phase4_universe_report.json"


def _seed_members(db_session, universe_version: str, snapshots: list[str], count: int = 2) -> None:
    existing = db_session.execute(
        select(UniverseMembershipRow).where(UniverseMembershipRow.universe_version == universe_version)
    ).scalars().all()
    if existing:
        return
    for index in range(count):
        db_session.add(UniverseMembershipRow(
            universe_version=universe_version,
            stock_code=f"9{index:05d}",
            exchange="SSE",
            board="主板",
            list_date=date(2010, 1, index + 1),
            status="active",
            source="test",
            source_snapshot=snapshots[index % len(snapshots)],
            delist_source="test",
        ))
    db_session.flush()
    db_session.commit()


def _seed_rows(db_session, universe_version: str, rows: list[tuple[str, str, date, date | None, str]]) -> None:
    """按 (code, source_snapshot, list_date, delist_date, status) 精确播种。

    本表 ``source_snapshot`` 是 NOT NULL DEFAULT ''，所以真 SQL NULL 在这一版
    schema 下物理不可写入；空 provenance 在本库的表现形式就是 ""。
    NULL 分支由 :class:`_StubResult` 直接喂给普查函数来覆盖。
    """
    existing = db_session.execute(
        select(UniverseMembershipRow).where(UniverseMembershipRow.universe_version == universe_version)
    ).scalars().all()
    if existing:
        return
    for code, snapshot, list_date, delist_date, status in rows:
        db_session.add(UniverseMembershipRow(
            universe_version=universe_version, stock_code=code, exchange="SSE", board="主板",
            list_date=list_date, delist_date=delist_date, status=status, source="test",
            source_snapshot=snapshot, delist_source="test" if delist_date else "NOT_AVAILABLE_FROM_PROVIDER",
        ))
    db_session.flush()
    db_session.commit()


class _StubResult:
    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def all(self) -> list[tuple]:
        return self._rows


class _StubSession:
    """直接喂 given rows，用来覆盖真库里写不出来的 SQL NULL。"""

    def __init__(self, rows: list[tuple]) -> None:
        self._rows = rows

    def execute(self, _stmt: object) -> _StubResult:
        return _StubResult(self._rows)


def _write_report(
    data_dir: Path,
    *,
    universe_version: str = "v4-full",
    generated_at: str | None = "2026-09-20T07:07:12.239634",
    vendor: str | None = _VENDOR_LABEL,
) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"phase": "4C", "universe_version": universe_version}
    if generated_at is not None:
        payload["generated_at"] = generated_at
    if vendor is not None:
        payload["vendor_data_version"] = vendor
    path = data_dir / _REPORT_NAME
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_source_snapshot_holding_an_iso_date_is_used_directly(db_session, tmp_path) -> None:
    _seed_members(db_session, "t-date", [_SNAPSHOT_DATE.isoformat()])
    result = resolve_universe_evidence_as_of(db_session, "t-date", data_dir=tmp_path)
    assert result.available is True
    assert result.as_of == _SNAPSHOT_DATE
    assert result.source == "universe_membership_source_snapshot"


def test_source_snapshot_accepts_full_datetime_label(db_session, tmp_path) -> None:
    _seed_members(db_session, "t-dt", ["2026-09-20T07:07:12"])
    result = resolve_universe_evidence_as_of(db_session, "t-dt", data_dir=tmp_path)
    assert result.as_of == _SNAPSHOT_DATE


def test_conflicting_date_snapshots_refuse_to_pick_one(db_session, tmp_path) -> None:
    """两个不同快照日期同时存在时必须拒答，不能挑一个看起来合理的。"""
    _seed_members(db_session, "t-two", ["2026-09-20", "2026-08-01"], count=2)
    result = resolve_universe_evidence_as_of(db_session, "t-two", data_dir=tmp_path)
    assert result.available is False
    assert "拒绝挑一个" in result.detail


def test_vendor_label_is_cross_checked_against_report_and_date_taken_from_it(db_session, tmp_path) -> None:
    _seed_members(db_session, "v4-full-x", [_VENDOR_LABEL])
    _write_report(tmp_path, universe_version="v4-full-x")
    result = resolve_universe_evidence_as_of(
        db_session, "v4-full-x", data_dir=tmp_path, report_files={"v4-full-x": _REPORT_NAME},
    )
    assert result.available is True
    assert result.as_of == _SNAPSHOT_DATE
    assert result.source == "universe_report_generated_at"


def test_unknown_universe_version_never_falls_back_to_a_report(db_session, tmp_path) -> None:
    """未登记报告的 universe 不得去读别人的报告文件。"""
    _seed_members(db_session, "t-unknown", [_VENDOR_LABEL])
    _write_report(tmp_path, universe_version="v4-full")
    result = resolve_universe_evidence_as_of(db_session, "t-unknown", data_dir=tmp_path)
    assert result.available is False
    assert "未登记正式证据报告" in result.detail


def test_vendor_label_mismatch_fails_closed(db_session, tmp_path) -> None:
    """报告声明的 vendor_data_version 与库内标签不一致 → 不采信该报告。"""
    _seed_members(db_session, "t-mismatch", ["phase4-vendor-hfq-v9-不认识的标签"])
    _write_report(tmp_path, universe_version="t-mismatch")
    result = resolve_universe_evidence_as_of(
        db_session, "t-mismatch", data_dir=tmp_path, report_files={"t-mismatch": _REPORT_NAME},
    )
    assert result.available is False
    assert "无法互相印证" in result.detail


def test_missing_generated_at_fails_closed(db_session, tmp_path) -> None:
    _seed_members(db_session, "t-nogen", [_VENDOR_LABEL])
    _write_report(tmp_path, universe_version="t-nogen", generated_at=None)
    result = resolve_universe_evidence_as_of(
        db_session, "t-nogen", data_dir=tmp_path, report_files={"t-nogen": _REPORT_NAME},
    )
    assert result.available is False
    assert "generated_at" in result.detail


def test_report_absent_from_disk_fails_closed(db_session, tmp_path) -> None:
    _seed_members(db_session, "t-nofile", [_VENDOR_LABEL])
    result = resolve_universe_evidence_as_of(
        db_session, "t-nofile", data_dir=tmp_path, report_files={"t-nofile": _REPORT_NAME},
    )
    assert result.available is False
    assert _REPORT_NAME in result.detail


def test_unparsable_report_fails_closed(db_session, tmp_path) -> None:
    _seed_members(db_session, "t-badjson", [_VENDOR_LABEL])
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / _REPORT_NAME).write_text("{不是合法 JSON", encoding="utf-8")
    result = resolve_universe_evidence_as_of(
        db_session, "t-badjson", data_dir=tmp_path, report_files={"t-badjson": _REPORT_NAME},
    )
    assert result.available is False
    assert "无法解析" in result.detail


def test_empty_universe_fails_closed(db_session, tmp_path) -> None:
    result = resolve_universe_evidence_as_of(db_session, "t-empty", data_dir=tmp_path)
    assert result.available is False
    assert "没有任何 membership 行" in result.detail


def test_unavailable_result_carries_no_as_of_and_a_stable_metadata_version() -> None:
    """fail closed 的返回值必须"没有日期"，不能有默认日期混进去。"""
    dead = UniverseEvidenceAsOf(universe_version="v", as_of=None, detail="x")
    assert dead.available is False
    assert dead.as_of is None
    assert dead.metadata_version == UNIVERSE_EVIDENCE_METADATA_VERSION


def test_report_generated_at_is_read_as_a_date_not_a_timestamp(db_session, tmp_path) -> None:
    _seed_members(db_session, "t-zone", [_VENDOR_LABEL])
    _write_report(tmp_path, universe_version="t-zone", generated_at="2026-09-20T23:30:00")
    result = resolve_universe_evidence_as_of(
        db_session, "t-zone", data_dir=tmp_path, report_files={"t-zone": _REPORT_NAME},
    )
    assert result.as_of == date(2026, 9, 20)
    assert isinstance(result.as_of, date) and not isinstance(result.as_of, datetime)


# ---------------------------------------------------------------------------
# R2 闸门 1：provenance 完整性 —— 空标签不得被静默丢弃
# ---------------------------------------------------------------------------
def test_r2_a_row_with_null_source_snapshot_fails_closed() -> None:
    """回归 A：3 行里 1 行 source_snapshot 为 NULL → 整个 universe 不可信。

    ``source_snapshot`` 在该版 schema 上是 NOT NULL DEFAULT ''，真 NULL 写不进库，
    因此这里直接给普查函数喂含 None 的行，覆盖 SQL NULL 这条分支。
    """
    stub = _StubSession([
        ("600000", _SNAPSHOT_DATE.isoformat(), date(1992, 5, 7), None, "active"),
        ("600519", _SNAPSHOT_DATE.isoformat(), date(2001, 8, 27), None, "active"),
        ("000001", None, date(1991, 4, 3), None, "active"),
    ])
    result = resolve_universe_evidence_as_of(stub, "v4-full")  # type: ignore[arg-type]
    assert result.available is False
    assert result.membership_total == 3
    assert result.snapshot_present == 2
    assert result.snapshot_missing == 1
    assert "source_snapshot 为空/NULL" in result.detail


def test_r2_b_row_with_empty_source_snapshot_fails_closed(db_session, tmp_path) -> None:
    """回归 B：空串 "" 与 NULL 同一条分支，都必须 fail closed。"""
    _seed_rows(db_session, "t-blank", [
        ("600000", _SNAPSHOT_DATE.isoformat(), date(1992, 5, 7), None, "active"),
        ("600519", _SNAPSHOT_DATE.isoformat(), date(2001, 8, 27), None, "active"),
        ("000001", "", date(1991, 4, 3), None, "active"),
    ])
    result = resolve_universe_evidence_as_of(db_session, "t-blank", data_dir=tmp_path)
    assert result.available is False
    assert (result.membership_total, result.snapshot_present, result.snapshot_missing) == (3, 2, 1)
    assert "membership_total=3" in result.detail
    assert "snapshot_present=2" in result.detail
    assert "snapshot_missing=1" in result.detail


def test_r2_c_full_provenance_single_date_is_accepted(db_session, tmp_path) -> None:
    """回归 C：全部行同一日期 → available，且计数全对。"""
    _seed_rows(db_session, "t-full", [
        ("600000", _SNAPSHOT_DATE.isoformat(), date(1992, 5, 7), None, "active"),
        ("600519", _SNAPSHOT_DATE.isoformat(), date(2001, 8, 27), None, "active"),
        ("000001", _SNAPSHOT_DATE.isoformat(), date(1991, 4, 3), None, "active"),
    ])
    result = resolve_universe_evidence_as_of(db_session, "t-full", data_dir=tmp_path)
    assert result.available is True
    assert result.as_of == _SNAPSHOT_DATE
    assert result.source == "universe_membership_source_snapshot"
    assert (result.membership_total, result.snapshot_present, result.snapshot_missing) == (3, 3, 0)


def test_r2_d_vendor_label_report_path_still_works_after_hardening(db_session, tmp_path) -> None:
    """回归 D：全部是供应商标签且与正式报告一致 → 仍走 report generated_at。"""
    _seed_rows(db_session, "t-vendor", [
        ("600000", _VENDOR_LABEL, date(1992, 5, 7), None, "active"),
        ("600519", _VENDOR_LABEL, date(2001, 8, 27), None, "active"),
    ])
    _write_report(tmp_path, universe_version="t-vendor")
    result = resolve_universe_evidence_as_of(
        db_session, "t-vendor", data_dir=tmp_path, report_files={"t-vendor": _REPORT_NAME},
    )
    assert result.available is True
    assert result.as_of == _SNAPSHOT_DATE
    assert result.source == "universe_report_generated_at"


def test_r2_blank_label_is_not_rescued_by_a_valid_report(db_session, tmp_path) -> None:
    """provenance 缺口不能被报告"救回来"：闸门 1 先于来源 2。"""
    _seed_rows(db_session, "t-blank2", [
        ("600000", _VENDOR_LABEL, date(1992, 5, 7), None, "active"),
        ("000001", "", date(1991, 4, 3), None, "active"),
    ])
    _write_report(tmp_path, universe_version="t-blank2")
    result = resolve_universe_evidence_as_of(
        db_session, "t-blank2", data_dir=tmp_path, report_files={"t-blank2": _REPORT_NAME},
    )
    assert result.available is False
    assert result.snapshot_missing == 1


# ---------------------------------------------------------------------------
# R2 闸门 2：证据截止日必须与 membership 事件自洽
# ---------------------------------------------------------------------------
def test_r2_membership_listed_after_candidate_fails_closed(db_session, tmp_path) -> None:
    """候选 09-20，却有 09-21 上市的行 → 库与 cutoff 矛盾，必须拒答。"""
    _seed_rows(db_session, "t-late", [
        ("600000", _SNAPSHOT_DATE.isoformat(), date(1992, 5, 7), None, "active"),
        ("688999", _SNAPSHOT_DATE.isoformat(), date(2026, 9, 21), None, "active"),
    ])
    result = resolve_universe_evidence_as_of(db_session, "t-late", data_dir=tmp_path)
    assert result.available is False
    assert "list_date 晚于候选证据截止日" in result.detail
    assert "2026-09-21" in result.detail


def test_r2_max_list_date_before_candidate_is_accepted(db_session, tmp_path) -> None:
    """正常情形：max(list_date)=09-01 早于候选 09-20 → 通过，且 as_of 仍是 09-20。

    这条专门用来证明对账没有被反向写成"快照日 = max(list_date)"。
    """
    _seed_rows(db_session, "t-ok", [
        ("600000", _SNAPSHOT_DATE.isoformat(), date(1992, 5, 7), None, "active"),
        ("688981", _SNAPSHOT_DATE.isoformat(), date(2026, 9, 1), None, "active"),
    ])
    result = resolve_universe_evidence_as_of(db_session, "t-ok", data_dir=tmp_path)
    assert result.available is True
    assert result.as_of == _SNAPSHOT_DATE
    assert result.as_of != date(2026, 9, 1), "as_of 绝不能等于 max(list_date)"


def test_r2_delisted_status_beyond_candidate_fails_closed(db_session, tmp_path) -> None:
    """status=delisted 而退市日晚于证据截止日 → 既成事实与 cutoff 矛盾。"""
    _seed_rows(db_session, "t-dconf", [
        ("600000", _SNAPSHOT_DATE.isoformat(), date(1992, 5, 7), None, "active"),
        ("601111", _SNAPSHOT_DATE.isoformat(), date(2005, 1, 5), date(2026, 9, 25), "delisted"),
    ])
    result = resolve_universe_evidence_as_of(db_session, "t-dconf", data_dir=tmp_path)
    assert result.available is False
    assert "status=delisted" in result.detail and "晚于候选证据" in result.detail


def test_r2_announced_future_delist_is_kept_as_note_not_a_claim(db_session, tmp_path) -> None:
    """退市日在 cutoff 之后但 status 尚未 delisted：按"已预告、未发生"处理，
    可以 available，但必须在 detail 留痕，不得当成截止日前已知信息。"""
    _seed_rows(db_session, "t-dnote", [
        ("600000", _SNAPSHOT_DATE.isoformat(), date(1992, 5, 7), None, "active"),
        ("602222", _SNAPSHOT_DATE.isoformat(), date(2005, 1, 5), date(2026, 12, 31), "suspended_long"),
    ])
    result = resolve_universe_evidence_as_of(db_session, "t-dnote", data_dir=tmp_path)
    assert result.available is True
    assert result.as_of == _SNAPSHOT_DATE
    assert "已预告、未发生" in result.detail
    assert "不当作截止日之前的已知信息" in result.detail


def test_r2_report_derived_candidate_is_audited_too(db_session, tmp_path) -> None:
    """来源 2 得到的候选日同样要过事件一致性闸。"""
    _seed_rows(db_session, "t-rep-audit", [
        ("600000", _VENDOR_LABEL, date(2026, 10, 9), None, "active"),
    ])
    _write_report(tmp_path, universe_version="t-rep-audit")  # generated_at → 2026-09-20
    result = resolve_universe_evidence_as_of(
        db_session, "t-rep-audit", data_dir=tmp_path, report_files={"t-rep-audit": _REPORT_NAME},
    )
    assert result.available is False
    assert "list_date 晚于候选证据截止日" in result.detail


def test_r2_metadata_version_bumped_for_stricter_rules() -> None:
    """收紧接受条件必须留下版本痕迹：v1 能过的库在 v2 可能拒答。"""
    assert UNIVERSE_EVIDENCE_METADATA_VERSION == "universe-evidence-asof-v2"
    assert UniverseEvidenceAsOf(universe_version="v", as_of=None).metadata_version == (
        UNIVERSE_EVIDENCE_METADATA_VERSION
    )
