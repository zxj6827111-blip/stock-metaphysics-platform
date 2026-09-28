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
import { DEFAULT_RESEARCH_DATASET_ID, TEN_GOD_CATEGORIES } from "@/lib/researchV2";
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
  const [relationType, setRelationType] = useState(search?.get("relation_type") ?? "");
  const [targetDate, setTargetDate] = useState(search?.get("target_date") ?? "");
  const [datasetId, setDatasetId] = useState(search?.get("dataset_id") || DEFAULT_RESEARCH_DATASET_ID);
  const [dataset, setDataset] = useState<ApiHistoricalDatasetV2 | null>(null);
  const [datasetLoading, setDatasetLoading] = useState(true);
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [scopeMode, setScopeMode] = useState<ScopeMode>(search?.get("scope_mode") === "stock" ? "stock" : "dates");
  const [stockCode, setStockCode] = useState(search?.get("stock_code") ?? "");
  const [dateFrom, setDateFrom] = useState(search?.get("date_from") ?? "");
  const [dateTo, setDateTo] = useState(search?.get("date_to") ?? "");
  const [factorId, setFactorId] = useState(search?.get("factor_id") ?? (relationType ? "" : "B_DAY_005"));
  const activationParam = search?.get("activation");
  const [activation, setActivation] = useState<Activation>(
    activationParam === "any" || activationParam === "positive" || activationParam === "negative" || activationParam === "nonzero"
      ? activationParam
      : "nonzero",
  );
  const [tenGodCategory, setTenGodCategory] = useState(search?.get("ten_god_category") ?? "");
  const [relationSourcePillar, setRelationSourcePillar] = useState(search?.get("relation_source_pillar") ?? "");
  const [relationTargetPillar, setRelationTargetPillar] = useState(search?.get("relation_target_pillar") ?? "");
  const [relationSourceComponent, setRelationSourceComponent] = useState(search?.get("relation_source_component") ?? "branch");
  const [relationTargetComponent, setRelationTargetComponent] = useState(search?.get("relation_target_component") ?? "branch");
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
      setErrors({ 1: "请提供因子、历史日期范围；个股模式还必须填写证券代码。" });
      return;
    }
    if (relationType && (!relationSourcePillar || !relationTargetPillar || !relationSourceComponent || !relationTargetComponent)) {
      setErrors({ 1: "关系条件必须完整指定来源柱、目标原局柱及两端参与组件。" });
      return;
    }
    if (tenGodCategory && !TEN_GOD_CATEGORIES.includes(tenGodCategory as (typeof TEN_GOD_CATEGORIES)[number])) {
      setErrors({ 1: "请选择受支持的十神类别。" });
      return;
    }
    const base: Omit<ApiHistoricalEventStudyRequest, "horizon"> = {
      dataset_id: dataset.dataset_id,
      scope_mode: scopeMode,
      stock_code: scopeMode === "stock" ? stockCode.trim() : null,
      date_from: dateFrom,
      date_to: dateTo,
      target_date: targetDate || null,
      factor_ids: [tenGodCategory ? "B_DAY_005" : id],
      activation,
      direction_filter: direction ? (Number(direction) as -1 | 0 | 1) : null,
      min_rule_score: null,
      ten_god_category: tenGodCategory || null,
      ten_god_layer: tenGodCategory ? "DAILY" : null,
      ten_god_position: tenGodCategory ? "day" : null,
      relation_type: relationType || null,
      relation_source_context: relationType ? relationSourcePillar as "year" | "month" | "day" | "dayun" : null,
      relation_source_pillar: relationType ? relationSourcePillar as "year" | "month" | "day" | "dayun" : null,
      relation_target_context: relationType ? "natal" : null,
      relation_target_pillar: relationType ? relationTargetPillar as "year" | "month" | "day" : null,
      relation_source_component: relationType ? relationSourceComponent as "stem" | "branch" : null,
      relation_target_component: relationType ? relationTargetComponent as "stem" | "branch" : null,
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
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>因子 ID<input className="smp-input mt-1 w-full" value={factorId} onChange={(event) => setFactorId(event.target.value)} placeholder="例如 B_DAY_005" data-testid="historical-factor-id" disabled={Boolean(tenGodCategory)} /></label>
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>十神精确类别
                <select className="smp-input mt-1 w-full" value={tenGodCategory} onChange={(event) => setTenGodCategory(event.target.value)} data-testid="historical-ten-god"><option value="">不筛选十神类别</option>{TEN_GOD_CATEGORIES.map((category) => <option key={category} value={category}>{category}（B_DAY_005 · DAILY/day）</option>)}</select>
              </label>
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>激活条件
                <select className="smp-input mt-1 w-full" value={activation} onChange={(event) => setActivation(event.target.value as Activation)} data-testid="historical-activation"><option value="any">全部可用值</option><option value="nonzero">非零</option><option value="positive">正值</option><option value="negative">负值</option></select>
              </label>
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>关系类型（精确事件）<input className="smp-input mt-1 w-full" value={relationType} onChange={(event) => setRelationType(event.target.value.trim())} placeholder="例如 六合" data-testid="historical-relation-type" /></label>
              {relationType ? <>
                <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>来源柱
                  <select className="smp-input mt-1 w-full" value={relationSourcePillar} onChange={(event) => setRelationSourcePillar(event.target.value)} data-testid="historical-relation-source-pillar"><option value="">选择来源柱</option><option value="year">流年</option><option value="month">流月</option><option value="day">流日</option><option value="dayun">大运假设</option></select>
                </label>
                <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>目标原局柱
                  <select className="smp-input mt-1 w-full" value={relationTargetPillar} onChange={(event) => setRelationTargetPillar(event.target.value)} data-testid="historical-relation-target-pillar"><option value="">选择柱位</option><option value="year">年柱</option><option value="month">月柱</option><option value="day">日柱</option></select>
                </label>
                <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>来源组件<select className="smp-input mt-1 w-full" value={relationSourceComponent} onChange={(event) => setRelationSourceComponent(event.target.value)} data-testid="historical-relation-source-component"><option value="branch">地支</option><option value="stem">天干</option></select></label>
                <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>目标组件<select className="smp-input mt-1 w-full" value={relationTargetComponent} onChange={(event) => setRelationTargetComponent(event.target.value)} data-testid="historical-relation-target-component"><option value="branch">地支</option><option value="stem">天干</option></select></label>
              </> : null}
              <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>扫描目标日期<input className="smp-input mt-1 w-full" type="date" value={targetDate} onChange={(event) => setTargetDate(event.target.value)} data-testid="historical-target-date" /></label>
              <div className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>目标日期保留扫描上下文；历史查询范围独立使用下方日期，不会把范围缩成目标日。</div>
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
              <Chip tone={dataset?.certification_status === "CERTIFIED_LIMITED_SCOPE" ? "gold" : "warn"}>认证：{dataset?.certification_status ?? "读取中"}</Chip>
              <Chip tone="flat">范围：{datasetDates[0] ?? "不可用"} ～ {datasetDates[datasetDates.length - 1] ?? "不可用"}</Chip>
              {dataset?.certified_stock_code ? <Chip tone="flat">认证证券：{dataset.certified_stock_code}</Chip> : null}
              <Chip tone="flat">数据行：{dataset?.row_count ?? "—"}</Chip>
              <span>{dataset?.certification_reason ?? "`null`、缺失原因和认证状态按 API 原样保留。"}</span>
              {dataset?.metadata.known_limitations?.length ? <span title={dataset.metadata.known_limitations.join("\n")}>已登记 {dataset.metadata.known_limitations.length} 项数据限制</span> : null}
            </div>
            {relationType ? <div className="border-t px-3 py-2 text-[11.5px]" style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }} data-testid="historical-relation-prefill">关系条件：{relationType} · 来源 {relationSourcePillar || "未指定"}/{relationSourceComponent === "branch" ? "地支" : "天干"} → 原局{relationTargetPillar || "未指定"}/{relationTargetComponent === "branch" ? "地支" : "天干"}；历史范围由独立日期字段控制。</div> : null}
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
      <div className="border-b px-3 py-2 text-[11px]" style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }} data-testid={`historical-executed-conditions-${result.horizon}`}>
        实际执行：{result.certified_stock_code ?? "未限定认证证券"} · {result.date_from} ～ {result.date_to}{result.target_date ? ` · 扫描目标日 ${result.target_date}` : ""} · {result.factor_ids.join(", ")} · activation={result.activation}
        {result.relation_type ? ` · ${result.relation_type}：${result.relation_source_context}/${result.relation_source_pillar}/${result.relation_source_component} → ${result.relation_target_context}/${result.relation_target_pillar}/${result.relation_target_component}` : ""}
        {result.ten_god_category ? ` · 十神=${result.ten_god_category}（${result.ten_god_layer}/${result.ten_god_position}）` : ""} · 条件逻辑 {result.condition_logic} · 单位 {result.observation_unit}
      </div>
      <div className="grid gap-2 p-3 sm:grid-cols-2 lg:grid-cols-5">
        <Metric label="候选观察" value={String(result.candidate_observation_count)} />
        <Metric label="命中观察" value={String(result.matched_observation_count)} />
        <Metric label="候选证券日期" value={String(result.candidate_security_date_count)} />
        <Metric label="命中证券日期" value={String(result.matched_security_date_count)} />
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
  return <div className="rounded border px-2.5 py-2" style={{ borderColor: "var(--color-border)" }}>
    <div className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>{title} · n={stats.sample_count} · 缺失={stats.missing_count}</div>
    <div className="mt-1 grid grid-cols-2 gap-1 text-[11.5px]"><span>均值 {formatPct(stats.mean_return)}</span><span>中位数 {formatPct(stats.median_return)}</span><span>胜率 {formatPct(stats.win_rate)}</span><span>盈亏比 {formatRatio(stats.payoff_ratio)}</span><span>样本最大收益 {formatPct(stats.max_return)}</span><span>样本最大亏损 {formatPct(stats.max_loss)}</span></div>
    <div className="mt-1 border-t pt-1" style={{ borderColor: "var(--color-border)" }}>
      {Object.entries(stats.metric_summaries).map(([name, metric]) => <details key={name} className="py-0.5 text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>
        <summary className="cursor-pointer">{name} · n={metric.sample_count} · 缺失={metric.missing_count} · 均值 {formatPct(metric.mean)} · 最小/最大 {formatPct(metric.minimum)} / {formatPct(metric.maximum)}</summary>
        <div className="pl-3">单位：{metric.unit === "fraction" ? "收益比例" : metric.unit}。{metric.definition}</div>
      </details>)}
    </div>
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded border px-2 py-1.5" style={{ borderColor: "var(--color-border)" }}><div className="smp-metric-label">{label}</div><div className="mt-1 smp-num text-[12px]" style={{ color: "var(--color-ink)" }}>{value}</div></div>; }
function TraceValue({ label, value }: { label: string; value: string }) { return <div className="rounded border px-2 py-1.5" style={{ borderColor: "var(--color-border)" }}><div className="smp-metric-label">{label}</div><div className="mt-1 break-all smp-num">{value}</div></div>; }
function versionLabel(versions: ApiHistoricalDatasetVersions): string { return `${versions.feature_version} · ${versions.label_version} · ${versions.factor_version} · ${versions.config_version}`; }
function formatPct(value: number | null): string { return value === null || value === undefined ? "不可用" : `${(value * 100).toFixed(2)}%`; }
function formatRatio(value: number | null): string { return value === null || value === undefined ? "不可用" : value.toFixed(4); }
function errorText(value: unknown): string { return value instanceof Error ? value.message : String(value); }

export default function HistoricalResearchPage() {
  return <Suspense fallback={<PageLoading />}><HistoricalResearchInner /></Suspense>;
}
