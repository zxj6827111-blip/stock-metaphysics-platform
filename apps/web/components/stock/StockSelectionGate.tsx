"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Card, CardHeader } from "../cards/Card";
import { IconSearch } from "../shell/Icons";
import { StockSearch } from "./StockSearch";
import { getRecentStocks, type RecentStock } from "@/lib/recentStockStore";

const TARGET_LABELS: Record<string, string> = {
  overview: "综合研判",
  timeline: "时间窗口",
  bazi: "八字",
  ziwei: "紫微斗数",
  huangli: "黄历 / 日课",
  backtest: "历史验证",
  evidence: "古籍证据",
  conflicts: "模型分歧",
};

export function StockSelectionGate() {
  const params = useSearchParams();
  const target = params.get("target") || "overview";
  const [recent, setRecent] = useState<RecentStock[]>([]);

  useEffect(() => {
    setRecent(getRecentStocks());
  }, []);

  return (
    <Card className="mx-auto mt-8 max-w-[900px]" testId="stock-selection-gate">
      <CardHeader
        icon={<IconSearch size={15} />}
        title="请选择研究标的"
        dense
        right={<span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>进入：{TARGET_LABELS[target] ?? target}</span>}
      />
      <div className="p-5">
        <StockSearch variant="hero" target={target} />
        <div className="mt-6 border-t pt-4" style={{ borderColor: "var(--color-border)" }}>
          <div className="mb-3 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>最近搜索</div>
          {recent.length ? (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {recent.map((item) => (
                <RecentStockButton key={item.code} item={item} target={target} />
              ))}
            </div>
          ) : (
            <div className="rounded border border-dashed px-3 py-8 text-center text-[12px]" style={{ borderColor: "var(--color-border)", color: "var(--color-ink-faint)" }}>
              暂无近期搜索股票
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function RecentStockButton({ item, target }: { item: RecentStock; target: string }) {
  const href = `/stock/${item.code}/${target}`;
  return (
    <a href={href} className="rounded border px-3 py-2 text-left transition-colors hover:bg-white/[0.04]" style={{ borderColor: "var(--color-border)" }}>
      <div className="smp-num text-[13px]" style={{ color: "var(--color-gold)" }}>{item.code}</div>
      <div className="mt-1 text-[12px]" style={{ color: "var(--color-ink)" }}>{item.name || "A股标的"}</div>
      <div className="mt-1 text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>{item.exchange}</div>
    </a>
  );
}
