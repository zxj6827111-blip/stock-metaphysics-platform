"use client";

/**
 * 时间窗口页（复刻 doc/ui-reference/10_time_window.png 的信息结构）。
 *
 * 三条不可妥协的规则
 * -----------------
 * 1. **禁止"流周"**：传统术数没有这一层。周度由**交易日**的流日结果聚合而来，
 *    页面必须显示 `aggregation_method` 与 `aggregation_version`；
 * 2. **月度不是一个综合数字**：每个月独立展示三模型观点 + 共识；
 * 3. **按实际返回粒度绘图**：月度数据画阶梯线，不插值成"每日预测曲线"；
 *    逐日视图用逐日端点（{@link ApiTimelineDays}）的真实流日结果，
 *    缺失模型断开而不是填 0。
 *
 * 与参考图的差异（如实说明，不补造）
 * --------------------------------
 * 参考图右栏有「关键触发因子（高权重/中权重）」与"仓位建议"。本页**不生成**这类内容：
 * 后端没有为窗口提供因子归因数据，伪造权重会让人以为存在逐窗口的因子贡献分解。
 * 右栏改为展示**该窗口的原始结果、依据、可用性、假设、版本与风险**。
 */

import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { TimelineStepChart } from "@/components/charts/Charts";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, ResearchStatusBadge, researchStatusLabel } from "@/components/shell/PageState";
import { SectionEmpty, SectionError, SectionLoading } from "@/components/shell/SectionState";
import { RawField, SourceMethod } from "@/components/shell/SourceMethod";
import { IconCalendar, IconTrend } from "@/components/shell/Icons";
import {
  api,
  endpoints,
  type ApiMonthWindow,
  type ApiOpinion,
  type ApiTimelineDays,
  type ApiTimelineMonths,
  type ApiTimelineWeeks,
  type ApiWeekWindow,
} from "@/lib/api";
import { useAnalysis } from "@/lib/analysisStore";
import { useAsOfParam } from "@/lib/useAsOfParam";
import { engineCn, variantModeLabel, windowPositionCn } from "@/lib/dataSource";
import { stripMdEmphasis } from "@/lib/text";
import {
  isFixtureActive,
  timelineDaysFixture,
  timelineMonthsFixture,
  timelineWeeksFixture,
} from "@/lib/fixture";

const DIR_CN: Record<string, string> = { "1": "偏强", "0": "中性", "-1": "偏弱" };
const ENGINE_COLOR: Record<string, string> = {
  bazi: "#6b8fd4",
  ziwei: "#b07cd6",
  huangli: "#d9b45f",
  combined: "#4fd39b",
};
/** 综合共识的中文语义（后端已给 label_cn；这里只做「不同引擎缺失」的兜底文案）。 */
function consensusLabelCn(consensus: { label_cn?: string } | null | undefined): string {
  return consensus?.label_cn ?? "—";
}

function TimelineInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  // 基准日可由 URL 指定（研究复核 / 验收需要确定的时点）
  const asOf = useAsOfParam();
  const { analysis, loading, error, reload } = useAnalysis(code, "forward", asOf);

  const [months, setMonths] = useState<ApiTimelineMonths | null>(null);
  const [weeks, setWeeks] = useState<ApiTimelineWeeks | null>(null);
  const [days, setDays] = useState<ApiTimelineDays | null>(null);

  // 每个数据源各自的三态：一块慢/失败不吞掉其它块
  const [winLoading, setWinLoading] = useState(false);
  const [winError, setWinError] = useState<string | null>(null);
  const [dayLoading, setDayLoading] = useState(false);
  const [dayError, setDayError] = useState<string | null>(null);
  const [winNonce, setWinNonce] = useState(0);
  const [dayNonce, setDayNonce] = useState(0);

  const [granularity, setGranularity] = useState<"days" | "months">("days");
  const [selected, setSelected] = useState<
    { kind: "month" | "week" | "day"; key: string } | null
  >(null);

  const fixture = isFixtureActive() && code === "600519";

  const loadWindows = useCallback(
    async (analysisId: string) => {
      if (fixture) {
        setMonths(timelineMonthsFixture);
        setWeeks(timelineWeeksFixture);
        setWinLoading(false);
        return;
      }
      setWinLoading(true);
      setWinError(null);
      try {
        const [m, w] = await Promise.all([
          api.get<ApiTimelineMonths>(endpoints.timelineMonths(analysisId, 12)),
          api.get<ApiTimelineWeeks>(endpoints.timelineWeeks(analysisId, 12)),
        ]);
        setMonths(m);
        setWeeks(w);
      } catch (e) {
        setWinError(e instanceof Error ? e.message : String(e));
      } finally {
        setWinLoading(false);
      }
    },
    [fixture],
  );

  const loadDays = useCallback(
    async (analysisId: string) => {
      if (fixture) {
        setDays(timelineDaysFixture);
        setDayLoading(false);
        return;
      }
      setDayLoading(true);
      setDayError(null);
      try {
        setDays(await api.get<ApiTimelineDays>(endpoints.timelineDays(analysisId, 20)));
      } catch (e) {
        setDayError(e instanceof Error ? e.message : String(e));
      } finally {
        setDayLoading(false);
      }
    },
    [fixture],
  );

  useEffect(() => {
    if (analysis?.analysis_id) void loadWindows(analysis.analysis_id);
  }, [analysis?.analysis_id, loadWindows, winNonce]);

  useEffect(() => {
    if (analysis?.analysis_id) void loadDays(analysis.analysis_id);
  }, [analysis?.analysis_id, loadDays, dayNonce]);

  const monthList = months?.months ?? [];
  const weekList = weeks?.weeks ?? [];
  const dayList = days?.days ?? [];
  const asOfDate = months?.as_of ?? weeks?.as_of ?? days?.as_of ?? analysis?.as_of ?? "";

  const monthTitle = winLoading
    ? "月度窗口（加载中…）"
    : monthList.length
      ? `共 ${monthList.length} 个月（${monthList[0].month} ~ ${monthList[monthList.length - 1].month}）`
      : "月度窗口";
  const weekTitle = winLoading
    ? "周度窗口（加载中…）"
    : weekList.length
      ? `共 ${weekList.length} 周（${weekList[0].week_start} ~ ${weekList[weekList.length - 1].week_end}）`
      : "周度窗口";

  // 主视图：按当前粒度装配真实序列
  const chart = useMemo(() => {
    if (granularity === "days") {
      const labels = dayList.map((d) => d.trade_date.slice(5));
      return {
        labels,
        series: [
          { name: "八字", color: ENGINE_COLOR.bazi, values: dayList.map((d) => d.bazi_score) },
          { name: "紫微", color: ENGINE_COLOR.ziwei, values: dayList.map((d) => d.ziwei_score) },
          { name: "黄历", color: ENGINE_COLOR.huangli, values: dayList.map((d) => d.huangli_score) },
        ],
        yLabel: "流日规则强度（0–100）",
      };
    }
    const labels = monthList.map((m) => m.month.slice(2));
    return {
      labels,
      series: [
        {
          name: "八字",
          color: ENGINE_COLOR.bazi,
          values: monthList.map((m) => opinionScore(m.bazi)),
        },
        {
          name: "紫微",
          color: ENGINE_COLOR.ziwei,
          values: monthList.map((m) => opinionScore(m.ziwei)),
        },
        {
          name: "黄历",
          color: ENGINE_COLOR.huangli,
          values: monthList.map((m) => opinionScore(m.huangli)),
        },
        {
          name: "共识均分",
          color: ENGINE_COLOR.combined,
          values: monthList.map((m) => m.consensus?.mean_score ?? null),
        },
      ],
      yLabel: "月度规则强度（0–100，阶梯）",
    };
  }, [granularity, dayList, monthList]);

  return (
    <ResearchPage
      activeNav="timeline"
      title="时间窗口"
      subtitle="识别关键月份、关键周与共振节奏，把握未来周期窗口"
      seal="时"
      couplet={["观天时", "察地利", "知而为", "行合律"]}
      motto={["周期有时", "万物有序"]}
      code={code}
      analysis={analysis}
      loading={loading}
      error={error}
      onReload={reload}
      loadingLabel="正在按交易日构建月度 / 周度 / 逐日窗口…"
    >
      {/* ============ ① 窗口摘要 ============ */}
      <Card testId="timeline-summary">
        <CardHeader
          icon={<IconCalendar size={15} />}
          title="未来窗口摘要"
          right={
            <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              聚合口径版本 {months?.aggregation_version ?? "—"} · 逐日口径版本{" "}
              {days?.daily_version ?? "—"}
            </span>
          }
          dense
        />
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
          <SummaryMetric
            label="月度覆盖"
            value={
              monthList.length
                ? `${monthList[0].month} ~ ${monthList[monthList.length - 1].month}`
                : "—"
            }
            hint={
              monthList.length
                ? `共 ${monthList.length} 个月（自 ${asOfDate.slice(0, 10)} 起）`
                : winLoading
                  ? "加载中…"
                  : "后端未返回"
            }
          />
          <SummaryMetric
            label="周度覆盖"
            value={
              weekList.length
                ? `${weekList[0].week_start} ~ ${weekList[weekList.length - 1].week_end}`
                : "—"
            }
            hint={
              weekList.length
                ? `共 ${weekList.length} 周（每 ${TRADING_DAYS_PER_WEEK} 个交易日）`
                : winLoading
                  ? "加载中…"
                  : "后端未返回"
            }
          />
          <SummaryMetric
            label="逐日覆盖"
            value={
              dayList.length
                ? `${dayList[0].trade_date} ~ ${dayList[dayList.length - 1].trade_date}`
                : "—"
            }
            hint={
              dayLoading
                ? "加载中…（逐日需按交易日逐日求值）"
                : dayList.length
                  ? `共 ${dayList.length} 个交易日 · 可用引擎：${
                      days?.available_engines.map((e) => engineCn(e)).join("/") || "无"
                    }`
                  : "后端未返回"
            }
          />
          <SummaryMetric
            label="最近窗口方向"
            value={
              dayList.length
                ? DIR_CN[String(dayList[0].combined_direction)] ?? "—"
                : monthList.length
                  ? consensusLabelCn(monthList[0].consensus)
                  : "—"
            }
            hint="规则强度方向，不是涨跌概率"
          />
        </div>

        {/* 三模型方向：逐个引擎给出，缺失显式标注 */}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px]">
          <span style={{ color: "var(--color-ink-muted)" }}>三模型方向（最近窗口）：</span>
          {(["bazi", "ziwei", "huangli"] as const).map((key) => {
            const op = latestOpinion(key, dayList, monthList);
            return (
              <span key={key} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ background: ENGINE_COLOR[key] }}
                />
                <span style={{ color: "var(--color-ink-sub)" }}>{engineCn(key)}</span>
                <span
                  className="smp-num"
                  style={{
                    color:
                      op === null
                        ? "var(--color-ink-faint)"
                        : op.direction > 0
                          ? "var(--color-up)"
                          : op.direction < 0
                            ? "var(--color-down)"
                            : "var(--color-flat)",
                  }}
                >
                  {op === null
                    ? "不可用"
                    : `${DIR_CN[String(op.direction)] ?? "—"} ${op.score ?? ""}`}
                </span>
              </span>
            );
          })}
        </div>

        <div className="mt-2 flex flex-wrap items-center gap-3">
          <ResearchStatusBadge
            status={months?.research_status ?? "NOT_RUN"}
            reasons={(months?.research_status_reasons ?? []).map((r) => stripMdEmphasis(r))}
          />
          <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            运限假设：{variantModeLabel(months?.variant_mode)}
          </span>
        </div>

        <div className="mt-2">
          <SourceMethod testId="timeline-source-method">
            <RawField label="分析基准日（as_of）" value={asOfDate.slice(0, 10) || "（未返回）"} />
            <RawField label="variant_mode（后端原值）" value={months?.variant_mode ?? "—"} />
            <RawField
              label="数据接口"
              value="GET /api/v1/analysis/{id}/timeline/{months|weeks|days}"
            />
            <RawField label="聚合版本" value={months?.aggregation_version ?? "—"} />
            <RawField label="逐日序列化版本" value={days?.daily_version ?? "—"} />
            {/* 交易日历的三层覆盖：实测成交 / 官方已公布 / 官方公布边界。
                "没有未来行情"与"无法确定未来交易日"必须能分开看。 */}
            <RawField
              label="实测成交日历"
              value={
                days?.calendar_coverage?.observed?.end
                  ? `${days.calendar_coverage.observed.start} ~ ${days.calendar_coverage.observed.end}`
                  : "（未返回）"
              }
            />
            <RawField
              label="官方已公布日历"
              value={
                days?.calendar_coverage?.published?.end
                  ? `${days.calendar_coverage.published.start} ~ ${days.calendar_coverage.published.end}` +
                    (days.calendar_coverage.published.verified === false
                      ? "（未通过交叉校验，未加载）"
                      : "")
                  : "（不可用）"
              }
            />
            <RawField
              label="行情快照"
              value="data/import/bars（只含已发生交易日，与交易日历是两回事）"
            />
            <div>
              窗口按实际交易日构建；后端返回多少个月/周/天就展示多少，不以前端补足凑数。
              实测成交日历之外的未来交易日取交易所**已公布**的安排；
              两层都没有覆盖的日期一律回答「未知」，不照搬上一年节假日。
            </div>
          </SourceMethod>
        </div>
      </Card>

      {/* ============ ② 主视图 + 右栏解释 ============ */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,7fr)_minmax(0,3fr)]">
        <div className="space-y-3">
          <Card testId="timeline-main-view">
            <CardHeader
              icon={<IconTrend size={15} />}
              title="未来周期时间轴"
              right={
                <div className="flex items-center gap-1" data-testid="timeline-granularity">
                  {(
                    [
                      { key: "days", label: "逐日（近20个交易日）" },
                      { key: "months", label: "月度" },
                    ] as const
                  ).map((g) => (
                    <button
                      key={g.key}
                      type="button"
                      onClick={() => setGranularity(g.key)}
                      className="rounded-[4px] px-2 py-[3px] text-[11.5px] transition-colors"
                      style={
                        g.key === granularity
                          ? {
                              color: "#241c0c",
                              background:
                                "linear-gradient(180deg, var(--color-gold-strong), var(--color-gold))",
                              fontWeight: 600,
                            }
                          : {
                              color: "var(--color-ink-sub)",
                              border: "1px solid var(--color-border)",
                            }
                      }
                      aria-pressed={g.key === granularity}
                      data-testid={`timeline-gran-${g.key}`}
                    >
                      {g.label}
                    </button>
                  ))}
                </div>
              }
              dense
            />

            {granularity === "days" ? (
              dayLoading ? (
                <SectionLoading
                  label="正在按交易日逐日求值（首次约数秒，之后命中缓存）…"
                  rows={4}
                />
              ) : dayError ? (
                <SectionError
                  what="逐日窗口"
                  message={dayError}
                  onRetry={() => setDayNonce((n) => n + 1)}
                  testId="timeline-days-error"
                />
              ) : dayList.length ? (
                <>
                  <TimelineStepChart
                    labels={chart.labels}
                    series={chart.series}
                    yLabel={chart.yLabel}
                  />
                  <p className="mt-1 text-[11.5px] leading-relaxed" style={{ color: "var(--color-ink-faint)" }}>
                    {stripMdEmphasis(days?.methodology)}
                    <br />
                    逐日视图只画三个模型各自的原始分数：后端给出的是该日的
                    <strong>综合方向</strong>（偏强/中性/偏弱）而不是综合分，
                    因此这里不合成"第四条线"，也不把方向换算成分数。
                  </p>
                </>
              ) : (
                <SectionEmpty
                  what="逐日窗口"
                  hint="as_of 之后没有可用交易日，或交易日历覆盖不足（不补造日期）。"
                />
              )
            ) : winLoading ? (
              <SectionLoading label="正在构建月度窗口…" rows={4} />
            ) : winError ? (
              <SectionError
                what="月度窗口"
                message={winError}
                onRetry={() => setWinNonce((n) => n + 1)}
                testId="timeline-windows-error"
              />
            ) : monthList.length ? (
              <>
                <TimelineStepChart
                  labels={chart.labels}
                  series={chart.series}
                  yLabel={chart.yLabel}
                />
                <p className="mt-1 text-[11.5px] leading-relaxed" style={{ color: "var(--color-ink-faint)" }}>
                  月度窗口取该月<strong>最后一个交易日</strong>求值；两点之间没有观测，因此用阶梯线而不是
                  平滑曲线。点击下方明细表的月份可查看该窗口的原始结果与假设。
                </p>
              </>
            ) : (
              <SectionEmpty what="月度窗口" hint="后端未返回月度窗口数据。" />
            )}
          </Card>

          {/* 月历热力图：真实交易日 + 可用逐日结果 */}
          <MonthHeatmapCard
            dayList={dayList}
            monthList={monthList}
            // 分区加载：热力图只用逐日结果，不应等月度/周度窗口一起完成
            loading={dayLoading}
            onPick={(key) => setSelected({ kind: "day", key })}
            selectedKey={selected?.kind === "day" ? selected.key : null}
          />
        </div>

        <div className="space-y-3">
          <WindowExplainer
            selected={selected}
            monthList={monthList}
            weekList={weekList}
            dayList={dayList}
            asOfDate={asOfDate}
          />
          <WeekRankingCard
            weekList={weekList}
            loading={winLoading}
            error={winError}
            onRetry={() => setWinNonce((n) => n + 1)}
            onPick={(key) => setSelected({ kind: "week", key })}
            selectedKey={selected?.kind === "week" ? selected.key : null}
          />
        </div>
      </div>

      {/* ============ ③ 明细表（可展开审计入口） ============ */}
      <Card testId="timeline-audit">
        <CardHeader icon={<IconCalendar size={15} />} title="窗口明细（审计入口）" dense />
        <details className="mt-1" open>
          <summary className="cursor-pointer text-[12.5px]" style={{ color: "var(--color-ink-sub)" }}>
            {monthTitle} · {weekTitle}
          </summary>

          {monthList.length ? (
            <div className="mt-2 overflow-x-auto">
              <table className="smp-table" data-testid="month-table">
                <thead>
                  <tr>
                    <th className="whitespace-nowrap">月份</th>
                    <th className="whitespace-nowrap text-right">交易日</th>
                    {["bazi", "ziwei", "huangli"].map((e) => (
                      <th key={e}>{engineCn(e)}</th>
                    ))}
                    <th>共识</th>
                    <th>冲突</th>
                    <th>研究状态</th>
                    <th>窗口</th>
                  </tr>
                </thead>
                <tbody>
                  {monthList.map((m) => (
                    <tr
                      key={m.month}
                      data-testid={`month-row-${m.month}`}
                      onClick={() => setSelected({ kind: "month", key: m.month })}
                      style={{
                        cursor: "pointer",
                        background:
                          selected?.kind === "month" && selected.key === m.month
                            ? "rgba(212,184,122,0.08)"
                            : undefined,
                      }}
                    >
                      <td className="font-semibold">{m.month}</td>
                      <td className="smp-num text-right">{m.trading_days}</td>
                      {[m.bazi, m.ziwei, m.huangli].map((op, i) => (
                        <td key={i} style={{ color: dirTone(op) }}>
                          {opinionText(op)}
                        </td>
                      ))}
                      <td>{consensusLabelCn(m.consensus)}</td>
                      <td style={{ color: m.conflict?.has_conflict ? "var(--color-conflict)" : "var(--color-ink-muted)" }}>
                        {conflictText(m.conflict)}
                      </td>
                      <td style={{ color: "var(--color-ink-muted)" }}>
                        {researchStatusLabel(m.research_status)}
                      </td>
                      <td style={{ color: "var(--color-ink-muted)" }}>
                        {windowPositionCn(
                          m.start_date ?? `${m.month}-01`,
                          m.end_date ?? `${m.month}-31`,
                          asOfDate.slice(0, 10),
                          "月",
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {weekList.length ? (
            <div className="mt-3 overflow-x-auto">
              <table className="smp-table" data-testid="week-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>区间</th>
                    <th className="text-right">交易日</th>
                    <th className="text-right">均值</th>
                    <th className="text-right">中位数</th>
                    <th className="text-right">最小</th>
                    <th className="text-right">最大</th>
                    <th className="text-right">偏强日占比</th>
                    <th className="whitespace-nowrap text-right">加权均值</th>
                    <th className="whitespace-nowrap">共识</th>
                    <th className="whitespace-nowrap">窗口</th>
                  </tr>
                </thead>
                <tbody>
                  {weekList.map((w) => (
                    <tr
                      key={w.week_index}
                      data-testid={`week-row-${w.week_index}`}
                      onClick={() => setSelected({ kind: "week", key: String(w.week_index) })}
                      style={{
                        cursor: "pointer",
                        background:
                          selected?.kind === "week" && selected.key === String(w.week_index)
                            ? "rgba(212,184,122,0.08)"
                            : undefined,
                      }}
                    >
                      <td className="smp-num">{w.week_index}</td>
                      <td className="whitespace-nowrap">
                        {w.week_start} ~ {w.week_end}
                      </td>
                      <td className="smp-num text-right">{w.trading_days}</td>
                      <td className="smp-num text-right" style={{ color: dirTone2(w.mean) }}>
                        {fmt(w.mean)}
                      </td>
                      <td className="smp-num text-right">{fmt(w.median)}</td>
                      <td className="smp-num text-right" style={{ color: dirTone2(w.min) }}>
                        {fmt(w.min)}
                      </td>
                      <td className="smp-num text-right" style={{ color: dirTone2(w.max) }}>
                        {fmt(w.max)}
                      </td>
                      <td className="smp-num text-right">
                        {w.positive_day_ratio === null
                          ? "—"
                          : `${(w.positive_day_ratio * 100).toFixed(0)}%`}
                      </td>
                      <td className="smp-num text-right">{fmt(w.weighted_mean)}</td>
                      <td>{consensusLabelCn(w.consensus)}</td>
                      <td style={{ color: "var(--color-ink-muted)" }}>
                        {windowPositionCn(w.week_start, w.week_end, asOfDate.slice(0, 10), "周")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </details>

        {weekList[0] ? (
          <div className="mt-2">
            <SectionNote>
              <b>聚合口径：</b>
              {weekList[0].aggregation_method}
              <br />
              传统术数<strong>没有「流周」这一层</strong>：周是聚合结果，不是独立运限。
              均值 / 中位数 / 最小 / 最大 / 偏强日占比 / 加权均值同时给出，
              避免用一个平均数掩盖分布。
            </SectionNote>
          </div>
        ) : null}

        <div className="mt-2">
          <SectionNote>{stripMdEmphasis(months?.methodology) || "（缺少方法论说明）"}</SectionNote>
          <ul className="mt-1.5 space-y-0.5 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
            <li>· 所有窗口基于实际交易日（交易所日历），不退化回自然日；</li>
            <li>· 日历覆盖不足时如实降级并给出 warning，不用周末规则假装肯定；</li>
            <li>· 窗口分数是传统规则强度，不是未来收益预测，也不转换为涨跌概率；</li>
            <li>· 历史有效性状态见上方 ResearchStatus，不由本页给出。</li>
          </ul>
          {months?.warnings?.length || days?.warnings?.length ? (
            <ul className="mt-1.5 space-y-0.5 text-[12px]" style={{ color: "var(--color-warn)" }}>
              {[...(months?.warnings ?? []), ...(days?.warnings ?? [])].map((w, i) => (
                <li key={`${i}-${w.code}`}>
                  · [{w.severity}] {w.code}：{stripMdEmphasis(w.message)}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </Card>
    </ResearchPage>
  );
}

const TRADING_DAYS_PER_WEEK = 5;

/* ------------------------------------------------------------------ */
/* 子组件                                                              */
/* ------------------------------------------------------------------ */

function SummaryMetric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded border p-2" style={{ borderColor: "var(--color-border)" }}>
      <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
        {label}
      </div>
      <div className="smp-num mt-0.5 font-semibold" style={{ color: "var(--color-ink)" }}>
        {value}
      </div>
      {hint ? (
        <div className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
          {hint}
        </div>
      ) : null}
    </div>
  );
}

/** 月历热力图：只用**真实交易日**与**可用逐日结果**，没有逐日结果的月份单独标注。 */
function MonthHeatmapCard({
  dayList,
  monthList,
  loading,
  onPick,
  selectedKey,
}: {
  dayList: ApiTimelineDays["days"];
  monthList: ApiMonthWindow[];
  loading: boolean;
  onPick: (key: string) => void;
  selectedKey: string | null;
}) {
  // 把逐日结果按自然月分组（逐日端点只覆盖最近约 20 个交易日 → 通常 1–2 个月）
  const byMonth = useMemo(() => {
    const map = new Map<string, ApiTimelineDays["days"]>();
    for (const d of dayList) {
      const key = d.trade_date.slice(0, 7);
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(d);
    }
    return map;
  }, [dayList]);

  const coveredMonths = [...byMonth.keys()].sort();
  const uncoveredMonths = monthList
    .map((m) => m.month)
    .filter((m) => !byMonth.has(m))
    .slice(0, 3);

  return (
    <Card testId="timeline-heatmap">
      <CardHeader
        icon={<IconCalendar size={15} />}
        title="交易日热力图"
        right={
          <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            逐日结果覆盖 {coveredMonths.length} 个月
          </span>
        }
        dense
      />
      {loading ? (
        <SectionLoading label="正在取逐日结果…" rows={3} />
      ) : coveredMonths.length ? (
        <div className="space-y-2.5">
          {coveredMonths.map((month) => (
            <MonthCalendar
              key={month}
              month={month}
              days={byMonth.get(month)!}
              onPick={onPick}
              selectedKey={selectedKey}
            />
          ))}
        </div>
      ) : (
        <SectionEmpty
          what="交易日热力图"
          hint="逐日结果未覆盖任何月份（as_of 之后日历覆盖不足，不补造日期）。"
        />
      )}

      {uncoveredMonths.length ? (
        <div
          className="mt-2 rounded border px-2.5 py-1.5 text-[11.5px] leading-relaxed"
          style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
          data-testid="timeline-heatmap-gap"
        >
          其余月份（{uncoveredMonths.join("、")}…）只有<strong>月度粒度</strong>结果，没有逐日结果：
          逐日视图只覆盖 as_of 之后连续的 20 个交易日。这里不用月度分数着色日历格子，
          否则会让人误以为那几天有独立观测。
        </div>
      ) : null}

      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11.5px]">
        <span style={{ color: "var(--color-ink-muted)" }}>
          图例（着色 = 该交易日<strong>可用引擎规则强度的均值</strong>，0–100）：
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-2.5 w-9 rounded-[2px]"
            style={{
              background:
                "linear-gradient(90deg, rgba(124,143,163,0.28), rgba(212,184,122,0.55), rgba(212,184,122,0.95))",
            }}
          />
          <span style={{ color: "var(--color-ink-sub)" }}>低 → 高</span>
        </span>
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-2.5 w-2.5 rounded-[2px]"
            style={{ background: "rgba(255,255,255,0.05)" }}
          />
          <span style={{ color: "var(--color-ink-sub)" }}>不可用（不填 0）</span>
        </span>
        <span style={{ color: "var(--color-ink-faint)" }}>
          · 悬停可看三个模型的分数与综合方向
        </span>
      </div>
    </Card>
  );
}

/** 一个自然月的真实交易日排布（按星期对齐，与自然日历一致）。 */
function MonthCalendar({
  month,
  days,
  onPick,
  selectedKey,
}: {
  month: string;
  days: ApiTimelineDays["days"];
  onPick: (key: string) => void;
  selectedKey: string | null;
}) {
  // 着色用的量 = 该交易日**可用引擎规则强度的均值**（对后端已给出的三个分数取均值）。
  // 为什么不用 combined_direction 着色：它是相对 50 分的三档方向，实测整段窗口都是 +1，
  // 全部格子同色等于没有信息；而均值是真实分数的直接聚合，可解释、可核对。
  const scoreOf = (d: ApiTimelineDays["days"][number]) =>
    meanOfScores([d.bazi_score, d.ziwei_score, d.huangli_score]);
  const scores = days.map(scoreOf).filter((v): v is number => v !== null);
  const scoreRange: [number, number] = scores.length
    ? [Math.min(...scores), Math.max(...scores)]
    : [0, 100];
  const [year, mon] = month.split("-").map(Number);
  const first = new Date(Date.UTC(year, mon - 1, 1));
  /** 周一为 0 的起始空格数（中文日历习惯以周一开头） */
  const lead = (first.getUTCDay() + 6) % 7;
  const cells: (ApiTimelineDays["days"][number] | null)[] = [
    ...Array.from({ length: lead }, () => null),
    ...days,
  ];

  return (
    <div data-testid={`timeline-calendar-${month}`}>
      <div className="mb-1 flex items-center gap-2 text-[11.5px]">
        <span className="font-semibold" style={{ color: "var(--color-ink-sub)" }}>
          {month}
        </span>
        <span style={{ color: "var(--color-ink-muted)" }}>{days.length} 个交易日</span>
        <span className="h-px flex-1" style={{ background: "var(--color-border)" }} />
      </div>
      <div className="grid grid-cols-7 gap-1 text-[10px]" style={{ color: "var(--color-ink-faint)" }}>
        {["一", "二", "三", "四", "五", "六", "日"].map((w) => (
          <div key={w} className="text-center">
            {w}
          </div>
        ))}
      </div>
      <div className="mt-0.5 grid grid-cols-7 gap-1">
        {cells.map((d, i) => {
          if (!d) return <div key={`pad-${i}`} />;
          const tone = scoreOf(d);
          const bg = heatColor(tone, scoreRange);
          const active = selectedKey === d.trade_date;
          return (
            <button
              key={d.trade_date}
              type="button"
              onClick={() => onPick(d.trade_date)}
              className="rounded-[3px] px-1 py-[3px] text-center transition-colors"
              style={{
                background: bg,
                border: active ? "1px solid var(--color-gold)" : "1px solid transparent",
                color: "var(--color-ink)",
              }}
              title={`${d.trade_date} 规则强度均值 ${tone === null ? "不可用" : tone.toFixed(1)}（八字 ${d.bazi_score ?? "—"} / 紫微 ${d.ziwei_score ?? "—"} / 黄历 ${d.huangli_score ?? "—"}；综合方向 ${d.combined_direction ?? "—"}）`}
              data-testid={`timeline-heat-${d.trade_date}`}
            >
              <span className="smp-num">{Number(d.trade_date.slice(8))}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/** 右栏「窗口解释」：点选月/周/日后的原始结果、依据、可用性、假设、版本与风险。 */
function WindowExplainer({
  selected,
  monthList,
  weekList,
  dayList,
  asOfDate,
}: {
  selected: { kind: "month" | "week" | "day"; key: string } | null;
  monthList: ApiMonthWindow[];
  weekList: ApiWeekWindow[];
  dayList: ApiTimelineDays["days"];
  asOfDate: string;
}) {
  const content = useMemo(() => {
    if (!selected) return null;
    if (selected.kind === "month") {
      const m = monthList.find((x) => x.month === selected.key);
      if (!m) return null;
      return {
        title: `月度窗口 ${m.month}`,
        position: windowPositionCn(
          m.start_date ?? `${m.month}-01`,
          m.end_date ?? `${m.month}-31`,
          asOfDate.slice(0, 10),
          "月",
        ),
        opinions: [m.bazi, m.ziwei, m.huangli],
        consensus: consensusLabelCn(m.consensus),
        conflict: m.conflict?.has_conflict
          ? `有冲突（${m.conflict.severity || "未分级"}）`
          : "无冲突",
        availability: m.trading_days ? `${m.trading_days} 个交易日` : "该月无交易日",
        status: researchStatusLabel(m.research_status),
        versions: `agg=${m.consensus ? "有共识" : "无共识"} · 该月采样日 ${m.sample_dates?.length ?? 0} 个`,
        risks: [
          "月度分数取该月最后一个交易日求值，不代表整月每日都成立；",
          "两点之间没有观测，图上用阶梯线表达，不做插值。",
        ],
        raw: m,
      };
    }
    if (selected.kind === "week") {
      const w = weekList.find((x) => String(x.week_index) === selected.key);
      if (!w) return null;
      return {
        title: `周度窗口 #${w.week_index}`,
        position: windowPositionCn(w.week_start, w.week_end, asOfDate.slice(0, 10), "周"),
        opinions: [],
        consensus: consensusLabelCn(w.consensus),
        conflict: "（周度不单独给出冲突分级）",
        availability: `${w.trading_days} 个交易日`,
        status: researchStatusLabel(w.research_status),
        versions: `${w.aggregation_version} · ${stripMdEmphasis(w.aggregation_method)}`,
        risks: [
          `周内分布：均值 ${fmt(w.mean)}／中位数 ${fmt(w.median)}／最小 ${fmt(w.min)}／最大 ${fmt(w.max)}／偏强日占比 ${
            w.positive_day_ratio === null ? "—" : `${(w.positive_day_ratio * 100).toFixed(0)}%`
          }；`,
          "传统术数没有「流周」这一层，周是聚合结果而非独立运限。",
        ],
        raw: w,
      };
    }
    const d = dayList.find((x) => x.trade_date === selected.key);
    if (!d) return null;
    return {
      title: `逐日窗口 ${d.trade_date}`,
      position: windowPositionCn(d.trade_date, d.trade_date, asOfDate.slice(0, 10), "周"),
      opinions: [],
      consensus: DIR_CN[String(d.combined_direction)] ?? "—",
      conflict:
        countAvailable([d.bazi_score, d.ziwei_score, d.huangli_score]) >= 2 &&
        new Set(
          [d.bazi_direction, d.ziwei_direction, d.huangli_direction].filter(
            (v) => v !== null && v !== undefined,
          ),
        ).size > 1
          ? "该日三模型方向不一致（冲突）"
          : "该日三模型方向一致或不足两个模型可用",
      availability: `可用引擎 ${countAvailable([
        d.bazi_score,
        d.ziwei_score,
        d.huangli_score,
      ])}/3`,
      status: "逐日结果不单独带研究状态；历史有效性由研究流水线回答",
      versions: "流日粒度（daily-v1）",
      risks: [
        "逐日结果是该交易日的流日规则强度，不是价格预测；",
        "缺失模型的分数字段为 null，不参与方向合成、也不以 0 替代。",
      ],
      raw: d,
    };
  }, [selected, monthList, weekList, dayList, asOfDate]);

  return (
    <Card testId="timeline-explainer">
      <CardHeader
        icon={<IconTrend size={15} />}
        title="窗口解释"
        right={
          <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            点击月/周/日查看
          </span>
        }
        dense
      />
      {!content ? (
        <SectionEmpty
          what="窗口解释"
          hint="点击左侧热力图的交易日、或下方明细表的月份 / 周，查看该窗口的原始结果与假设。"
        />
      ) : (
        <div className="space-y-2" data-testid="timeline-explainer-body">
          <div>
            <div className="smp-serif-title text-[15px]" style={{ color: "var(--color-gold-strong)" }}>
              {content.title}
            </div>
            <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              {content.position}
            </div>
          </div>

          {content.opinions.filter(Boolean).length ? (
            <div className="space-y-1">
              {content.opinions.filter(Boolean).map((op, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between rounded border px-2 py-1 text-[11.5px]"
                  style={{ borderColor: "var(--color-border)" }}
                >
                  <span style={{ color: "var(--color-ink-sub)" }}>{engineCn(op!.engine)}</span>
                  <span className="smp-num" style={{ color: dirTone(op) }}>
                    {opinionText(op)}
                  </span>
                </div>
              ))}
            </div>
          ) : null}

          <ExplainerRow label="共识 / 方向" value={content.consensus} />
          <ExplainerRow label="冲突" value={content.conflict} />
          <ExplainerRow label="可用性" value={content.availability} />
          <ExplainerRow label="研究状态" value={content.status} />
          <ExplainerRow label="版本 / 口径" value={content.versions} />

          <ul className="space-y-0.5 text-[11.5px]" style={{ color: "var(--color-warn)" }}>
            {content.risks.map((r, i) => (
              <li key={i}>· {r}</li>
            ))}
          </ul>

          <details
            className="rounded border px-2 py-1.5"
            style={{ borderColor: "var(--color-border)" }}
          >
            <summary className="cursor-pointer text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              该窗口原始 JSON（审计）
            </summary>
            <pre
              className="smp-scroll mt-1 max-h-56 overflow-auto text-[10.5px] leading-snug"
              style={{ color: "var(--color-ink-muted)" }}
              data-testid="timeline-explainer-raw"
            >
              {JSON.stringify(content.raw, null, 1)}
            </pre>
          </details>

          <p className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
            本面板不提供因子归因：后端未为单个窗口提供因子贡献分解，
            因此不生成"关键触发因子"这类内容，避免伪造权重。
          </p>
        </div>
      )}
    </Card>
  );
}

function ExplainerRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-2 text-[11.5px]">
      <span className="shrink-0" style={{ color: "var(--color-ink-muted)" }}>
        {label}
      </span>
      <span className="text-right" style={{ color: "var(--color-ink-sub)" }}>
        {value}
      </span>
    </div>
  );
}

/** 周度排名（参考图的「未来 N 周窗口排名」）：按后端给出的加权均值排序，不重算。 */
function WeekRankingCard({
  weekList,
  loading,
  error,
  onRetry,
  onPick,
  selectedKey,
}: {
  weekList: ApiWeekWindow[];
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onPick: (key: string) => void;
  selectedKey: string | null;
}) {
  const ranked = useMemo(() => {
    const withScore = weekList.map((w) => ({
      w,
      // 排序用"周内可用引擎规则强度的均值"：由该周 daily_results 里后端已给出的分数聚合。
      // 不用 weighted_mean 排序是因为它按方向（-1/0/1）加权，实测整段窗口恒为 1.00，
      // 排出来的名次没有信息量；两个量都展示，读者可以对照。
      level: meanOfScores(
        (w.daily_results ?? []).flatMap((d) => [d.bazi_score, d.ziwei_score, d.huangli_score]),
      ),
    }));
    return [...withScore].sort((a, b) => (b.level ?? -1) - (a.level ?? -1));
  }, [weekList]);

  return (
    <Card testId="timeline-week-ranking">
      <CardHeader
        icon={<IconTrend size={15} />}
        title={`周度排名（${weekList.length} 周）`}
        right={
          <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            按周内平均规则强度排序
          </span>
        }
        dense
      />
      {loading ? (
        <SectionLoading label="正在聚合成周…" rows={4} />
      ) : error ? (
        <SectionError what="周度窗口" message={error} onRetry={onRetry} testId="timeline-weeks-error" />
      ) : ranked.length ? (
        <table className="smp-table" data-testid="week-ranking-table">
          <thead>
            <tr>
              <th>#</th>
              <th className="whitespace-nowrap">区间</th>
              <th className="whitespace-nowrap text-right">平均规则强度</th>
              <th className="whitespace-nowrap text-right">方向加权均值</th>
              <th className="whitespace-nowrap text-right">偏强日</th>
              <th className="whitespace-nowrap">共识</th>
            </tr>
          </thead>
          <tbody>
            {ranked.slice(0, 12).map(({ w, level }) => (
              <tr
                key={w.week_index}
                onClick={() => onPick(String(w.week_index))}
                style={{
                  cursor: "pointer",
                  background:
                    selectedKey === String(w.week_index) ? "rgba(212,184,122,0.08)" : undefined,
                }}
              >
                <td className="smp-num">{w.week_index}</td>
                <td className="smp-num whitespace-nowrap text-[11px]">
                  {w.week_start.slice(5)}~{w.week_end.slice(5)}
                </td>
                <td className="smp-num text-right" style={{ color: "var(--color-gold)" }}>
                  {level === null ? "—" : level.toFixed(2)}
                </td>
                <td className="smp-num text-right" style={{ color: dirTone2(w.weighted_mean) }}>
                  {fmt(w.weighted_mean)}
                </td>
                <td className="smp-num text-right">
                  {w.positive_day_ratio === null
                    ? "—"
                    : `${(w.positive_day_ratio * 100).toFixed(0)}%`}
                </td>
                <td>{consensusLabelCn(w.consensus)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <SectionEmpty
          what="周度窗口"
          hint="后端未返回周度窗口（可能是 as_of 之后的交易日历覆盖不足）。"
        />
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* 工具                                                                */
/* ------------------------------------------------------------------ */

function opinionScore(op: ApiOpinion | null | undefined): number | null {
  if (!op || op.availability !== "ok") return null;
  return op.score ?? null;
}

function opinionText(op: ApiOpinion | null | undefined): string {
  if (!op) return "—";
  if (op.availability !== "ok") return "不可用";
  return `${DIR_CN[String(op.direction)] ?? "—"} ${op.score ?? "—"}`;
}

function dirTone(op: ApiOpinion | null | undefined): string {
  if (!op || op.availability !== "ok") return "var(--color-ink-faint)";
  if (op.direction > 0) return "var(--color-up)";
  if (op.direction < 0) return "var(--color-down)";
  return "var(--color-flat)";
}

function dirTone2(v: number | null | undefined): string {
  if (v === null || v === undefined) return "var(--color-ink-faint)";
  if (v > 0.05) return "var(--color-up)";
  if (v < -0.05) return "var(--color-down)";
  return "var(--color-flat)";
}

function latestOpinion(
  key: "bazi" | "ziwei" | "huangli",
  dayList: ApiTimelineDays["days"],
  monthList: ApiMonthWindow[],
): { direction: number; score: number | null } | null {
  const day = dayList[0];
  if (day) {
    const score =
      key === "bazi" ? day.bazi_score : key === "ziwei" ? day.ziwei_score : day.huangli_score;
    const direction =
      key === "bazi"
        ? day.bazi_direction
        : key === "ziwei"
          ? day.ziwei_direction
          : day.huangli_direction;
    // 分数缺失即该模型当日不可用 —— 不返回方向，避免把"不知道"当成中性
    if (score === null || score === undefined) return null;
    return { direction, score };
  }
  const month = monthList[0];
  const op = month ? month[key] : null;
  if (op && op.availability === "ok") return { direction: op.direction, score: op.score };
  return null;
}

function countAvailable(values: (number | null)[]): number {
  return values.filter((v) => v !== null && v !== undefined).length;
}

/** 可用引擎规则强度的均值；全部不可用时返回 null（不填 0）。 */
function meanOfScores(values: (number | null)[]): number | null {
  const present = values.filter((v): v is number => v !== null && v !== undefined);
  if (!present.length) return null;
  return present.reduce((a, b) => a + b, 0) / present.length;
}

/** 热力图着色的强度色带（金 → 中性灰），不使用红涨绿跌语义。 */
function heatColor(value: number | null, range: [number, number]): string {
  if (value === null) return "rgba(255,255,255,0.05)";
  const [lo, hi] = range;
  const t = hi > lo ? (value - lo) / (hi - lo) : 0.5;
  const alpha = 0.16 + 0.62 * t;
  return `rgba(212,184,122,${alpha.toFixed(3)})`;
}

/** 冲突的中文表达：级别来自后端，不在前端重新判定。 */
function conflictText(conflict: ApiMonthWindow["conflict"]): string {
  if (!conflict) return "—";
  if (!conflict.has_conflict) return "无冲突";
  const level = conflict.conflict_level ?? conflict.severity ?? "";
  const levelCn: Record<string, string> = {
    none: "无",
    minor: "轻微",
    moderate: "中等",
    major: "显著",
    severe: "严重",
  };
  return level ? `有冲突（${levelCn[level] ?? level}）` : "有冲突";
}

function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(2);
}

export default function TimelinePage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <TimelineInner />
    </Suspense>
  );
}
