"use client";

/**
 * 模型分歧中心（复刻 doc/ui-reference/07_model_conflict_center.png）。
 *
 * 数据**全部来自正式 ConflictDetector**（`src/core/orchestration/consensus.py`），
 * 不是展示层拼出来的示意。四条硬约束：
 *
 * 1. **禁止用平均分掩盖分歧**：每个模型的方向与分数分别列出；
 * 2. 冲突必须给出**可读原因**（方向 / 因子 / 时间尺度 / 假设四类）；
 * 3. `historical_conflict_stats` 未运行时必须显示 `NOT_RUN`，
 *    不能让人误以为"历史上的类似冲突已经统计过"；
 * 4. 不可用引擎不参与比较，也不以 0 分计入。
 */

import { useParams } from "next/navigation";
import { Suspense } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, ResearchStatusBadge } from "@/components/shell/PageState";
import { IconNodes, IconWarning } from "@/components/shell/Icons";
import { useAnalysis } from "@/lib/analysisStore";
import { engineCn } from "@/lib/dataSource";

const DIR_CN: Record<string, string> = { "1": "偏强 ↑", "0": "中性 →", "-1": "偏弱 ↓" };
const DIR_TONE: Record<string, string> = { "1": "var(--color-up)", "0": "var(--color-flat)", "-1": "var(--color-down)" };

function ConflictsInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const { analysis, loading, error, reload } = useAnalysis(code);

  const conflict = analysis?.conflict;
  const opinions = analysis?.opinions ?? {};

  return (
    <ResearchPage
      activeNav="conflicts"
      title="模型分歧中心"
      subtitle="识别多模型之间的不一致来源，辅助研究者判断冲突与偏差"
      seal="异"
      code={code}
      analysis={analysis}
      loading={loading}
      error={error}
      onReload={reload}
      loadingLabel="正在计算三模型观点与分歧…"
    >
      <Card>
        <CardHeader icon={<IconWarning size={15} />} title="当前分歧判定" dense />
        <div className="flex flex-wrap items-center gap-4">
          <div data-testid="conflict-level">
            <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              冲突级别
            </div>
            <div className="text-[26px] font-bold" style={{ color: conflict?.has_conflict ? "var(--color-warn)" : "var(--color-flat)" }}>
              {conflict?.has_conflict ? (conflict.conflict_level ?? "minor") : "none"}
            </div>
          </div>
          <div>
            <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              可用引擎
            </div>
            <div className="text-[20px] font-semibold">
              {analysis?.consensus?.available_engine_count ?? 0} / 3
            </div>
          </div>
          <div>
            <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              方向一致度
            </div>
            <div className="text-[20px] font-semibold">
              {analysis?.consensus?.agreement_score !== undefined
                ? analysis.consensus.agreement_score.toFixed(2)
                : "—"}
            </div>
          </div>
          <div className="ml-auto max-w-[420px]">
            <SectionNote>
              {analysis?.consensus?.interpretation ??
                "共识与历史有效性是两件事：方向一致度高**不代表**历史统计支持。"}
            </SectionNote>
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader icon={<IconNodes size={15} />} title="各模型观点总览（不做平均）" dense />
        <div className="grid grid-cols-3 gap-3" data-testid="opinion-cards">
          {["bazi", "ziwei", "huangli"].map((key) => {
            const op = opinions[key];
            const ok = op && op.availability === "ok" && op.score !== null;
            return (
              <div
                key={key}
                className="rounded border p-3"
                style={{ borderColor: "var(--color-line)" }}
                data-testid={`opinion-${key}`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-[13px] font-semibold">{engineCn(key)}</span>
                  <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                    {op?.engine_version || ""}
                  </span>
                </div>
                {ok ? (
                  <>
                    <div
                      className="mt-1 text-[22px] font-bold"
                      style={{ color: DIR_TONE[String(op!.direction)] ?? "var(--color-flat)" }}
                    >
                      {DIR_CN[String(op!.direction)] ?? "—"}
                    </div>
                    <div className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
                      规则强度 {op!.score}/100 · 置信度 {op!.confidence.toFixed(2)}
                    </div>
                  </>
                ) : (
                  <div className="mt-2 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
                    不可用（score = null，不计入共识分母）
                    <br />
                    {op?.note ?? "本次未产出该引擎观点"}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      <Card>
        <CardHeader icon={<IconWarning size={15} />} title="冲突归因" dense />
        {conflict?.reasons?.length ? (
          <ul className="space-y-2 text-[12.5px]" data-testid="conflict-reasons">
            {conflict.reasons.map((r, i) => (
              <li key={`${i}-${r.slice(0, 12)}`} className="flex gap-2">
                <span style={{ color: "var(--color-warn)" }}>▸</span>
                <span>{r}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
            当前无显著冲突：各可用模型方向一致或均为中性。
          </p>
        )}

        {conflict?.major_conflicts?.length ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-[12px]" data-testid="major-conflicts">
              <thead>
                <tr style={{ color: "var(--color-ink-muted)" }}>
                  <th className="text-left">模型</th>
                  <th className="text-left">方向</th>
                  <th className="text-left">规则强度</th>
                  <th className="text-left">主要依据</th>
                </tr>
              </thead>
              <tbody>
                {conflict.major_conflicts.map((c, i) => {
                  const row = c as Record<string, unknown>;
                  const reasons = (row.reasons as string[]) ?? [];
                  return (
                    <tr key={`${i}-${String(row.engine)}`} style={{ borderTop: "1px solid var(--color-line)" }}>
                      <td className="py-1">{engineCn(String(row.engine))}</td>
                      <td style={{ color: DIR_TONE[String(row.direction)] ?? "var(--color-flat)" }}>
                        {String(row.direction_label ?? "")}
                      </td>
                      <td className="smp-num">{String(row.score ?? "—")}</td>
                      <td style={{ color: "var(--color-ink-muted)" }}>{reasons.slice(0, 2).join("；") || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>

      <Card>
        <CardHeader icon={<IconNodes size={15} />} title="因子级 / 时间尺度 / 假设冲突" dense />
        <div className="space-y-2 text-[12.5px]">
          <ConflictList title="跨引擎同主题反向因子" items={conflict?.factor_conflicts as Record<string, unknown>[] | undefined} field="description" />
          <ConflictList title="时间尺度不一致" items={conflict?.time_horizon_conflicts as Record<string, unknown>[] | undefined} field="description" />
          <ConflictList title="假设差异（解释分歧来源，不代表谁对）" items={conflict?.assumption_conflicts as Record<string, unknown>[] | undefined} field="description" />
        </div>
      </Card>

      <Card>
        <CardHeader icon={<IconWarning size={15} />} title="历史类似冲突" dense />
        <ResearchStatusBadge status={analysis?.consensus?.research_status ?? "NOT_RUN"} />
        <div className="mt-2">
          <SectionNote>
            「历史类似冲突的后续表现」需要单独的历史统计。当前状态：
            <code>{JSON.stringify(conflict?.historical_conflict_stats ?? { status: "NOT_RUN" })}</code>
            <br />
            未运行时，本页面**不会**给出任何「历史上冲突后如何」的说法 ——
            那属于研究结论，必须由 <code>POST /api/v1/research/consensus</code> 产出。
          </SectionNote>
        </div>
      </Card>
    </ResearchPage>
  );
}

function ConflictList({
  title,
  items,
  field,
}: {
  title: string;
  items?: Record<string, unknown>[];
  field: string;
}) {
  return (
    <div>
      <div className="font-semibold">{title}</div>
      {items?.length ? (
        <ul className="mt-1 space-y-1" style={{ color: "var(--color-ink-muted)" }}>
          {items.slice(0, 6).map((it, i) => (
            <li key={`${i}-${String(it[field] ?? "").slice(0, 10)}`}>
              · {String(it[field] ?? JSON.stringify(it))}
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-1" style={{ color: "var(--color-ink-muted)" }}>
          未检出。
        </div>
      )}
    </div>
  );
}

export default function ConflictsPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <ConflictsInner />
    </Suspense>
  );
}
