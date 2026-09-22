"use client";

import { Card, CardHeader, Chip } from "@/components/cards/Card";
import type { ApiRelationStockResult } from "@/lib/api";

const labels: Record<string, string> = { year: "流年", month: "流月", day: "流日" };
const natalLabels: Record<string, string> = { year: "股票年柱", month: "股票月柱", day: "股票日柱", hour: "股票时柱" };

export function RelationMatrix({ row, onClose }: { row: ApiRelationStockResult; onClose: () => void }) {
  const matrix = row.matrix;
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/55 p-3 md:items-center" role="dialog" aria-label={`${row.stock_code} 日期关系详情`}>
      <Card className="max-h-[90vh] w-full max-w-[1180px] overflow-auto" testId="relation-detail-drawer">
        <CardHeader title={`${row.stock_code} ${row.name || ""} · 日期 × 股票八字`} dense action={{ label: "关闭", onClick: onClose }} />
        <div className="space-y-3 p-3">
          <div className="flex flex-wrap gap-2 text-[12px]">
            <Chip tone="gold">日主 {row.day_master || "—"}</Chip>
            <Chip tone="flat">用神 {row.yong_shen.join("、") || "—"}</Chip>
            <Chip tone="flat">喜神 {row.xi_shen.join("、") || "—"}</Chip>
            <Chip tone="warn">关系规则 {matrix?.relation_rule_version ?? "—"}</Chip>
          </div>
          {matrix ? (
            <div className="overflow-x-auto">
              <table className="smp-table min-w-[840px]">
                <thead><tr><th>日期外部柱</th>{matrix.columns.map((column) => <th key={column}>{natalLabels[column] ?? column}</th>)}</tr></thead>
                <tbody>
                  {matrix.rows.map((matrixRow) => (
                    <tr key={matrixRow.source_pillar}>
                      <th>{labels[matrixRow.source_pillar] ?? matrixRow.source_pillar}<br /><span className="smp-num" style={{ color: "var(--color-gold)" }}>{matrixRow.source_ganzhi}</span></th>
                      {matrixRow.cells.map((cell) => (
                        <td key={cell.target_pillar} className="align-top">
                          <div className="smp-num text-[11px]" style={{ color: "var(--color-ink-muted)" }}>{cell.target_ganzhi}</div>
                          <div className="mt-1 flex flex-wrap gap-1">{cell.relation_types.length ? cell.relation_types.map((type) => <Chip key={type} tone={type.includes("冲") || type.includes("刑") || type.includes("害") || type.includes("破") ? "warn" : "flat"}>{type}</Chip>) : <span style={{ color: "var(--color-ink-faint)" }}>—</span>}</div>
                          {cell.events.length > 0 ? <div className="mt-1 text-[10.5px] leading-[16px]" style={{ color: "var(--color-ink-muted)" }}>{cell.events.map((event) => event.notes).join("；")}</div> : null}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="smp-disclaimer">该股票原局不可用，无法生成 3×4 矩阵；系统不会以 0 或空盘面替代。</div>}
          <div className="smp-disclaimer">该矩阵展示确定性关系事件，不代表预期收益率、上涨概率或交易建议。历史行为需要单独登记假设并进行 TRAIN / VALIDATION / OOS 研究。</div>
        </div>
      </Card>
    </div>
  );
}
