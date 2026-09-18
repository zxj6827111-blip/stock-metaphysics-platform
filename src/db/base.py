"""SQLAlchemy 声明式基类与会话管理。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for col in self.__table__.columns:  # type: ignore[attr-defined]
            val = getattr(self, col.name)
            if isinstance(val, datetime | date):
                val = val.isoformat()
            out[col.name] = val
        return out


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine(url: str | None = None, *, echo: bool = False) -> Engine:
    global _engine
    if _engine is None or url is not None:
        target = url or settings.resolved_database_url
        connect_args = {"check_same_thread": False} if target.startswith("sqlite") else {}
        engine = create_engine(target, echo=echo, future=True, connect_args=connect_args)

        if target.startswith("sqlite"):

            @event.listens_for(engine, "connect")
            def _set_sqlite_pragma(dbapi_conn, _rec):  # type: ignore[no-untyped-def]
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()

        if url is not None:
            _engine = engine
        else:
            _engine = engine
    return _engine


def get_session_factory(url: str | None = None) -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None or url is not None:
        _SessionLocal = sessionmaker(bind=get_engine(url), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def reset_engine_state() -> None:
    """测试用：丢弃已缓存的 engine/sessionmaker。"""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


@contextmanager
def session_scope(url: str | None = None) -> Iterator[Session]:
    """事务性会话上下文。"""
    factory = get_session_factory(url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI 依赖注入用生成器。"""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def init_db(url: str | None = None) -> None:
    """建表（开发/测试便捷入口；生产 migration 走 Alembic）。"""
    from src.db import models  # noqa: F401  确保模型已注册

    Base.metadata.create_all(bind=get_engine(url))
