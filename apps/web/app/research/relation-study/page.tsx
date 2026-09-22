"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { ResearchNav } from "@/components/research/ResearchNav";
import { AppShell } from "@/components/shell/AppShell";
import { PageError, PageLoading, ResearchStatusBadge, UnavailableBlock } from "@/components/shell/PageState";
import { PageHero } from "@/components/shell/TopBar";
import { api, endpoints, type ApiRelationStudy } from "@/lib/api";

const RELATION_OPTIONS = [
  "六合", "六冲", "三合", "半合", "三会", "相刑", "自刑", "相害", "六破", "同支",
  "伏吟", "反吟", "天合地合", "天克地冲", "天干五合", "天干相冲", "天干生", "天干克", "天干同五行",
];

function RelationStudyInner() {
  const search = useSearchParams();
  const fixture = search?.get("fixture") === "ui-reference";
  const [relation, setRelation] = useState("六合");
  const [dateFrom, setDateFrom] = useState("2016-01-01");
  const [dateTo, setDateTo] = useState("2026-09-18");
  const [study, setStudy] = useState<ApiRelationStudy | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const result = await api.post<ApiRelationStudy>(endpoints.relationStudy(), {
        relation_type: relation,
        universe: "v4-full",
        date_from: dateFrom,
        date_to: dateTo,
        horizons: [1, 5, 20],
        sample_step_months: 3,
        run_negative_controls: true,
        persist: true,
      });
      setStudy(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStudy(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <AppShell activeNav="research" dataStatus={error ? "bad" : loading ? "warn" : "ok"} statusText={error ? "研究失败" : loading ? "关系研究中" : "研究模块就绪"}>
      <PageHero title="关系历史研究" subtitle="将关系事件作为无方向研究因子，比较历史行为与负对照" seal="验" couplet={["先看事件", "再问统计"]} />
      <ResearchNav />
      {fixture ? <Card><UnavailableBlock what="关系历史研究" reason="UI fixture 只冻结十张视觉样本，不伪造关系研究统计。移除 ?fixture=ui-reference 后运行真实研究。" /></Card> : null}
      <Card testId="relation-study-controls">
        <CardHeader title="研究参数" dense right={<Chip tone="gold">direction = 0</Chip>} />
        <div className="grid gap-3 p-3 md:grid-cols-[1.3fr_170px_170px_auto] md:items-end">
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>关系类型
            <select className="smp-input mt-1 w-full" value={relation} onChange={(event) => setRelation(event.target.value)}>
              {RELATION_OPTIONS.map((item) => <option key={item}>{item}</option>)}
            </select>
          </label>
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>开始日期<input className="smp-input mt-1 w-full" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} /></label>
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>结束日期<input className="smp-input mt-1 w-full" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} /></label>
          <button type="button" className="smp-btn smp-btn--primary h-[34px] px-4" onClick={() => void run()} disabled={loading || fixture} data-testid="relation-study-run">{loading ? "运行中…" : "运行研究"}</button>
        </div>
        <div className="border-t px-3 py-2 text-[11.5px]" style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}>股票池：v4-full · 按时间顺序切分 TRAIN / VALIDATION / OOS · 1D / 5D / 20D · 负对照：随机出生日、±7 天、随机因子。</div>
      </Card>
      {loading ? <PageLoading label="正在构造关系观测并运行 Event Study…" /> : null}
      {error ? <PageError title="关系历史研究失败" message={error} onRetry={() => void run()} /> : null}
      {study ? <StudyResult study={study} /> : <Card className="mt-2"><CardBody><div className="smp-disclaimer">尚未运行关系研究。关系命中不代表涨跌方向，未运行时不显示任何统计数字。</div></CardBody></Card>}
    </AppShell>
  );
}

function StudyResult({ study }: { study: ApiRelationStudy }) {
  return (
    <div className="mt-2 space-y-2" data-testid="relation-study-result">
      <Card>
        <CardHeader title={`${study.relation_type} · 关系事件研究`} dense right={<Chip tone="flat">{study.factor_id}</Chip>} />
        <div className="grid grid-cols-2 gap-2 p-3 md:grid-cols-5"><Metric label="股票池" value={`${study.universe} · ${study.universe_size}`} /><Metric label="研究区间" value={`${study.date_from ?? "—"} ～ ${study.date_to ?? "—"}`} /><Metric label="方向" value="0（无方向）" /><Metric label="实验ID" value={study.experiment_id} /><Metric label="数据" value={study.data_source.is_real === false ? "合成/降级" : "真实/待核验"} /></div>
      </Card>
      {study.splits.map((split) => (
        <Card key={split.name} testId={`relation-study-${split.name.toLowerCase()}`}>
          <CardHeader title={`${split.name} · ${split.date_from ?? "—"} ～ ${split.date_to ?? "—"}`} dense right={<ResearchStatusBadge status={split.research_status} reasons={split.research_status_reasons} />} />
          <div className="grid grid-cols-2 gap-2 px-3 py-2 text-[11.5px] md:grid-cols-4"><Metric label="事件数" value={String(split.event_count)} /><Metric label="样本数" value={String(split.sample_count)} /><Metric label="激活率" value={formatPct(split.activation_rate)} /><Metric label="对照" value={String(Object.keys(split.negative_controls).length)} /></div>
          <div className="overflow-x-auto px-3 pb-3"><table className="smp-table min-w-[900px]"><thead><tr><th>持有期</th><th>样本数</th><th>平均收益</th><th>中位数</th><th>上涨率</th><th>超额收益</th><th>p-value</th><th>q-value</th><th>随机对照均值</th></tr></thead><tbody>{split.horizons.map((item) => <tr key={item.horizon}><td>{item.horizon}D</td><td>{item.sample_count}</td><td>{formatPct(item.mean_return)}</td><td>{formatPct(item.median_return)}</td><td>{formatPct(item.up_rate)}</td><td>{formatPct(item.mean_excess_return)}</td><td>{formatNumber(item.p_value)}</td><td>{formatNumber(item.q_value)}</td><td>{formatPct(item.control_mean_return)}</td></tr>)}</tbody></table></div>
        </Card>
      ))}
      <Card><CardHeader title="研究方法与边界" dense /><CardBody><div className="smp-disclaimer">{study.methodology}</div>{study.warnings.length ? <div className="mt-2 text-[11.5px]" style={{ color: "var(--color-warn)" }}>{study.warnings.map((warning) => <div key={warning}>· {warning}</div>)}</div> : null}</CardBody></Card>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded border px-2 py-2" style={{ borderColor: "var(--color-border)" }}><div className="smp-metric-label">{label}</div><div className="mt-1 text-[12px]" style={{ color: "var(--color-ink)" }}>{value}</div></div>; }
function formatPct(value: number | null): string { return value === null || value === undefined ? "—" : `${(value * 100).toFixed(2)}%`; }
function formatNumber(value: number | null): string { return value === null || value === undefined ? "—" : value.toFixed(4); }

export default function RelationStudyPage() { return <Suspense fallback={<PageLoading />}><RelationStudyInner /></Suspense>; }
