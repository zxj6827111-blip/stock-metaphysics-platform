"use client";

import { Card, CardHeader, StatPair } from "@/components/cards/Card";
import type { ApiDateScanResponse } from "@/lib/api";

const ORDER = ["高协同", "高扰动", "高混合", "弱关系", "不可用"];

export function MarketRelationSummary({ data }: { data: ApiDateScanResponse }) {
  const items = [
    ["股票总数", data.stock_total, "flat"],
    ["有效扫描", data.valid_scan_count, "gold"],
    ...ORDER.slice(0, 4).map((group) => [group, data.group_counts[group] ?? 0, group === "高扰动" ? "warn" : "flat"]),
  ] as [string, number, "flat" | "gold" | "warn"][];
  return (
    <Card testId="market-relation-summary">
      <CardHeader title="全市场关系分布" dense right={<span className="smp-num text-[11px]" style={{ color: "var(--color-ink-muted)" }}>{data.cache.hit ? "缓存命中" : "首次计算"}</span>} />
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
        <StatPair label="股票池" value={data.versions.universe_version} />
        <StatPair label="出生基准" value="上市首日开盘" />
      </div>
    </Card>
  );
}
