"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { ResearchNav } from "@/components/research/ResearchNav";
import { AppShell } from "@/components/shell/AppShell";
import { PageError, PageLoading, ResearchStatusBadge, UnavailableBlock } from "@/components/shell/PageState";
import { PageHero } from "@/components/shell/TopBar";
import { api, endpoints, type ApiExperimentDetail, type ApiExperimentListResponse, type ApiExperimentSummary } from "@/lib/api";
import type { ApiExperimentReportV2Response } from "@/lib/researchV2";

const KINDS = ["", "event_study", "relation_event_study", "negative_control", "consensus"];
const STATUSES = ["", "NO_SIGNAL", "INCONCLUSIVE", "WEAK_EVIDENCE", "INVALID_CONTROL", "NO_REAL_DATA", "SUPPORTED_IN_SAMPLE"];

function ExperimentsContent() {
  const search = useSearchParams();
  const fixture = search?.get("fixture") === "ui-reference";
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [list, setList] = useState<ApiExperimentListResponse | null>(null);
  const [selected, setSelected] = useState<ApiExperimentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load(nextKind = kind, nextStatus = status) {
    setLoading(true);
    setError(null);
    try {
      const response = await api.get<ApiExperimentListResponse>(endpoints.researchExperiments(50, { kind: nextKind || undefined, status: nextStatus || undefined }));
      setList(response);
      if (response.items.length) await selectExperiment(response.items[0]);
      else setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function selectExperiment(item: ApiExperimentSummary) {
    try {
      setSelected(await api.get<ApiExperimentDetail>(endpoints.researchExperiment(item.experiment_id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    if (fixture) { setLoading(false); return; }
    void load();
  }, [fixture]);

  return (
    <AppShell activeNav="research" dataStatus={error ? "bad" : loading ? "warn" : "ok"} statusText={error ? "实验读取失败" : loading ? "读取实验" : "实验目录就绪"}>
      <PageHero title="历史实验" subtitle="查看 Event Study、关系研究、负对照与样本外实验的真实记录" seal="验" />
      <ResearchNav />
      <FrozenExperimentReports fixture={fixture} />
      {fixture ? <Card className="mt-2"><CardBody><UnavailableBlock what="v1 实验档案" reason="UI fixture 不含后端入库实验；移除 ?fixture=ui-reference 后读取真实存档。" /></CardBody></Card> : <>
        <Card testId="experiments-controls"><CardHeader title="兼容存档实验筛选 · v1" dense /><div className="flex flex-wrap gap-2 p-3"><label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>类型<select className="smp-input ml-2" value={kind} onChange={(event) => { setKind(event.target.value); void load(event.target.value, status); }}>{KINDS.map((value) => <option key={value} value={value}>{value || "全部"}</option>)}</select></label><label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>状态<select className="smp-input ml-2" value={status} onChange={(event) => { setStatus(event.target.value); void load(kind, event.target.value); }}>{STATUSES.map((value) => <option key={value} value={value}>{value || "全部"}</option>)}</select></label><span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>共 {list?.filtered_count ?? 0} 条 · 返回 {list?.returned_count ?? 0} 条</span></div></Card>
        {loading && !list ? <PageLoading label="正在读取历史实验…" /> : null}
        {error ? <PageError title="v1 实验存档读取失败" message={error} onRetry={() => void load()} /> : null}
        {list?.items.length ? <div className="mt-2 grid gap-2 lg:grid-cols-[0.9fr_1.1fr]"><Card testId="experiment-list"><CardHeader title="v1 实验目录" dense /><div className="divide-y" style={{ borderColor: "var(--color-border)" }}>{list.items.map((item) => <button key={item.experiment_id} type="button" onClick={() => void selectExperiment(item)} className="block w-full px-3 py-2 text-left hover:bg-white/[0.03]" style={{ borderColor: "var(--color-border)" }}><div className="flex items-center gap-2"><span className="smp-num text-[11px]" style={{ color: "var(--color-gold)" }}>{item.experiment_id}</span><Chip tone="flat">{item.kind}</Chip><ResearchStatusBadge status={item.status} /></div><div className="mt-1 text-[12px]" style={{ color: "var(--color-ink)" }}>{item.name}</div><div className="mt-1 text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>{item.created_at.slice(0, 19)} · {item.factor_ids.join("、")}</div></button>)}</div></Card><ExperimentDetail detail={selected} /></div> : !loading ? <Card className="mt-2"><CardBody><UnavailableBlock what="v1 历史实验" reason="当前筛选下没有已入库旧版实验。F5 冻结协议结果见上方 v2 报告区。" /></CardBody></Card> : null}
      </>}
    </AppShell>
  );
}

export default function ExperimentsPage() {
  return <Suspense fallback={<PageLoading />}><ExperimentsContent /></Suspense>;
}

const FROZEN_EXPERIMENTS = [
  { id: "F5-EXP-001", title: "流日十神十类" },
  { id: "F5-EXP-002", title: "六合、六冲、相害" },
  { id: "F5-EXP-003", title: "组合实验（未配置）" },
] as const;

function FrozenExperimentReports({ fixture }: { fixture: boolean }) {
  const [selectedId, setSelectedId] = useState<string>(FROZEN_EXPERIMENTS[0].id);
  const [response, setResponse] = useState<ApiExperimentReportV2Response | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (fixture) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setResponse(null);
    void api.get<ApiExperimentReportV2Response>(endpoints.experimentReportV2(selectedId)).then((value) => {
      if (!cancelled) setResponse(value);
    }).catch((value: unknown) => {
      if (!cancelled) setError(value instanceof Error ? value.message : String(value));
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, [fixture, selectedId, nonce]);

  const report = response?.report ?? {};
  const dataset = asRecord(report.dataset);
  const metadata = asRecord(dataset.metadata);
  const scope = asRecord(report.scope);
  const registration = asRecord(report.registration);
  const correction = asRecord(report.family_correction);
  const tests = asRecordList(report.registered_tests);
  const reasons = asStringList(report.research_status_reasons);
  const categories = Array.isArray(scope.categories) ? scope.categories.map(String) : [];
  const dates = asRecord(scope.date_range);

  return (
    <Card className="mt-2" testId="frozen-experiment-reports">
      <CardHeader title="F5 冻结实验报告 · v2" dense right={<Chip tone="warn">探索性，不具确认性资格</Chip>} />
      {fixture ? <CardBody><UnavailableBlock what="F5 v2 实验报告" reason="UI fixture 不读取本机生成的实验产物；移除 ?fixture=ui-reference 后由 API 读取固定报告。" /></CardBody> : <>
        <div className="flex flex-wrap gap-1 border-b px-3 py-2" style={{ borderColor: "var(--color-border)" }}>
          {FROZEN_EXPERIMENTS.map((item) => <button key={item.id} type="button" onClick={() => setSelectedId(item.id)} className={`smp-btn px-2.5 py-1.5 text-[11.5px] ${selectedId === item.id ? "smp-btn--primary" : ""}`} data-testid={`frozen-experiment-${item.id}`}>{item.id} · {item.title}</button>)}
        </div>
        {loading ? <div className="p-3"><PageLoading label={`正在读取 ${selectedId} 的 v2 固定报告…`} /></div> : null}
        {error ? <div className="p-3"><PageError title={`${selectedId} 报告不可用`} message={error} onRetry={() => setNonce((value) => value + 1)} /></div> : null}
        {response ? <div className="space-y-2 p-3" data-testid="frozen-experiment-detail">
          <div className="flex flex-wrap items-center gap-2"><ResearchStatusBadge status={stringValue(report.research_status, "NOT_RUN")} showCode compact /><span className="smp-num text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>report_digest={response.report_digest}</span></div>
          {reasons.map((reason) => <div key={reason} className="text-[11.5px]" style={{ color: "var(--color-warn)" }}>· {reason}</div>)}
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="数据集" value={stringValue(dataset.dataset_id)} />
            <Field label="Dataset digest" value={stringValue(dataset.dataset_digest)} />
            <Field label="数据范围" value={`${stringValue(dates.start)} ～ ${stringValue(dates.end)}`} />
            <Field label="研究 / 确认性资格" value={`${boolLabel(dataset.research_eligible)} / ${boolLabel(dataset.confirmatory_research_eligible)}`} />
            <Field label="观察数 / 证券数" value={`${stringValue(scope.observation_count)} / ${stringValue(scope.security_count)}`} />
            <Field label="协议版本 / 摘要" value={`${stringValue(report.protocol_version)} / ${stringValue(report.protocol_sha256)}`} />
            <Field label="结果摘要" value={stringValue(report.result_digest)} />
            <Field label="先导标签已查看" value={boolLabel(registration.pilot_labels_previously_seen)} />
          </div>
          {categories.length ? <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>预注册类别：{categories.join("、")}</div> : null}
          {Array.isArray(metadata.known_limitations) && metadata.known_limitations.length ? <div className="rounded border px-2.5 py-2 text-[11px]" style={{ borderColor: "var(--color-border)", color: "var(--color-warn)" }} data-testid="frozen-experiment-limitations">数据集限制：{metadata.known_limitations.map(String).join("；")}</div> : null}
          {Object.keys(correction).length ? <div className="rounded border px-2.5 py-2 text-[11px]" style={{ borderColor: "var(--color-border)" }} data-testid="frozen-experiment-correction">检验族校正：family={stringValue(correction.family_id)} · 固定族大小={stringValue(correction.registered_test_count)} · 可计算 p={stringValue(correction.evaluable_p_value_count)} · 不可用 p={stringValue(correction.unavailable_p_value_count)} · FDR 通过={stringValue(correction.fdr_pass_count)} · Bonferroni 通过={stringValue(correction.bonferroni_pass_count)}</div> : null}
          {tests.length ? <div className="overflow-x-auto"><table className="smp-table min-w-[950px]" data-testid="frozen-experiment-tests"><thead><tr><th>条件</th><th>因子</th><th>分区</th><th>周期</th><th>样本状态</th><th>命中 / 补集</th><th>p / q</th><th>置换 / 区间</th><th>负对照诊断</th></tr></thead><tbody>{tests.map((item, index) => { const permutation = asRecord(item.permutation); const bootstrap = asRecord(item.moving_block_bootstrap); return <tr key={`${stringValue(item.hypothesis_id)}-${index}`}><td>{stringValue(item.condition_title, stringValue(item.condition_id))}</td><td>{stringValue(item.factor_id)}</td><td>{stringValue(item.partition)}</td><td>{stringValue(item.horizon)}D</td><td>{stringValue(item.sample_status)}</td><td>{stringValue(item.matched_observation_count)} / {stringValue(item.complement_observation_count)}</td><td>{nullableNumber(item.raw_p_value)} / {nullableNumber(item.fdr_q_value)}</td><td>{stringValue(permutation.status)} ({stringValue(permutation.permutation_count)}) / {stringValue(bootstrap.status)} ({stringValue(bootstrap.bootstrap_count)})</td><td>{shortJson(item.negative_control)}</td></tr>; })}</tbody></table></div> : <UnavailableBlock what="检验明细" reason={selectedId === "F5-EXP-003" ? "此实验按冻结计划保持未配置，没有执行组合搜索。" : "报告没有注册检验明细。"} />}
          <details className="text-[11px]"><summary className="cursor-pointer" style={{ color: "var(--color-ink-muted)" }}>冻结条件与完整 v2 报告 JSON</summary><pre className="mt-2 max-h-[380px] overflow-auto rounded p-2" style={{ background: "rgba(255,255,255,0.03)" }}>{JSON.stringify({ frozen_conditions: report.frozen_conditions, analysis_protocol: report.analysis_protocol, time_split_protocol: report.time_split_protocol, report }, null, 2)}</pre></details>
        </div> : null}
      </>}
    </Card>
  );
}

function asRecord(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function asRecordList(value: unknown): Record<string, unknown>[] { return Array.isArray(value) ? value.map(asRecord) : []; }
function asStringList(value: unknown): string[] { return Array.isArray(value) ? value.map(String) : []; }
function stringValue(value: unknown, fallback = "不可用"): string { return value === null || value === undefined || value === "" ? fallback : String(value); }
function boolLabel(value: unknown): string { return value === true ? "是" : value === false ? "否" : "不可用"; }
function nullableNumber(value: unknown): string { return typeof value === "number" && Number.isFinite(value) ? value.toFixed(4) : "不可用"; }
function shortJson(value: unknown): string { return value && typeof value === "object" ? JSON.stringify(value).slice(0, 180) : stringValue(value); }

function ExperimentDetail({ detail }: { detail: ApiExperimentDetail | null }) {
  if (!detail) return <Card><CardBody><div className="smp-disclaimer">选择左侧实验查看真实详情。</div></CardBody></Card>;
  const exp = detail.experiment;
  return <Card testId="experiment-detail"><CardHeader title="实验详情" dense right={<ResearchStatusBadge status={exp.status ?? "NOT_RUN"} />} /><CardBody><div className="grid grid-cols-2 gap-2 text-[11.5px] md:grid-cols-4"><Field label="Experiment ID" value={exp.experiment_id} /><Field label="研究类型" value={exp.kind} /><Field label="创建时间" value={exp.created_at} /><Field label="股票池" value={exp.universe.join("、")} /><Field label="日期区间" value={`${exp.date_from ?? "—"} ～ ${exp.date_to ?? "—"}`} /><Field label="持有期" value={exp.horizons.join("、")} /><Field label="基准" value={exp.benchmark_code ?? "—"} /><Field label="随机种子" value={exp.seed} /></div><div className="mt-3 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>{exp.methodology}</div><div className="mt-3 overflow-x-auto"><table className="smp-table min-w-[760px]"><thead><tr><th>Variant</th><th>持有期</th><th>样本数</th><th>上涨率</th><th>平均收益</th><th>超额收益</th><th>研究状态 / 备注</th></tr></thead><tbody>{Object.entries(detail.results_by_variant).flatMap(([variant, rows]) => rows.map((row) => <tr key={`${variant}-${row.horizon}`}><td>{variant}</td><td>{row.horizon}D</td><td>{row.sample_count}</td><td>{formatPct(row.up_rate)}</td><td>{formatPct(row.mean_return)}</td><td>{formatPct(row.mean_excess_return)}</td><td>{String(row.extra?.research_status ?? row.extra?.note ?? "—")}</td></tr>))}</tbody></table></div></CardBody></Card>;
}
function Field({ label, value }: { label: string; value: string | number | null }) { return <div className="rounded border px-2 py-1.5" style={{ borderColor: "var(--color-border)" }}><div className="smp-metric-label">{label}</div><div className="mt-1 break-all" style={{ color: "var(--color-ink)" }}>{value ?? "—"}</div></div>; }
function formatPct(value: number | null): string { return value === null || value === undefined ? "—" : `${(value * 100).toFixed(2)}%`; }
