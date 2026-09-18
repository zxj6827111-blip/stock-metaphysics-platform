"""pytest 公共夹具。

关键设计：
* 每个测试会话使用**独立的临时 SQLite 库**，绝不触碰开发库 `data/smp.sqlite3`。
* 默认使用离线合成行情（`SMP_MARKET_PROVIDER=synthetic`），
  保证测试在无网络环境下可重复运行，且不依赖第三方接口稳定性。
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest

# --- 必须在导入 src.* 之前设置环境变量，因为 Settings 会被 lru_cache 缓存 ---
_TMPDIR = tempfile.mkdtemp(prefix="smp-tests-")
_DB_PATH = Path(_TMPDIR) / "test.sqlite3"
os.environ["SMP_DATABASE_URL"] = f"sqlite:///{_DB_PATH.as_posix()}"
os.environ["SMP_MARKET_PROVIDER"] = "synthetic"
os.environ["SMP_NEGATIVE_CONTROL_SEED"] = "20260918"
os.environ["SMP_DEBUG"] = "0"


@pytest.fixture(scope="session", autouse=True)
def _prepare_database() -> Iterator[None]:
    """建库（含 Alembic 之外的最小 schema）并注入古籍语料。"""
    from src.db.base import init_db, reset_engine_state

    reset_engine_state()
    init_db()
    from src.knowledge.ingest.loader import seed_database

    seed_database()
    yield
    reset_engine_state()


@pytest.fixture()
def db_session():
    from src.db.base import get_session_factory

    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture()
def market():
    """离线确定性行情源。"""
    from src.market.providers.synthetic import SyntheticMarketProvider

    return SyntheticMarketProvider(start=date(2018, 1, 1))


@pytest.fixture()
def calendar_engine():
    from src.engines.calendar.calendar_engine import CalendarEngine

    return CalendarEngine()


@pytest.fixture()
def huangli_engine(calendar_engine):
    from src.engines.huangli.huangli_engine import HuangliEngine

    return HuangliEngine(calendar_engine)


@pytest.fixture()
def bazi_engine(calendar_engine):
    from src.engines.bazi.bazi_engine import BaziEngine

    return BaziEngine(calendar_engine)


@pytest.fixture()
def maotai_chart(bazi_engine):
    """贵州茅台（600519）2001-08-27 09:30 上市的八字盘，基准时间 2024-11-15 14:32。"""
    return bazi_engine.build_chart(
        birth_datetime=datetime(2001, 8, 27, 9, 30),
        as_of=datetime(2024, 11, 15, 14, 32),
        stock_code="600519",
    )


@pytest.fixture()
def factor_set(maotai_chart, huangli_engine):
    from src.factors.registry.compute import compute_factor_set

    huangli = huangli_engine.snapshot(datetime(2024, 11, 15, 14, 32), days=31)
    return compute_factor_set(maotai_chart, huangli, datetime(2024, 11, 15, 14, 32), stock_code="600519")


@pytest.fixture(scope="session")
def client():
    """FastAPI TestClient（离线行情）。"""
    from fastapi.testclient import TestClient

    from apps.api.main import app

    with TestClient(app) as c:
        yield c
