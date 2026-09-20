"use client";

/**
 * 时间窗口页（复刻 doc/ui-reference/10_time_window.png）。
 *
 * 两条不可妥协的规则：
 * 1. **禁止"流周"**：传统术数没有这一层。周度由**交易日**的流日结果聚合而来，
 *    页面必须显示 `aggregation_method` 与 `aggregation_version`；
 * 2. **月度不是一个综合数字**：每个月独立展示三模型观点 + 共识。
 *
 * 聚合指标同时给出 mean / median / min / max / positive_day_ratio / weighted_mean
 * —— 只给平均值会把「5 天里 3 天偏强 2 天偏弱」和「一致偏强」混为一谈。
 */

import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, ResearchStatusBadge, UnavailableBlock } from "@/components/shell/PageState";
import { IconCalendar, IconTrend } from "@/components/shell/Icons";
import { api, endpoints, type ApiTimelineMonths, type ApiTimelineWeeks } from "@/lib/api";
import { useAnalysis } from "@/lib/analysisStore";
import { engineCn } from "@/lib/dataSource";
import { isFixtureActive, timelineMonthsFixture, timelineWeeksFixture } from "@/lib/fixture";

const DIR_TONE: Record<string, string> = {
  "1": "var(--color-up)",
  "0": "var(--color-flat)",
  "-1": "var(--color-down)",
};
const DIR_CN: Record<string, string> = { "1": "偏强", "0": "中性", "-1": "偏弱" };

function TimelineInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const { analysis, loading, error, reload } = useAnalysis(code);

  const [months, setMonths] = useState<ApiTimelineMonths | null>(null);
  const [weeks, setWeeks] = useState<ApiTimelineWeeks | null>(null);
  const [twError, setTwError] = useState<string | null>(null);
  const [twLoading, setTwLoading] = useState(false);

  const loadWindows = useCallback(async (analysisId: string) => {
    if (isFixtureActive()) {
      setMonths(timelineMonthsFixture);
      setWeeks(timelineWeeksFixture);
      setTwLoading(false);
      return;
    }
    setTwLoading(true);
    setTwError(null);
    try {
      const [m, w] = await Promise.all([
        api.get<ApiTimelineMonths>(endpoints.timelineMonths(analysisId, 12)),
        api.get<ApiTimelineWeeks>(endpoints.timelineWeeks(analysisId, 12)),
      ]);
      setMonths(m);
      setWeeks(w);
    } catch (e) {
      setTwError(e instanceof Error ? e.message : String(e));
    } finally {
      setTwLoading(false);
    }
  }, []);

  useEffect(() => {
    if (analysis?.analysis_id) void loadWindows(analysis.analysis_id);
  }, [analysis?.analysis_id, loadWindows]);

  const firstWeek = weeks?.weeks?.[0];
  const firstMonth = months?.months?.[0];

  return (
    <ResearchPage
      activeNav="timeline"
      title="时间窗口"
      subtitle="识别关键月份、关键周与共振节奏，把握未来周期窗口"
      seal="时"
      code={code}
      analysis={analysis}
      loading={loading}
      error={error}
      onReload={reload}
      loadingLabel="正在按交易日构建未来 12 个月 / 12 周窗口…"
    >
      <Card testId="timeline-summary">
        <CardHeader
          icon={<IconCalendar size={15} />}
          title="未来窗口总览"
          right={
            <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              聚合口径版本 {weeks?.aggregation_version ?? "—"}
            </span>
          }
          dense
        />
        <div className="grid grid-cols-4 gap-3 text-[12.5px]">
          <Metric
            label="下一周"
            value={firstWeek ? `${firstWeek.week_start} ~ ${firstWeek.week_end}` : "—"}
            hint={firstWeek ? `${firstWeek.trading_days} 个交易日` : "等待数据"}
          />
          <Metric
            label="下一月"
            value={firstMonth?.month ?? "—"}
            hint={firstMonth ? `${firstMonth.trading_days} 个交易日` : "等待数据"}
          />
          <Metric
            label="窗口研究状态"
            value={months?.research_status ?? "—"}
            hint="历史有效性由研究流水线回答"
          />
          <Metric label="本次变体" value={months?.variant_mode ?? "—"} hint="顺行 / 逆行是假设，不是事实" />
        </div>
        <div className="mt-2">
          <ResearchStatusBadge
            status={months?.research_status ?? "NOT_RUN"}
            reasons={months?.research_status_reasons ?? []}
          />
        </div>
      </Card>

      {twError ? (
        <Card testId="timeline-error">
          <div className="py-3 text-[13px]" style={{ color: "var(--color-warn)" }}>
            时间窗口加载失败：{twError}
          </div>
        </Card>
      ) : null}

      <Card>
        <CardHeader icon={<IconCalendar size={15} />} title="未来 12 个月（逐月独立三模型观点）" dense />
        {twLoading ? (
          <div className="py-3 text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
            正在计算…
          </div>
        ) : null}
        {months?.months?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]" data-testid="month-table">
              <thead>
                <tr style={{ color: "var(--color-ink-muted)" }}>
                  <th className="text-left">月份</th>
                  <th className="text-left">交易日</th>
                  {["bazi", "ziwei", "huangli"].map((e) => (
                    <th key={e} className="text-left">
                      {engineCn(e)}
                    </th>
                  ))}
                  <th className="text-left">共识</th>
                  <th className="text-left">研究状态</th>
                </tr>
              </thead>
              <tbody>
                {months.months.map((m) => (
                  <tr
                    key={m.month}
                    style={{ borderTop: "1px solid var(--color-border)" }}
                    data-testid={`month-row-${m.month}`}
                  >
                    <td className="py-1 font-semibold">{m.month}</td>
                    <td className="smp-num">{m.trading_days}</td>
                    {[m.bazi, m.ziwei, m.huangli].map((op, i) => (
                      <td key={i} style={{ color: DIR_TONE[String(op?.direction ?? 0)] }}>
                        {op && op.availability === "ok"
                          ? `${DIR_CN[String(op.direction)]} ${op.score}`
                          : "不可用"}
                      </td>
                    ))}
                    <td>{m.consensus?.label_cn ?? "—"}</td>
                    <td style={{ color: "var(--color-ink-muted)" }}>{m.research_status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !twLoading ? (
          <UnavailableBlock what="月度窗口" reason="后端未返回月度窗口数据。" />
        ) : null}
      </Card>

      <Card>
        <CardHeader
          icon={<IconTrend size={15} />}
          title="未来 12 周（交易日流日聚合）"
          right={
            <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              聚合版本 {weeks?.aggregation_version ?? "—"}
            </span>
          }
          dense
        />
        {firstWeek ? (
          <SectionNote>
            <b>聚合口径：</b>
            {firstWeek.aggregation_method}
            <br />
            传统术数<strong>没有「流周」这一层</strong>：周是聚合结果，不是独立运限。
          </SectionNote>
        ) : null}
        {weeks?.weeks?.length ? (
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-[12px]" data-testid="week-table">
              <thead>
                <tr style={{ color: "var(--color-ink-muted)" }}>
                  <th className="text-left">#</th>
                  <th className="text-left">区间</th>
                  <th className="text-left">交易日</th>
                  <th className="text-right">均值</th>
                  <th className="text-right">中位数</th>
                  <th className="text-right">最小</th>
                  <th className="text-right">最大</th>
                  <th className="text-right">偏强日占比</th>
                  <th className="text-right">加权均值</th>
                </tr>
              </thead>
              <tbody>
                {weeks.weeks.map((w) => (
                  <tr
                    key={w.week_index}
                    style={{ borderTop: "1px solid var(--color-border)" }}
                    data-testid={`week-row-${w.week_index}`}
                  >
                    <td className="smp-num">{w.week_index}</td>
                    <td>
                      {w.week_start} ~ {w.week_end}
                    </td>
                    <td className="smp-num">{w.trading_days}</td>
                    <td className="smp-num text-right" style={{ color: DIR_TONE[dirKey(w.mean)] }}>
                      {fmt(w.mean)}
                    </td>
                    <td className="smp-num text-right">{fmt(w.median)}</td>
                    <td className="smp-num text-right" style={{ color: DIR_TONE[dirKey(w.min)] }}>
                      {fmt(w.min)}
                    </td>
                    <td className="smp-num text-right" style={{ color: DIR_TONE[dirKey(w.max)] }}>
                      {fmt(w.max)}
                    </td>
                    <td className="smp-num text-right">
                      {w.positive_day_ratio === null
                        ? "—"
                        : `${(w.positive_day_ratio * 100).toFixed(0)}%`}
                    </td>
                    <td className="smp-num text-right">{fmt(w.weighted_mean)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !twLoading ? (
          <UnavailableBlock
            what="周度窗口"
            reason="后端未返回周度窗口（可能是 as_of 之后的交易日历覆盖不足）。"
          />
        ) : null}
      </Card>

      <Card>
        <CardHeader icon={<IconTrend size={15} />} title="方法与限制" dense />
        <SectionNote>{months?.methodology ?? "（缺少方法论说明）"}</SectionNote>
        <ul className="mt-2 space-y-1 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          <li>· 所有窗口基于实际交易日（交易所日历），不退化回自然日；</li>
          <li>· 日历覆盖不足时如实降级并给出 warning，不用周末规则假装肯定；</li>
          <li>· 窗口分数是传统规则强度，不是未来收益预测；</li>
          <li>· 历史有效性状态见上方 ResearchStatus。</li>
        </ul>
        {months?.warnings?.length ? (
          <ul className="mt-2 space-y-1 text-[12px]" style={{ color: "var(--color-warn)" }}>
            {months.warnings.map((w, i) => (
              <li key={`${i}-${w.code}`}>
                · [{w.severity}] {w.code}: {w.message}
              </li>
            ))}
          </ul>
        ) : null}
      </Card>
    </ResearchPage>
  );
}

function dirKey(v: number | null | undefined): string {
  if (v === null || v === undefined) return "0";
  return v > 0.05 ? "1" : v < -0.05 ? "-1" : "0";
}

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(2);
}

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded border p-2" style={{ borderColor: "var(--color-border)" }}>
      <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
        {label}
      </div>
      <div className="mt-0.5 font-semibold">{value}</div>
      {hint ? (
        <div className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
          {hint}
        </div>
      ) : null}
    </div>
  );
}

export default function TimelinePage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <TimelineInner />
    </Suspense>
  );
}
