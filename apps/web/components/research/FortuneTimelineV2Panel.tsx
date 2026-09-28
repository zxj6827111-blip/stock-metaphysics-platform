"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { SectionError, SectionLoading, SectionUnavailable } from "@/components/shell/SectionState";
import { api, endpoints, type ApiRelationCatalog } from "@/lib/api";
import type { ApiFortuneTimelineV2Response, ApiSystemVersions } from "@/lib/researchV2";
import { TEN_GOD_CATEGORIES, type ApiFortuneRelationFilter } from "@/lib/researchV2";
import { isFixtureActive } from "@/lib/fixture";

type FortuneDateMode = "ALL_CALENDAR_DAYS" | "TRADING_DAYS_ONLY";
type RelationComponent = NonNullable<ApiFortuneRelationFilter["source_component"]>;

interface TimelineQuery {
  startDate: string;
  endDate: string;
  dateMode: FortuneDateMode;
  tenGodCategory: string;
  relationType: string;
  relationSourcePillar: "year" | "month" | "day";
  relationTargetPillar: "year" | "month" | "day";
  relationSourceComponent: RelationComponent;
  relationTargetComponent: RelationComponent;
}

const DEFAULT_QUERY: Omit<TimelineQuery, "startDate" | "endDate"> = {
  dateMode: "ALL_CALENDAR_DAYS",
  tenGodCategory: "",
  relationType: "",
  relationSourcePillar: "day",
  relationTargetPillar: "year",
  relationSourceComponent: "branch",
  relationTargetComponent: "branch",
};

export function FortuneTimelineV2Panel({ stockCode, startDate }: { stockCode: string; startDate: string }) {
  const fixture = isFixtureActive();
  const requestStartDate = startDate.slice(0, 10);
  const [data, setData] = useState<ApiFortuneTimelineV2Response | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rangeStart, setRangeStart] = useState(requestStartDate);
  const [rangeEnd, setRangeEnd] = useState(() => addCalendarDays(requestStartDate, 20));
  const [dateMode, setDateMode] = useState<FortuneDateMode>(DEFAULT_QUERY.dateMode);
  const [tenGodCategory, setTenGodCategory] = useState("");
  const [relationType, setRelationType] = useState("");
  const [relationSourcePillar, setRelationSourcePillar] = useState<TimelineQuery["relationSourcePillar"]>(DEFAULT_QUERY.relationSourcePillar);
  const [relationTargetPillar, setRelationTargetPillar] = useState<TimelineQuery["relationTargetPillar"]>(DEFAULT_QUERY.relationTargetPillar);
  const [relationSourceComponent, setRelationSourceComponent] = useState<RelationComponent>(DEFAULT_QUERY.relationSourceComponent);
  const [relationTargetComponent, setRelationTargetComponent] = useState<RelationComponent>(DEFAULT_QUERY.relationTargetComponent);
  const [catalog, setCatalog] = useState<ApiRelationCatalog | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [catalogNonce, setCatalogNonce] = useState(0);
  const requestSequence = useRef(0);

  const queryTimeline = useCallback(async (query: TimelineQuery) => {
    const invalidRange = validateDateRange(query.startDate, query.endDate);
    if (invalidRange) {
      setError(invalidRange);
      setData(null);
      return;
    }

    const sequence = ++requestSequence.current;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const versions = await api.get<ApiSystemVersions>(endpoints.systemVersions());
      const tenGodFilters = query.tenGodCategory
        ? [{ layer: "day", ten_god: query.tenGodCategory }]
        : [];
      const relationFilters: ApiFortuneRelationFilter[] = query.relationType
        ? [{
            relation_type: query.relationType,
            source_context: query.relationSourcePillar,
            source_pillar: query.relationSourcePillar,
            target_context: "natal",
            target_pillar: query.relationTargetPillar,
            source_component: query.relationSourceComponent,
            target_component: query.relationTargetComponent,
          }]
        : [];
      const response = await api.post<ApiFortuneTimelineV2Response>(endpoints.fortuneTimelineV2(), {
        stock_code: stockCode,
        start_date: query.startDate,
        end_date: query.endDate,
        date_mode: query.dateMode,
        anchor_mode: "EXACT_LOCAL_TIME",
        evaluation_time: "12:00:00",
        timezone: "Asia/Shanghai",
        market_session_version: "a-share-session-v1",
        config_version: versions.config_version,
        ten_god_filters: tenGodFilters,
        relation_filters: relationFilters,
        include_relation_events: true,
        include_month_segments: true,
        include_ten_god_index: true,
      });
      if (sequence === requestSequence.current) setData(response);
    } catch (value) {
      if (sequence === requestSequence.current) {
        setError(value instanceof Error ? value.message : String(value));
      }
    } finally {
      if (sequence === requestSequence.current) setLoading(false);
    }
  }, [stockCode]);

  useEffect(() => {
    if (fixture) return;
    let cancelled = false;
    void api.get<ApiRelationCatalog>(endpoints.relationCatalog()).then((response) => {
      if (!cancelled) {
        setCatalog(response);
        setCatalogError(null);
      }
    }).catch((value) => {
      if (!cancelled) setCatalogError(value instanceof Error ? value.message : String(value));
    });
    return () => { cancelled = true; };
  }, [fixture, catalogNonce]);

  useEffect(() => {
    if (fixture || !stockCode || !requestStartDate) return;
    const initialQuery: TimelineQuery = {
      ...DEFAULT_QUERY,
      startDate: requestStartDate,
      endDate: addCalendarDays(requestStartDate, 20),
    };
    setRangeStart(initialQuery.startDate);
    setRangeEnd(initialQuery.endDate);
    setDateMode(initialQuery.dateMode);
    setTenGodCategory(initialQuery.tenGodCategory);
    setRelationType(initialQuery.relationType);
    setRelationSourcePillar(initialQuery.relationSourcePillar);
    setRelationTargetPillar(initialQuery.relationTargetPillar);
    setRelationSourceComponent(initialQuery.relationSourceComponent);
    setRelationTargetComponent(initialQuery.relationTargetComponent);
    void queryTimeline(initialQuery);
  }, [fixture, queryTimeline, requestStartDate, stockCode]);

  const relationTypes = catalog?.groups.flatMap((group) => group.items) ?? [];
  const timeline = data?.timeline;
  const birth = timeline?.birth_context;
  const assumptions = dedupeAssumptions([...(birth?.assumptions ?? []), ...(timeline?.assumptions ?? [])]);
  const activeQuery: TimelineQuery = {
    startDate: rangeStart,
    endDate: rangeEnd,
    dateMode,
    tenGodCategory,
    relationType,
    relationSourcePillar,
    relationTargetPillar,
    relationSourceComponent,
    relationTargetComponent,
  };
  const rangeError = validateDateRange(rangeStart, rangeEnd);

  return (
    <Card className="mt-3" testId="fortune-timeline-v2">
      <CardHeader title="Fortune 证券时间轴 · v2" dense right={<Chip tone={timeline?.availability === "available" ? "gold" : "warn"}>{timeline?.availability ?? (fixture ? "fixture 未提供" : loading ? "加载中" : "不可用")}</Chip>} />
      <CardBody>
        <div className="mb-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          排盘与结构筛选由服务端执行；区间最多 3,660 个自然日，多项十神/关系条件按 AND 组合，不代表收益预测或交易信号。
        </div>
        {fixture ? <SectionUnavailable what="Fortune v2" reason="UI fixture 没有冻结的 Fortune v2 响应；移除 ?fixture=ui-reference 后读取真实接口，页面不会自行计算术数。" testId="fortune-fixture-unavailable" /> : null}
        <div className="grid gap-2 rounded border p-3 sm:grid-cols-2 xl:grid-cols-4" style={{ borderColor: "var(--color-border)" }} data-testid="fortune-timeline-controls">
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>开始日期
            <input className="smp-input mt-1 w-full" type="date" value={rangeStart} onChange={(event) => setRangeStart(event.target.value)} data-testid="fortune-range-start" />
          </label>
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>结束日期
            <input className="smp-input mt-1 w-full" type="date" value={rangeEnd} onChange={(event) => setRangeEnd(event.target.value)} data-testid="fortune-range-end" />
          </label>
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>日期口径
            <select className="smp-input mt-1 w-full" value={dateMode} onChange={(event) => setDateMode(event.target.value as FortuneDateMode)} data-testid="fortune-date-mode">
              <option value="ALL_CALENDAR_DAYS">全部自然日</option>
              <option value="TRADING_DAYS_ONLY">仅交易日（需交易日证据）</option>
            </select>
          </label>
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>流日十神类别
            <select className="smp-input mt-1 w-full" value={tenGodCategory} onChange={(event) => setTenGodCategory(event.target.value)} data-testid="fortune-ten-god-filter">
              <option value="">不筛选</option>
              {TEN_GOD_CATEGORIES.map((category) => <option key={category} value={category}>{category}</option>)}
            </select>
          </label>
          <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>关系类型（服务端目录）
            <select className="smp-input mt-1 w-full" value={relationType} onChange={(event) => setRelationType(event.target.value)} disabled={!catalog || Boolean(catalogError)} data-testid="fortune-relation-filter">
              <option value="">不筛选</option>
              {relationTypes.map((relation) => <option key={relation} value={relation}>{relation}</option>)}
            </select>
          </label>
          {relationType ? <>
            <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>关系来源柱
              <select className="smp-input mt-1 w-full" value={relationSourcePillar} onChange={(event) => setRelationSourcePillar(event.target.value as TimelineQuery["relationSourcePillar"])} data-testid="fortune-relation-source-pillar">
                <option value="year">流年</option><option value="month">流月</option><option value="day">流日</option>
              </select>
            </label>
            <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>关系目标原局柱
              <select className="smp-input mt-1 w-full" value={relationTargetPillar} onChange={(event) => setRelationTargetPillar(event.target.value as TimelineQuery["relationTargetPillar"])} data-testid="fortune-relation-target-pillar">
                <option value="year">年柱</option><option value="month">月柱</option><option value="day">日柱</option>
              </select>
            </label>
            <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>来源组件
              <select className="smp-input mt-1 w-full" value={relationSourceComponent} onChange={(event) => setRelationSourceComponent(event.target.value as RelationComponent)} data-testid="fortune-relation-source-component">
                <option value="branch">地支</option><option value="stem">天干</option><option value="pillar">整柱</option>
              </select>
            </label>
            <label className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>目标组件
              <select className="smp-input mt-1 w-full" value={relationTargetComponent} onChange={(event) => setRelationTargetComponent(event.target.value as RelationComponent)} data-testid="fortune-relation-target-component">
                <option value="branch">地支</option><option value="stem">天干</option><option value="pillar">整柱</option>
              </select>
            </label>
          </> : null}
          <div className="text-[11px] sm:col-span-2 xl:col-span-3" style={{ color: "var(--color-ink-muted)" }}>
            {catalogError ? <span data-testid="fortune-relation-catalog-error">关系目录不可用：{catalogError}</span> : <span>关系选项来自服务端目录；目标日期上下文与历史研究数据集范围相互独立。</span>}
            {rangeError ? <span className="ml-2" role="alert" data-testid="fortune-range-error">{rangeError}</span> : null}
          </div>
          <div className="flex items-end gap-2">
            <button type="button" className="smp-btn smp-btn--primary px-4" onClick={() => void queryTimeline(activeQuery)} disabled={fixture || loading || Boolean(rangeError) || !stockCode} data-testid="fortune-run">{loading ? "查询中…" : "运行 Fortune v2"}</button>
            {catalogError ? <button type="button" className="smp-btn px-3" onClick={() => setCatalogNonce((value) => value + 1)} data-testid="fortune-relation-catalog-retry">重试关系目录</button> : null}
          </div>
        </div>
        {loading ? <SectionLoading label="正在由服务端解析首日行情证据并构建 Fortune 时间轴…" rows={3} /> : null}
        {error ? <SectionError what="Fortune v2 时间轴" message={error} onRetry={() => void queryTimeline(activeQuery)} testId="fortune-v2-error" /> : null}
        {timeline ? <div className="mt-2 rounded border px-3 py-2 text-[11.5px]" style={{ borderColor: "var(--color-border)" }} data-testid="fortune-executed-query">
          <div>实际日期范围：{timeline.start_date} ～ {timeline.end_date} · {timeline.date_mode === "ALL_CALENDAR_DAYS" ? "全部自然日" : "仅交易日"}</div>
          <div className="mt-1">实际条件：{describeTimelineConditions(timeline.ten_god_filters, timeline.relation_filters)}</div>
          {timeline.ten_god_filters.length + timeline.relation_filters.length > 1 ? <div className="mt-1">组合逻辑：AND</div> : null}
        </div> : null}
        {birth ? (
          <>
            <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4" data-testid="fortune-birth-profile">
              <ProfileValue label="出生基准" value={birth.birth_basis} detail={`${birth.symbol} · ${birth.exchange}`} />
              <ProfileValue label="时间精度" value={birth.birth_time_precision} detail={birth.birth_datetime_status} />
              <ProfileValue label="计算时刻" value={birth.birth_datetime ?? "不可用"} detail={`首笔证据日期：${birth.first_trade_date ?? "不可用"}`} />
              <ProfileValue label="证据来源" value={birth.source.source} detail={`${birth.source_version} · ${birth.first_trade_resolution}`} />
            </div>
            {assumptions.length ? <div className="mt-2 rounded border p-2 text-[11.5px]" style={{ borderColor: "var(--color-border)" }} data-testid="fortune-assumptions"><div className="font-semibold" style={{ color: "var(--color-ink)" }}>显式假设</div>{assumptions.map((assumption) => <div className="mt-1" key={`${assumption.key}-${assumption.value}`}>· {assumption.key}：{assumption.value}。{assumption.reason}{assumption.impact ? ` 影响：${assumption.impact}` : ""}</div>)}</div> : <div className="mt-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }} data-testid="fortune-assumptions-empty">本响应没有记录额外假设。</div>}
            {birth.data_quality?.notes.length ? <div className="mt-2 text-[11px]" style={{ color: "var(--color-warn)" }} data-testid="fortune-birth-quality">数据质量 {birth.data_quality.grade}：{birth.data_quality.notes.join("；")}</div> : null}
            <div className="mt-2 overflow-x-auto">
              {timeline.points.length ? <table className="smp-table min-w-[680px]" data-testid="fortune-v2-points"><thead><tr><th>日期</th><th>年柱</th><th>月柱</th><th>日柱</th><th>交易日证据</th><th>可用性</th></tr></thead><tbody>{timeline.points.map((point) => <tr key={point.date}><td>{point.date} · {point.evaluation_datetime.slice(11, 16)}</td><td>{pillar(point.annual_pillar)}</td><td>{pillar(point.monthly_pillar)}</td><td>{pillar(point.daily_pillar)}</td><td>{point.trading_day === null ? `未知（${point.trading_calendar_source}）` : point.trading_day ? `是（${point.trading_calendar_source}）` : `否（${point.trading_calendar_source}）`}</td><td>{point.availability}</td></tr>)}</tbody></table> : <SectionUnavailable what="时间轴点位" reason="服务端未返回本请求范围的可用点位；保留出生档案和上游不可用原因，不补造排盘结果。" />}
            </div>
            {timeline.warnings.length ? <div className="mt-2 text-[11px]" style={{ color: "var(--color-warn)" }} data-testid="fortune-v2-warnings">{timeline.warnings.map((warning) => <div key={`${warning.code}-${warning.message}`}>· {warning.code}：{warning.message}</div>)}</div> : null}
            <details className="mt-2 text-[11px]"><summary className="cursor-pointer" style={{ color: "var(--color-ink-muted)" }}>版本与来源追溯</summary><pre className="mt-1 max-h-[180px] overflow-auto rounded p-2" style={{ background: "rgba(255,255,255,0.03)" }}>{JSON.stringify({ resolved_versions: data?.resolved_versions, rule_versions: timeline.rule_versions, provenance: timeline.provenance, rule_version: timeline.rule_version }, null, 2)}</pre></details>
          </>
        ) : !loading && !error && !fixture ? <SectionUnavailable what="Fortune 出生档案" reason="后端没有返回可展示的出生档案；页面不会根据股票代码自行推定日期或精度。" /> : null}
      </CardBody>
    </Card>
  );
}

function describeTimelineConditions(
  tenGodFilters: ApiFortuneTimelineV2Response["timeline"]["ten_god_filters"],
  relationFilters: ApiFortuneTimelineV2Response["timeline"]["relation_filters"],
): string {
  const conditions = [
    ...tenGodFilters.map((filter) => `十神 ${contextLabel(filter.layer)}/${filter.ten_god}${filter.position ? `/${pillarLabel(filter.position)}` : ""}`),
    ...relationFilters.map((filter) => `关系 ${filter.relation_type}：${contextLabel(filter.source_context)}/${pillarLabel(filter.source_pillar)}/${componentLabel(filter.source_component)} → ${contextLabel(filter.target_context)}/${pillarLabel(filter.target_pillar)}/${componentLabel(filter.target_component)}`),
  ];
  return conditions.length ? conditions.join("；") : "无结构筛选";
}

function validateDateRange(startDate: string, endDate: string): string | null {
  if (!startDate || !endDate) return "请选择开始日期和结束日期。";
  const start = Date.parse(`${startDate}T00:00:00Z`);
  const end = Date.parse(`${endDate}T00:00:00Z`);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "日期格式无效。";
  if (end < start) return "结束日期不得早于开始日期。";
  if ((end - start) / 86_400_000 + 1 > 3660) return "单次 Fortune 时间轴最多支持 3,660 个自然日。";
  return null;
}

function contextLabel(value: string): string {
  return ({ natal: "原局", year: "流年", month: "流月", day: "流日", dayun: "大运" } as Record<string, string>)[value] ?? value;
}

function pillarLabel(value: string): string {
  return ({ year: "年柱", month: "月柱", day: "日柱", hour: "时柱", dayun: "大运" } as Record<string, string>)[value] ?? value;
}

function componentLabel(value: string | null | undefined): string {
  if (!value) return "未指定组件";
  return ({ branch: "地支", stem: "天干", pillar: "整柱" } as Record<string, string>)[value] ?? value;
}

function ProfileValue({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="rounded border px-2.5 py-2" style={{ borderColor: "var(--color-border)" }}><div className="smp-metric-label">{label}</div><div className="mt-1 break-all text-[12px]" style={{ color: "var(--color-ink)" }}>{value}</div><div className="mt-1 break-all text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>{detail}</div></div>;
}

function pillar(value: { stem: string; branch: string } | null | undefined): string {
  return value ? `${value.stem}${value.branch}` : "不可用";
}

function addCalendarDays(date: string, count: number): string {
  const [year, month, day] = date.split("-").map(Number);
  if (!year || !month || !day) return date;
  return new Date(Date.UTC(year, month - 1, day + count)).toISOString().slice(0, 10);
}

function dedupeAssumptions<T extends { key: string; value: string }>(items: T[]): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.key}:${item.value}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
