"""Read-only checks used by the W8 local runtime scripts."""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.core.config import settings  # noqa: E402
from src.market.providers.vendor_parquet import DEFAULT_VENDOR_DATA_DIR, vendor_available  # noqa: E402
from src.research.historical_dataset_event_study import get_historical_dataset_v2  # noqa: E402


def _sqlite_path() -> Path:
    url = make_url(settings.resolved_database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError("W8 本机运行只接受持久化 SQLite 数据库；未输出连接串以保护凭据。")
    path = Path(url.database)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def main() -> int:
    failures: list[str] = []
    print(f"PYTHON_VERSION={sys.version.split()[0]}")
    print(f"MARKET_PROVIDER={settings.market_provider}")
    print(f"SYNTHETIC_FALLBACK={str(settings.allow_synthetic_market_fallback).lower()}")

    if settings.market_provider != "vendor_parquet":
        failures.append("研究运行要求 SMP_MARKET_PROVIDER=vendor_parquet")
    if settings.allow_synthetic_market_fallback:
        failures.append("研究运行要求 SMP_ALLOW_SYNTHETIC_MARKET_FALLBACK=false")

    vendor_root = Path(DEFAULT_VENDOR_DATA_DIR)
    if not vendor_root.is_absolute():
        vendor_root = (ROOT / vendor_root).resolve()
    print(f"VENDOR_ROOT={vendor_root}")
    print(f"VENDOR_PARQUET_AVAILABLE={str(vendor_available(vendor_root)).lower()}")
    if not vendor_available(vendor_root):
        failures.append("供应商行情 Parquet 路径缺少必需文件")

    try:
        database_path = _sqlite_path()
        print(f"DATABASE_PATH={database_path}")
        if not database_path.is_file():
            failures.append("配置的 SQLite 数据库文件不存在")
        else:
            with sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True, timeout=10) as connection:
                check = connection.execute("PRAGMA quick_check(1)").fetchone()
                integrity = check[0] if check else "no_result"
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                revisions = (
                    [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
                    if "alembic_version" in tables
                    else []
                )
            script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
            heads = script.get_heads()
            print(f"DATABASE_QUICK_CHECK={integrity}")
            print(f"DATABASE_REVISION={','.join(revisions) if revisions else 'missing'}")
            print(f"ALEMBIC_HEADS={','.join(heads) if heads else 'missing'}")
            if integrity != "ok":
                failures.append("SQLite quick_check 未通过")
            if len(heads) != 1 or revisions != heads:
                failures.append("数据库迁移未到唯一 Alembic head；预检不会自动迁移")
    except Exception as exc:  # noqa: BLE001 - expose safe diagnostic, never print connection URL
        failures.append(f"数据库只读检查失败：{type(exc).__name__}: {exc}")

    dataset_id = os.environ.get(
        "NEXT_PUBLIC_SMP_RESEARCH_DATASET_ID", "w4-engineering-002561-20120223-asof-v2"
    )
    try:
        dataset = get_historical_dataset_v2(settings.data_dir / "research_datasets", dataset_id)
        print(f"RESEARCH_DATASET_ID={dataset.dataset_id}")
        print(f"RESEARCH_DATASET_STATUS={dataset.status}")
        print(f"RESEARCH_DATASET_ROWS={dataset.row_count}")
        print(f"RESEARCH_ELIGIBLE={str(dataset.research_eligible).lower()}")
        print(f"CONFIRMATORY_ELIGIBLE={str(dataset.confirmatory_research_eligible).lower()}")
        if not dataset.research_eligible:
            print("RESEARCH_GATE=NO-GO (dataset exists but is not certified for research)")
    except Exception as exc:  # noqa: BLE001 - missing research data must remain explicit
        print(f"RESEARCH_DATASET_STATUS=unavailable ({type(exc).__name__}: {exc})")
        print("RESEARCH_GATE=NO-GO")

    if failures:
        for failure in failures:
            print(f"PREFLIGHT_ERROR={failure}")
        print("CORE_PREFLIGHT=FAIL")
        return 2

    print("CORE_PREFLIGHT=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
