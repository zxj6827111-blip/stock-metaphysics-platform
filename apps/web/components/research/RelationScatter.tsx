"use client";

import { Card, CardHeader } from "@/components/cards/Card";
import type { ApiRelationStockResult } from "@/lib/api";

export function RelationScatter({ rows }: { rows: ApiRelationStockResult[] }) {
  const valid = rows.filter((row) => row.availability === "ok" && row.metrics.s_raw !== null && row.metrics.v_raw !== null);
  const maxS = Math.max(1, ...valid.map((row) => row.metrics.s_raw ?? 0));
  const maxV = Math.max(1, ...valid.map((row) => row.metrics.v_raw ?? 0));
  return (
    <Card testId="relation-scatter">
      <CardHeader title="S × V 关系分布" dense right={<span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>点大小代表 U</span>} />
      <div className="relative m-3 h-[230px] rounded border" style={{ borderColor: "var(--color-border)", background: "rgba(7,15,23,0.42)" }}>
        <div className="absolute inset-x-8 bottom-7 top-5 border-b border-l" style={{ borderColor: "var(--color-border-strong)" }}>
          {valid.slice(0, 160).map((row) => {
            const x = ((row.metrics.s_raw ?? 0) / maxS) * 96;
            const y = 96 - ((row.metrics.v_raw ?? 0) / maxV) * 92;
            const size = 5 + Math.min(10, (row.metrics.u_raw ?? 0) * 2);
            return (
              <span
                key={row.stock_code}
                title={`${row.stock_code} ${row.name} · S ${row.metrics.s_raw} · V ${row.metrics.v_raw} · U ${row.metrics.u_raw}`}
                className="absolute rounded-full"
                style={{ left: `${x}%`, top: `${y}%`, width: size, height: size, background: row.metrics.group === "扰动型" ? "var(--color-warn)" : row.metrics.group === "混合型" ? "var(--color-conflict)" : "var(--color-gold)", opacity: 0.82 }}
                data-testid={`relation-point-${row.stock_code}`}
              />
            );
          })}
        </div>
        <span className="absolute bottom-1 left-1/2 text-[10px]" style={{ color: "var(--color-ink-muted)" }}>协同关系 S</span>
        <span className="absolute left-1 top-1/2 -rotate-90 text-[10px]" style={{ color: "var(--color-ink-muted)" }}>扰动关系 V</span>
      </div>
      <p className="px-3 pb-3 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>S / V / U 仅统计流日行（external_day_row）；图中点为关系描述指标，不表示收益方向或交易建议。</p>
    </Card>
  );
}
