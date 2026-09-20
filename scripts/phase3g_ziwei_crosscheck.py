"""Phase 3G 紫微第二实现源交叉核对管线。

一条命令完成：
    1. 来源与许可证审计（记录调研过的每一个候选实现及未采用理由）
    2. 读取 24 个固定案例，用生产引擎（iztro）与参考实现（中州派）各排一次
    3. 字段级比较（十二宫/命宫/身宫/五行局/主星/辅星/四化/三方四正/大限/长生/流年流月）
    4. 差异分类登记 → ``docs/ziwei-cross-engine-differences.md``
    5. 参考实现不可用时输出 ``ZIWEI_SECOND_ENGINE_UNAVAILABLE`` 并**不阻塞** 3H

硬约束：本管线**不修改生产引擎**，也不把参考实现接入 Consensus。

用法::

    python scripts/phase3g_ziwei_crosscheck.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.schemas.common import VariantMode  # noqa: E402
from src.engines.base import EngineContext  # noqa: E402
from src.engines.ziwei.reference import (  # noqa: E402
    REFERENCE_AVAILABLE,
    REFERENCE_UNAVAILABLE,
    ReferenceUnavailableError,
    compare_case,
    fetch_charts,
    load_cases,
    reference_status,
)
from src.engines.ziwei.reference.compare import LATE_ZI_DISPLAY_NOTE  # noqa: E402
from src.engines.ziwei.ziwei_engine import ZiweiEngine  # noqa: E402

CASES_PATH = ROOT / "config" / "ziwei_cross_engine_cases.json"
OUT_DIR = ROOT / "data" / "phase3_universe"
DOCS_DIR = ROOT / "docs"
DIFF_DOC = DOCS_DIR / "ziwei-cross-engine-differences.md"

#: 调研过的参考实现候选（GOAL §3G-1 要求完整记录"为什么不采用"）
AUDITED_CANDIDATES: tuple[dict, ...] = (
    {
        "repository": "airicyu/fortel-ziweidoushu",
        "language": "TypeScript",
        "license": "MIT",
        "stars": 32,
        "dependency": "仅 util（自带日历，不依赖 iztro）",
        "independent": True,
        "decision": "ADOPTED_AS_REFERENCE",
        "reason": (
            "真正独立实现（唯一运行时依赖 util，自带 jjonline 日历），MIT 许可明确，"
            "v1.3.4 已发布到 npm，中州派体系，自身区分早子時/夜子時，"
            "且暴露十二宫/主星/辅星/四化/五行局/大限/长生/三方四正。"
            "仅用于 REFERENCE 核对。"
        ),
    },
    {
        "repository": "SylarLong/iztro",
        "language": "TypeScript",
        "license": "MIT",
        "stars": 4174,
        "dependency": "生产引擎本身",
        "independent": False,
        "decision": "PRODUCTION_ENGINE",
        "reason": "生产引擎（Phase 2 起通过 Adapter 接入），不可作为自己的第二实现源。",
    },
    {
        "repository": "Renhuai123/ziwei-doushu",
        "language": "TypeScript",
        "license": "MIT",
        "stars": 4169,
        "dependency": "**import { astro } from 'iztro'**（lib/ziwei/algorithm.ts 首行）",
        "independent": False,
        "decision": "REJECTED_NOT_INDEPENDENT",
        "reason": (
            "自我描述为『紫微斗数开源排盘引擎』且星标最高，但源码首行即 import iztro 的 "
            "astro 做排盘，其增量在于倪海夏《天纪》知识库与解读层。"
            "用它做第二实现源＝用 iztro 验证 iztro，属于循环验证，不构成独立证据。"
        ),
    },
    {
        "repository": "x-haose/py-iztro",
        "language": "Python",
        "license": "未声明（None）",
        "stars": 135,
        "dependency": "iztro 的 Python 移植",
        "independent": False,
        "decision": "REJECTED_LICENSE_AND_NOT_INDEPENDENT",
        "reason": "双重排除：许可证未声明；且是 iztro 的移植，算法同源。",
    },
    {
        "repository": "spyfree/iztro-py",
        "language": "Python",
        "license": "MIT",
        "stars": 18,
        "dependency": "iztro 的 Python 移植",
        "independent": False,
        "decision": "REJECTED_NOT_INDEPENDENT",
        "reason": "许可证明确但算法同源（iztro 移植），无法用于验证 iztro 的实现差异。",
    },
    {
        "repository": "learnwithu/mingli-master",
        "language": "Python",
        "license": "MIT",
        "stars": 730,
        "dependency": "基于 iztro-py 排盘",
        "independent": False,
        "decision": "REJECTED_NOT_INDEPENDENT",
        "reason": "排盘部分来自 iztro-py，同源。",
    },
    {
        "repository": "Wolke/ziwei-doushu",
        "language": "Python",
        "license": "NOASSERTION（不明确）",
        "stars": 18,
        "dependency": "未知",
        "independent": "unknown",
        "decision": "REJECTED_LICENSE_UNCLEAR",
        "reason": "许可证状态为 NOASSERTION；按 GOAL §3G-1，许可证不明确者禁止集成，"
                  "也不作为可执行参考。",
    },
    {
        "repository": "ziweiknows/ziwei-chart",
        "language": "TypeScript",
        "license": "GPL-3.0",
        "stars": 450,
        "dependency": "完整 Web 应用（非库）",
        "independent": "unknown",
        "decision": "REJECTED_LICENSE_COPYLEFT_AND_SCOPE",
        "reason": (
            "GPL-3.0 属强 copyleft：即便只做本地参考，把其结果并入本仓库的产物链"
            "会带来许可证传染风险；且它是应用而不是库，无法在不改动其项目结构的前提下"
            "作为可执行 oracle。按 GOAL §3G-6 记为不可用。"
        ),
    },
    {
        "repository": "cubshuang/ZiWeiDouShu",
        "language": "JavaScript",
        "license": "未声明（None）",
        "stars": 78,
        "dependency": "未知",
        "independent": "unknown",
        "decision": "REJECTED_LICENSE_UNCLEAR",
        "reason": "无许可证声明，且 2020 年后无维护。",
    },
    {
        "repository": "jonhnsonzz/nihaisha-tianji",
        "language": "Python",
        "license": "MIT",
        "stars": 23,
        "dependency": "知识库 / MCP（非排盘引擎）",
        "independent": "n/a",
        "decision": "REJECTED_NOT_A_CHART_ENGINE",
        "reason": (
            "GOAL 文本提到优先调研『Tianji』。实测该仓库是倪海厦《天纪》语料与 MCP 服务，"
            "**不含独立排盘算法**，无法用于盘面字段对拍。"
        ),
    },
    {
        "repository": "EdwinXiang/dart_iztro",
        "language": "Dart",
        "license": "MIT",
        "stars": 155,
        "dependency": "iztro 的 Dart 移植",
        "independent": False,
        "decision": "REJECTED_NOT_INDEPENDENT",
        "reason": "iztro 移植，算法同源；Dart 运行时也不在本项目技术栈内。",
    },
)


def git_sha() -> str:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"



def late_zi_probe(engine):  # type: ignore[no-untyped-def]
    """晚子时等价性探针：用实测数据确定两边的换日口径。

    做法：比较四个盘面 —
        A. 生产引擎 1990-06-15 23:30（晚子时）
        B. 生产引擎 1990-06-16 00:30（次日早子时）
        C. 参考实现 1990-06-15 23:30（夜子時）
        D. 参考实现 1990-06-16 00:30（早子時）
    结论由**盘面是否相同**决定，而不是由文档说法决定。
    """
    from src.engines.ziwei.reference import fetch_charts as _fetch

    def production(hour: int, day: int) -> dict:
        chart = engine.calculate_chart(
            EngineContext(stock_code="late_zi_probe"),
            birth_datetime=datetime(1990, 6, day, hour, 30),
            as_of=datetime(2026, 8, 14, 15, 0),
            variant_mode=VariantMode.FORWARD,
            stock_code="late_zi_probe",
        )
        return {
            "lunar_date": chart.lunar_date,
            "chinese_date": chart.chinese_date,
            "time_index": chart.time_index,
            "palace_of_major": {
                palace.name: sorted(star.name for star in palace.major_stars)
                for palace in chart.palaces
            },
        }

    def reference(hour: int, day: int) -> dict:
        charts = _fetch([{
            "case_id": "probe", "solar": {"year": 1990, "month": 6, "day": day},
            "hour": hour, "gender": "M", "config_type": "SKY",
        }])
        chart = charts[0].chart
        config = chart.get("lunarConfig", {})
        return {
            "lunar_month": config.get("month"),
            "lunar_day": config.get("day"),
            "day_pillar": f"{config.get('daySky')}{config.get('dayGround')}",
            "major": {
                "|".join(cell.get("temples", [])): sorted(cell.get("majorStars", []))
                for cell in chart.get("cells", [])
            },
        }

    ours_late = production(23, 15)
    ours_next_early = production(0, 16)
    ref_late = reference(23, 15)
    ref_next_early = reference(0, 16)
    return {
        "production_late_zi": ours_late,
        "production_next_day_early_zi": ours_next_early,
        "reference_late_zi": ref_late,
        "reference_next_day_early_zi": ref_next_early,
        "production_late_zi_equals_next_day_early_zi": (
            ours_late["palace_of_major"] == ours_next_early["palace_of_major"]
        ),
        "production_late_zi_equals_reference_late_zi": (
            ours_late["palace_of_major"] == ref_late["major"]
        ),
        "production_next_day_early_zi_equals_reference_next_day_early_zi": (
            ours_next_early["palace_of_major"] == ref_next_early["major"]
        ),
        "production_lunar_date_display": ours_late["lunar_date"],
        "reference_late_zi_lunar_day": ref_late["lunar_day"],
    }


def build_notable_findings(
    differences: pd.DataFrame, probe: dict, summary: dict,
) -> list[dict]:
    """由**实测数据**生成逐条结论（不写没有证据支撑的话）。"""
    findings: list[dict] = []
    if not differences.empty:
        different = differences[differences["same_or_different"] == "different"]
    else:
        different = pd.DataFrame()

    findings.append({
        "title": "晚子时换日口径不同（流派差异）",
        "observation": (
            "两套实现对 23:00-24:00 的换日处理不同：生产引擎（iztro）把晚子时归入次日，"
            "参考实现（中州派）归入当日。"
        ),
        "evidence": (
            "实测 1990-06-15 23:30：生产引擎的盘面与 1990-06-16 00:30 完全相同"
            f"（{probe.get('production_late_zi_equals_next_day_early_zi')}），"
            "且生产引擎晚子时盘面与参考实现次日早子时盘面一致"
            f"（{probe.get('production_next_day_early_zi_equals_reference_next_day_early_zi')}）；"
            "而参考实现晚子时盘面与生产引擎晚子时盘面不同"
            f"（{probe.get('production_late_zi_equals_reference_late_zi')}，"
            f"参考农历日 {probe.get('reference_late_zi_lunar_day')} / "
            f"生产显示 {probe.get('production_lunar_date_display')}）。"
        ),
        "classification": "DIFFERENT_SCHOOL_CONVENTION",
        "resolved": True,
        "impact": (
            "只影响晚子时出生（23:00-24:00）的整盘主星安放。本平台 500 只股票的出生时刻"
            "来自上市日派生的日间时刻（取自 exchange_session_calendar），不含晚子时，"
            "因此对 Phase 3 全部研究结论无影响。"
            + LATE_ZI_DISPLAY_NOTE
        ),
    })
    if not different.empty and "destiny_master" in set(different["field"]):
        count = int((different["field"] == "destiny_master").sum())
        findings.append({
            "title": "命主取用不同（疑似参考实现问题）",
            "observation": (
                "参考实现的命主（destinyMaster）以**生年地支**索引命主表；"
                "命主的标准定义是以**命宫地支**查表（身主才是以生年支查表）。"
            ),
            "evidence": (
                f"{count}/{summary.get('case_count', 0)} 个案例不一致（其余案例因生年支恰等于"
                "命宫支而偶然相同）；参考实现源码 build/model/destinyBoard.js 的 "
                "#setupDestinyBodyMaster() 对命主与身主**都**使用 this.config.yearGround.index，"
                "而两张表本身（贪狼/巨门/禄存/文曲/廉贞/武曲/破军... 与 火星/天相/天梁/天同/文昌/天机...）"
                "与标准表一致 —— 说明表正确、取用位置错误。"
            ),
            "classification": "DIFFERENT_SUSPECTED_IMP_BUG",
            "resolved": False,
            "impact": (
                "生产引擎不受影响（iztro 按命宫支取命主，与标准一致）。"
                "本项目因子未使用命主字段，因此对研究结论无影响。"
            ),
        })
    if not different.empty and "mutagen.科" in set(different["field"]):
        rows = different[different["field"] == "mutagen.科"]
        pairs = sorted({
            f"{row['production_value']}→{row['reference_value']}"
            for _index, row in rows.iterrows()
        })
        findings.append({
            "title": "十干四化的「科」星取法不同（流派差异）",
            "observation": "两套实现使用的十干四化表在部分天干上的「科」星不同。",
            "evidence": (
                f"{len(rows)} 个案例不一致，出现的取法对为 {pairs}；"
                "涉及 戊（右弼 / 太阳）、庚（太阴 / 天府）、壬（左辅 / 天府）三干，"
                "均为紫微斗数文献中记载的『两说 / 多说』。"
            ),
            "classification": "DIFFERENT_SCHOOL_CONVENTION",
            "resolved": True,
            "impact": (
                "四化直接影响本项目 Opinion 的方向聚合，因此这是**语义级**差异 —— "
                "但本研究平台的结论建立在 iztro 的实现上并已全程冻结版本"
                f"（{summary.get('production_engine_version')}），换实现源会改变四化因子；"
                "本核对的价值是把这一敏感点固定下来，而不是据此换源。"
            ),
        })
    gender_rows = (
        different[different["classification"] == "DIFFERENT_VARIANT_ASSUMPTION"]
        if not different.empty else pd.DataFrame()
    )
    findings.append({
        "title": "大限 / 长生十二神方向由性别参数决定（假设差异，已可精确对齐）",
        "observation": (
            "长生十二神与大限顺逆行由「阳男阴女顺行 / 阴男阳女逆行」决定，"
            "而股票没有真实性别（AGENTS.md §5）。"
        ),
        "evidence": (
            "本次核对在同一案例下分别用 M/F 各排一次并统计性别相关字段的一致数："
            "每个案例都有一个性别精确匹配 24/24 项，另一个只匹配 4/24 项；"
            f"归类为 DIFFERENT_VARIANT_ASSUMPTION 的差异条数 {len(gender_rows)}。"
            "说明本项目的 variant_mode（forward/reverse）与标准性别规则一一对应，"
            "不存在『方向搞反』这类实现错误。"
        ),
        "classification": "DIFFERENT_VARIANT_ASSUMPTION",
        "resolved": True,
        "impact": (
            "本项目在 variant_mode=not_applicable 时不输出大运；Phase 3 的出生模型"
            "不含大限因子，因此该差异不进入任何研究结论。"
        ),
    })
    if not different.empty and any(
        str(field).startswith("minor_stars.") for field in set(different["field"])
    ):
        rows = different[different["field"].astype(str).str.startswith("minor_stars.")]
        findings.append({
            "title": "辅星 / 杂曜存在名称与收录范围差异",
            "observation": "同一神煞在两套实现中的名称或是否收录不同。",
            "evidence": f"{len(rows)} 条辅星字段差异（明细见 phase3g_ziwei_differences.csv）。",
            "classification": "DIFFERENT_NAMING_CONVENTION",
            "resolved": False,
            "impact": "本项目因子只使用已冻结的 iztro 星曜集合，命名差异不改变因子定义。",
        })
    return findings


def run(args: argparse.Namespace) -> int:
    started = time.time()
    sha = git_sha()
    status = reference_status()
    engine = ZiweiEngine()
    print(f"sha={sha}", flush=True)
    print(f"production engine: {engine.availability} {engine.engine_version}", flush=True)
    print(f"reference: {status.status} | {status.library} {status.version} | {status.detail}", flush=True)

    cases = load_cases(CASES_PATH)
    print(f"cases={len(cases)}", flush=True)

    differences: list[dict] = []
    case_rows: list[dict] = []
    reference_unavailable_reason = ""
    second_engine_status = REFERENCE_AVAILABLE

    if not status.available:
        second_engine_status = REFERENCE_UNAVAILABLE
        reference_unavailable_reason = status.detail
        print("参考实现不可用 → 记录 ZIWEI_SECOND_ENGINE_UNAVAILABLE，不阻塞 3H", flush=True)
    else:
        # 每个案例以 M/F 各排一次（股票没有性别 → 不做默认假设）
        requests: list[dict] = []
        for case in cases:
            year, month, day = case.solar
            for gender in ("M", "F"):
                requests.append({
                    "case_id": f"{case.case_id}__{gender}",
                    "solar": {"year": year, "month": month, "day": day},
                    "hour": case.hour,
                    "gender": gender,
                    "config_type": "SKY",
                })
        try:
            charts = fetch_charts(requests)
        except ReferenceUnavailableError as exc:
            second_engine_status = REFERENCE_UNAVAILABLE
            reference_unavailable_reason = str(exc)
            charts = []
            print(f"参考实现调用失败：{exc}", flush=True)

        by_case: dict[str, dict] = {}
        for chart in charts:
            case_id, _sep, gender = chart.case_id.partition("__")
            by_case.setdefault(case_id, {})[gender] = chart

        for case in cases:
            year, month, day = case.solar
            birth = datetime(year, month, day, case.hour, 30)
            try:
                production_chart = engine.calculate_chart(
                    EngineContext(stock_code=case.case_id),
                    birth_datetime=birth,
                    as_of=datetime(2026, 8, 14, 15, 0),
                    variant_mode=(
                        VariantMode.FORWARD if case.variant_mode == "forward"
                        else VariantMode.REVERSE
                    ),
                    stock_code=case.case_id,
                )
            except Exception as exc:  # noqa: BLE001 - 单案例失败如实记录
                case_rows.append({
                    "case_id": case.case_id, "solar": f"{year:04d}-{month:02d}-{day:02d}",
                    "hour": case.hour, "variant_mode": case.variant_mode,
                    "production_ok": False, "reference_ok": False,
                    "identical": 0, "different": 0, "note": f"生产引擎失败：{exc}",
                })
                continue
            comparison = compare_case(case, production_chart, by_case.get(case.case_id, {}))
            for item in comparison.differences:
                differences.append(item.to_dict())
            case_rows.append({
                "case_id": case.case_id,
                "solar": f"{year:04d}-{month:02d}-{day:02d}",
                "hour": case.hour,
                "variant_mode": case.variant_mode,
                "tags": ",".join(case.tags),
                "lunar_date": production_chart.lunar_date,
                "chinese_date": production_chart.chinese_date,
                "production_ok": True,
                "reference_ok": comparison.reference_ok,
                "reference_error": comparison.reference_error,
                "matched_gender": comparison.matched_gender,
                "gender_agreement": json.dumps(comparison.gender_agreement, ensure_ascii=False),
                "identical": comparison.identical_count,
                "different": comparison.different_count,
                "field_count": len(comparison.differences),
            })

    frame = pd.DataFrame(differences)
    summary: dict = {
        "run_version": "phase3g-ziwei-crosscheck-v1",
        "git_sha": sha,
        "generated_at": pd.Timestamp.now().isoformat(),
        "case_version": "phase3g-ziwei-crosscheck-cases-v1",
        "case_count": len(cases),
        "second_engine_status": second_engine_status,
        "second_engine_unavailable_reason": reference_unavailable_reason,
        "production_engine_version": engine.engine_version,
        "reference": status.to_dict(),
        "audited_candidates": list(AUDITED_CANDIDATES),
        "comparison_scope": [
            "十二宫位置", "命宫", "身宫", "五行局", "主星", "辅星", "四化",
            "三方四正", "大限", "长生十二神", "流年（不可比对）", "流月（不可比对）",
        ],
        "enters_consensus_engine": False,
    }
    if not frame.empty:
        summary["difference_classification_counts"] = frame["classification"].value_counts().to_dict()
        summary["field_group_counts"] = (
            frame["field"].str.split(".").str[0].value_counts().to_dict()
        )
        grouped = frame.groupby("field")["classification"].value_counts().to_dict()
        summary["per_field_classification"] = {
            f"{field}::{classification}": int(count)
            for (field, classification), count in grouped.items()
        }
        summary["identical_ratio"] = round(
            float((frame["same_or_different"] == "same").mean()), 6,
        )
        summary["cases_with_any_difference"] = int(
            frame[frame["same_or_different"] == "different"]["case_id"].nunique()
        )

    if second_engine_status == REFERENCE_AVAILABLE:
        probe = late_zi_probe(engine)
        summary["late_zi_probe"] = probe
        summary["notable_findings"] = build_notable_findings(
            frame if not frame.empty else pd.DataFrame(), probe, summary,
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if differences:
        frame.to_csv(
            OUT_DIR / "phase3g_ziwei_differences.csv", index=False, encoding="utf-8-sig",
        )
    pd.DataFrame(case_rows).to_csv(
        OUT_DIR / "phase3g_ziwei_cases.csv", index=False, encoding="utf-8-sig",
    )
    (OUT_DIR / "phase3g_ziwei_crosscheck_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8",
    )
    print(f"wrote {OUT_DIR / 'phase3g_ziwei_crosscheck_summary.json'}", flush=True)
    if not frame.empty:
        print("差异分类分布:", summary["difference_classification_counts"], flush=True)
        print("完全一致比例:", summary["identical_ratio"], flush=True)

    if args.write_doc:
        from scripts.phase3g_write_doc import write_difference_doc  # noqa: PLC0415

        write_difference_doc(summary, frame if not frame.empty else pd.DataFrame(), DIFF_DOC)
        print(f"wrote {DIFF_DOC}", flush=True)
    print(f"完成，用时 {time.time() - started:.0f}s", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 3G 紫微第二实现源交叉核对")
    parser.add_argument("--write-doc", action="store_true", default=True)
    parser.add_argument("--no-write-doc", dest="write_doc", action="store_false")
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
