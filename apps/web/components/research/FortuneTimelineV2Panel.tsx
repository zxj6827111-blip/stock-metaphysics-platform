"use client";

import { useEffect, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { SectionError, SectionLoading, SectionUnavailable } from "@/components/shell/SectionState";
import { api, endpoints } from "@/lib/api";
import type { ApiFortuneTimelineV2Response, ApiSystemVersions } from "@/lib/researchV2";
import { isFixtureActive } from "@/lib/fixture";

export function FortuneTimelineV2Panel({ stockCode, startDate }: { stockCode: string; startDate: string }) {
  const fixture = isFixtureActive();
  const requestStartDate = startDate.slice(0, 10);
  const [data, setData] = useState<ApiFortuneTimelineV2Response | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (fixture || !stockCode || !requestStartDate) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const versions = await api.get<ApiSystemVersions>(endpoints.systemVersions());
        const response = await api.post<ApiFortuneTimelineV2Response>(endpoints.fortuneTimelineV2(), {
          stock_code: stockCode,
          start_date: requestStartDate,
          end_date: addCalendarDays(requestStartDate, 20),
          date_mode: "ALL_CALENDAR_DAYS",
          anchor_mode: "EXACT_LOCAL_TIME",
          evaluation_time: "12:00:00",
          timezone: "Asia/Shanghai",
          market_session_version: "a-share-session-v1",
          config_version: versions.config_version,
          include_relation_events: true,
          include_month_segments: true,
          include_ten_god_index: true,
        });
        if (!cancelled) setData(response);
      } catch (value) {
        if (!cancelled) setError(value instanceof Error ? value.message : String(value));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [fixture, stockCode, requestStartDate, nonce]);

  const timeline = data?.timeline;
  const birth = timeline?.birth_context;
  const assumptions = dedupeAssumptions([...(birth?.assumptions ?? []), ...(timeline?.assumptions ?? [])]);

  return (
    <Card className="mt-3" testId="fortune-timeline-v2">
      <CardHeader title="Fortune 证券时间轴 · v2" dense right={<Chip tone={timeline?.availability === "available" ? "gold" : "warn"}>{timeline?.availability ?? (fixture ? "fixture 未提供" : loading ? "加载中" : "不可用")}</Chip>} />
      <CardBody>
        <div className="mb-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          独立展示服务端按行情解析的证券出生档案；时间精度、假设和来源均来自 Fortune v2 响应。
        </div>
        {fixture ? <SectionUnavailable what="Fortune v2" reason="UI fixture 没有冻结的 Fortune v2 响应；移除 ?fixture=ui-reference 后读取真实接口。" testId="fortune-fixture-unavailable" /> : null}
        {loading ? <SectionLoading label="正在由服务端解析首笔行情证据并构建 Fortune 时间轴…" rows={3} /> : null}
        {error ? <SectionError what="Fortune v2 时间轴" message={error} onRetry={() => setNonce((value) => value + 1)} testId="fortune-v2-error" /> : null}
        {birth ? (
          <>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4" data-testid="fortune-birth-profile">
              <ProfileValue label="出生基准" value={birth.birth_basis} detail={`${birth.symbol} · ${birth.exchange}`} />
              <ProfileValue label="时间精度" value={birth.birth_time_precision} detail={birth.birth_datetime_status} />
              <ProfileValue label="计算时刻" value={birth.birth_datetime ?? "不可用"} detail={`首笔证据日期：${birth.first_trade_date ?? "不可用"}`} />
              <ProfileValue label="证据来源" value={birth.source.source} detail={`${birth.source_version} · ${birth.first_trade_resolution}`} />
            </div>
            {assumptions.length ? <div className="mt-2 rounded border p-2 text-[11.5px]" style={{ borderColor: "var(--color-border)" }} data-testid="fortune-assumptions"><div className="font-semibold" style={{ color: "var(--color-ink)" }}>显式假设</div>{assumptions.map((assumption) => <div className="mt-1" key={`${assumption.key}-${assumption.value}`}>· {assumption.key}：{assumption.value}。{assumption.reason}{assumption.impact ? ` 影响：${assumption.impact}` : ""}</div>)}</div> : <div className="mt-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }} data-testid="fortune-assumptions-empty">本响应没有记录额外假设。</div>}
            {birth.data_quality?.notes.length ? <div className="mt-2 text-[11px]" style={{ color: "var(--color-warn)" }} data-testid="fortune-birth-quality">数据质量 {birth.data_quality.grade}：{birth.data_quality.notes.join("；")}</div> : null}
            <div className="mt-2 overflow-x-auto">
              {timeline?.points.length ? <table className="smp-table min-w-[680px]" data-testid="fortune-v2-points"><thead><tr><th>日期</th><th>年柱</th><th>月柱</th><th>日柱</th><th>交易日证据</th><th>可用性</th></tr></thead><tbody>{timeline.points.map((point) => <tr key={point.date}><td>{point.date} · {point.evaluation_datetime.slice(11, 16)}</td><td>{pillar(point.annual_pillar)}</td><td>{pillar(point.monthly_pillar)}</td><td>{pillar(point.daily_pillar)}</td><td>{point.trading_day === null ? `未知（${point.trading_calendar_source}）` : point.trading_day ? `是（${point.trading_calendar_source}）` : `否（${point.trading_calendar_source}）`}</td><td>{point.availability}</td></tr>)}</tbody></table> : <SectionUnavailable what="时间轴点位" reason="服务端未返回本请求范围的可用点位。" />}
            </div>
            {timeline?.warnings.length ? <div className="mt-2 text-[11px]" style={{ color: "var(--color-warn)" }} data-testid="fortune-v2-warnings">{timeline.warnings.map((warning) => <div key={`${warning.code}-${warning.message}`}>· {warning.code}：{warning.message}</div>)}</div> : null}
            <details className="mt-2 text-[11px]"><summary className="cursor-pointer" style={{ color: "var(--color-ink-muted)" }}>版本与来源追溯</summary><pre className="mt-1 max-h-[180px] overflow-auto rounded p-2" style={{ background: "rgba(255,255,255,0.03)" }}>{JSON.stringify({ resolved_versions: data?.resolved_versions, rule_versions: timeline?.rule_versions, provenance: timeline?.provenance, rule_version: timeline?.rule_version }, null, 2)}</pre></details>
          </>
        ) : !loading && !error && !fixture ? <SectionUnavailable what="Fortune 出生档案" reason="后端没有返回可展示的出生档案；页面不会根据股票代码自行推定日期或精度。" /> : null}
      </CardBody>
    </Card>
  );
}

function ProfileValue({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="rounded border px-2.5 py-2" style={{ borderColor: "var(--color-border)" }}><div className="smp-metric-label">{label}</div><div className="mt-1 break-all text-[12px]" style={{ color: "var(--color-ink)" }}>{value}</div><div className="mt-1 break-all text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>{detail}</div></div>;
}

function pillar(value: { stem: string; branch: string } | null | undefined): string {
  return value ? `${value.stem}${value.branch}` : "不可用";
}

function addCalendarDays(date: string, count: number): string {
  const [year, month, day] = date.split("-").map(Number);
  if (!year || !month || !day) throw new Error("Fortune 时间轴起始日期无效");
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
