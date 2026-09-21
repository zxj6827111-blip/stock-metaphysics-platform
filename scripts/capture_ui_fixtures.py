"""把演示模式（`?fixture=ui-reference`）用到的研究样本**从真实来源重新冻结**。

为什么需要它
------------
上一轮的演示样本是**手写**的：古籍条目是编的（`EV-SUP-01` 之类），
历史验证样本带着"胜率具备初步统计显著性"这种从未跑过的研究结论。
演示面板看起来越完整，伪造的结论就越容易被当真 ——
所以演示样本必须与真实模式**同源**，只是被冻结。

本脚本做三件事（全部只读，不写共享研究库）：
1. 古籍证据：对真实因子组合跑一次 KnowledgeProvider 检索，冻结返回条目
   （entry_id / 书名 / 版本 / provenance / license_status 与真实模式逐条一致）；
2. 研究实验：从 `backtest_experiment` / `backtest_result` 里取**已入库**的
   真实实验（含负对照判决与 Jaccard），冻结详情；
3. 逐因子研究结论：**没有**该能力，因此把 EventStudy 冻结成"未运行"的空态，
   而不是编一组好看的收益数字。

用法
----
    python scripts/capture_ui_fixtures.py            # 打印 JSON（供人工核对后粘贴）
    python scripts/capture_ui_fixtures.py --write    # 直接改写 apps/web/lib/fixture.ts
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:  # 直接以脚本方式运行时也能 import src.*
    sys.path.insert(0, str(PROJECT_ROOT))

DB_PATH = PROJECT_ROOT / "data" / "smp.sqlite3"
FIXTURE_TS = PROJECT_ROOT / "apps" / "web" / "lib" / "fixture.ts"

#: 古籍证据样本使用的真实因子组合（名称见因子字典）
EVIDENCE_FACTORS = ["B_NATAL_001", "B_NATAL_002", "B_NATAL_009"]

#: 研究实验样本：一个多持有期的事件研究（含四类负对照）+ 一个负对照失效的例子
EXPERIMENT_IDS = ["EXP-20260918162712-ddade1", "EXP-20260918173500-6f0889"]


# ----------------------------------------------------------------------
# ① 古籍证据
# ----------------------------------------------------------------------
def build_evidence() -> dict:
    from src.factors.registry.definitions import DEFINITION_INDEX
    from src.knowledge.retrieval.provider import (
        build_query_from_factors,
        get_knowledge_provider,
    )

    provider = get_knowledge_provider()
    bundle = provider.search(build_query_from_factors(EVIDENCE_FACTORS))
    payload = bundle.model_dump(mode="json")

    def item(e: dict) -> dict:
        return {
            "entry_id": e["entry_id"],
            "book": e["book"],
            "chapter": e.get("chapter") or "",
            "school": e.get("school") or "",
            "topic": e.get("topic") or [],
            "original_text": e["original_text"],
            "modern_note": e.get("modern_note") or "",
            "score": e["score"],
            "authority_weight": e.get("authority_weight"),
            "stance": e.get("stance"),
            "source": e.get("source") or "",
            "edition": e.get("edition") or "",
            "provenance": e.get("provenance") or "",
            "license_status": e.get("license_status") or "",
            "matched_query_terms": e.get("matched_query_terms") or [],
        }

    return {
        "analysis_id": "AN-20241115143200-600519-987e89",
        "driver_factors": [
            {
                "factor_id": fid,
                "name": DEFINITION_INDEX[fid].name,
                "normalized_value": None,
                "direction": 1,
            }
            for fid in EVIDENCE_FACTORS
            if fid in DEFINITION_INDEX
        ],
        "evidence": {
            "query": {
                "query": payload["query"]["query"],
                "factor_ids": payload["query"]["factor_ids"],
                "topics": payload["query"]["topics"],
            },
            "supporting_evidence": [item(e) for e in payload["supporting_evidence"]],
            "counter_evidence": [item(e) for e in payload["counter_evidence"]],
            "neutral_evidence": [item(e) for e in payload["neutral_evidence"]],
            "total_candidates": payload["total_candidates"],
            "retrieval_method": payload["retrieval_method"],
            "knowledge_version": payload["knowledge_version"],
            "note": payload["note"],
        },
        "disclaimer": (
            "古籍条文只说明传统术数的说法，不构成对股票收益的任何判断。"
            "条目文字由项目组从公版古籍录入，未逐字对照权威刊本校勘，正式引用前必须完成校勘。"
        ),
    }


# ----------------------------------------------------------------------
# ② 研究实验（只读既有结果）
# ----------------------------------------------------------------------
def build_experiments(conn: sqlite3.Connection) -> tuple[list[dict], dict[str, dict]]:
    conn.row_factory = sqlite3.Row
    summaries: list[dict] = []
    details: dict[str, dict] = {}

    for eid in EXPERIMENT_IDS:
        row = conn.execute(
            "select * from backtest_experiment where experiment_id=?", (eid,)
        ).fetchone()
        if row is None:
            print(f"  [warn] 实验不存在，跳过：{eid}", file=sys.stderr)
            continue
        exp = dict(row)
        results = [
            dict(r)
            for r in conn.execute(
                "select * from backtest_result where experiment_id=? "
                "order by variant, cast(horizon as integer)",
                (eid,),
            )
        ]
        grouped: dict[str, list[dict]] = {}
        for r in results:
            grouped.setdefault(r["variant"], []).append(
                {
                    "horizon": str(r["horizon"]),
                    "sample_count": r["sample_count"],
                    "up_rate": r["up_rate"],
                    "mean_return": r["mean_return"],
                    "median_return": r["median_return"],
                    "mean_excess_return": r["mean_excess_return"],
                    "max_drawdown": r["max_drawdown"],
                    "excess_up_rate": r["excess_up_rate"],
                    "extra": json.loads(r["extra_json"] or "{}"),
                }
            )
        summaries.append(
            {
                "experiment_id": str(exp["experiment_id"]),
                "kind": str(exp["kind"]),
                "name": exp["name"],
                "factor_ids": json.loads(exp["factor_ids_json"] or "[]"),
                "universe": json.loads(exp["universe_json"] or "[]"),
                "created_at": str(exp["created_at"]),
                "status": str(exp["status"]),
            }
        )
        details[exp["experiment_id"]] = {
            "experiment": {
                "experiment_id": str(exp["experiment_id"]),
                "kind": str(exp["kind"]),
                "name": exp["name"],
                "factor_ids": json.loads(exp["factor_ids_json"] or "[]"),
                "universe": json.loads(exp["universe_json"] or "[]"),
                "horizons": json.loads(exp["horizons_json"] or "[]"),
                "methodology": exp["methodology"],
                # SQLite 这几列是动态类型，统一成字符串，冻结样本才可复现
                "seed": str(exp["seed"] or ""),
                "created_at": str(exp["created_at"]),
                "status": str(exp["status"]),
                "date_from": str(exp["date_from"]) if exp["date_from"] else None,
                "date_to": str(exp["date_to"]) if exp["date_to"] else None,
                "benchmark_code": str(exp["benchmark_code"]) if exp["benchmark_code"] else None,
                "params": json.loads(exp["params_json"] or "{}"),
            },
            "results_by_variant": grouped,
        }
    summaries.sort(key=lambda s: s["created_at"], reverse=True)
    return summaries, details


# ----------------------------------------------------------------------
# ③ 因子字典（真实注册表，整表冻结）
# ----------------------------------------------------------------------
def build_factor_dictionary() -> dict:
    """冻结真实的 `/api/v1/factor-dictionary` 响应。

    演示模式以前是**手写的 4 个因子**（`B_STRUCT_002 食神生财格` 之类），
    它们在真实注册表里并不存在 —— 演示会展示一个系统里没有的字典。
    """
    from src.core.config import settings
    from src.factors.registry.definitions import DEFINITION_INDEX

    items = [d.model_dump(mode="json") for d in DEFINITION_INDEX.values()]
    by_category: dict[str, int] = {}
    for d in DEFINITION_INDEX.values():
        key = str(d.category)
        by_category[key] = by_category.get(key, 0) + 1
    return {
        "total": len(items),
        "total_all": len(items),
        "by_category": by_category,
        "items": items,
        "disclaimer": (
            "因子 direction / rule_score 表达的是**传统规则认为的方向与强度**，"
            "不是预期收益率，也不是上涨概率。财星 ≠ 股票上涨；三合 ≠ 股票上涨。"
        ),
        "rule_version": settings.factor_rule_version,
    }


# ----------------------------------------------------------------------
# ④ 模型分歧的三种场景（真实 ConflictDetector 在固定输入上的输出）
# ----------------------------------------------------------------------
def _opinion(engine: str, *, direction: int, score: float | None, confidence: float,
             availability: str = "ok", note: str = "") -> dict:
    return {
        "engine": engine,
        "engine_version": f"{engine}-1.0.0",
        "availability": availability,
        "direction": direction,
        "score": score,
        "confidence": confidence,
        "top_positive_reasons": (
            [{"text": f"{engine} 的主要支持依据（演示固定输入）", "factor_ids": []}]
            if availability == "ok" and direction >= 0 else []
        ),
        "top_negative_reasons": (
            [{"text": f"{engine} 的主要反对依据（演示固定输入）", "factor_ids": []}]
            if availability == "ok" and direction <= 0 else []
        ),
        "factor_ids": [],
        "note": note,
        "assumptions": [],
    }


def build_conflict_scenarios() -> dict:
    """三种场景都用**真实 ConflictDetector / ConsensusEngine** 产出。

    演示面板要能分别截图"无冲突 / 有冲突 / 模型不可用"三种状态，
    但每种状态都必须来自真实判定逻辑，不能手写一个 has_conflict=true 的 JSON。
    """
    from src.core.orchestration.analysis_service import AnalysisService
    from src.core.schemas.analysis import MetaphysicsOpinion

    cases: dict[str, dict[str, dict]] = {
        "no_conflict": {
            "bazi": _opinion("bazi", direction=1, score=68.0, confidence=0.72),
            "ziwei": _opinion("ziwei", direction=1, score=61.5, confidence=0.63),
            "huangli": _opinion("huangli", direction=1, score=57.2, confidence=0.55),
        },
        "conflict": {
            "bazi": _opinion("bazi", direction=1, score=71.0, confidence=0.74),
            "ziwei": _opinion("ziwei", direction=0, score=52.0, confidence=0.48),
            "huangli": _opinion("huangli", direction=-1, score=41.5, confidence=0.58),
        },
        "engine_unavailable": {
            "bazi": _opinion("bazi", direction=1, score=66.0, confidence=0.70),
            "ziwei": _opinion(
                "ziwei", direction=0, score=None, confidence=0.0, availability="unavailable",
                note="紫微排盘服务不可用，本次未产出观点（不以 0 分参与共识）。",
            ),
            "huangli": _opinion("huangli", direction=-1, score=44.0, confidence=0.6),
        },
    }

    out: dict[str, dict] = {}
    for name, raw in cases.items():
        opinions = {k: MetaphysicsOpinion(**v) for k, v in raw.items()}
        # 走与 API 完全相同的组装路径，冻结样本的字段形状才与真实响应一致
        consensus, conflict = AnalysisService.build_consensus_and_conflict(opinions)
        out[name] = {
            "opinions": raw,
            "consensus": consensus.model_dump(mode="json"),
            "conflict": conflict.model_dump(mode="json"),
        }
    return out


# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="重新冻结 UI 演示样本（只读）")
    parser.add_argument("--write", action="store_true", help="直接改写 fixture.ts")
    args = parser.parse_args(argv)

    evidence = build_evidence()
    print(
        "古籍：支持 {s} / 反证 {c} / 中性 {n} 条（knowledge_version {v}）".format(
            s=len(evidence["evidence"]["supporting_evidence"]),
            c=len(evidence["evidence"]["counter_evidence"]),
            n=len(evidence["evidence"]["neutral_evidence"]),
            v=evidence["evidence"]["knowledge_version"],
        ),
        flush=True,
    )

    conn = sqlite3.connect(DB_PATH)
    summaries, details = build_experiments(conn)
    conn.close()
    print(f"研究实验：{len(summaries)} 个（{', '.join(s['experiment_id'] for s in summaries)}）", flush=True)

    dictionary = build_factor_dictionary()
    print(f"因子字典：{dictionary['total_all']} 个因子（rule_version {dictionary['rule_version']}）", flush=True)
    scenarios = build_conflict_scenarios()
    print(f"分歧场景：{', '.join(sorted(scenarios))}", flush=True)

    payload = {
        "evidence": evidence,
        "experiments": summaries,
        "experiment_details": details,
        "factor_dictionary": dictionary,
        "conflict_scenarios": scenarios,
    }
    out = PROJECT_ROOT / "output" / "fixturegen" / "ui-fixtures.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写出：{out}")

    if args.write:
        _patch_fixture_ts(payload)
        print(f"已改写：{FIXTURE_TS}")
    return 0


def _patch_fixture_ts(payload: dict) -> None:
    """把冻结结果写入 fixture.ts 的对应常量（整块替换，保留其余夹具）。"""
    import re

    text = FIXTURE_TS.read_text(encoding="utf-8")

    def replace_const(src: str, name: str, decl: str, body: str, comment: str) -> str:
        """整块替换 `export const <name>: <decl> = {...};`（含紧邻上方的块注释）。

        用**括号配平**扫描而不是正则：常量体是 JSON，里面同样有 `};`
        这类序列，非贪婪正则会一路吞到远处的常量（实测会吞掉整份文件）。
        """
        marker = f"export const {name}: {decl} = "
        decl_start = src.find(marker)
        assert decl_start != -1, f"未找到 {name} 常量"
        # 紧邻上方的块注释一并替换（start 之后会被前移到注释起点，
        # 所以体偏移必须用 decl_start 算）
        start = decl_start
        head = src.rfind("/**", 0, decl_start)
        if head != -1 and src[src.find("*/", head) + 2: decl_start].strip() == "":
            start = head
        i = src.index("{", decl_start + len(marker))
        depth = 0
        in_str = False
        esc = False
        end = -1
        for j in range(i, len(src)):
            ch = src[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j + 1
                    break
        assert end != -1, f"{name} 常量括号不配平"
        while end < len(src) and src[end] in "; \n":
            end += 1
        return src[:start] + f"{comment}\nexport const {name}: {decl} = {body};\n" + src[end:]

    ev_comment = (
        "/** 古籍证据演示样本。\n"
        " *\n"
        " * **不是手写样例**：由 scripts/capture_ui_fixtures.py 用真实 KnowledgeProvider\n"
        " * 对真实因子组合检索本地公版语料后**冻结**；entry_id / 书名 / 版本 / provenance\n"
        " * 与真实模式同源、逐条可核对。语料自身声明未逐字校勘，该限制在页面如实展示。\n"
        " */"
    )
    text = replace_const(
        text,
        "evidenceFixture",
        "ApiEvidence",
        json.dumps(payload["evidence"], ensure_ascii=False, indent=2),
        ev_comment,
    )

    exp_comment = (
        "/** 研究实验演示样本（列表 + 详情）。\n"
        " *\n"
        " * 来自 scripts/capture_ui_fixtures.py 对 `backtest_experiment` / `backtest_result`\n"
        " * 中**已入库的真实实验**的冻结读取（含四类负对照判决与 Jaccard 重合度）。\n"
        " * 页面打开只读这份样本，不触发任何研究计算。\n"
        " */"
    )
    text = replace_const(
        text,
        "experimentFixture",
        "{ list: ApiExperimentSummary[]; details: Record<string, ApiExperimentDetail> }",
        json.dumps(
            {"list": payload["experiments"], "details": payload["experiment_details"]},
            ensure_ascii=False,
            indent=2,
        ),
        exp_comment,
    )

    dict_comment = (
        "/** 因子字典演示样本。\n"
        " *\n"
        " * 来自 scripts/capture_ui_fixtures.py 对**真实因子注册表**的整表冻结：\n"
        " * factor_id / definition / computation / requires / rule_version 与真实模式逐条一致。\n"
        " * 早期版本这里是手写的 4 个因子（表里并不存在），会在演示模式展示一个\n"
        " * 系统里没有的字典 —— 已废弃。\n"
        " */"
    )
    text = replace_const(
        text,
        "factorsDictionaryFixture",
        "{ total: number; total_all: number; by_category: Record<string, number>; "
        "items: Record<string, unknown>[]; disclaimer: string; rule_version: string }",
        json.dumps(payload["factor_dictionary"], ensure_ascii=False, indent=2),
        dict_comment,
    )

    scen_comment = (
        "/** 模型分歧的三种场景（无冲突 / 有冲突 / 模型不可用）。\n"
        " *\n"
        " * 由 scripts/capture_ui_fixtures.py 用**真实 ConflictDetector / ConsensusEngine**\n"
        " * 在固定输入上产出；不是手写的 has_conflict 布尔值。\n"
        " * 页面用 `?scenario=` 选择（仅演示模式生效），便于逐场景截图验收。\n"
        " */"
    )
    text = replace_const(
        text,
        "conflictScenariosFixture",
        "Record<string, { opinions: Record<string, Record<string, unknown>>; "
        "consensus: ApiConsensus; conflict: ApiConflict }>",
        json.dumps(payload["conflict_scenarios"], ensure_ascii=False, indent=2),
        scen_comment,
    )

    bt_comment = (
        "/** 逐标的 EventStudy 演示样本。\n"
        " *\n"
        " * **刻意为空**：演示数据没有跑过事件研究流水线，因此 `horizons` 为空数组、\n"
        " * 状态为 NOT_RUN。早期版本这里填了一组看起来很漂亮的收益与\"显著性\"结论，\n"
        " * 那是伪造研究结论 —— 现在改为真实空态，页面显示\"无样本\"并说明原因。\n"
        " */"
    )
    text = replace_const(
        text,
        "backtestFixture",
        "ApiEventStudy",
        json.dumps(
            {
                "experiment_id": "",
                "factor_ids": [],
                "event_count": 0,
                "universe_size": 0,
                "research_status": "NOT_RUN",
                "research_status_reasons": [
                    "演示数据：该标的未运行事件研究流水线（无标签样本），"
                    "历史有效性判定不可用；本页不下任何\"已通过验证\"的结论。"
                ],
                "horizons": [],
                "methodology": "",
                "warnings": [],
                "data_source": None,
            },
            ensure_ascii=False,
            indent=2,
        ),
        bt_comment,
    )
    FIXTURE_TS.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
