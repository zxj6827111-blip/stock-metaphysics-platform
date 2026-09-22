"use client";

import { useEffect, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { ResearchNav } from "@/components/research/ResearchNav";
import { AppShell } from "@/components/shell/AppShell";
import { PageError, PageLoading, ResearchStatusBadge, UnavailableBlock } from "@/components/shell/PageState";
import { PageHero } from "@/components/shell/TopBar";
import { api, endpoints, type ApiExperimentDetail, type ApiExperimentListResponse, type ApiExperimentSummary } from "@/lib/api";

const KINDS = ["", "event_study", "relation_event_study", "negative_control", "consensus"];
const STATUSES = ["", "NO_SIGNAL", "INCONCLUSIVE", "WEAK_EVIDENCE", "INVALID_CONTROL", "NO_REAL_DATA", "SUPPORTED_IN_SAMPLE"];

export default function ExperimentsPage() {
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

  useEffect(() => { void load(); }, []);

  return (
    <AppShell activeNav="research" dataStatus={error ? "bad" : loading ? "warn" : "ok"} statusText={error ? "实验读取失败" : loading ? "读取实验" : "实验目录就绪"}>
      <PageHero title="历史实验" subtitle="查看 Event Study、关系研究、负对照与样本外实验的真实记录" seal="验" />
      <ResearchNav />
      <Card testId="experiments-controls"><CardHeader title="实验筛选" dense /><div className="flex flex-wrap gap-2 p-3"><label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>类型<select className="smp-input ml-2" value={kind} onChange={(event) => { setKind(event.target.value); void load(event.target.value, status); }}>{KINDS.map((value) => <option key={value} value={value}>{value || "全部"}</option>)}</select></label><label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>状态<select className="smp-input ml-2" value={status} onChange={(event) => { setStatus(event.target.value); void load(kind, event.target.value); }}>{STATUSES.map((value) => <option key={value} value={value}>{value || "全部"}</option>)}</select></label><span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>共 {list?.filtered_count ?? 0} 条 · 返回 {list?.returned_count ?? 0} 条</span></div></Card>
      {loading && !list ? <PageLoading label="正在读取历史实验…" /> : null}
      {error ? <PageError title="历史实验读取失败" message={error} onRetry={() => void load()} /> : null}
      {list?.items.length ? <div className="mt-2 grid gap-2 lg:grid-cols-[0.9fr_1.1fr]"><Card testId="experiment-list"><CardHeader title="实验目录" dense /><div className="divide-y" style={{ borderColor: "var(--color-border)" }}>{list.items.map((item) => <button key={item.experiment_id} type="button" onClick={() => void selectExperiment(item)} className="block w-full px-3 py-2 text-left hover:bg-white/[0.03]" style={{ borderColor: "var(--color-border)" }}><div className="flex items-center gap-2"><span className="smp-num text-[11px]" style={{ color: "var(--color-gold)" }}>{item.experiment_id}</span><Chip tone="flat">{item.kind}</Chip><ResearchStatusBadge status={item.status} /></div><div className="mt-1 text-[12px]" style={{ color: "var(--color-ink)" }}>{item.name}</div><div className="mt-1 text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>{item.created_at.slice(0, 19)} · {item.factor_ids.join("、")}</div></button>)}</div></Card><ExperimentDetail detail={selected} /></div> : !loading ? <Card className="mt-2"><CardBody><UnavailableBlock what="历史实验" reason="当前筛选下没有已入库实验。运行关系研究或研究流水线后，实验会自动出现在这里。" /></CardBody></Card> : null}
    </AppShell>
  );
}

function ExperimentDetail({ detail }: { detail: ApiExperimentDetail | null }) {
  if (!detail) return <Card><CardBody><div className="smp-disclaimer">选择左侧实验查看真实详情。</div></CardBody></Card>;
  const exp = detail.experiment;
  return <Card testId="experiment-detail"><CardHeader title="实验详情" dense right={<ResearchStatusBadge status={exp.status ?? "NOT_RUN"} />} /><CardBody><div className="grid grid-cols-2 gap-2 text-[11.5px] md:grid-cols-4"><Field label="Experiment ID" value={exp.experiment_id} /><Field label="研究类型" value={exp.kind} /><Field label="创建时间" value={exp.created_at} /><Field label="股票池" value={exp.universe.join("、")} /><Field label="日期区间" value={`${exp.date_from ?? "—"} ～ ${exp.date_to ?? "—"}`} /><Field label="持有期" value={exp.horizons.join("、")} /><Field label="基准" value={exp.benchmark_code ?? "—"} /><Field label="随机种子" value={exp.seed} /></div><div className="mt-3 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>{exp.methodology}</div><div className="mt-3 overflow-x-auto"><table className="smp-table min-w-[760px]"><thead><tr><th>Variant</th><th>持有期</th><th>样本数</th><th>上涨率</th><th>平均收益</th><th>超额收益</th><th>研究状态 / 备注</th></tr></thead><tbody>{Object.entries(detail.results_by_variant).flatMap(([variant, rows]) => rows.map((row) => <tr key={`${variant}-${row.horizon}`}><td>{variant}</td><td>{row.horizon}D</td><td>{row.sample_count}</td><td>{formatPct(row.up_rate)}</td><td>{formatPct(row.mean_return)}</td><td>{formatPct(row.mean_excess_return)}</td><td>{String(row.extra?.research_status ?? row.extra?.note ?? "—")}</td></tr>))}</tbody></table></div></CardBody></Card>;
}
function Field({ label, value }: { label: string; value: string | number | null }) { return <div className="rounded border px-2 py-1.5" style={{ borderColor: "var(--color-border)" }}><div className="smp-metric-label">{label}</div><div className="mt-1 break-all" style={{ color: "var(--color-ink)" }}>{value ?? "—"}</div></div>; }
function formatPct(value: number | null): string { return value === null || value === undefined ? "—" : `${(value * 100).toFixed(2)}%`; }
