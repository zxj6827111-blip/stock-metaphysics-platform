"""第三方隔离测试（ADR-0001）—— 架构约束的机器可验证版本。

规则（AGENTS.md §12）：
    * 业务层不得直接 import 第三方排盘 / 行情库；
    * 只允许 Adapter 模块持有第三方对象；
    * 业务层不得消费第三方对象（如 lunar-python 的 ``Lunar`` / ``EightChar``）。
"""

from __future__ import annotations

import ast
import pathlib

import pytest

#: 允许直接 import 第三方库的模块白名单（Adapter 层）
ALLOWED_LUNAR = {
    pathlib.Path("src/engines/calendar/calendar_engine.py"),
    pathlib.Path("src/engines/bazi/bazi_engine.py"),   # 仅用于大运/胎元等辅助字段
}
ALLOWED_AKSHARE = {
    pathlib.Path("src/market/providers/akshare_provider.py"),
}

SKIP_DIRS = {".venv", "node_modules", "__pycache__", ".next"}


def _iter_python_files(root: str = "src") -> list[pathlib.Path]:
    base = pathlib.Path(root)
    return [
        p for p in base.rglob("*.py")
        if not any(part in SKIP_DIRS for part in p.parts)
    ]


def _imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


class TestThirdPartyIsolation:
    def test_lunar_python_only_in_allowed_adapters(self):
        offenders = [
            str(p) for p in _iter_python_files("src")
            if "lunar_python" in _imported_modules(p) and p not in ALLOWED_LUNAR
        ]
        assert not offenders, f"lunar_python 泄漏到业务层：{offenders}"

    def test_akshare_only_in_market_adapter(self):
        offenders = [
            str(p) for p in _iter_python_files("src")
            if "akshare" in _imported_modules(p) and p not in ALLOWED_AKSHARE
        ]
        assert not offenders, f"akshare 泄漏到业务层：{offenders}"

    def test_api_layer_does_not_import_third_party(self):
        offenders: list[str] = []
        for path in pathlib.Path("apps").rglob("*.py"):
            mods = _imported_modules(path)
            for forbidden in ("lunar_python", "akshare"):
                if forbidden in mods:
                    offenders.append(f"{path}: {forbidden}")
        assert not offenders, f"API 层直接依赖第三方库：{offenders}"

    def test_factors_layer_does_not_import_third_party(self):
        offenders: list[str] = []
        for path in pathlib.Path("src/factors").rglob("*.py"):
            mods = _imported_modules(path)
            for forbidden in ("lunar_python", "akshare"):
                if forbidden in mods:
                    offenders.append(f"{path}: {forbidden}")
        assert not offenders, f"因子层直接依赖第三方库：{offenders}"

    def test_research_layer_does_not_import_third_party(self):
        offenders: list[str] = []
        for path in pathlib.Path("src/research").rglob("*.py"):
            mods = _imported_modules(path)
            for forbidden in ("lunar_python", "akshare"):
                if forbidden in mods:
                    offenders.append(f"{path}: {forbidden}")
        assert not offenders, f"研究层直接依赖第三方库：{offenders}"

    def test_knowledge_layer_is_isolated(self):
        offenders: list[str] = []
        for path in pathlib.Path("src/knowledge").rglob("*.py"):
            mods = _imported_modules(path)
            for forbidden in ("lunar_python", "akshare"):
                if forbidden in mods:
                    offenders.append(f"{path}: {forbidden}")
        assert not offenders


class TestEngineContractsExist:
    """六个核心接口必须存在且可实例化（Phase 2 不得破坏的契约）。"""

    def test_calendar_engine_implements_base(self):
        from src.engines.base import MetaphysicsEngine
        from src.engines.calendar.calendar_engine import CalendarEngine

        assert issubclass(CalendarEngine, MetaphysicsEngine)

    def test_huangli_engine_implements_base(self):
        from src.engines.base import MetaphysicsEngine
        from src.engines.huangli.huangli_engine import HuangliEngine

        assert issubclass(HuangliEngine, MetaphysicsEngine)

    def test_bazi_engine_implements_base(self):
        from src.engines.base import MetaphysicsEngine
        from src.engines.bazi.bazi_engine import BaziEngine

        assert issubclass(BaziEngine, MetaphysicsEngine)

    def test_market_data_provider_interface(self):
        from src.market.providers.base import MarketDataProvider

        for method in ("search", "get_stock", "get_daily_bars", "get_benchmark_bars"):
            assert hasattr(MarketDataProvider, method)

    def test_knowledge_provider_interface(self):
        from src.knowledge.retrieval.provider import KnowledgeProvider

        assert hasattr(KnowledgeProvider, "search")
        assert hasattr(KnowledgeProvider, "entry_count")

    def test_backtest_provider_interface(self):
        from src.research.backtest.provider import BacktestProvider

        for method in ("evaluate_factor", "evaluate_signal", "evaluate_negative_controls"):
            assert hasattr(BacktestProvider, method)

    def test_all_engines_declare_metadata(self):
        from src.engines.bazi.bazi_engine import BaziEngine
        from src.engines.calendar.calendar_engine import CalendarEngine
        from src.engines.huangli.huangli_engine import HuangliEngine

        for cls in (CalendarEngine, HuangliEngine, BaziEngine):
            meta = cls.metadata
            assert meta.engine_id
            assert meta.engine_version
            assert meta.third_party
            assert meta.display_name


class TestPlaceholderEngines:
    """未实现的术数引擎只能预留接口，不得返回伪造结果。"""

    def test_ziwei_engine_is_placeholder(self):
        import pathlib

        ziwei = pathlib.Path("src/engines/ziwei")
        files = [p for p in ziwei.rglob("*.py") if p.name != "__init__.py"]
        # Phase 1 允许为空（仅占位），一旦有实现必须实现 MetaphysicsEngine
        for path in files:
            text = path.read_text(encoding="utf-8")
            assert "MetaphysicsEngine" in text or "Phase 2" in text

    def test_package_dirs_exist_for_future_engines(self):
        import pathlib

        for name in ("ziwei", "liuyao", "qimen"):
            assert (pathlib.Path("src/engines") / name).is_dir(), f"缺少 {name} 预留目录"


class TestNoBusinessEnumLeakage:
    """业务层不得消费第三方对象类型。"""

    def test_no_lunar_types_in_schemas(self):
        """Schema 模块的**类型注解**中不得出现第三方类型名。

        用 AST 精确判断注解，避免把 `lunar: LunarDate` 这类本项目类型误判。
        """
        import ast
        import pathlib

        forbidden_exact = {"Lunar", "EightChar", "Solar", "JieQi", "DaYun"}

        def annotation_names(node: ast.AST) -> set[str]:
            found: set[str] = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name):
                    found.add(sub.id)
                elif isinstance(sub, ast.Attribute):
                    found.add(sub.attr)
            return found

        offenders: list[str] = []
        for path in pathlib.Path("src/core/schemas").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.AnnAssign) and node.annotation is not None:
                    hit = annotation_names(node.annotation) & forbidden_exact
                    if hit:
                        offenders.append(f"{path}:{node.lineno} -> {sorted(hit)}")
                elif isinstance(node, ast.arg) and node.annotation is not None:
                    hit = annotation_names(node.annotation) & forbidden_exact
                    if hit:
                        offenders.append(f"{path}:{node.lineno} -> {sorted(hit)}")

        assert not offenders, f"Schema 暴露了第三方类型注解：{offenders}"

    def test_calendar_snapshot_has_raw_source_but_typed_fields(self):
        """raw_source 只用于审计；其余字段必须是本项目自己的类型。"""
        from datetime import datetime

        from src.engines.calendar.calendar_engine import CalendarEngine

        snap = CalendarEngine().snapshot(datetime(2024, 1, 1, 12, 0))
        assert isinstance(snap.raw_source, dict)
        # 结构化字段不是第三方对象
        assert isinstance(snap.day_ganzhi.text, str)
        assert not hasattr(snap.day_ganzhi, "getDayGan")
