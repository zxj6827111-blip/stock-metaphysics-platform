"use client";

import { useEffect, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { PageError, PageLoading, ResearchStatusBadge } from "@/components/shell/PageState";
import { api, endpoints } from "@/lib/api";
import {
  DEFAULT_RESEARCH_DATASET_ID,
  type ApiHistoricalDatasetV2,
  type ApiHistoricalEventStudyRequest,
  type ApiHistoricalEventStudyV2,
} from "@/lib/researchV2";
import { isFixtureActive } from "@/lib/fixture";

const HORIZONS = [1, 5, 20] as const;

export function StockHistoricalV2Panel({ stockCode }: { stockCode: string }) {
  const fixture = isFixtureActive();
  const [dataset, setDataset] = useState<ApiHistoricalDatasetV2 | null>(null);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [datasetLoading, setDatasetLoading] = useState(!fixture);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [factorId, setFactorId] = useState("B_DAY_005");
  const [activation, setActivation] = useState<ApiHistoricalEventStudyRequest["activation"]>("nonzero");
  const [results, setResults] = useState<ApiHistoricalEventStudyV2[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (fixture) return;
    let cancelled = false;
    setDatasetLoading(true);
    void api.get<ApiHistoricalDatasetV2>(endpoints.historicalDatasetV2(DEFAULT_RESEARCH_DATASET_ID))
      .then((value) => {
        if (cancelled) return;
        setDataset(value);
        const dates = [...(value.metadata.scope?.research_dates ?? [])].sort();
        setDateFrom(value.certified_date_from ?? dates[0] ?? "");
        setDateTo(value.certified_date_to ?? dates[dates.length - 1] ?? "");
      })
      .catch((reason: unknown) => {
        if (!cancelled) setDatasetError(reason instanceof Error ? reason.message : String(reason));
      })
      .finally(() => { if (!cancelled) setDatasetLoading(false); });
    return () => { cancelled = true; };
  }, [fixture]);

  async function runStudy() {
    if (!dataset || !dataset.available_versions[0] || !dateFrom || !dateTo || !factorId.trim()) return;
    setLoading(true);
    setError(null);
    setResults([]);
    const base: Omit<ApiHistoricalEventStudyRequest, "horizon"> = {
      dataset_id: dataset.dataset_id,
      scope_mode: "stock",
      stock_code: stockCode,
      date_from: dateFrom,
      date_to: dateTo,
      target_date: null,
      factor_ids: [factorId.trim()],
      activation,
      direction_filter: null,
      min_rule_score: null,
      ten_god_category: null,
      ten_god_layer: null,
      ten_god_position: null,
      relation_type: null,
      relation_source_context: null,
      relation_source_pillar: null,
      relation_target_context: null,
      relation_target_pillar: null,
      relation_source_component: null,
      relation_target_component: null,
      versions: dataset.available_versions[0],
      limit: 100,
      offset: 0,
    };
    const settled = await Promise.allSettled(
      HORIZONS.map((horizon) => api.post<ApiHistoricalEventStudyV2>(
        endpoints.historicalEventStudyV2(), { ...base, horizon },
      )),
    );
    const responses = settled.flatMap((item) => item.status === "fulfilled" ? [item.value] : []);
    const failure = settled.find((item) => item.status === "rejected");
    setResults(responses);
    setError(failure?.status === "rejected" ? failure.reason instanceof Error ? failure.reason.message : String(failure.reason) : null);
    setLoading(false);
  }

  return (
    <Card testId="stock-historical-v2">
      <CardHeader title="认证历史研究 v2" dense right={<Chip tone={dataset?.certification_status === "CERTIFIED_LIMITED_SCOPE" ? "gold" : "warn"}>{dataset?.certification_status ?? (fixture ? "fixture 无真实数据" : "核验中")}</Chip>} />
      <CardBody className="space-y-2 !py-2">
        <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          使用同一 W4 数据集、版本目录及 v2 事件结果；本股票代码必须落在数据集证书范围内。默认 dataset：{DEFAULT_RESEARCH_DATASET_ID}
        </div>
        {fixture ? <div data-testid="stock-v2-fixture-note">UI fixture 不包含真实认证历史数据。</div> : null}
        {datasetLoading ? <PageLoading label="正在读取 v2 数据集证书和版本目录…" /> : null}
        {datasetError ? <PageError title="v2 历史数据集不可用" message={datasetError} onRetry={() => window.location.reload()} /> : null}
        {dataset && !fixture ? <>
          <div className="grid gap-2 md:grid-cols-[1fr_1fr_1.2fr_1.2fr_auto] md:items-end">
            <label className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>股票代码<input className="smp-input mt-1 w-full" value={stockCode} readOnly data-testid="stock-v2-code" /></label>
            <label className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>因子 ID<input className="smp-input mt-1 w-full" value={factorId} onChange={(event) => setFactorId(event.target.value)} data-testid="stock-v2-factor" /></label>
            <label className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>历史开始日期<input className="smp-input mt-1 w-full" type="date" min={dataset.certified_date_from ?? undefined} max={dataset.certified_date_to ?? undefined} value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} data-testid="stock-v2-date-from" /></label>
            <label className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>历史结束日期<input className="smp-input mt-1 w-full" type="date" min={dataset.certified_date_from ?? undefined} max={dataset.certified_date_to ?? undefined} value={dateTo} onChange={(event) => setDateTo(event.target.value)} data-testid="stock-v2-date-to" /></label>
            <label className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>激活条件<select className="smp-input mt-1 w-full" value={activation} onChange={(event) => setActivation(event.target.value as typeof activation)} data-testid="stock-v2-activation"><option value="nonzero">非零</option><option value="any">全部可用值</option><option value="positive">正值</option><option value="negative">负值</option></select></label>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
            <Chip tone="flat">证书证券：{dataset.certified_stock_code ?? "未限定"}</Chip>
            <Chip tone="flat">认证范围：{dataset.certified_date_from ?? "不可用"} ～ {dataset.certified_date_to ?? "不可用"}</Chip>
            <span>{dataset.certification_reason}</span>
            <button type="button" className="smp-btn smp-btn--primary px-3 py-1" onClick={() => void runStudy()} disabled={loading || datasetLoading || !dataset.available_versions.length} data-testid="stock-v2-run">{loading ? "读取 1/5/20 日…" : "运行 v2 历史研究"}</button>
          </div>
        </> : null}
        {error ? <div className="text-[12px]" style={{ color: "var(--color-warn)" }} data-testid="stock-v2-error">上游请求失败：{error}</div> : null}
        {loading ? <PageLoading label="读取 v2 历史事件结果…" /> : null}
        {results.map((result) => <div key={result.horizon} className="rounded border p-2" style={{ borderColor: "var(--color-border)" }} data-testid={`stock-v2-result-${result.horizon}`}>
          <div className="flex flex-wrap items-center justify-between gap-2"><b>{result.horizon} 日 · {result.date_from} ～ {result.date_to} · {result.factor_ids.join(", ")} · {result.activation}</b><ResearchStatusBadge status={result.research_status} reasons={result.research_status_reasons} compact showCode /></div>
          <div className="mt-1 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>{result.candidate_observation_count} 个因子观察 / {result.candidate_security_date_count} 个证券日期 · 命中 {result.matched_observation_count} / {result.matched_security_date_count} · 收益 {pct(result.matched.mean_return)} · 胜率 {pct(result.matched.win_rate)} · 盈亏比 {ratio(result.matched.payoff_ratio)} · 样本最大收益 {pct(result.matched.max_return)} · 样本最大亏损 {pct(result.matched.max_loss)}</div>
          <div className="mt-1 grid gap-1 md:grid-cols-2" data-testid={`stock-v2-metrics-${result.horizon}`}>
            {Object.entries(result.matched.metric_summaries).map(([name, metric]) => <details key={name} className="rounded border px-2 py-1 text-[10.5px]" style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}>
              <summary className="cursor-pointer">{metricLabel(name)} · n={metric.sample_count} · 缺失={metric.missing_count} · 均值 {pct(metric.mean)} · 最小/最大 {pct(metric.minimum)} / {pct(metric.maximum)}</summary>
              <div className="pl-3">单位：{metric.unit === "fraction" ? "收益比例" : metric.unit}。{metric.definition}</div>
            </details>)}
          </div>
          {result.research_status_reasons.map((reason) => <div key={reason} className="mt-1 text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>· {reason}</div>)}
        </div>)}
      </CardBody>
    </Card>
  );
}

function pct(value: number | null): string { return value === null ? "不可用" : `${(value * 100).toFixed(2)}%`; }
function ratio(value: number | null): string { return value === null ? "不可用" : value.toFixed(4); }
function metricLabel(name: string): string {
  return ({
    benchmark_return: "基准收益",
    excess_return: "超额收益",
    max_favorable_move: "区间最大有利变动",
    max_adverse_move: "区间最大不利变动",
    max_drawdown: "最大回撤",
  } satisfies Record<string, string>)[name] ?? name;
}
