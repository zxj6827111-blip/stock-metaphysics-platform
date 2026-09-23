"""择日关系扫描 v3 证据文件的可复现性回归（bazi-relation-v3）。

``docs/relation-v3-evidence/pingan-000001-2026-v3.csv`` 不是手工作品，
它必须能由当前生产代码逐日、逐字段再生：

* 原局（000001 年/月/日三柱 + 日主 + 喜用忌仇闲）在两条解析路径上相等；
* 365 天的流日事件、S/V/U、结构分组、流日十神与喜忌 verdict 全部复现。

如果某天或某个字段复现失败，说明「计算口径」或「 evidence 产物」两者
至少有一个出现了漂移——此时应当提升 relation_rule_version 并重新生成证据，
而不是改测试断言去迁就结果。
"""

from __future__ import annotations

import csv
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pytest

from src.core.orchestration.date_relation_scan import _load_static_natal_cache
from src.core.relations.date_relation import (
    COMPOUND_RELATIONS,
    DISTURBING_RELATIONS,
    SUPPORTIVE_RELATIONS,
    build_day_stem_verdict,
    build_relation_matrix,
    classify_relation_group,
    events_for_source_pillar,
)
from src.core.schemas.calendar import GanZhi
from src.engines.bazi.bazi_engine import BaziEngine
from src.engines.calendar.calendar_engine import CalendarEngine

CSV_PATH = Path(__file__).resolve().parents[2] / "docs" / "relation-v3-evidence" / "pingan-000001-2026-v3.csv"
EXPECTED_COLUMNS = [
    "date", "day_ganzhi", "day_stem", "relation_types", "S", "V", "U", "group",
    "day_stem_wuxing", "ten_god", "ten_god_group", "wuxing_role", "verdict", "is_yong_or_xi",
]


def _load_rows() -> list[dict[str, str]]:
    assert CSV_PATH.exists(), f"证据文件缺失: {CSV_PATH}"
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        assert list(reader.fieldnames or []) == EXPECTED_COLUMNS
        return list(reader)


@lru_cache(maxsize=1)
def _pingan_natal():
    """解析 000001 的 v3 原局并缓存（365 天复用同一份输入）。

    优先版本化快照（本地），否则退回确定性引擎（CI）。
    两条路径已在本文件的 ``test_pingan_natal_two_channel_equivalence`` 中对拍
    （年/月/日三柱与喜用忌仇闲五类都相同）；构造次数从每日一次降为一次。
    """
    static = _load_static_natal_cache().get("000001")
    if static is not None:
        return static
    # CI 没有 phase4 离线快照，直接按 canonical birth profile 现场排盘。
    from src.core.orchestration.date_relation_scan import _snapshot_from_chart

    chart = BaziEngine().build_chart(
        birth_datetime=datetime(1991, 4, 3, 9, 30),
        as_of=datetime(2026, 1, 5, 12),
        variant_mode="not_applicable",
        stock_code="000001",
    )
    return _snapshot_from_chart(chart)


@lru_cache(maxsize=1)
def _calendar() -> CalendarEngine:
    return CalendarEngine()


@pytest.mark.parametrize("row", _load_rows(), ids=lambda row: row["date"])
def test_evidence_csv_reproduces_from_live_engine(row):
    natal = _pingan_natal()
    calendar = _calendar()
    day = datetime.fromisoformat(row["date"]).replace(hour=12)
    snapshot = calendar.snapshot(day)

    natal_matrix = {
        position: GanZhi.from_text(natal.stems[position] + natal.branches[position])
        for position in ("year", "month", "day")
    }
    external = {
        "year": snapshot.year_ganzhi,
        "month": snapshot.month_ganzhi,
        "day": snapshot.day_ganzhi,
    }
    matrix = build_relation_matrix(external, natal_matrix, day_master=natal.day_master)
    events = events_for_source_pillar(matrix, "day")
    types = list(dict.fromkeys(event.relation_type for event in events))
    s = sum(1 for event in events if event.relation_type in SUPPORTIVE_RELATIONS)
    v = sum(1 for event in events if event.relation_type in DISTURBING_RELATIONS)
    u = sum(1 for event in events if event.relation_type in COMPOUND_RELATIONS)
    verdict = build_day_stem_verdict(
        day_master=natal.day_master,
        day_stem=snapshot.day_ganzhi.stem,
        yong_shen=natal.yong_shen,
        xi_shen=natal.xi_shen,
        ji_shen=natal.ji_shen,
        chou_shen=natal.chou_shen,
        xian_shen=natal.xian_shen,
    )
    actual = {
        "date": day.date().isoformat(),
        "day_ganzhi": snapshot.day_ganzhi.text,
        "day_stem": snapshot.day_ganzhi.stem,
        "relation_types": "/".join(types),
        "S": str(s),
        "V": str(v),
        "U": str(u),
        "group": classify_relation_group(s, v, u),
        "day_stem_wuxing": verdict.day_stem_wuxing,
        "ten_god": verdict.ten_god,
        "ten_god_group": verdict.ten_god_group,
        "wuxing_role": verdict.wuxing_role,
        "verdict": verdict.verdict,
        "is_yong_or_xi": "" if verdict.is_yong_or_xi is None else str(verdict.is_yong_or_xi),
    }
    assert actual == row, (
        f"{row['date']} 复现失败（证据文件与当前生产代码不一致；"
        f"如果有意改口径必须提升 relation_rule_version 并重新生成证据）\n"
        f"expected(csv)={row}\nactual(engine)={actual}"
    )


def test_evidence_csv_distribution_summary():
    """汇总断言与 docs/calculation-differences-relation.md 的登记数字一致。"""
    rows = _load_rows()
    assert len(rows) == 365
    assert {row["verdict"] for row in rows} == {"不匹配", "匹配"}
    assert sum(1 for row in rows if row["verdict"] == "匹配") == 144
    assert sum(1 for row in rows if row["verdict"] == "不匹配") == 221
    assert len({row["ten_god"] for row in rows}) == 10, "全年十神必须由流日干驱动，十种全出现"
    assert len({row["group"] for row in rows}) >= 2, "全年至少出现两种结构分组"


def _resolve_natal_from_static():
    return _load_static_natal_cache().get("000001")


def test_pingan_natal_two_channel_equivalence():
    """000001 的静态快照与引擎现场排盘必须给出同一份矩阵输入。

    这一断言把「本地（static）」与「CI（engine）」环境固定在同一口径，
    防止测试在不同环境里悄悄测到不同内容。
    """
    static = _resolve_natal_from_static()
    if static is None:
        pytest.skip("静态原局快照不可用（CI 环境），仅以引擎路径运行证据复现")
    from src.core.orchestration.date_relation_scan import _snapshot_from_chart

    chart = BaziEngine().build_chart(
        birth_datetime=datetime(1991, 4, 3, 9, 30),
        as_of=datetime(2026, 9, 22, 12),
        variant_mode="not_applicable",
        stock_code="000001",
    )
    engine = _snapshot_from_chart(chart)
    for position in ("year", "month", "day"):
        assert (engine.stems[position], engine.branches[position]) == (
            static.stems[position], static.branches[position],
        ), f"{position} 柱两通道不一致"
    assert engine.day_master == static.day_master
    assert engine.yong_shen == static.yong_shen
    assert engine.xi_shen == static.xi_shen
    assert engine.ji_shen == static.ji_shen
    assert engine.chou_shen == static.chou_shen
    assert engine.xian_shen == static.xian_shen
