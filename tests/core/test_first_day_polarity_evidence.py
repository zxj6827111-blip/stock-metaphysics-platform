from __future__ import annotations

from datetime import date

from src.core.fortune.polarity_evidence import read_first_day_polarity_evidence
from src.db.models import StockMasterRow


def _stock(evidence: dict | None) -> StockMasterRow:
    return StockMasterRow(
        stock_code="600519",
        exchange="SSE",
        listing_date=date(2024, 11, 15),
        first_day_pct_chg=0.03,
        first_day_yinyang="阳",
        first_day_evidence_json=evidence,
    )


def _record() -> dict:
    return {
        "schema_version": "first-day-polarity-evidence-v1",
        "status": "available",
        "source": "user_authoritative_first_day_table",
        "source_version": "sha256:verified-test",
        "first_day_yinyang": "阳",
        "first_day_pct_chg": 0.03,
        "price_basis": "工作簿原值；收盘价/开盘价-1",
        "observation_date": "2024-11-15",
        "trading_day_evidence": {"is_trading_day": True, "source": "published_exchange_calendar"},
        "market_session_version": "a-share-session-v1",
        "visible_at": "2024-11-15T15:00:00+08:00",
        "market_session": {"timezone": "Asia/Shanghai", "close_time": "15:00:00"},
    }


def test_verified_source_record_becomes_typed_luck_cycle_evidence() -> None:
    summary, evidence = read_first_day_polarity_evidence(_stock(_record()))

    assert summary.status == "available"
    assert summary.first_day_yinyang == "阳"
    assert summary.price_basis == "工作簿原值；收盘价/开盘价-1"
    assert summary.source_version == "sha256:verified-test"
    assert summary.visible_at.isoformat() == "2024-11-15T15:00:00+08:00"
    assert evidence is not None
    assert evidence.visible_at == summary.visible_at
    assert evidence.is_trading_day is True


def test_bare_stock_master_value_is_not_treated_as_provenance() -> None:
    summary, evidence = read_first_day_polarity_evidence(_stock(None))

    assert summary.first_day_yinyang == "阳"
    assert summary.status == "unavailable"
    assert "字段级来源证据" in summary.reason
    assert evidence is None


def test_conflicting_database_value_fails_closed() -> None:
    record = _record()
    record["first_day_yinyang"] = "阴"
    summary, evidence = read_first_day_polarity_evidence(_stock(record))

    assert summary.status == "conflict"
    assert evidence is None
    assert "不一致" in summary.reason
