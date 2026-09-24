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
