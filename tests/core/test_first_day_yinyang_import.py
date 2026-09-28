from types import SimpleNamespace

from scripts.phase4d_import_first_day_yinyang import _can_fill_source_values


def test_only_complete_available_evidence_can_fill_missing_values():
    master = SimpleNamespace(first_day_yinyang=None, first_day_pct_chg=None)
    source = {"status": "available", "first_day_yinyang": "阳", "first_day_pct_chg": 0.0}

    assert _can_fill_source_values(source, master)


def test_conflicted_source_never_fills_empty_values():
    master = SimpleNamespace(first_day_yinyang=None, first_day_pct_chg=None)
    source = {"status": "conflict", "first_day_yinyang": "阳", "first_day_pct_chg": 0.03}

    assert not _can_fill_source_values(source, master)


def test_existing_nonmatching_values_are_never_overwritten():
    master = SimpleNamespace(first_day_yinyang="阴", first_day_pct_chg=-0.02)
    source = {"status": "available", "first_day_yinyang": "阳", "first_day_pct_chg": 0.03}

    assert not _can_fill_source_values(source, master)
