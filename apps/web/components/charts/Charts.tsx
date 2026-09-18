"use client";

/**
 * ECharts 图表组件。
 *
 * 参考图中的图表是深色背景 + 细线 + 金色高亮的量化终端风格。
 * 所有图表都必须附带文本摘要（UI_RULES §11），因此每个组件都同时渲染
 * 一段可读的 `<figcaption>`。
 */

import ReactECharts from "echarts-for-react";
import { useMemo } from "react";

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
      animationDuration: 400,
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
      <ReactECharts option={option} style={{ height }} opts={{ renderer: "svg" }} notMerge />
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
      animationDuration: 300,
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
      <ReactECharts option={option} style={{ height }} opts={{ renderer: "svg" }} notMerge />
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
      animation: false,
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
  return <ReactECharts option={option} style={{ height }} opts={{ renderer: "svg" }} notMerge />;
}
