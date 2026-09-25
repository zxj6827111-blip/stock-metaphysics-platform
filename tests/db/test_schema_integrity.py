"""数据库 schema 审计（验收 §11）。

机械校验 docs/database.md 承诺的内容：

1. 16+1 张业务表全部存在；
2. 关键唯一约束存在且真的被数据库执行；
3. 外键约束在写入端生效；
4. 版本化语义：``stock_birth_profile`` / ``chart_artifact`` /
   ``factor_observation`` 不允许同版本覆盖后丢失历史；
5. 每张业务表都有创建/更新时间语义字段。
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import inspect, text

EXPECTED_TABLES = {
    "stock_master", "stock_birth_profile", "exchange_session_calendar",
    "market_bar_daily", "market_fetch_log",
    "engine_version", "engine_run", "chart_artifact",
    "factor_definition", "factor_observation",
    "classical_book", "classical_entry", "evidence_link",
    "backtest_experiment", "backtest_result",
    "analysis_run", "forward_label",
}

#: 每张业务表都必须有时间戳字段（created_at 或等价领域时间戳）
TIMESTAMP_EQUIVALENTS: dict[str, set[str]] = {
    "stock_master": {"created_at", "updated_at"},
    "stock_birth_profile": {"created_at", "updated_at"},
    "exchange_session_calendar": {"created_at", "updated_at"},
    "market_bar_daily": {"ingested_at", "updated_at"},
    "market_fetch_log": {"fetched_at", "updated_at"},
    "engine_version": {"registered_at", "updated_at"},
    "engine_run": {"created_at", "updated_at"},
    "chart_artifact": {"calculated_at", "updated_at"},
    "factor_definition": {"created_at", "updated_at"},
    "factor_observation": {"computed_at", "updated_at"},
    "classical_book": {"updated_at"},
    "classical_entry": {"updated_at"},
    "evidence_link": {"created_at", "updated_at"},
    "backtest_experiment": {"created_at", "updated_at"},
    "backtest_result": {"created_at", "updated_at"},
    "forward_label": {"created_at", "updated_at"},
    "analysis_run": {"created_at", "updated_at"},
}


@pytest.fixture()
def engine():
    from src.db.base import get_engine, init_db

    init_db()
    return get_engine()


class TestSchemaCompleteness:
    def test_all_business_tables_exist(self, engine):
        with engine.connect() as conn:
            existing = {
                r[0] for r in conn.execute(
                    text("select name from sqlite_master where type='table'")
                )
            }
        missing = EXPECTED_TABLES - existing
        assert not missing, f"缺少业务表: {missing}"

    def test_every_table_has_timestamp_columns(self, engine):
        insp = inspect(engine)
        for table, required in TIMESTAMP_EQUIVALENTS.items():
            cols = {c["name"] for c in insp.get_columns(table)}
            missing = required - cols
            assert not missing, f"{table} 缺少时间戳列: {missing}"

    def test_chart_artifact_birth_version_column_fits_frozen_fortune_version(self):
        from src.db.models import ChartArtifactRow

        column = ChartArtifactRow.__table__.c.birth_profile_version
        assert column.type.length >= len("stock-fortune-birth-v2")

    def test_unique_constraints_present(self, engine):
        insp = inspect(engine)
        expected_uniques = {
            "stock_birth_profile": {"stock_code", "birth_basis", "birth_profile_version"},
            "market_bar_daily": {"stock_code", "trade_date", "adjust"},
            "factor_observation": {"stock_code", "as_of", "factor_id", "rule_version"},
            "factor_definition": {"factor_id", "rule_version"},
            "engine_version": {"engine_id", "engine_version"},
            "forward_label": {"stock_code", "as_of", "benchmark_code", "label_source"},
        }
        for table, cols in expected_uniques.items():
            found = [set(u["column_names"]) for u in insp.get_unique_constraints(table)]
            assert cols in found, f"{table} 缺少唯一约束 {cols}（实际: {found}）"


class TestVersioningSemantics:
    """版本化是不可破坏的契约：新版本生成新行，永不覆盖。"""

    def test_birth_profile_versions_coexist(self, db_session):
        from src.db.models import StockBirthProfileRow, StockMasterRow

        db_session.add(StockMasterRow(stock_code="TST001", name="测试", exchange="SSE"))
        for v in ("v1", "v2"):
            db_session.add(StockBirthProfileRow(
                stock_code="TST001", exchange="SSE", birth_basis="listing_open",
                birth_datetime=datetime(2001, 8, 27, 9, 30),
                source="test", birth_profile_version=v,
            ))
        db_session.flush()
        rows = db_session.query(StockBirthProfileRow).filter_by(stock_code="TST001").count()
        assert rows == 2, "不同 birth_profile_version 必须并存"

    def test_chart_artifact_keeps_old_engine_versions(self, db_session):
        from src.db.models import ChartArtifactRow

        for ver in ("smx-bazi-native-1.0.0", "smx-bazi-native-9.9.9"):
            db_session.add(ChartArtifactRow(
                chart_id=f"chart-{ver}", stock_code="TST001", engine="bazi",
                engine_version=ver, as_of=datetime(2024, 1, 1),
                input_json={}, raw_chart={"stub": True},
            ))
        db_session.flush()
        count = db_session.query(ChartArtifactRow).filter_by(stock_code="TST001").count()
        assert count == 2, "chart_artifact 必须保留旧 engine_version 的盘面"

    def test_chart_artifact_preserves_frozen_fortune_birth_profile_version(self, db_session):
        from src.db.models import ChartArtifactRow

        version = "stock-fortune-birth-v2"
        db_session.add(ChartArtifactRow(
            chart_id="chart-stock-fortune-birth-v2",
            stock_code="TST003",
            engine="bazi",
            engine_version="bazi-v1",
            birth_profile_version=version,
            as_of=datetime(2024, 1, 1),
            input_json={},
            raw_chart={"stub": True},
        ))
        db_session.flush()
        stored = db_session.query(ChartArtifactRow).filter_by(
            chart_id="chart-stock-fortune-birth-v2"
        ).one()
        assert stored.birth_profile_version == version

    def test_fortune_artifact_writer_is_idempotent(self, db_session):
        from zoneinfo import ZoneInfo

        from src.core.orchestration.stock_fortune import DatabaseFortuneChartArtifactWriter
        from src.db.models import ChartArtifactRow

        writer = DatabaseFortuneChartArtifactWriter(db_session)
        payload = {
            "engine_id": "bazi",
            "engine_version": "bazi-v1",
            "symbol": "TST004",
            "as_of": datetime(2025, 1, 2, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
            "input_payload": {"request": "same"},
            "raw_chart": {"pillars": ["甲子", "乙丑", "丙寅", "丁卯"]},
            "assumptions": [{"key": "mode", "value": "forward"}],
            "warnings": [],
            "birth_profile_version": "stock-fortune-birth-v2",
            "config_version": "config-test-v1",
        }
        first_id = writer.persist_chart_artifact(**payload)
        replay_id = writer.persist_chart_artifact(**payload)

        assert replay_id == first_id
        assert db_session.query(ChartArtifactRow).filter_by(chart_id=first_id).count() == 1
        row = db_session.get(ChartArtifactRow, first_id)
        assert row is not None
        assert row.birth_profile_version == "stock-fortune-birth-v2"
        assert row.raw_chart == payload["raw_chart"]

    def test_factor_observation_distinguishes_rule_versions(self, db_session):
        from src.db.models import FactorObservationRow

        for rule_version in ("v1", "v2"):
            db_session.add(FactorObservationRow(
                factor_id="B_NATAL_001", stock_code="TST001",
                as_of=datetime(2024, 1, 1), engine="bazi", category="natal",
                normalized_value=1.0, direction=1, rule_score=10.0,
                rule_version=rule_version,
            ))
        db_session.flush()
        count = db_session.query(FactorObservationRow).filter_by(
            stock_code="TST001", factor_id="B_NATAL_001"
        ).count()
        assert count == 2, "同因子不同 rule_version 必须并存"

    def test_duplicate_same_version_rejected(self, db_session):
        """唯一约束必须真的被数据库执行（不是只靠应用层自觉）。"""
        from sqlalchemy.exc import IntegrityError

        from src.db.models import StockBirthProfileRow, StockMasterRow

        db_session.add(StockMasterRow(stock_code="TST002", name="x", exchange="SSE"))
        db_session.add(StockBirthProfileRow(
            stock_code="TST002", exchange="SSE", birth_basis="listing_open",
            birth_datetime=datetime(2000, 1, 1), source="t", birth_profile_version="v1",
        ))
        db_session.flush()
        db_session.add(StockBirthProfileRow(
            stock_code="TST002", exchange="SZSE", birth_basis="listing_open",
            birth_datetime=datetime(2000, 1, 2), source="t", birth_profile_version="v1",
        ))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()


class TestForeignKeys:
    def test_birth_profile_requires_existing_stock(self, db_session):
        from sqlalchemy.exc import IntegrityError

        from src.db.models import StockBirthProfileRow

        db_session.add(StockBirthProfileRow(
            stock_code="NO_SUCH_STOCK", exchange="SSE", birth_basis="listing_open",
            birth_datetime=datetime(2000, 1, 1), source="t", birth_profile_version="v1",
        ))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_foreign_keys_pragma_enabled(self, db_session):
        result = db_session.execute(text("PRAGMA foreign_keys")).scalar()
        assert result == 1, "SQLite 外键约束未启用（foreign_keys=ON 是基础完整性保障）"
