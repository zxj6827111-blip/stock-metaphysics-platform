"use client";

import { Card, CardHeader, StatPair } from "@/components/cards/Card";
import type { ApiDateScanResponse } from "@/lib/api";

const ORDER = ["协同型", "扰动型", "混合型", "弱关系", "不可用"];

export function MarketRelationSummary({ data }: { data: ApiDateScanResponse }) {
  const items = [
    ["PIT股票池", data.stock_total, "flat"],
    ["可计算股票", data.valid_scan_count, "gold"],
    ...ORDER.slice(0, 4).map((group) => [group, data.group_counts[group] ?? 0, group === "扰动型" ? "warn" : "flat"]),
  ] as [string, number, "flat" | "gold" | "warn"][];
  return (
    <Card testId="market-relation-summary">
      <CardHeader title="全市场关系分布（流日行口径）" dense right={<span className="smp-num text-[11px]" style={{ color: "var(--color-ink-muted)" }}>{data.cache.hit ? "缓存命中" : "首次计算"}</span>} />
      <div className="grid grid-cols-2 gap-2 p-3 md:grid-cols-6">
        {items.map(([label, value, tone]) => (
          <div key={label} className="rounded border px-2.5 py-2" style={{ borderColor: "var(--color-border)" }}>
            <div className="smp-metric-label">{label}</div>
            <div className="mt-1 smp-num text-[18px]" style={{ color: tone === "gold" ? "var(--color-gold)" : tone === "warn" ? "var(--color-warn)" : "var(--color-ink)" }}>{value}</div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-4 px-3 pb-3">
        <StatPair label="关系规则" value={data.versions.relation_rule_version} />
        <StatPair label="矩阵 schema" value={data.versions.relation_matrix_schema_version} />
        <StatPair label="股票池" value={data.versions.universe_version} />
        <StatPair label="出生基准" value="上市首日开盘" />
      </div>
      <div className="px-3 pb-3 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>分组为结构型（协同型 = S&gt;0 且 V=0；扰动型 = V&gt;0 且 S=0；混合型 = 两者皆有；弱关系 = 均为 0），不使用凭观感标定的阈值。S / V / U 只统计流日行（external_day_row），不是整个 3×3 矩阵的全部事件。</div>
    </Card>
  );
}
