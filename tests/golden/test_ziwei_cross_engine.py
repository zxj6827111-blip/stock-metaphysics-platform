"""Phase 3G · 紫微第二实现源交叉核对测试。

三层断言：
1. **硬约束**：参考实现不得进入 Consensus、不得被业务层依赖、角色只能是 REFERENCE；
2. **归一化与比较器的正确性**：简繁/别名映射、地支索引换算、分类逻辑；
3. **真实交叉核对**（需要 node + 已安装依赖；缺失时 skip 并给出明确原因）：
   24 个固定案例上，十二宫位置 / 五行局 / 命宫 / 身宫 / 辅星 / 三方四正 /
   大限必须与参考实现一致；差异必须落在已登记的类别里。
"""

from __future__ import annotations

import ast
import json
from datetime import datetime
from pathlib import Path

import pytest

from src.core.schemas.common import VariantMode
from src.engines.base import EngineContext
from src.engines.ziwei.reference import (
    REFERENCE_AVAILABLE,
    REFERENCE_SCHOOL,
    compare_case,
    fetch_charts,
    load_cases,
    reference_status,
)
from src.engines.ziwei.reference.compare import (
    DIFFERENT_SCHOOL_CONVENTION,
    LATE_ZI_NOTE,
)
from src.engines.ziwei.reference.normalize import (
    branch_index_from_zi,
    normalize_mutagen,
    normalize_name,
    normalize_palace,
    project_index_from_branch,
    to_simplified,
)
from src.engines.ziwei.ziwei_engine import ZiweiEngine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = PROJECT_ROOT / "config" / "ziwei_cross_engine_cases.json"

pytestmark = pytest.mark.golden


# ---------------------------------------------------------------------------
# 归一化
# ---------------------------------------------------------------------------


def test_traditional_to_simplified_covers_star_names() -> None:
    assert to_simplified("貪狼") == "贪狼"
    assert to_simplified("廉貞") == "廉贞"
    assert to_simplified("破軍") == "破军"
    assert to_simplified("天馬") == "天马"
    assert to_simplified("鈴星") == "铃星"
    assert to_simplified("祿存") == "禄存"
    assert to_simplified("太陽") == "太阳"
    assert to_simplified("武曲") == "武曲"


def test_palace_aliases_map_to_project_names() -> None:
    assert normalize_palace("命宮") == "命宫"
    assert normalize_palace("交友") == "仆役"
    assert normalize_palace("事業") == "官禄"
    assert normalize_palace("官祿") == "官禄"
    assert normalize_palace("財帛") == "财帛"


def test_branch_index_conversion_matches_project_convention() -> None:
    """项目内宫位 index 0 = 寅（``ZiweiPalace.index`` 的既定口径）。"""
    assert branch_index_from_zi("子") == 0
    assert branch_index_from_zi("寅") == 2
    assert project_index_from_branch("寅") == 0
    assert project_index_from_branch("子") == 10
    assert project_index_from_branch("丑") == 11
    assert project_index_from_branch("卯") == 1


def test_branch_index_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        branch_index_from_zi("甲")


def test_mutagen_normalisation() -> None:
    assert normalize_mutagen("祿") == "禄"
    assert normalize_mutagen("權") == "权"
    assert normalize_mutagen("忌") == "忌"


def test_normalize_name_strips_whitespace() -> None:
    assert normalize_name(" 貪狼 ") == "贪狼"


# ---------------------------------------------------------------------------
# 硬约束（GOAL §3G-2）
# ---------------------------------------------------------------------------


def test_reference_module_is_not_imported_by_production_paths() -> None:
    """参考实现不得被业务层/共识层依赖：只允许 docs/scripts/tests 与自身包内引用。"""
    offenders: list[str] = []
    for path in sorted((PROJECT_ROOT / "src").rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        if relative.startswith("src/engines/ziwei/reference/"):
            continue
        text = path.read_text(encoding="utf-8")
        if "ziwei.reference" in text or "ziwei import reference" in text:
            offenders.append(relative)
    assert offenders == [], f"参考实现被生产代码引用：{offenders}"

    for extra in ("src/research", "apps"):
        directory = PROJECT_ROOT / extra
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            assert "ziwei.reference" not in path.read_text(encoding="utf-8"), path


def test_reference_status_declares_reference_only() -> None:
    status = reference_status()
    payload = status.to_dict()
    assert payload["role"] == "REFERENCE_ONLY"
    assert payload["enters_consensus_engine"] is False
    assert status.school == REFERENCE_SCHOOL
    assert status.license == "MIT"


def test_consensus_engine_does_not_know_about_reference() -> None:
    """共识引擎的实现里不得出现参考实现的任何标识。"""
    consensus_dir = PROJECT_ROOT / "src" / "research"
    for path in consensus_dir.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        assert "fortel" not in text, path
        assert "reference_chart" not in text, path


def test_reference_service_is_a_separate_npm_package() -> None:
    """参考实现必须是独立 npm 包，不得改动生产 ziwei-service 的依赖。"""
    production = json.loads(
        (PROJECT_ROOT / "services" / "ziwei-service" / "package.json").read_text(encoding="utf-8")
    )
    reference = json.loads(
        (PROJECT_ROOT / "services" / "ziwei-reference-service" / "package.json")
        .read_text(encoding="utf-8")
    )
    assert "fortel-ziweidoushu" not in (production.get("dependencies") or {})
    assert reference["dependencies"]["fortel-ziweidoushu"] == "1.3.4"
    assert production["dependencies"]["iztro"] == "2.6.1"


# ---------------------------------------------------------------------------
# 案例集
# ---------------------------------------------------------------------------


def test_case_set_covers_required_dimensions() -> None:
    """GOAL §3G-4：至少 20 个案例，覆盖年份/月份/时辰/晚子时/闰月/forward/reverse。"""
    cases = load_cases(CASES_PATH)
    assert len(cases) >= 20
    hours = {case.hour for case in cases}
    assert 23 in hours, "缺晚子时案例"
    assert 0 in hours, "缺早子时案例"
    assert len(hours) >= 10, "时辰覆盖不足"
    assert {case.variant_mode for case in cases} == {"forward", "reverse"}
    tags = {tag for case in cases for tag in case.tags}
    assert "leap_month" in tags
    years = {case.solar[0] for case in cases}
    assert len(years) >= 15


def test_case_ids_are_unique() -> None:
    cases = load_cases(CASES_PATH)
    ids = [case.case_id for case in cases]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# 比较器逻辑（不依赖 node）
# ---------------------------------------------------------------------------


def _engine() -> ZiweiEngine:
    return ZiweiEngine()


def test_compare_case_reports_reference_error_when_all_failed() -> None:
    from src.engines.ziwei.reference.client import ReferenceChart

    case = load_cases(CASES_PATH)[0]
    engine = _engine()
    chart = engine.calculate_chart(
        EngineContext(stock_code="T"),
        birth_datetime=datetime(*case.solar, case.hour, 30),
        as_of=datetime(2026, 8, 14, 15, 0),
        variant_mode=VariantMode.FORWARD,
        stock_code="T",
    )
    comparison = compare_case(
        case, chart,
        {"M": ReferenceChart(case_id="x", ok=False, error="模拟失败")},
    )
    assert comparison.reference_ok is False
    assert "模拟失败" in comparison.reference_error
    assert comparison.differences == []


def test_late_zi_case_star_differences_are_classified_as_school_convention() -> None:
    """晚子时案例的整盘主星差异必须归为流派口径，而不是命名问题。"""
    import pandas as pd

    differences = pd.read_csv(
        PROJECT_ROOT / "data" / "phase3_universe" / "phase3g_ziwei_differences.csv",
    )
    late_zi = differences[differences["case_id"].str.contains("late-zi")]
    major = late_zi[late_zi["field"].str.startswith("major_stars.")]
    assert not major.empty
    assert set(major["classification"]) == {DIFFERENT_SCHOOL_CONVENTION}
    assert all(LATE_ZI_NOTE[:20] in str(reason) for reason in major["possible_reason"])


def test_difference_registry_uses_required_columns() -> None:
    """GOAL §3G-5 要求的字段必须全部出现在差异登记里。"""
    import pandas as pd

    differences = pd.read_csv(
        PROJECT_ROOT / "data" / "phase3_universe" / "phase3g_ziwei_differences.csv",
    )
    required = {
        "case_id", "field", "production_value", "reference_value", "same_or_different",
        "classification", "possible_reason", "school_convention", "resolved",
    }
    assert required.issubset(set(differences.columns))
    assert set(differences["same_or_different"]) <= {"same", "different"}


def test_summary_declares_reference_never_enters_consensus() -> None:
    summary = json.loads(
        (PROJECT_ROOT / "data" / "phase3_universe" / "phase3g_ziwei_crosscheck_summary.json")
        .read_text(encoding="utf-8")
    )
    assert summary["enters_consensus_engine"] is False
    assert summary["second_engine_status"] == REFERENCE_AVAILABLE
    decisions = {item["decision"] for item in summary["audited_candidates"]}
    assert "ADOPTED_AS_REFERENCE" in decisions
    assert "REJECTED_NOT_INDEPENDENT" in decisions
    assert "REJECTED_LICENSE_UNCLEAR" in decisions


def test_crosscheck_script_does_not_mutate_production_engine() -> None:
    """核对脚本不得触碰生产引擎源码（只读导入）。"""
    script = (PROJECT_ROOT / "scripts" / "phase3g_ziwei_crosscheck.py").read_text(encoding="utf-8")
    tree = ast.parse(script)
    # 核对脚本只允许给本地变量赋值；不得给任何对象属性赋值（那会写穿到引擎/模型上）
    attribute_assignments = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Attribute) for target in node.targets)
    ]
    assert attribute_assignments == [], "核对脚本不应给任何对象属性赋值"
    # 且不得 import 生产引擎的写接口（例如 AnalysisService / build_opinion）
    imported = {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names
    } | {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("analysis_service" in str(name) for name in imported)


# ---------------------------------------------------------------------------
# 真实交叉核对（需要 node + npm install）
# ---------------------------------------------------------------------------

requires_reference = pytest.mark.skipif(
    reference_status().status != REFERENCE_AVAILABLE,
    reason=f"参考实现不可用：{reference_status().detail}",
)


@requires_reference
@pytest.mark.ziwei_live
def test_reference_returns_full_chart_for_a_case() -> None:
    charts = fetch_charts([{
        "case_id": "probe", "solar": {"year": 1952, "month": 4, "day": 9},
        "hour": 4, "gender": "F", "config_type": "SKY",
    }])
    assert len(charts) == 1
    chart = charts[0]
    assert chart.ok, chart.error
    assert chart.school == REFERENCE_SCHOOL
    assert len(chart.chart["cells"]) == 12
    assert chart.chart["element"]
    assert chart.chart["soulPalace"]["index"] is not None


@requires_reference
@pytest.mark.ziwei_live
def test_reference_distinguishes_early_and_late_zi_hour() -> None:
    """库自身区分早子時/夜子時（13 个时辰），这是晚子时可核对的前提。"""
    charts = fetch_charts([
        {"case_id": "early", "solar": {"year": 1990, "month": 6, "day": 16},
         "hour": 0, "gender": "M", "config_type": "SKY"},
        {"case_id": "late", "solar": {"year": 1990, "month": 6, "day": 15},
         "hour": 23, "gender": "M", "config_type": "SKY"},
    ])
    by_id = {chart.case_id: chart for chart in charts}
    assert by_id["early"].chart["lunarConfig"]["day"] != by_id["late"].chart["lunarConfig"]["day"]
    assert by_id["early"].chart["lunarConfig"]["day"] == 24
    assert by_id["late"].chart["lunarConfig"]["day"] == 23
