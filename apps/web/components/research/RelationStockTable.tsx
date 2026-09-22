"use client";

import { Chip } from "@/components/cards/Card";
import type { ApiRelationStockResult } from "@/lib/api";

const visible = (values: string[], max = 3) => values.length ? values.slice(0, max).join(" · ") : "—";
const firstExplanation = (values: string[]) => values[0] || "—";

export function RelationStockTable({ rows, onSelect }: { rows: ApiRelationStockResult[]; onSelect: (row: ApiRelationStockResult) => void }) {
  return (
    <div className="overflow-x-auto" data-testid="relation-stock-table">
      <table className="smp-table min-w-[1080px]">
        <thead><tr><th>代码 / 名称</th><th>股票八字</th><th>S</th><th>V</th><th>U</th><th>命中关系</th><th>命中说明</th><th>天干</th><th>地支</th><th>组合</th><th>十神 / 喜用</th><th>研究状态</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.stock_code} className="cursor-pointer" onClick={() => onSelect(row)} data-testid={`relation-row-${row.stock_code}`}>
              <td><button type="button" className="text-left" style={{ color: "var(--color-gold-strong)" }} onClick={() => onSelect(row)}><span className="smp-num">{row.stock_code}</span><br /><span>{row.name || "未命名"}</span></button></td>
              <td className="smp-num">{row.availability === "ok" ? `${row.natal.year} ${row.natal.month} ${row.natal.day} ${row.natal.hour}` : "不可用"}</td>
              <td className="smp-num">{row.metrics.s_raw ?? "—"}</td>
              <td className="smp-num">{row.metrics.v_raw ?? "—"}</td>
              <td className="smp-num">{row.metrics.u_raw ?? "—"}</td>
              <td>{row.relation_types.slice(0, 3).map((value) => <Chip key={value} tone="flat">{value}</Chip>)}</td>
              <td className="max-w-[320px] text-[11px]" title={row.hit_explanations.join("；")} style={{ color: "var(--color-ink-muted)" }}>{firstExplanation(row.hit_explanations)}</td>
              <td>{visible(row.stem_relations, 2)}</td>
              <td>{visible(row.branch_relations, 2)}</td>
              <td>{visible(row.compound_relations, 2)}</td>
              <td>{visible(row.ten_gods, 1)} / {visible(row.yong_shen_relations, 1)}</td>
              <td><Chip tone={row.availability === "ok" ? "gold" : "warn"}>{row.availability === "ok" ? row.metrics.group : "不可用"}</Chip></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length ? <div className="p-6 text-center text-[12px]" style={{ color: "var(--color-ink-muted)" }}>没有符合条件的关系结果</div> : null}
    </div>
  );
}
