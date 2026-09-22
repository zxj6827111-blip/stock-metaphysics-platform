"use client";

import { Card, CardHeader, Chip } from "@/components/cards/Card";
import type { ApiRelationStockResult } from "@/lib/api";

const labels: Record<string, string> = { year: "流年", month: "流月", day: "流日" };
const natalLabels: Record<string, string> = { year: "股票年柱", month: "股票月柱", day: "股票日柱" };

function verdictTone(verdict: string): "gold" | "warn" | "flat" {
  if (verdict === "匹配") return "gold";
  if (verdict === "不匹配") return "warn";
  return "flat";
}

export function RelationMatrix({ row, onClose }: { row: ApiRelationStockResult; onClose: () => void }) {
  const matrix = row.matrix;
  const verdict = row.day_stem_verdict;
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-black/55 p-3 md:items-center" role="dialog" aria-label={`${row.stock_code} 日期关系详情`}>
      <Card className="max-h-[90vh] w-full max-w-[1180px] overflow-auto" testId="relation-detail-drawer">
        <CardHeader title={`${row.stock_code} ${row.name || ""} · 流年/流月/流日 × 股票年/月/日`} dense action={{ label: "关闭", onClick: onClose }} />
        <div className="space-y-3 p-3">
          <div className="flex flex-wrap gap-2 text-[12px]">
            <Chip tone="gold">日主 {row.day_master || "—"}</Chip>
            <Chip tone="flat">用神 {row.yong_shen.join("、") || "—"}</Chip>
            <Chip tone="flat">喜神 {row.xi_shen.join("、") || "—"}</Chip>
            <Chip tone="flat">忌神 {row.ji_shen.join("、") || "—"}</Chip>
            <Chip tone="flat">仇神 {row.chou_shen.join("、") || "—"}</Chip>
            <Chip tone="flat">闲神 {row.xian_shen.join("、") || "—"}</Chip>
            <Chip tone="warn">关系规则 {matrix?.relation_rule_version ?? "—"}</Chip>
            <Chip tone="flat">矩阵 schema {matrix?.schema_version ?? "—"}</Chip>
          </div>

          {verdict ? (
            <div className="rounded border px-3 py-2" data-testid="relation-day-verdict" style={{ borderColor: "var(--color-border)" }}>
              <div className="flex flex-wrap items-center gap-2 text-[12px]">
                <Chip tone="gold">流日 {verdict.day_stem}（{verdict.day_stem_wuxing}）</Chip>
                <Chip tone="flat">十神 {verdict.ten_god || "—"}（{verdict.ten_god_group || "—"}）</Chip>
                <Chip tone={verdictTone(verdict.verdict)}>{verdict.verdict} · {verdict.wuxing_role}</Chip>
              </div>
              <div className="mt-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }} data-testid="relation-day-verdict-reason">{verdict.reason}</div>
            </div>
          ) : null}

          {matrix ? (
            <div className="overflow-x-auto">
              <table className="smp-table min-w-[840px]" data-testid="relation-matrix-table">
                <thead><tr><th>日期外部柱</th>{matrix.columns.map((column) => <th key={column}>{natalLabels[column] ?? column}</th>)}</tr></thead>
                <tbody>
                  {matrix.rows.map((matrixRow) => (
                    <tr key={matrixRow.source_pillar} data-testid={`relation-matrix-row-${matrixRow.source_pillar}`}>
                      <th>{labels[matrixRow.source_pillar] ?? matrixRow.source_pillar}<br /><span className="smp-num" style={{ color: "var(--color-gold)" }}>{matrixRow.source_ganzhi}</span>
                        <div className="mt-1 text-[10.5px] font-normal" data-testid={`relation-matrix-row-types-${matrixRow.source_pillar}`} style={{ color: "var(--color-ink-muted)" }}>行内关系：{matrixRow.relation_types.join(" · ") || "—"}</div>
                      </th>
                      {matrixRow.cells.map((cell) => (
                        <td key={cell.target_pillar} className="align-top" data-testid={`relation-matrix-cell-${matrixRow.source_pillar}-${cell.target_pillar}`}>
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
          ) : <div className="smp-disclaimer">该股票原局不可用，无法生成 3×3 矩阵；系统不会以 0 或空盘面替代。</div>}
          <div className="smp-disclaimer">矩阵为流年/流月/流日 × 股票年/月/日 3×3；九格内关系事件全部保留。S/V/U、筛选与「行内关系」只统计流日行（external_day_row）。喜用神来自完整四柱原局，故喜忌部分仍可能间接受出生时辰模型影响。该矩阵不代表预期收益率、上涨概率或交易建议。</div>
        </div>
      </Card>
    </div>
  );
}
