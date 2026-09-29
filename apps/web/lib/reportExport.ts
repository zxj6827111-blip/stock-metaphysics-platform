"use client";

/**
 * 研究报告导出（Markdown / HTML / 结构化 JSON）。
 *
 * 设计要点
 * --------
 * 1. **导出冻结当前上下文**：调用时把 `analysisId`、股票、as_of、出生档案、
 *    变体等一起捕获成一份不可变快照。导出过程中用户切股票不会把两只股票的
 *    数据混进同一个文件（这是"导出"最容易出的错，且用户看不出来）。
 * 2. **真实模式复用后端已实现的报告**：`GET /analysis/{id}/report` 由
 *    `src/core/orchestration/report.py` 渲染，包含 ResearchStatus / 版本 /
 *    假设 / 限制 / 负对照 —— 前端不参与内容拼装，不新增第二套口径。
 * 3. **演示模式必须显式标注**：fixture 的 analysis_id 在后端并不存在，
 *    因此演示模式的报告在前端就地生成，并且**每一页都带"演示数据"标记**。
 *    绝不为了走通按钮而伪造一份后端报告。
 * 4. **不把浏览器行为说成后端能力**：HTML 报告是"可打印的 HTML"，不是
 *    服务端 PDF；界面上如实写"可打印 HTML"。
 */

import { api, endpoints, type ApiMultiAnalysis } from "./api";
import { isFixtureActive } from "./fixture";
import type {
  ApiHistoricalDatasetV2,
  ApiHistoricalEventStudyRequest,
  ApiHistoricalEventStudyV2,
} from "./researchV2";

export type ExportFormat = "markdown" | "html" | "json";

export interface ExportTarget {
  analysisId: string;
  /** 分析上下文快照（导出期间不随页面状态变化）。 */
  snapshot: Pick<
    ApiMultiAnalysis,
    "stock" | "birth_profile" | "as_of" | "variant_mode" | "horizon"
  > & {
    opinions?: ApiMultiAnalysis["opinions"];
    consensus?: ApiMultiAnalysis["consensus"];
    conflict?: ApiMultiAnalysis["conflict"];
    versions?: Record<string, string>;
    warnings?: ApiMultiAnalysis["warnings"];
    factors?: ApiMultiAnalysis["factors"];
  };
  fixture: boolean;
}

/** 从当前分析结果构造冻结的导出目标。 */
export function buildExportTarget(
  analysis: ApiMultiAnalysis | null | undefined,
  analysisId: string | null | undefined,
  fixture = isFixtureActive(),
): ExportTarget | null {
  if (!analysis || !analysisId) return null;
  return {
    analysisId,
    fixture,
    snapshot: {
      stock: analysis.stock,
      birth_profile: analysis.birth_profile,
      as_of: analysis.as_of,
      variant_mode: analysis.variant_mode,
      horizon: analysis.horizon,
      opinions: analysis.opinions,
      consensus: analysis.consensus,
      conflict: analysis.conflict,
      versions: analysis.versions,
      warnings: analysis.warnings,
      factors: analysis.factors,
    },
  };
}

function stamp(): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

/** 触发浏览器下载。返回值用于提示"已下载"，不声称"已导出到服务器"。 */
function download(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // 立即 revoke 在部分浏览器会取消下载，放到下一个宏任务
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/* -------------------------------------------------------------------------- */
/* 真实模式                                                                    */
/* -------------------------------------------------------------------------- */

export async function exportReport(target: ExportTarget, format: ExportFormat): Promise<void> {
  if (target.fixture) {
    return exportFixtureReport(target, format);
  }
  if (format === "json") {
    const json = JSON.stringify(
      { exported_at: new Date().toISOString(), analysis_id: target.analysisId, analysis: target.snapshot },
      null,
      2,
    );
    download(`report-${target.analysisId}-${stamp()}.json`, json, "application/json;charset=utf-8");
    return;
  }
  const text = await api.raw(endpoints.report(target.analysisId, format));
  if (format === "html") {
    download(
      `report-${target.analysisId}-${stamp()}.html`,
      text,
      "text/html;charset=utf-8",
    );
  } else {
    download(
      `report-${target.analysisId}-${stamp()}.md`,
      text,
      "text/markdown;charset=utf-8",
    );
  }
}

export interface HistoricalResearchV2ExportInput {
  dataset: ApiHistoricalDatasetV2;
  requests: ApiHistoricalEventStudyRequest[];
  results: ApiHistoricalEventStudyV2[];
}

/** 导出当前页面消费的同一组 v2 数据集、请求口径和 API 响应。 */
export function exportHistoricalResearchV2(
  input: HistoricalResearchV2ExportInput,
  format: "markdown" | "json",
): void {
  const exportedAt = new Date().toISOString();
  const base = `historical-research-${input.dataset.dataset_id}-${stamp()}`;
  if (format === "json") {
    download(
      `${base}.json`,
      JSON.stringify({ schema_version: "historical-research-v2-export-v1", exported_at: exportedAt, ...input }, null, 2),
      "application/json;charset=utf-8",
    );
    return;
  }

  const scope = input.dataset.metadata.scope;
  const rangeDates = scope?.research_dates ?? [];
  const knownLimitations = input.dataset.metadata.known_limitations ?? [];
  const lines: string[] = [
    `# 历史事件研究 v2 · ${input.dataset.dataset_id}`,
    "",
    `- 导出时间：${exportedAt}`,
    `- 数据集摘要：\`${input.dataset.dataset_digest}\``,
    `- Schema：\`${input.dataset.schema_version}\` · Manifest：${input.dataset.status}`,
    `- 数据行：${input.dataset.row_count} · 分片：${input.dataset.complete_shard_count}/${input.dataset.expected_shard_count}`,
    `- 认证状态：${input.dataset.certification_status} · ${input.dataset.certification_reason}`,
    `- 研究资格：${input.dataset.research_eligible ? "eligible" : "不具备"} · 确认性资格：${input.dataset.confirmatory_research_eligible ? "eligible" : "不具备"}`,
    `- 证书：${input.dataset.scope_certificate_id ?? "未绑定"} · SHA-256：\`${input.dataset.scope_certificate_sha256 ?? "不可用"}\``,
    `- 认证证券/范围：${input.dataset.certified_stock_code ?? "未限定"} · ${input.dataset.certified_date_from ?? "不可用"} ～ ${input.dataset.certified_date_to ?? "不可用"}`,
    `- 样本范围：${rangeDates[0] ?? "不可用"} ～ ${rangeDates[rangeDates.length - 1] ?? "不可用"} · ${scope?.stock_code ?? "全范围"} · ${scope?.sample_kind ?? "未说明"}`,
    "",
    "## 请求口径",
    "",
  ];
  for (const request of input.requests) {
    lines.push(
      `- ${request.scope_mode} · 历史范围 ${request.date_from} ～ ${request.date_to}${request.target_date ? ` · 扫描目标日 ${request.target_date}` : ""} · ${request.factor_ids.join(", ")} · activation=${request.activation}${request.relation_type ? ` · relation=${request.relation_type} ${request.relation_source_context}/${request.relation_source_pillar}/${request.relation_source_component}→${request.relation_target_context}/${request.relation_target_pillar}/${request.relation_target_component}` : ""}${request.ten_god_category ? ` · ten_god=${request.ten_god_category} ${request.ten_god_layer}/${request.ten_god_position}` : ""} · 条件逻辑 AND · ${request.horizon}D · price_basis=${request.versions.price_basis} · factor_version=${request.versions.factor_version}`,
    );
  }
  lines.push("", "## API 结果", "");
  for (const result of input.results) {
    lines.push(
      `### ${result.horizon}D · ${result.research_status}`,
      "",
      `- Dataset：\`${result.dataset_id}\` / \`${result.dataset_digest}\``,
      `- 实际条件：${result.scope_mode} · 历史范围 ${result.date_from} ～ ${result.date_to}${result.target_date ? ` · 扫描目标日 ${result.target_date}` : ""} · ${result.factor_ids.join(", ")} · activation=${result.activation}${result.relation_type ? ` · relation=${result.relation_type} ${result.relation_source_context}/${result.relation_source_pillar}/${result.relation_source_component}→${result.relation_target_context}/${result.relation_target_pillar}/${result.relation_target_component}` : ""}${result.ten_god_category ? ` · ten_god=${result.ten_god_category} ${result.ten_god_layer}/${result.ten_god_position}` : ""} · ${result.condition_logic} · 统计单位=${result.observation_unit}`,
      `- 认证范围：${result.certified_stock_code ?? "不可用"} · ${result.certified_date_from ?? "不可用"} ～ ${result.certified_date_to ?? "不可用"}`,
      `- 候选观察：${result.candidate_observation_count} · 命中观察：${result.matched_observation_count} · 候选证券日期：${result.candidate_security_date_count} · 命中证券日期：${result.matched_security_date_count} · 命中日期：${result.matched_date_count} · 缺失：${result.missing_observation_count}`,
      `- 命中组：n=${result.matched.sample_count}，均值=${formatExportPct(result.matched.mean_return)}，中位数=${formatExportPct(result.matched.median_return)}，胜率=${formatExportPct(result.matched.win_rate)}`,
      `- 命中组风险：平均盈利=${formatExportPct(result.matched.mean_positive_return)}，平均亏损=${formatExportPct(result.matched.mean_negative_return)}，盈亏比=${formatExportRatio(result.matched.payoff_ratio)}，样本最大收益=${formatExportPct(result.matched.max_return)}，样本最大亏损=${formatExportPct(result.matched.max_loss)}`,
      `- 补集：n=${result.complement.sample_count}，均值=${formatExportPct(result.complement.mean_return)}，中位数=${formatExportPct(result.complement.median_return)}，胜率=${formatExportPct(result.complement.win_rate)}`,
      `- 整体：n=${result.overall.sample_count}，均值=${formatExportPct(result.overall.mean_return)}，中位数=${formatExportPct(result.overall.median_return)}，胜率=${formatExportPct(result.overall.win_rate)}`,
      `- 整体风险：平均盈利=${formatExportPct(result.overall.mean_positive_return)}，平均亏损=${formatExportPct(result.overall.mean_negative_return)}，盈亏比=${formatExportRatio(result.overall.payoff_ratio)}，样本最大收益=${formatExportPct(result.overall.max_return)}，样本最大亏损=${formatExportPct(result.overall.max_loss)}`,
      "",
    );
    for (const [groupName, stats] of [["命中组", result.matched], ["未命中补集", result.complement], ["整体", result.overall]] as const) {
      lines.push(`### ${groupName}的基准、超额与路径指标`, "", "| 指标 | 样本数 | 缺失数 | 均值 | 最小 | 最大 | 定义 |", "|---|---:|---:|---:|---:|---:|---|");
      for (const [metricName, metric] of Object.entries(stats.metric_summaries)) {
        lines.push(`| ${metricName} | ${metric.sample_count} | ${metric.missing_count} | ${formatExportPct(metric.mean)} | ${formatExportPct(metric.minimum)} | ${formatExportPct(metric.maximum)} | ${escapeMarkdownCell(metric.definition)} |`);
      }
      lines.push("");
    }
    if (result.research_status_reasons.length) {
      lines.push("研究状态原因：", ...result.research_status_reasons.map((reason) => `- ${reason}`), "");
    }
    lines.push("事件（当前响应页）：", "", "| 日期 | 股票 | 因子 | 收益 | 基准 | 超额 | 标签 | 缺失原因 |", "|---|---|---|---:|---:|---:|---|---|");
    for (const event of result.events) {
      lines.push(
        `| ${event.research_date} | ${event.stock_code} | ${event.factor_id} | ${formatExportPct(event.return_value)} | ${formatExportPct(event.benchmark_return)} | ${formatExportPct(event.excess_return)} | ${event.label_available ? "可用" : "不可用"} | ${escapeMarkdownCell(event.missing_reason ?? "—")} |`,
      );
    }
    if (!result.events.length) lines.push("| — | — | — | — | — | — | — | 当前响应页无事件 | ");
    lines.push("");
    if (result.warnings.length) lines.push("警告：", ...result.warnings.map((warning) => `- ${warning}`), "");
  }
  if (knownLimitations.length) {
    lines.push("## 数据集已登记限制", "", ...knownLimitations.map((limitation) => `- ${limitation}`), "");
  }
  lines.push("---", "本报告保留后端返回的 unavailable/null；描述统计不等于预测能力或交易建议。");
  download(`${base}.md`, lines.join("\n"), "text/markdown;charset=utf-8");
}

function formatExportPct(value: number | null): string {
  return value === null || value === undefined ? "不可用" : `${(value * 100).toFixed(4)}%`;
}

function formatExportRatio(value: number | null): string {
  return value === null || value === undefined ? "不可用" : value.toFixed(4);
}

function escapeMarkdownCell(value: string): string {
  return value.replace(/\|/g, "\\|").replace(/[\r\n]+/g, " ");
}

/* -------------------------------------------------------------------------- */
/* 演示模式：就地生成，且逐页标注"演示数据"                                       */
/* -------------------------------------------------------------------------- */

const DEMO_BANNER =
  "【演示数据】本文件由演示模式（?fixture=ui-reference）生成，全部内容为冻结样本，" +
  "不代表任何真实标的的当前分析结果，也不构成研究结论。";

function fixturePayload(target: ExportTarget) {
  const s = target.snapshot;
  const opinions = s.opinions ?? {};
  return {
    demo: true,
    demo_notice: DEMO_BANNER,
    exported_at: new Date().toISOString(),
    analysis_id: target.analysisId,
    stock: {
      code: s.stock?.stock_code ?? "",
      name: s.stock?.name ?? "",
      exchange: s.stock?.exchange ?? "",
      listing_date: s.stock?.listing_date ?? "",
    },
    as_of: s.as_of,
    variant_mode: s.variant_mode,
    // 导出身份必须与页面显示、请求参数一致：缺了 horizon 就会出现
    // "页面选 60d、报告里查不到窗口"的三份身份互不相认。
    horizon: s.horizon ?? null,
    birth_profile: {
      basis: s.birth_profile?.birth_basis ?? "",
      datetime: s.birth_profile?.birth_datetime ?? "",
      timezone: s.birth_profile?.timezone ?? "",
      data_quality: s.birth_profile?.data_quality ?? null,
      assumptions: s.birth_profile?.assumptions ?? [],
    },
    engines: Object.entries(opinions).map(([engine, op]) => ({
      engine,
      availability: op.availability,
      score: op.score,
      direction: op.direction,
      confidence: op.confidence,
      // 不可用引擎的 score 必须保持 null（不填 0）
      note: op.note,
    })),
    consensus: s.consensus
      ? {
          label: s.consensus.label,
          label_cn: s.consensus.label_cn,
          agreement: s.consensus.agreement,
          mean_score: s.consensus.mean_score,
          unavailable_engines: s.consensus.unavailable_engines,
          note: s.consensus.note,
        }
      : null,
    conflict: s.conflict
      ? {
          has_conflict: s.conflict.has_conflict,
          severity: s.conflict.severity,
          reasons: s.conflict.reasons,
          note: s.conflict.note,
        }
      : null,
    versions: s.versions ?? {},
    warnings: s.warnings ?? [],
    limitations: [
      "演示样本为冻结数据，不含逐标的 EventStudy 结果，因此没有任何收益 / 胜率 / 曲线。",
      "分数是传统规则强度，不代表预期收益率，也不代表上涨概率。",
      "模型分歧如实保留，未用平均值掩盖。",
    ],
  };
}

function fixtureHtml(target: ExportTarget): string {
  const p = fixturePayload(target);
  const rows = (p.engines as Record<string, unknown>[])
    .map((e) => {
      const score = e.score === null || e.score === undefined ? "null（不可用，不用 0 代替）" : String(e.score);
      return `<tr><td>${esc(String(e.engine))}</td><td>${esc(String(e.availability))}</td><td>${esc(score)}</td><td>${esc(String(e.confidence))}</td></tr>`;
    })
    .join("");
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>${esc(p.stock.code)} 演示报告</title>
<style>
 body{background:#0b1219;color:#e8edf2;font-family:"SMP Sans SC","Microsoft YaHei",sans-serif;
      margin:0;padding:28px 34px;line-height:1.7}
 h1{font-size:20px;color:#d4b87a;margin:0 0 4px}
 h2{font-size:15px;color:#d4b87a;margin:22px 0 8px;border-bottom:1px solid #1e3444;padding-bottom:5px}
 .banner{border:1px solid #e0a458;background:rgba(224,164,88,0.12);color:#e0a458;
         padding:10px 14px;border-radius:6px;margin-bottom:18px;font-weight:600}
 table{border-collapse:collapse;width:100%;font-size:13px}
 th,td{border:1px solid #1e3444;padding:6px 9px;text-align:left}
 th{background:#101f2b;color:#9faebc}
 .muted{color:#6f7d8a;font-size:12px}
 ul{margin:6px 0 0 18px;padding:0}
</style></head><body>
<div class="banner">${esc(DEMO_BANNER)}</div>
<h1>${esc(p.stock.name)} ${esc(p.stock.code)} · 演示报告</h1>
<div class="muted">分析 ID：${esc(p.analysis_id)} ｜ 基准日：${esc(String(p.as_of))} ｜ 变体：${esc(String(p.variant_mode))} ｜ 研究窗口：${esc(String(p.horizon ?? "未指定"))}</div>

<h2>出生档案</h2>
<table><tr><th>出生模型</th><td>${esc(p.birth_profile.basis)}</td></tr>
<tr><th>出生时刻</th><td>${esc(p.birth_profile.datetime)}</td></tr>
<tr><th>时区</th><td>${esc(p.birth_profile.timezone)}</td></tr>
<tr><th>数据质量</th><td>${esc(JSON.stringify(p.birth_profile.data_quality))}</td></tr></table>

<h2>三模型结果（演示数据）</h2>
<table><tr><th>引擎</th><th>可用性</th><th>分数</th><th>置信度</th></tr>${rows}</table>

<h2>共识与冲突（不取平均掩盖分歧）</h2>
<pre class="muted">${esc(JSON.stringify({ consensus: p.consensus, conflict: p.conflict }, null, 2))}</pre>

<h2>版本</h2>
<pre class="muted">${esc(JSON.stringify(p.versions, null, 2))}</pre>

<h2>研究限制</h2>
<ul>${(p.limitations as string[]).map((l) => `<li>${esc(l)}</li>`).join("")}</ul>

<div class="muted" style="margin-top:26px">股票玄学多模型研究平台 · 可打印 HTML（不是服务端 PDF）· 研究与教育用途，不构成投资建议</div>
</body></html>`;
}

async function exportFixtureReport(target: ExportTarget, format: ExportFormat): Promise<void> {
  const code = target.snapshot.stock?.stock_code ?? "demo";
  if (format === "json") {
    download(
      `demo-report-${code}-${stamp()}.json`,
      JSON.stringify(fixturePayload(target), null, 2),
      "application/json;charset=utf-8",
    );
    return;
  }
  if (format === "html") {
    download(`demo-report-${code}-${stamp()}.html`, fixtureHtml(target), "text/html;charset=utf-8");
    return;
  }
  download(`demo-report-${code}-${stamp()}.md`, fixtureMarkdown(target), "text/markdown;charset=utf-8");
}

function fixtureMarkdown(target: ExportTarget): string {
  const p = fixturePayload(target);
  const L: string[] = [];
  L.push(`> **${DEMO_BANNER}**`, "");
  L.push(`# ${p.stock.name} ${p.stock.code} · 演示报告`, "");
  L.push(`- 分析 ID：\`${p.analysis_id}\``);
  L.push(`- 基准日：${p.as_of}`);
  L.push(`- 变体：${p.variant_mode}`);
  L.push(`- 研究窗口：${p.horizon ?? "未指定"}`);
  L.push(`- 导出时间：${p.exported_at}`, "");
  L.push("## 出生档案", "");
  L.push(`- 出生模型：${p.birth_profile.basis}`);
  L.push(`- 出生时刻：${p.birth_profile.datetime}`);
  L.push(`- 时区：${p.birth_profile.timezone}`, "");
  L.push("## 三模型结果（演示数据）", "");
  L.push("| 引擎 | 可用性 | 分数 | 置信度 |");
  L.push("|---|---|---|---|");
  for (const e of p.engines as Record<string, unknown>[]) {
    L.push(`| ${e.engine} | ${e.availability} | ${e.score === null || e.score === undefined ? "null" : e.score} | ${e.confidence} |`);
  }
  L.push("", "## 共识与冲突", "");
  L.push("```json");
  L.push(JSON.stringify({ consensus: p.consensus, conflict: p.conflict }, null, 2));
  L.push("```", "", "## 研究限制", "");
  for (const l of p.limitations as string[]) L.push(`- ${l}`);
  L.push("", "---", "股票玄学多模型研究平台 · 研究与教育用途，不构成投资建议");
  return L.join("\n");
}

function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
