"""`load_historical_stats` 的真实库调用回归。

为什么单独写这一批
------------------
这个函数是 `GET /api/v1/analysis/{id}/report`（导出报告）的必经路径，但**此前全仓库
没有任何测试真正调用过它** —— 于是它长期访问一个不存在的列
（`BacktestExperimentRow.payload_json`，真实列名是 `universe_json` / `factor_ids_json`），
接口在真实调用时 **100% 返回 500**。

前端一直没有导出入口，所以这个坏路径从未被触发；本轮把导出接上 UI 后，
真实模式 E2E 立刻把它打出来了。教训：**"没有测试的代码路径"不等于"能用的代码路径"**。

这里因此**不 mock 会话、不 mock 模型**：直接在真实 schema 上建实验与结果行，
按真实列写入，再断言返回值。
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.db.base import Base
from src.db.models import BacktestExperimentRow, BacktestResultRow


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine)
    session = maker()
    try:
        yield session
    finally:
        session.close()


def _exp(db: Session, eid: str, universe=None, factors=None) -> None:
    db.add(
        BacktestExperimentRow(
            experiment_id=eid,
            kind="event_study",
            name=f"exp {eid}",
            factor_ids_json=factors,
            universe_json=universe,
            horizons_json=[5, 20],
            methodology="等权事件研究",
            status="completed",
        )
    )


def _res(db: Session, eid: str, variant: str = "real") -> None:
    db.add(
        BacktestResultRow(
            experiment_id=eid,
            variant=variant,
            horizon=20,
            sample_count=42,
            up_rate=0.5,
            mean_return=0.01,
            median_return=0.008,
            std_return=0.12,
            mean_excess_return=0.002,
            max_drawdown=-0.15,
        )
    )


class TestLoadHistoricalStats:
    def test_does_not_touch_nonexistent_payload_column(self, db: Session):
        """核心回归：函数必须在真实模型上跑通（修前这里抛 AttributeError）。"""
        from src.core.orchestration.evidence import load_historical_stats

        _exp(db, "EXP-1", universe=[{"stock_code": "600519"}])
        _res(db, "EXP-1")
        db.commit()

        out = load_historical_stats(db, "600519")
        assert out["status"] == "AVAILABLE"
        assert out["experiments"] == ["EXP-1"]
        assert out["universe_size"] == 1
        assert out["results"][0]["sample_count"] == 42
        assert out["methodology"]

    def test_matches_stock_in_universe_list(self, db: Session):
        from src.core.orchestration.evidence import load_historical_stats

        _exp(db, "EXP-A", universe=["600519", "000001"])
        _exp(db, "EXP-B", universe=["300750"])
        _res(db, "EXP-A")
        _res(db, "EXP-B")
        db.commit()

        assert load_historical_stats(db, "000001")["experiments"] == ["EXP-A"]
        assert load_historical_stats(db, "300750")["experiments"] == ["EXP-B"]

    def test_matches_stock_in_universe_dicts(self, db: Session):
        """股票池可能是对象列表（研究管线写入的形态），也要能匹配。"""
        from src.core.orchestration.evidence import load_historical_stats

        _exp(db, "EXP-C", universe=[{"stock_code": "600519", "name": "贵州茅台"}])
        _res(db, "EXP-C")
        db.commit()

        assert load_historical_stats(db, "600519")["experiments"] == ["EXP-C"]

    def test_matches_stock_in_factor_ids(self, db: Session):
        """研究实验不按股票池、而按因子清单关联时，仍要能找到相关实验。"""
        from src.core.orchestration.evidence import load_historical_stats

        _exp(db, "EXP-D", universe=[], factors=["B_NATAL_001"])
        _res(db, "EXP-D")
        db.commit()

        assert load_historical_stats(db, "B_NATAL_001")["experiments"] == ["EXP-D"]

    def test_returns_not_run_when_no_experiment_references_stock(self, db: Session):
        """没有相关实验 → 如实 NOT_RUN，不编造统计。"""
        from src.core.orchestration.evidence import load_historical_stats

        _exp(db, "EXP-E", universe=["300750"])
        _res(db, "EXP-E")
        db.commit()

        out = load_historical_stats(db, "600519")
        assert out["status"] == "NOT_RUN"
        assert "尚无历史验证实验记录" in out["note"]

    def test_experiment_without_results_is_not_run(self, db: Session):
        from src.core.orchestration.evidence import load_historical_stats

        _exp(db, "EXP-F", universe=["600519"])
        db.commit()

        out = load_historical_stats(db, "600519")
        assert out["status"] == "NOT_RUN"
        assert out["experiments"] == ["EXP-F"]
        assert "没有结果行" in out["note"]

    def test_empty_tables_return_not_run(self, db: Session):
        from src.core.orchestration.evidence import load_historical_stats

        out = load_historical_stats(db, "600519")
        assert out["status"] == "NOT_RUN"

    def test_null_json_columns_do_not_crash(self, db: Session):
        """JSON 列为 NULL 时不得抛异常（研究管线的早期实验可能没有股票池）。"""
        from src.core.orchestration.evidence import load_historical_stats

        _exp(db, "EXP-G", universe=None, factors=None)
        db.commit()
        out = load_historical_stats(db, "600519")
        assert out["status"] == "NOT_RUN"
