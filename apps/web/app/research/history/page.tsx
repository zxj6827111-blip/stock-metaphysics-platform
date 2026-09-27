"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { ResearchNav } from "@/components/research/ResearchNav";
import { AppShell } from "@/components/shell/AppShell";
import { PageError, PageLoading, PageEmpty, ResearchStatusBadge, UnavailableBlock } from "@/components/shell/PageState";
import { SectionError, SectionUnavailable } from "@/components/shell/SectionState";
import { PageHero } from "@/components/shell/TopBar";
import { api, endpoints } from "@/lib/api";
import { exportHistoricalResearchV2 } from "@/lib/reportExport";
import { DEFAULT_RESEARCH_DATASET_ID } from "@/lib/researchV2";
import type {
  ApiHistoricalDatasetV2,
  ApiHistoricalEventStudyRequest,
  ApiHistoricalEventStudyV2,
  ApiHistoricalDatasetVersions,
} from "@/lib/researchV2";

const HORIZONS = [1, 5, 20] as const;
type Horizon = (typeof HORIZONS)[number];
type ScopeMode = "stock" | "dates";
type Activation = "any" | "nonzero" | "positive" | "negative";

function HistoricalResearchInner() {
  const search = useSearchParams();
  const fixture = search?.get("fixture") === "ui-reference";
  const relationType = search?.get("relation_type") ?? "";
  const [datasetId, setDatasetId] = useState(search?.get("dataset_id") || DEFAULT_RESEARCH_DATASET_ID);
  const [dataset, setDataset] = useState<ApiHistoricalDatasetV2 | null>(null);
  const [datasetLoading, setDatasetLoading] = useState(true);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [scopeMode, setScopeMode] = useState<ScopeMode>(search?.get("scope_mode") === "stock" ? "stock" : "dates");
  const [stockCode, setStockCode] = useState(search?.get("stock_code") ?? "");
  const [dateFrom, setDateFrom] = useState(search?.get("date_from") ?? "");
  const [dateTo, setDateTo] = useState(search?.get("date_to") ?? "");
  const [factorId, setFactorId] = useState(search?.get("factor_id") ?? (relationType ? "" : "B_DAY_005"));
  const [activation, setActivation] = useState<Activation>(search?.get("activation") === "nonzero" ? "nonzero" : "any");
  const [direction, setDirection] = useState<"" | "-1" | "0" | "1">("");
  const [versionIndex, setVersionIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<Partial<Record<Horizon, ApiHistoricalEventStudyV2>>>({});
  const [requests, setRequests] = useState<ApiHistoricalEventStudyRequest[]>([]);
  const [errors, setErrors] = useState<Partial<Record<Horizon, string>>>({});

  async function loadDataset(id = datasetId) {
    setDatasetLoading(true);
    setDatasetError(null);
    setDataset(null);
    setResults({});
    try {
      const response = await api.get<ApiHistoricalDatasetV2>(endpoints.historicalDatasetV2(id.trim()));
      setDataset(response);
      setVersionIndex(0);
      const dates = [...(response.metadata.scope?.research_dates ?? [])].sort();
      if (!search?.get("date_from") && dates.length) setDateFrom(dates[0]);
      if (!search?.get("date_to") && dates.length) setDateTo(dates[dates.length - 1]);
      if (!stockCode && response.metadata.scope?.stock_code) setStockCode(response.metadata.scope.stock_code);
    } catch (error) {
      setDatasetError(errorText(error));
    } finally {
      setDatasetLoading(false);
    }
  }

  useEffect(() => {
    if (!fixture) void loadDataset(datasetId);
    // Initial URL context is the dataset identity for this page load.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fixture]);

  const selectedVersions = dataset?.available_versions[versionIndex] ?? null;
  const datasetDates = useMemo(
    () => [...(dataset?.metadata.scope?.research_dates ?? [])].sort(),
    [dataset],
  );

  async function runStudy() {
    if (!dataset || !selectedVersions) return;
    const id = factorId.trim();
    if (!id || !dateFrom || !dateTo || (scopeMode === "stock" && !stockCode.trim())) {
      setErrors({ 1: "请提供因子、日期范围；个股模式还必须填写证券代码。" });
      return;
    }
    const base: Omit<ApiHistoricalEventStudyRequest, "horizon"> = {
      dataset_id: dataset.dataset_id,
      scope_mode: scopeMode,
      stock_code: scopeMode === "stock" ? stockCode.trim() : null,
      date_from: dateFrom,
      date_to: dateTo,
      factor_ids: [id],
      activation,
      direction_filter: direction ? (Number(direction) as -1 | 0 | 1) : null,
      min_rule_score: null,
      versions: selectedVersions,
      limit: 100,
      offset: 0,
    };
    const nextRequests = HORIZONS.map((horizon): ApiHistoricalEventStudyRequest => ({ ...base, horizon }));
    setRequests(nextRequests);
    setLoading(true);
    setErrors({});
    setResults({});
    const settled = await Promise.allSettled(
      nextRequests.map((request) => api.post<ApiHistoricalEventStudyV2>(endpoints.historicalEventStudyV2(), request)),
    );
    const nextResults: Partial<Record<Horizon, ApiHistoricalEventStudyV2>> = {};
    const nextErrors: Partial<Record<Horizon, string>> = {};
    settled.forEach((result, index) => {
      const horizon = HORIZONS[index];
      if (result.status === "fulfilled") nextResults[horizon] = result.value;
      else nextErrors[horizon] = errorText(result.reason);
    });
    setResults(nextResults);
    setErrors(nextErrors);
    setLoading(false);
  }

  const completeResults = HORIZONS.flatMap((horizon) => results[horizon] ? [results[horizon]!] : []);

  return (
    <AppShell activeNav="research" dataStatus={datasetError || Object.keys(errors).length ? "bad" : loading || datasetLoading ? "warn" : "ok"} statusText={datasetError ? "数据集读取失败" : loading ? "历史事件研究中" : "历史研究就绪"}>
      <PageHero title="历史验证" subtitle="基于显式 W4 数据集与完整版本组，查看 1 / 5 / 20 日事件表现与缺失状态" seal="验" />
      <ResearchNav />
      {fixture ? <Card><CardBody><UnavailableBlock what="历史验证" reason="UI fixture 不包含冻结的 v2 历史数据集；移除 ?fixture=ui-reference 后读取服务端数据，页面不会把演示样本伪装成研究结果。" /></CardBody></Card> : null}
      {!fixture ? (
        <>
          <Card testId="historical-study-controls">
            <CardHeader title="数据集与研究条件" dense right={<Chip tone={dataset?.confirmatory_research_eligible ? "gold" : "warn"}>{dataset?.confirmatory_research_eligible ? "确认性资格已登记" : "确认性资格未具备"}</Chip>} />
            <div className="grid gap-3 p-3 md:grid-cols-2 xl:grid-cols-4">
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>数据集 ID
                <div className="mt-1 flex gap-1"><input className="smp-input min-w-0 flex-1" value={datasetId} onChange={(event) => setDatasetId(event.target.value)} data-testid="historical-dataset-id" /><button type="button" className="smp-btn px-2" onClick={() => void loadDataset()} disabled={datasetLoading || !datasetId.trim()} data-testid="historical-load-dataset">读取</button></div>
              </label>
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>分析范围
                <select className="smp-input mt-1 w-full" value={scopeMode} onChange={(event) => setScopeMode(event.target.value as ScopeMode)} data-testid="historical-scope-mode"><option value="dates">日期维度</option><option value="stock">单只股票</option></select>
              </label>
              {scopeMode === "stock" ? <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>股票代码<input className="smp-input mt-1 w-full" value={stockCode} onChange={(event) => setStockCode(event.target.value)} data-testid="historical-stock-code" /></label> : null}
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>因子 ID<input className="smp-input mt-1 w-full" value={factorId} onChange={(event) => setFactorId(event.target.value)} placeholder="例如 B_DAY_005" data-testid="historical-factor-id" /></label>
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>激活条件
                <select className="smp-input mt-1 w-full" value={activation} onChange={(event) => setActivation(event.target.value as Activation)} data-testid="historical-activation"><option value="any">全部可用值</option><option value="nonzero">非零</option><option value="positive">正值</option><option value="negative">负值</option></select>
              </label>
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>开始日期<input className="smp-input mt-1 w-full" type="date" value={dateFrom} min={datasetDates[0]} max={datasetDates[datasetDates.length - 1]} onChange={(event) => setDateFrom(event.target.value)} data-testid="historical-date-from" /></label>
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>结束日期<input className="smp-input mt-1 w-full" type="date" value={dateTo} min={datasetDates[0]} max={datasetDates[datasetDates.length - 1]} onChange={(event) => setDateTo(event.target.value)} data-testid="historical-date-to" /></label>
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>方向筛选
                <select className="smp-input mt-1 w-full" value={direction} onChange={(event) => setDirection(event.target.value as typeof direction)} data-testid="historical-direction"><option value="">不筛选方向</option><option value="-1">-1</option><option value="0">0</option><option value="1">1</option></select>
              </label>
              <label className="text-[12px] md:col-span-2 xl:col-span-3" style={{ color: "var(--color-ink-muted)" }}>完整版本组
                <select className="smp-input mt-1 w-full" value={String(versionIndex)} onChange={(event) => setVersionIndex(Number(event.target.value))} data-testid="historical-version-select">
                  {dataset?.available_versions.map((versions, index) => <option key={`${versions.feature_version}-${index}`} value={index}>{versionLabel(versions)}</option>)}
                </select>
              </label>
              <button type="button" className="smp-btn smp-btn--primary self-end px-4" onClick={() => void runStudy()} disabled={loading || datasetLoading || !dataset || !selectedVersions || fixture} data-testid="historical-run">{loading ? "读取 1/5/20 日…" : "运行 v2 历史验证"}</button>
            </div>
              <div className="flex flex-wrap items-center gap-2 border-t px-3 py-2 text-[11px]" style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}>
              <Chip tone={dataset?.research_eligible ? "gold" : "warn"}>研究资格：{dataset?.research_eligible ? "可用" : "未认证"}</Chip>
              <Chip tone="flat">范围：{datasetDates[0] ?? "不可用"} ～ {datasetDates[datasetDates.length - 1] ?? "不可用"}</Chip>
              <Chip tone="flat">数据行：{dataset?.row_count ?? "—"}</Chip>
              <span>未认证数据仍只返回描述统计；`null`、缺失原因和样本不足状态按 API 原样保留。</span>
              {dataset?.metadata.known_limitations?.length ? <span title={dataset.metadata.known_limitations.join("\n")}>已登记 {dataset.metadata.known_limitations.length} 项数据限制</span> : null}
            </div>
            {relationType ? <div className="border-t px-3 py-2 text-[11.5px]" style={{ borderColor: "var(--color-border)", color: "var(--color-warn)" }} data-testid="historical-relation-prefill">来自日期扫描：{relationType}。关系与 W4 因子是不同契约；请确认已映射的因子 ID 后再运行。</div> : null}
          </Card>

          {datasetLoading ? <PageLoading label="正在核验数据集 manifest、分片摘要与可用版本…" /> : null}
          {datasetError ? <PageError title="研究数据集不可用" message={datasetError} onRetry={() => void loadDataset()} /> : null}
          {dataset && !datasetLoading && !datasetError && !dataset.available_versions.length ? <Card className="mt-2"><CardBody><UnavailableBlock what="历史验证" reason="数据集没有可用于事件查询的完整版本组；不会用默认版本补齐请求。" /></CardBody></Card> : null}
          {loading ? <PageLoading label="按同一数据集与版本读取 1、5、20 日结果…" /> : null}
          {HORIZONS.map((horizon) => errors[horizon] ? <Card key={`error-${horizon}`} className="mt-2"><CardBody><SectionError what={`${horizon} 日事件研究`} message={errors[horizon]!} testId={`historical-error-${horizon}`} /></CardBody></Card> : null)}
          {HORIZONS.map((horizon) => results[horizon] ? <HorizonResult key={horizon} result={results[horizon]!} /> : null)}
          {Object.keys(results).length > 0 ? (
            <Card className="mt-2" testId="historical-export">
              <CardHeader title="导出当前 v2 结果" dense />
              <CardBody>
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" className="smp-btn px-3 py-1.5" onClick={() => dataset && exportHistoricalResearchV2({ dataset, requests, results: completeResults }, "json")} data-testid="historical-export-json">导出 JSON</button>
                  <button type="button" className="smp-btn px-3 py-1.5" onClick={() => dataset && exportHistoricalResearchV2({ dataset, requests, results: completeResults }, "markdown")} data-testid="historical-export-markdown">导出 Markdown</button>
                  <span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>导出包含同一份 dataset digest、请求版本组和 API 响应，不在浏览器重新计算统计。</span>
                </div>
              </CardBody>
            </Card>
          ) : null}
          {!loading && !datasetLoading && dataset && !Object.keys(results).length && !Object.keys(errors).length ? <Card className="mt-2"><CardBody><PageEmpty title="尚未运行历史验证" hint="选择范围与因子后，页面会分别读取 1、5、20 日结果；未运行时不会显示占位统计。" /></CardBody></Card> : null}
          {dataset ? <Card className="mt-2"><CardHeader title="数据来源、版本与限制" dense /><CardBody><div className="grid gap-2 text-[11px] md:grid-cols-3"><TraceValue label="dataset_digest" value={dataset.dataset_digest} /><TraceValue label="schema_version" value={dataset.schema_version} /><TraceValue label="selected version group" value={selectedVersions ? versionLabel(selectedVersions) : "不可用"} /></div><details className="mt-2"><summary className="cursor-pointer text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>查看完整数据集元数据与已登记限制</summary><pre className="mt-2 max-h-[240px] overflow-auto rounded p-2 text-[10.5px]" style={{ background: "rgba(255,255,255,0.03)" }}>{JSON.stringify({ metadata: dataset.metadata, failed_shards: dataset.failed_shards, missing_shards: dataset.missing_shards }, null, 2)}</pre></details></CardBody></Card> : null}
          <div className="pt-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>结果为历史描述统计，不代表未来收益或投资建议。<Link href="/research/experiments" className="ml-1 underline" style={{ color: "var(--color-gold-strong)" }}>查看冻结实验报告</Link></div>
        </>
      ) : null}
    </AppShell>
  );
}

function HorizonResult({ result }: { result: ApiHistoricalEventStudyV2 }) {
  return (
    <Card className="mt-2" testId={`historical-result-${result.horizon}`}>
      <CardHeader title={`${result.horizon} 日历史事件`} dense right={<ResearchStatusBadge status={result.research_status} reasons={result.research_status_reasons} showCode compact />} />
      <div className="grid gap-2 p-3 sm:grid-cols-2 lg:grid-cols-5">
        <Metric label="候选观察" value={String(result.candidate_observation_count)} />
        <Metric label="命中观察" value={String(result.matched_observation_count)} />
        <Metric label="命中日期" value={String(result.matched_date_count)} />
        <Metric label="缺失观察" value={String(result.missing_observation_count)} />
        <Metric label="返回事件" value={`${result.returned_count} / ${result.matched_observation_count}`} />
      </div>
      <div className="grid gap-2 px-3 pb-3 md:grid-cols-3">
        <Statistics title="命中组" stats={result.matched} />
        <Statistics title="未命中补集" stats={result.complement} />
        <Statistics title="整体" stats={result.overall} />
      </div>
      {result.research_status_reasons.length ? <div className="px-3 pb-2 text-[11.5px]" style={{ color: "var(--color-warn)" }} data-testid={`historical-reasons-${result.horizon}`}>{result.research_status_reasons.map((reason) => <div key={reason}>· {reason}</div>)}</div> : null}
      {Object.keys(result.missing_by_reason).length ? <div className="px-3 pb-2 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>缺失原因：{Object.entries(result.missing_by_reason).map(([reason, count]) => `${reason} (${count})`).join(" · ")}</div> : null}
      <div className="overflow-x-auto border-t" style={{ borderColor: "var(--color-border)" }}>
        {result.events.length ? <table className="smp-table min-w-[900px]" data-testid={`historical-events-${result.horizon}`}><thead><tr><th>研究日期</th><th>证券</th><th>因子</th><th>调整收益</th><th>基准收益</th><th>超额收益</th><th>标签</th><th>缺失原因</th></tr></thead><tbody>{result.events.map((event) => <tr key={`${event.security_id}-${event.research_date}-${event.factor_id}`}><td>{event.research_date}</td><td>{event.stock_code}</td><td>{event.factor_id}</td><td>{formatPct(event.return_value)}</td><td>{formatPct(event.benchmark_return)}</td><td>{formatPct(event.excess_return)}</td><td>{event.label_available ? "可用" : "不可用"}</td><td>{event.missing_reason ?? "—"}</td></tr>)}</tbody></table> : <div className="p-3"><SectionUnavailable what="事件列表" reason="当前版本与范围没有返回可用事件；这不表示无信号，样本数和缺失原因见上方。" testId={`historical-events-empty-${result.horizon}`} /></div>}
      </div>
      {result.warnings.length ? <div className="border-t px-3 py-2 text-[11px]" style={{ borderColor: "var(--color-border)", color: "var(--color-warn)" }}>{result.warnings.map((warning) => <div key={warning}>· {warning}</div>)}</div> : null}
    </Card>
  );
}

function Statistics({ title, stats }: { title: string; stats: ApiHistoricalEventStudyV2["matched"] }) {
  return <div className="rounded border px-2.5 py-2" style={{ borderColor: "var(--color-border)" }}><div className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>{title} · n={stats.sample_count} · 缺失={stats.missing_count}</div><div className="mt-1 grid grid-cols-3 gap-1 text-[11.5px]"><span>均值 {formatPct(stats.mean_return)}</span><span>中位数 {formatPct(stats.median_return)}</span><span>胜率 {formatPct(stats.win_rate)}</span></div></div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded border px-2 py-1.5" style={{ borderColor: "var(--color-border)" }}><div className="smp-metric-label">{label}</div><div className="mt-1 smp-num text-[12px]" style={{ color: "var(--color-ink)" }}>{value}</div></div>; }
function TraceValue({ label, value }: { label: string; value: string }) { return <div className="rounded border px-2 py-1.5" style={{ borderColor: "var(--color-border)" }}><div className="smp-metric-label">{label}</div><div className="mt-1 break-all smp-num">{value}</div></div>; }
function versionLabel(versions: ApiHistoricalDatasetVersions): string { return `${versions.feature_version} · ${versions.label_version} · ${versions.factor_version} · ${versions.config_version}`; }
function formatPct(value: number | null): string { return value === null || value === undefined ? "不可用" : `${(value * 100).toFixed(2)}%`; }
function errorText(value: unknown): string { return value instanceof Error ? value.message : String(value); }

export default function HistoricalResearchPage() {
  return <Suspense fallback={<PageLoading />}><HistoricalResearchInner /></Suspense>;
}
