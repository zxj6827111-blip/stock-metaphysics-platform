"use client";

/**
 * ECharts 图表组件。
 *
 * 参考图中的图表是深色背景 + 细线 + 金色高亮的量化终端风格。
 * 所有图表都必须附带文本摘要（UI_RULES §11），因此每个组件都同时渲染
 * 一段可读的 `<figcaption>`。
 */

import { SmpECharts } from "./SmpECharts";
import { useMemo } from "react";

import { stripMdEmphasis } from "@/lib/text";
import type { DistributionBin, TimeWindowSeries } from "@/lib/types";

const AXIS_COLOR = "var(--color-ink-faint)";
const SPLIT_COLOR = "rgba(30,52,68,0.6)";

export function TimeWindowChart({
  data,
  height = 250,
}: {
  data: TimeWindowSeries;
  height?: number;
}) {
  const option = useMemo(
    () => ({
      grid: { left: 44, right: 16, top: 14, bottom: 26 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(9,20,30,0.96)",
        borderColor: "var(--color-border-strong)",
        textStyle: { color: "#E8EDF2", fontSize: 12 },
      },
      legend: { show: false },
      xAxis: {
        type: "category",
        data: data.dates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: SPLIT_COLOR } },
        axisTick: { show: false },
        axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        interval: 20,
        axisLine: { show: false },
        splitLine: { lineStyle: { color: SPLIT_COLOR, type: "dashed" } },
        axisLabel: { color: AXIS_COLOR, fontSize: 11 },
      },
      series: [
        ...data.series.map((s, i) => ({
          name: s.name,
          type: "line",
          smooth: true,
          symbol: "circle",
          symbolSize: i === data.series.length - 1 ? 4 : 3,
          lineStyle: {
            width: i === data.series.length - 1 ? 2.4 : 1.6,
            color: s.color,
          },
          itemStyle: { color: s.color },
          data: s.values,
          markArea:
            i === 0
              ? {
                  silent: true,
                  data: data.markers.map((m) => [
                    {
                      xAxis: m.date,
                      itemStyle: {
                        color:
                          m.tone === "consensus"
                            ? "rgba(79,211,155,0.13)"
                            : "rgba(176,124,214,0.13)",
                      },
                      label: {
                        show: true,
                        position: "insideTop",
                        color:
                          m.tone === "consensus" ? "#4fd39b" : "#b07cd6",
                        fontSize: 11,
                      },
                      name: m.label,
                    },
                    { xAxis: data.dates[Math.min(data.dates.indexOf(m.date) + 1, data.dates.length - 1)] },
                  ]),
                }
              : undefined,
        })),
      ],
    }),
    [data],
  );

  const last = data.series[data.series.length - 1];
  const summary = last
    ? `${last.name}从 ${last.values[0] ?? "—"} 变化到 ${last.values[last.values.length - 1] ?? "—"}`
    : "暂无数据";

  return (
    <figure className="m-0" data-testid="time-window-chart">
      <SmpECharts option={option} height={height} />
      <figcaption className="sr-only">{summary}</figcaption>
    </figure>
  );
}

export function DistributionChart({
  bins,
  height = 108,
}: {
  bins: DistributionBin[];
  height?: number;
}) {
  const option = useMemo(
    () => ({
      grid: { left: 34, right: 8, top: 8, bottom: 22 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(9,20,30,0.96)",
        borderColor: "var(--color-border-strong)",
        textStyle: { color: "#E8EDF2", fontSize: 12 },
      },
      xAxis: {
        type: "category",
        data: bins.map((b) => b.label),
        axisLine: { lineStyle: { color: SPLIT_COLOR } },
        axisTick: { show: false },
        axisLabel: { color: AXIS_COLOR, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        splitLine: { lineStyle: { color: SPLIT_COLOR, type: "dashed" } },
        axisLabel: { color: AXIS_COLOR, fontSize: 10 },
      },
      series: [
        {
          type: "bar",
          barWidth: "58%",
          data: bins.map((b) => ({
            value: b.value,
            itemStyle: {
              color: b.tone === "up" ? "var(--color-up)" : "var(--color-down)",
              opacity: 0.82,
              borderRadius: [2, 2, 0, 0],
            },
          })),
        },
      ],
    }),
    [bins],
  );

  const up = bins.filter((b) => b.tone === "up").reduce((a, b) => a + b.value, 0);
  const down = bins.filter((b) => b.tone === "down").reduce((a, b) => a + b.value, 0);

  return (
    <figure className="m-0" data-testid="distribution-chart">
      <SmpECharts option={option} height={height} />
      <figcaption className="mt-1 text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
        正收益区间样本 {up} 个，负收益区间样本 {down} 个（样本分布，非预测）
      </figcaption>
    </figure>
  );
}

export function MiniTrend({
  values,
  tone,
  height = 46,
}: {
  values: number[];
  tone: "up" | "down";
  height?: number;
}) {
  const color = tone === "up" ? "var(--color-up)" : "var(--color-down)";
  const option = useMemo(
    () => ({
      grid: { left: 0, right: 0, top: 4, bottom: 4 },
      xAxis: { type: "category", show: false, data: values.map((_, i) => i) },
      yAxis: { type: "value", show: false, scale: true },
      series: [
        {
          type: "line",
          data: values,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 1.6, color },
          areaStyle: {
            color: {
              type: "linear",
              x: 0, y: 0, x2: 0, y2: 1,
              colorStops: [
                { offset: 0, color: tone === "up" ? "rgba(232,88,90,0.34)" : "rgba(79,211,155,0.34)" },
                { offset: 1, color: "rgba(0,0,0,0)" },
              ],
            },
          },
        },
      ],
    }),
    [values, tone, color],
  );
  return <SmpECharts option={option} height={height} />;
}

/* ==========================================================================
   黄历分类历史表现 / 时间窗口主视图
   ========================================================================== */

/** 日课分类语义色：与传统吉凶对应，**与行情涨跌色（红涨绿跌）分属两套语义**。 */
export const CLASS_TONE: Record<string, string> = {
  auspicious: "#d9b45f",
  inauspicious: "#8d7ea6",
  unknown: "var(--color-flat)",
};
export const CLASS_TONE_CN: Record<string, string> = {
  auspicious: "吉日",
  inauspicious: "凶日",
  unknown: "未给出分类",
};

/**
 * 分类收益时间图。
 *
 * 纵轴 = 各类别"截至该日期的平均持有期收益"（扩展均值）。
 * **不是净值、不是累计收益**：系统没有可复现的组合规则，因此不画资金曲线。
 * 早期样本少时用虚线灰点提示，避免把 3 个样本画成一条醒目的趋势线。
 */
export function HuangliClassTrendChart({
  dates,
  byClass,
  countsByClass,
  height = 210,
}: {
  dates: string[];
  byClass: Record<string, (number | null)[]>;
  countsByClass: Record<string, number[]>;
  height?: number;
}) {
  const keys = Object.keys(byClass);
  const option = useMemo(
    () => ({
      grid: { left: 52, right: 14, top: 26, bottom: 30 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(9,20,30,0.96)",
        borderColor: "var(--color-border-strong)",
        textStyle: { color: "#E8EDF2", fontSize: 12 },
        valueFormatter: (v: number | null) => (v === null ? "—" : `${(v * 100).toFixed(2)}%`),
      },
      legend: {
        show: true,
        top: 0,
        right: 0,
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { color: "var(--color-ink-sub)", fontSize: 11 },
        data: keys.map((k) => CLASS_TONE_CN[k] ?? k),
      },
      xAxis: {
        type: "category",
        data: dates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: SPLIT_COLOR } },
        axisTick: { show: false },
        axisLabel: { color: AXIS_COLOR, fontSize: 10.5, hideOverlap: true },
      },
      yAxis: {
        type: "value",
        scale: true,
        axisLine: { show: false },
        splitLine: { lineStyle: { color: SPLIT_COLOR, type: "dashed" } },
        axisLabel: {
          color: AXIS_COLOR,
          fontSize: 10.5,
          formatter: (v: number) => `${(v * 100).toFixed(1)}%`,
        },
      },
      series: keys.map((k) => ({
        name: CLASS_TONE_CN[k] ?? k,
        type: "line",
        showSymbol: false,
        connectNulls: false,
        data: byClass[k].map((v) => (v === null ? null : Number(v.toFixed(6)))),
        lineStyle: { width: 1.9, color: CLASS_TONE[k] ?? "var(--color-flat)" },
        itemStyle: { color: CLASS_TONE[k] ?? "var(--color-flat)" },
        emphasis: { focus: "series" },
      })),
    }),
    [dates, byClass, countsByClass, keys],
  );

  const latest = keys.map((k) => {
    const arr = byClass[k];
    const v = arr.length ? arr[arr.length - 1] : null;
    const c = countsByClass[k]?.length ? countsByClass[k][countsByClass[k].length - 1] : 0;
    return `${CLASS_TONE_CN[k] ?? k} 最新均值 ${v === null ? "—" : `${(v * 100).toFixed(2)}%`}（n=${c}）`;
  });

  return (
    <figure className="m-0" data-testid="huangli-class-trend">
      <SmpECharts option={option} height={height} />
      <figcaption className="mt-1 text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
        {latest.join("；") || "暂无数据"}。纵轴为扩展均值，非累计收益。
      </figcaption>
    </figure>
  );
}

/**
 * 时间窗口主视图：按**实际返回粒度**绘制三模型与共识的阶梯线。
 *
 * 为什么用 `step` 而不是平滑曲线：月度/周度数据在两个月之间没有观测，
 * 平滑插值会暗示"中间每一天都有预测值"。阶梯线明确表达"该窗口内取这个值"，
 * 缺失模型用 `null` 断开（不连、不填 0）。
 */
export function TimelineStepChart({
  labels,
  series,
  height = 230,
  yLabel = "规则强度（0–100）",
}: {
  labels: string[];
  series: { name: string; color: string; values: (number | null)[] }[];
  height?: number;
  yLabel?: string;
}) {
  const option = useMemo(
    () => ({
      grid: { left: 46, right: 14, top: 26, bottom: 30 },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(9,20,30,0.96)",
        borderColor: "var(--color-border-strong)",
        textStyle: { color: "#E8EDF2", fontSize: 12 },
        valueFormatter: (v: number | null) => (v === null ? "不可用" : String(v)),
      },
      legend: {
        show: true,
        top: 0,
        right: 0,
        itemWidth: 12,
        itemHeight: 8,
        textStyle: { color: "var(--color-ink-sub)", fontSize: 11 },
      },
      xAxis: {
        type: "category",
        data: labels,
        boundaryGap: false,
        axisLine: { lineStyle: { color: SPLIT_COLOR } },
        axisTick: { show: false },
        axisLabel: { color: AXIS_COLOR, fontSize: 10.5, hideOverlap: true },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        name: yLabel,
        nameTextStyle: { color: AXIS_COLOR, fontSize: 10.5, align: "left" },
        nameGap: 14,
        axisLine: { show: false },
        splitLine: { lineStyle: { color: SPLIT_COLOR, type: "dashed" } },
        axisLabel: { color: AXIS_COLOR, fontSize: 10.5 },
      },
      series: series.map((s) => ({
        name: s.name,
        type: "line",
        step: "end",
        showSymbol: true,
        // 线宽/点径按 1× 屏幕可辨识度设定：真实规则强度集中在 45–70 的窄带里，
        // 1.9px 的线在 1× 下几乎看不见，会被误读成"没有数据"。
        symbolSize: 6,
        connectNulls: false,
        data: s.values,
        lineStyle: { width: 2.4, color: s.color },
        itemStyle: { color: s.color, borderWidth: 0 },
        emphasis: { focus: "series", scale: 1.3 },
      })),
    }),
    [labels, series, yLabel],
  );

  const summary = series
    .map((s) => {
      const present = s.values.filter((v) => v !== null).length;
      return `${s.name} 覆盖 ${present}/${s.values.length} 个窗口`;
    })
    .join("；");

  return (
    <figure className="m-0" data-testid="timeline-step-chart">
      <SmpECharts option={option} height={height} />
      <figcaption className="mt-1 text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
        {summary || "暂无数据"}。阶梯线按实际返回粒度绘制，缺失窗口断开而非补值。
      </figcaption>
    </figure>
  );
}

/**
 * 持有期对比图（历史验证页）。
 *
 * 只画**后端已经算出来的字段**：每个持有期的平均收益与平均超额收益，
 * 按 variant（不同出生模型口径等）分组并列。三条纪律：
 *
 * 1. **不派生新指标**：不画"基准收益 = 收益 − 超额"这类由前端反推的序列；
 * 2. **不画收益分布 / 净值曲线**：前者要逐样本收益序列，后者要可复现的组合规则，
 *    当前数据契约里两者都没有；
 * 3. 缺失的持有期**断开**（connectNulls: false），不插值、不补 0。
 */
export function HorizonComparisonChart({
  labels,
  series,
  height = 168,
  captionLines,
}: {
  labels: string[];
  series: { name: string; values: (number | null)[]; tone: "up" | "down" | "flat" }[];
  height?: number;
  /** 摘要行数；05 首屏的持有期卡只有 194px 参考高度，传 1 收成一行为标题带。 */
  captionLines?: 1;
}) {
  const option = useMemo(
    () => ({
      grid: { left: 46, right: 8, top: 18, bottom: 24 },
      legend: {
        data: series.map((s) => s.name),
        top: 0,
        textStyle: { color: "var(--color-ink-muted)", fontSize: 10.5 },
        itemWidth: 10,
        itemHeight: 8,
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "rgba(9,20,30,0.96)",
        borderColor: "var(--color-border-strong)",
        textStyle: { color: "#E8EDF2", fontSize: 12 },
        valueFormatter: (v: unknown) =>
          v === null || v === undefined ? "不可用" : `${(Number(v) * 100).toFixed(2)}%`,
      },
      xAxis: {
        type: "category",
        data: labels,
        axisLine: { lineStyle: { color: SPLIT_COLOR } },
        axisTick: { show: false },
        axisLabel: { color: AXIS_COLOR, fontSize: 10 },
      },
      yAxis: {
        type: "value",
        axisLine: { show: false },
        splitLine: { lineStyle: { color: SPLIT_COLOR, type: "dashed" } },
        axisLabel: {
          color: AXIS_COLOR,
          fontSize: 10,
          // 收益量级很小（±1%），整数百分比会出现 "0% / -0%" 这种无信息刻度
          formatter: (v: number) => {
            const pctv = v * 100;
            const shown = Math.abs(pctv) < 0.05 ? 0 : pctv;
            return `${shown.toFixed(1)}%`;
          },
        },
      },
      series: series.map((s) => ({
        name: s.name,
        type: "bar",
        barMaxWidth: 22,
        connectNulls: false,
        data: s.values.map((v) => ({
          value: v,
          itemStyle: {
            color:
              s.tone === "up"
                ? "var(--color-up)"
                : s.tone === "down"
                  ? "var(--color-down)"
                  : "var(--color-flat)",
            opacity: 0.82,
            borderRadius: [2, 2, 0, 0],
          },
        })),
      })),
    }),
    [labels, series],
  );

  const summary = series
    .map((s) => {
      const present = s.values.filter((v) => v !== null).length;
      const best = s.values
        .map((v, i) => ({ v, i }))
        .filter((x) => x.v !== null)
        .sort((a, b) => (b.v as number) - (a.v as number))[0];
      return best
        ? `${s.name} 覆盖 ${present}/${s.values.length} 个持有期，最高在 ${labels[best.i] ?? best.i}（${((best.v as number) * 100).toFixed(2)}%）`
        : `${s.name} 无可用持有期`;
    })
    .join("；");

  return (
    <figure className="m-0" data-testid="horizon-comparison-chart">
      <SmpECharts option={option} height={height} />
      <figcaption
        className={`mt-1 text-[10.5px] ${captionLines === 1 ? "line-clamp-1" : ""}`}
        // 文本摘要不能因为收高度而消失：单行截断时把全文挂到 title 上，
        // DOM 里也仍然是完整句子（可搜索、可截图放大）。
        title={captionLines === 1 ? summary : undefined}
        style={{ color: "var(--color-ink-faint)" }}
      >
        {summary || "暂无数据"}。仅绘制后端已算出的平均收益 / 平均超额收益；
        缺失持有期断开，不做插值，也不由前端派生基准序列。
      </figcaption>
    </figure>
  );
}
