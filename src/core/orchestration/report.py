"""研究报告渲染（Phase 2F）：Markdown / HTML。

报告必须包含（任务书 §44）
--------------------------
股票基础资料 / 出生模型 / 八字原盘 / 紫微原盘 / 黄历 / 三模型独立判断 /
共识 / 分歧 / 历史验证 / 负对照 / 古籍 / AI 解释 / ResearchStatus /
数据质量 / 版本 / 假设 / 限制。

两条硬要求：
1. **不美化**：ResearchStatus 是 `NO_SIGNAL` / `NO_REAL_DATA` / `INVALID_CONTROL`
   时，报告顶部必须显著标注，不能藏在末尾。
2. **冲突不被平均掩盖**：MIXED 时每个模型的方向都必须单独列出。
"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime

from src.core.schemas.evidence import EvidenceBundle

STATUS_LABEL: dict[str, str] = {
    "NOT_RUN": "未运行（没有历史统计）",
    "NO_REAL_DATA": "无真实数据（合成/降级行情，不构成证据）",
    "INSUFFICIENT_SAMPLE": "样本不足",
    "INVALID_CONTROL": "负对照失效",
    "NO_SIGNAL": "未发现稳定信号",
    "INCONCLUSIVE": "结论不明确",
    "WEAK_EVIDENCE": "弱证据（仅样本内）",
    "SUPPORTED_IN_SAMPLE": "样本内支持（不等于样本外有效）",
    "SUPPORTED_OUT_OF_SAMPLE": "样本外支持",
}

#: 必须在报告顶部显著提示的状态
ALERT_STATUSES = {"NO_REAL_DATA", "INVALID_CONTROL", "NO_SIGNAL", "INSUFFICIENT_SAMPLE"}


def render_report(bundle: EvidenceBundle, *, fmt: str = "markdown") -> tuple[str, str, str]:
    """返回 ``(内容, media_type, 文件名)``。"""
    md = render_markdown(bundle)
    if fmt == "html":
        name = f"report-{bundle.analysis_id}.html"
        return render_html(md, bundle), "text/html; charset=utf-8", name
    name = f"report-{bundle.analysis_id}.md"
    return md, "text/markdown; charset=utf-8", name


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def render_markdown(b: EvidenceBundle) -> str:
    L: list[str] = []
    name = b.stock.name if b.stock else ""
    code = b.stock.stock_code if b.stock else ""
    L.append(f"# {name} {code} · 股票玄学多模型研究报告")
    L.append("")
    L.append(f"- 分析 ID：`{b.analysis_id}`")
    L.append(f"- 生成时间：{b.generated_at.isoformat()}")
    L.append(f"- Bundle 版本：`{b.bundle_version}`")
    L.append("")

    # --- 顶部状态警示（不藏在末尾） ---
    status = b.research_status or "NOT_RUN"
    L.append("## ⚠️ 研究状态")
    L.append("")
    L.append(f"**ResearchStatus = `{status}`** —— {STATUS_LABEL.get(status, status)}")
    L.append("")
    if status in ALERT_STATUSES:
        L.append(
            "> **本报告不构成任何有效性宣称。** 上方状态是本次分析在研究纪律下的"
            "最终结论，请先读它，再读下面的分数与共识。"
        )
        L.append("")
    for r in b.historical.research_status_reasons[:6]:
        L.append(f"> {r}")
    L.append("")

    # --- 1. 基础资料 ---
    L += ["## 一、股票基础资料", ""]
    if b.stock:
        L += [
            "| 字段 | 值 |",
            "|---|---|",
            f"| 代码 | {b.stock.stock_code} |",
            f"| 名称 | {b.stock.name} |",
            f"| 交易所 | {b.stock.exchange} |",
            f"| 板块 | {b.stock.board} |",
            f"| 行业 | {b.stock.industry} |",
            f"| 上市日期 | {b.stock.listing_date} |",
            "",
        ]

    L += ["## 二、出生模型（研究假设）", ""]
    bp = b.birth_profile
    if bp:
        L += [
            "| 字段 | 值 |",
            "|---|---|",
            f"| 基准 | {bp.birth_basis} |",
            f"| 出生时刻 | {bp.birth_datetime} |",
            f"| 时区 | {bp.timezone} |",
            f"| variant_mode | {bp.variant_mode} |",
            f"| 版本 | {bp.birth_profile_version} |",
            "",
        ]
    L += [
        "> **股票不存在传统意义的出生时间。** 上表是一个**必须被回测检验的研究假设**，",
        "> 不是事实。切换基准会生成新版本，不覆盖历史。",
        "",
    ]

    # --- 3. 原始盘面 ---
    L += ["## 三、八字原盘", ""]
    L.append(_bazi_table(b.bazi_chart))
    L.append("")

    L += ["## 四、紫微原盘", ""]
    L.append(_ziwei_summary(b.ziwei_charts))
    L.append("")

    L += ["## 五、黄历", ""]
    L.append(_huangli_summary(b.huangli))
    L.append("")

    # --- 6. 三模型独立判断 ---
    L += ["## 六、三模型独立判断", ""]
    L.append(
        "> 三个模型**各自独立**给出判断，本报告不做平均、不做加权成一个总分。"
    )
    L.append("")
    if b.engine_opinions:
        L += ["| 模型 | 可用性 | 方向 | 规则强度 | 置信度 | 引擎版本 |",
              "|---|---|---|---|---|---|"]
        cn = {"bazi": "八字", "ziwei": "紫微斗数", "huangli": "黄历"}
        dirmap = {1: "偏强 ↑", 0: "中性 →", -1: "偏弱 ↓"}
        for key in ("bazi", "ziwei", "huangli"):
            op = b.engine_opinions.get(key)
            if op is None:
                continue
            avail = str(op.availability)
            L.append(
                f"| {cn.get(key, key)} | {avail} | "
                f"{dirmap.get(int(op.direction), '—') if avail == 'ok' else '—'} | "
                f"{op.score if op.score is not None else 'null'} | "
                f"{op.confidence if avail == 'ok' else '—'} | {op.engine_version or '—'} |"
            )
        L.append("")
        for key in ("bazi", "ziwei", "huangli"):
            op = b.engine_opinions.get(key)
            if op is None or str(op.availability) != "ok":
                continue
            L.append(f"**{cn.get(key, key)}** 依据：")
            for r in op.top_positive_reasons[:3]:
                L.append(f"  - （正）{r.text}")
            for r in op.top_negative_reasons[:3]:
                L.append(f"  - （负）{r.text}")
            L.append("")
    L.append("> 上表 `规则强度` 是**传统规则强度指标**，不是上涨概率、不是预期收益率。")
    L.append("")

    # --- 7. 共识 ---
    L += ["## 七、共识", ""]
    c = b.consensus
    if c is None:
        L.append("共识不可评估。")
    else:
        L += [
            f"- 共识分类：**{c.label_cn or c.consensus_class}**",
            f"- 方向一致度：{c.agreement_score}（与多数方向相同的引擎占比，**不是分数平均**）",
            f"- 可用引擎数：{c.available_engine_count}",
            f"- 正向 / 负向 / 中性：{c.positive_engine_count} / "
            f"{c.negative_engine_count} / {c.neutral_engine_count}",
            f"- 纳入的引擎：{', '.join(str(x) for x in c.participating_engines) or '—'}",
            f"- 未纳入的引擎：{', '.join(str(x) for x in c.unavailable_engines) or '—'}",
            f"- 历史有效性：{c.historical_validity or '未计算'}",
            "",
        ]
        if c.interpretation:
            L += [f"> {c.interpretation}", ""]

    # --- 8. 分歧 ---
    L += ["## 八、模型分歧", ""]
    cf = b.conflicts
    if cf is None or not cf.has_conflict:
        L.append("本次未检出显著模型分歧。")
    else:
        L.append(f"- 冲突级别：**{cf.conflict_level}**")
        L.append(f"- 涉及引擎：{', '.join(str(x) for x in cf.conflicting_engines) or '—'}")
        L.append("")
        L.append("**冲突明细**")
        L.append("")
        for item in cf.major_conflicts[:8]:
            L.append(
                f"- `{item.get('engine')}` 判为 **{item.get('direction_label')}**"
                f"（强度 {item.get('score')}）：" + "；".join(item.get("reasons", [])[:2])
            )
        for item in cf.factor_conflicts[:8]:
            L.append(f"- 因子冲突：{item.get('description')}")
        for item in cf.time_horizon_conflicts[:4]:
            L.append(f"- 时间尺度冲突：{item.get('description')}")
        L.append("")
        L.append("> **禁止用平均分掩盖分歧。** 以上各模型方向与依据均如实并列。")
    L.append("")

    # --- 9. 历史验证 + 负对照 ---
    L += ["## 九、历史验证与负对照", ""]
    h = b.historical.stats
    if not h or h.get("status") == "NOT_RUN":
        L.append("**本次没有历史验证记录。** 没有负对照的『有效』在本项目中不被承认。")
    else:
        L.append("```json")
        L.append(json.dumps(h, ensure_ascii=False, indent=2)[:3000])
        L.append("```")
    L.append("")
    if b.negative_control_stats:
        L.append("**负对照**")
        L.append("")
        L.append("```json")
        L.append(json.dumps(b.negative_control_stats, ensure_ascii=False, indent=2)[:2000])
        L.append("```")
        L.append("")

    # --- 10. 古籍 ---
    L += ["## 十、古籍依据与反证", ""]
    L.append(f"**支持性证据（{len(b.classical_support)} 条）**")
    L.append("")
    for e in b.classical_support[:6]:
        L.append(f"- 《{e.get('book')}》{('·' + e.get('chapter')) if e.get('chapter') else ''}："
                 f"「{e.get('original_text')}」（`{e.get('entry_id')}`，"
                 f"相似度 {e.get('score')}）")
    L.append("")
    L.append(f"**反证 / 不同流派解释（{len(b.classical_counter_evidence)} 条）**")
    L.append("")
    for e in b.classical_counter_evidence[:6]:
        L.append(f"- 《{e.get('book')}》：「{e.get('original_text')}」（`{e.get('entry_id')}`）")
    if not b.classical_counter_evidence:
        L.append("")
        L.append(
            "> 未检索到反证 —— 这本身需要警惕：反证为空可能意味着检索词覆盖不足，"
            "**不得**据此认为『古籍一致支持』。"
        )
    L.append("")
    for w in b.classical.corpus_warnings[:4]:
        L.append(f"> ⚠️ {w}")
    L.append("")

    # --- 11. 数据质量 / 版本 / 假设 ---
    L += ["## 十一、数据质量", ""]
    mq = b.market_data_quality
    L += [
        f"- 行情来源：{mq.source or '未标注'}",
        f"- 是否降级：{'**是**' if mq.is_degraded else '否'}",
        f"- 是否真实数据：{'是' if mq.is_real else '**否（合成/降级）**'}",
        f"- 数据行数：{mq.bar_rows}",
        "",
    ]
    for n in mq.notes:
        L.append(f"- {n}")
    L.append("")

    L += ["## 十二、版本", ""]
    v = b.versions
    L += [
        "| 版本项 | 值 |",
        "|---|---|",
        f"| engine_version | {v.engine_version or '—'} |",
        f"| rule_version | {v.rule_version or '—'} |",
        f"| config_version | {v.config_version or '—'} |",
        f"| birth_profile_version | {v.birth_profile_version or '—'} |",
        f"| knowledge_version | {v.knowledge_version or '—'} |",
        f"| market_data_version | {v.market_data_version or '—'} |",
        "",
    ]

    L += ["## 十三、假设", ""]
    for a in b.assumptions[:20]:
        L.append(f"- {a}")
    if not b.assumptions:
        L.append("- （本记录未携带引擎级假设；请参考 `docs/model-limitations.md`）")
    L.append("")

    L += ["## 十四、限制与免责", ""]
    if b.warnings:
        L.append("**本次运行的警告**")
        L.append("")
        for w in b.warnings[:12]:
            L.append(f"- `[{w.severity}] {w.code}` {w.message}")
        L.append("")
    L += [
        "* 本报告是**研究性输出**，不是投资建议，也不是荐股系统。",
        "* 观点分数是**传统规则强度**，不代表预期收益率，也不代表上涨概率。",
        "* 传统术数与股票未来收益之间不存在经现代金融科学确认的稳定因果关系。",
        "* 模型之间的「共识」只表示方向一致程度，**不表示预测能力**。",
        "* 历史统计不代表未来表现；样本内结果不得外推。",
        "* 假设与已知限制详见 `docs/model-limitations.md`。",
        "",
    ]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 原盘渲染
# ---------------------------------------------------------------------------


def _bazi_table(chart: dict | None) -> str:
    if not chart:
        return "（本次未保存八字原盘）"
    rows: list[str] = ["| 柱 | 干支 | 纳音 | 天干十神 | 藏干 |", "|---|---|---|---|---|"]
    labels = {"year_pillar": "年柱", "month_pillar": "月柱",
              "day_pillar": "日柱", "hour_pillar": "时柱"}
    for key, label in labels.items():
        p = chart.get(key) or {}
        gz = (p.get("ganzhi") or {})
        hidden = "、".join(
            f"{h.get('stem', '')}({h.get('ten_god', '')})" for h in (p.get("hidden_stems") or [])
        )
        rows.append(
            f"| {label} | {gz.get('text', '')} | {p.get('nayin', '')} | "
            f"{p.get('stem_ten_god', '')} | {hidden or '—'} |"
        )
    extra = []
    if chart.get("day_master"):
        extra.append(f"日主：{chart['day_master']}（{chart.get('day_master_wuxing', '')}）")
    yong = chart.get("yong_shen") or {}
    if yong:
        extra.append(
            f"用神：{'、'.join(yong.get('yong_shen', []) or []) or '—'}；"
            f"喜神：{'、'.join(yong.get('xi_shen', []) or []) or '—'}；"
            f"忌神：{'、'.join(yong.get('ji_shen', []) or []) or '—'}"
        )
    if chart.get("variant_mode"):
        extra.append(f"variant_mode：{chart['variant_mode']}")
    return "\n".join(rows) + ("\n\n" + "；".join(extra) if extra else "")


def _ziwei_summary(charts: dict[str, dict]) -> str:
    if not charts:
        return "（本次未产出紫微盘面；可能未指定方向 variant，或紫微服务不可用）"
    out: list[str] = []
    for variant, payload in sorted(charts.items()):
        chart = payload.get("chart") or {}
        palaces = chart.get("palaces") or []
        soul = chart.get("soul_palace_index", -1)
        soul_name = palaces[soul]["name"] if 0 <= soul < len(palaces) else "—"
        soul_branch = chart.get("soul_palace_branch", "")
        out.append(
            f"**variant={variant}**：{chart.get('chinese_date', '')}，"
            f"五行局 {chart.get('five_elements_class', '')}，"
            f"命宫 {soul_name}（{soul_branch}），命主 {chart.get('soul', '')}、"
            f"身主 {chart.get('body', '')}。"
        )
        mut = "；".join(
            f"{m.get('mutagen')}{m.get('star')}→{m.get('palace_name')}"
            for m in (chart.get("natal_mutagens") or [])
        )
        out.append(f"  生年四化：{mut or '—'}")
        out.append("")
        out.append("  | 宫 | 宫干支 | 主星 | 煞曜 |")
        out.append("  |---|---|---|---|")
        for p in palaces:
            major = "、".join(s.get("name", "") for s in (p.get("major_stars") or [])) or "空宫"
            mal = "、".join(
                s.get("name", "") for s in (p.get("minor_stars") or [])
                if s.get("name") in {"擎羊", "陀罗", "火星", "铃星", "地空", "地劫"}
            ) or "—"
            out.append(
                f"  | {p.get('name')} | {p.get('heavenly_stem', '')}{p.get('earthly_branch', '')} "
                f"| {major} | {mal} |"
            )
        out.append("")
        out.append(
            "  > 顺行/逆行 variant 的差异**仅限于大限/小限顺逆与长生十二神顺逆**；"
            "两者不是两条独立证据。"
        )
        out.append("")
    return "\n".join(out)


def _huangli_summary(huangli: dict | None) -> str:
    if not huangli:
        return "（本次未保存黄历快照）"
    s = huangli.get("summary") or huangli
    if isinstance(s, dict):
        keep = {k: v for k, v in s.items() if not isinstance(v, (dict, list))}
        return "```json\n" + json.dumps(keep, ensure_ascii=False, indent=1)[:1500] + "\n```"
    return str(s)[:1000]


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_CSS = """
:root{--bg:#0d1117;--fg:#e6edf3;--muted:#8b949e;--card:#161b22;--line:#30363d;}
body{background:var(--bg);color:var(--fg);font:15px/1.7 -apple-system,"Segoe UI",
"Microsoft YaHei",sans-serif;max-width:960px;margin:0 auto;padding:32px 24px;}
h1{font-size:26px;border-bottom:2px solid #d4a04a;padding-bottom:10px;}
h2{font-size:19px;margin-top:32px;color:#d4a04a;}
h3{font-size:16px;}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:13px;}
th,td{border:1px solid var(--line);padding:6px 10px;text-align:left;}
th{background:var(--card);}
code{background:var(--card);padding:1px 5px;border-radius:3px;font-size:13px;}
pre{background:var(--card);padding:12px;border-radius:6px;overflow-x:auto;font-size:12px;}
blockquote{border-left:3px solid #d4a04a;margin:12px 0;padding:6px 14px;color:var(--muted);}
hr{border:0;border-top:1px solid var(--line);margin:24px 0;}
.footer{margin-top:40px;color:var(--muted);font-size:12px;text-align:center;}
"""


def render_html(markdown_text: str, bundle: EvidenceBundle) -> str:
    """把 Markdown 渲染成自包含 HTML。

    刻意**不引入 markdown 库**：报告结构由本项目完全控制，用一个小转换器
    既避免新增依赖，也避免第三方渲染器把内容改写成我们不想要的样子。
    """
    body = _md_to_html(markdown_text)
    status = bundle.research_status or "NOT_RUN"
    banner = ""
    if status in ALERT_STATUSES:
        banner = (
            f'<div style="background:#3d1f1f;border:1px solid #d4a04a;padding:12px 16px;'
            f'border-radius:6px;margin-bottom:20px;">'
            f'<b>ResearchStatus = {html.escape(status)}</b> —— '
            f'{html.escape(STATUS_LABEL.get(status, status))}<br>'
            f'<span style="color:#8b949e">本报告不构成任何有效性宣称。</span></div>'
        )
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(bundle.analysis_id)} · 研究报告</title>"
        f"<style>{_CSS}</style></head><body>{banner}{body}"
        f'<div class="footer">股票玄学多模型研究平台 · 生成于 '
        f"{html.escape(datetime.now().isoformat(timespec='seconds'))} · "
        "研究与教育用途，不构成投资建议</div></body></html>"
    )


def _md_to_html(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    in_table = False
    in_code = False
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            close_list()
            if in_table:
                out.append("</table>")
                in_table = False
            out.append("<pre>" if not in_code else "</pre>")
            in_code = not in_code
            continue
        if in_code:
            out.append(html.escape(raw))
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= {"-", ":"} and c for c in cells):
                continue
            close_list()
            if not in_table:
                out.append("<table>")
                in_table = True
                out.append("<tr>" + "".join(f"<th>{_inline(c)}</th>" for c in cells) + "</tr>")
            else:
                out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False

        if line.startswith("# "):
            close_list()
            out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            close_list()
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("### "):
            close_list()
            out.append(f"<h3>{_inline(line[4:])}</h3>")
        elif line.startswith("> "):
            close_list()
            out.append(f"<blockquote>{_inline(line[2:])}</blockquote>")
        elif line.strip() in ("---", "***"):
            close_list()
            out.append("<hr>")
        elif re.match(r"^\s*[-*] ", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^\s*[-*] ", "", line)
            out.append(f"<li>{_inline(item)}</li>")
        elif not line.strip():
            close_list()
        else:
            close_list()
            out.append(f"<p>{_inline(line)}</p>")

    close_list()
    if in_table:
        out.append("</table>")
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


def _inline(text: str) -> str:
    t = html.escape(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t


__all__ = ["render_report", "render_markdown", "render_html", "STATUS_LABEL"]
