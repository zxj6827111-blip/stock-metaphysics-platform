"use client";

import { Chip } from "@/components/cards/Card";
import type { ApiRelationStockResult } from "@/lib/api";

const firstExplanation = (values: string[]) => values[0] || "—";

function verdictTone(verdict: string): "gold" | "warn" | "flat" {
  if (verdict === "匹配") return "gold";
  if (verdict === "不匹配") return "warn";
  return "flat";
}

export function RelationStockTable({ rows, onSelect }: { rows: ApiRelationStockResult[]; onSelect: (row: ApiRelationStockResult) => void }) {
  return (
    <div className="overflow-x-auto" data-testid="relation-stock-table">
      <table className="smp-table min-w-[1180px]">
        <thead><tr><th>代码 / 名称</th><th>股票三柱</th><th>S</th><th>V</th><th>U</th><th>流日十神</th><th>流日喜忌</th><th>流日主要关系</th><th>命中说明</th><th>研究状态</th></tr></thead>
        <tbody>
          {rows.map((row) => {
            const verdict = row.day_stem_verdict;
            return (
              <tr key={row.stock_code} className="cursor-pointer" onClick={() => onSelect(row)} data-testid={`relation-row-${row.stock_code}`}>
                <td><button type="button" className="text-left" style={{ color: "var(--color-gold-strong)" }} onClick={() => onSelect(row)}><span className="smp-num">{row.stock_code}</span><br /><span>{row.name || "未命名"}</span></button></td>
                <td className="smp-num">{row.availability === "ok" ? `${row.natal.year} ${row.natal.month} ${row.natal.day}` : "不可用"}</td>
                <td className="smp-num">{row.metrics.s_raw ?? "—"}</td>
                <td className="smp-num">{row.metrics.v_raw ?? "—"}</td>
                <td className="smp-num">{row.metrics.u_raw ?? "—"}</td>
                <td>{verdict?.ten_god ? <span title={`十神分组：${verdict.ten_god_group}`}>{verdict.ten_god}</span> : "—"}</td>
                <td title={verdict?.reason || "原局喜忌资料不足"}>{verdict ? <Chip tone={verdictTone(verdict.verdict)}>{verdict.verdict} · {verdict.wuxing_role}</Chip> : "—"}</td>
                <td className="max-w-[260px]">{row.relation_types.slice(0, 4).map((value) => <Chip key={value} tone="flat">{value}</Chip>)}</td>
                <td className="max-w-[300px] text-[11px]" title={row.hit_explanations.join("；")} style={{ color: "var(--color-ink-muted)" }}>{firstExplanation(row.hit_explanations)}</td>
                <td><Chip tone={row.availability === "ok" ? "gold" : "warn"}>{row.availability === "ok" ? row.metrics.group : "不可用"}</Chip></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {!rows.length ? <div className="p-6 text-center text-[12px]" style={{ color: "var(--color-ink-muted)" }}>没有符合条件的关系结果</div> : null}
      <div className="px-3 pb-3 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>「流日十神」由股票日主 × 流日日干直接计算；「流日喜忌」是流日干五行在原局喜用忌仇闲中的角色。十神与喜忌是两套独立维度，不构成涨跌判断。</div>
    </div>
  );
}
