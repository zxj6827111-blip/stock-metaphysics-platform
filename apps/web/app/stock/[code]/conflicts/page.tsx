"use client";

/**
 * 模型分歧中心（复刻 doc/ui-reference/07_model_conflict_center.png）。
 *
 * 数据**全部来自正式 ConflictDetector**（`src/core/orchestration/consensus.py`），
 * 不是展示层拼出来的示意。五条硬约束：
 *
 * 1. **禁止用平均分掩盖分歧**：每个模型的方向与分数分别列出；
 * 2. 冲突必须给出**可读原因**（方向 / 因子 / 时间尺度 / 假设四类）；
 * 3. `historical_conflict_stats` 未运行时必须显示 `NOT_RUN`，
 *    不能让人误以为"历史上的类似冲突已经统计过"；
 * 4. 不可用引擎不参与比较，也不以 0 分计入；
 * 5. **不捏造雷达维度**：参考图的多维能力雷达需要后端给出可比较的维度定义，
 *    当前没有这样的数据契约，因此本页用**真实可核对的量**
 *    （方向 / 规则强度 / 置信度 / 参与共识）做对比，而不是画一个看起来专业但
 *    维度是编出来的雷达图。
 *
 * 三种场景（无冲突 / 有冲突 / 模型不可用）都在同一套结构里显式呈现，
 * 用 `data-scenario` 标注，便于验收时逐一截图。
 */

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, ResearchStatusBadge, researchStatusLabel } from "@/components/shell/PageState";
import { RawField, SourceMethod } from "@/components/shell/SourceMethod";
import { IconNodes, IconWarning } from "@/components/shell/Icons";
import { useAnalysis } from "@/lib/analysisStore";
import { useBirthBasisParam } from "@/lib/useBirthBasisParam";
import { useHorizonParam } from "@/lib/useHorizonParam";
import type { ApiMultiAnalysis } from "@/lib/api";

type ApiMultiAnalysisOpinions = ApiMultiAnalysis["opinions"];
import { conflictLevelLabel, engineCn } from "@/lib/dataSource";
import { FIXTURE_QUERY_VALUE, conflictScenariosFixture, isFixtureActive } from "@/lib/fixture";

const DIR_CN: Record<string, string> = { "1": "偏强 ↑", "0": "中性 →", "-1": "偏弱 ↓" };
const DIR_TONE: Record<string, string> = {
  "1": "var(--color-up)",
  "0": "var(--color-flat)",
  "-1": "var(--color-down)",
};
const ENGINES = ["bazi", "ziwei", "huangli"] as const;

/** 演示模式下可显式选择的三种分歧场景（由真实检测器在固定输入上产出）。 */
const SCENARIOS = ["no_conflict", "conflict", "engine_unavailable"] as const;
type ScenarioKey = (typeof SCENARIOS)[number];

const SCENARIO_LABEL: Record<ScenarioKey, string> = {
  no_conflict: "无冲突",
  conflict: "有冲突",
  engine_unavailable: "模型不可用",
};

function ConflictsInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const searchParams = useSearchParams();
  const birthBasis = useBirthBasisParam();
  const horizon = useHorizonParam();
  const { analysis: rawAnalysis, loading, error, reload } = useAnalysis(
    code, "forward", undefined, birthBasis, horizon,
  );

  // 演示模式下用 ?scenario= 切换三种分歧场景（真实后端不会出现这个参数）
  const scenarioParam = searchParams.get("scenario") as ScenarioKey | null;
  const scenarioFixture =
    isFixtureActive() && scenarioParam && SCENARIOS.includes(scenarioParam)
      ? conflictScenariosFixture[scenarioParam]
      : null;

  // 只在基础分析已就绪时覆盖这三个字段：提前覆盖会得到一个缺 analysis_id /
  // 标的信息的半成品对象，上下文栏与页面外壳都会崩。
  const analysis =
    scenarioFixture && rawAnalysis
      ? {
          ...rawAnalysis,
          opinions: scenarioFixture.opinions as unknown as ApiMultiAnalysisOpinions,
          consensus: scenarioFixture.consensus,
          conflict: scenarioFixture.conflict,
        }
      : rawAnalysis;

  const conflict = analysis?.conflict;
  const consensus = analysis?.consensus;
  const opinions = analysis?.opinions ?? {};
  const histStats = conflict?.historical_conflict_stats as { status?: string } | undefined;
  const histStatus = histStats?.status ?? "NOT_RUN";

  const availableCount = ENGINES.filter((k) => opinions[k]?.availability === "ok").length;
  const unavailable = ENGINES.filter((k) => opinions[k]?.availability !== "ok");
  // 场景标签：验收需要分别截图"无冲突 / 有冲突 / 模型不可用"
  const scenario = unavailable.length
    ? "engine_unavailable"
    : conflict?.has_conflict
      ? "conflict"
      : "no_conflict";

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
      <div data-testid="conflict-scenario" data-scenario={scenario} />

      {isFixtureActive() ? (
        <div
          className="mb-2 flex flex-wrap items-center gap-1.5 rounded border px-2.5 py-1.5 text-[11.5px]"
          style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
          data-testid="conflict-scenario-switcher"
        >
          <span>演示场景（真实检测器在固定输入上产出）：</span>
          {SCENARIOS.map((k) => {
            const on = scenario === k;
            return (
              <Link
                key={k}
                href={`/stock/${code}/conflicts?fixture=${FIXTURE_QUERY_VALUE}&scenario=${k}`}
                className="rounded-[4px] border px-2 py-[2px]"
                style={{
                  borderColor: on ? "var(--color-gold)" : "var(--color-border)",
                  color: on ? "var(--color-gold)" : "var(--color-ink-sub)",
                }}
                data-testid={`scenario-${k}`}
              >
                {SCENARIO_LABEL[k]}
              </Link>
            );
          })}
        </div>
      ) : null}

      {/* ---------- ① 分歧摘要（与共识并列，不互相掩盖） ---------- */}
      <Card testId="conflict-summary">
        <CardHeader icon={<IconWarning size={15} />} title="分歧摘要" dense />
        <CardBody className="!py-2">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <div data-testid="conflict-level">
              <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                冲突级别
              </div>
              <div
                className="text-[24px] font-bold leading-tight"
                style={{ color: conflict?.has_conflict ? "var(--color-warn)" : "var(--color-flat)" }}
              >
                {conflictLevelLabel(conflict?.conflict_level, !!conflict?.has_conflict)}
              </div>
            </div>
            <div>
              <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                可用引擎
              </div>
              <div className="text-[19px] font-semibold leading-tight" data-testid="available-engines">
                {consensus?.available_engine_count ?? availableCount} / 3
              </div>
            </div>
            <div>
              <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                方向一致度
              </div>
              <div className="text-[19px] font-semibold leading-tight">
                {consensus?.agreement_score !== undefined
                  ? consensus.agreement_score.toFixed(2)
                  : "—"}
              </div>
            </div>
            <div>
              <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                共识标签（并列展示，不替代分歧）
              </div>
              <div className="text-[15px] font-semibold leading-tight" data-testid="consensus-label">
                {consensus?.label_cn ?? "—"}
                <span className="ml-2 text-[11.5px] font-normal" style={{ color: "var(--color-ink-muted)" }}>
                  {consensus?.participating_engines?.length
                    ? `参与：${consensus.participating_engines.map(engineCn).join("/")}`
                    : "无引擎参与"}
                </span>
              </div>
            </div>
            <div className="ml-auto max-w-[440px]">
              <SectionNote>
                {consensus?.interpretation ?? (
                  <>
                    共识与历史有效性是两件事：方向一致度高<strong>不代表</strong>历史统计支持。
                    共识只描述"模型之间是否一致"，不描述"是否赚得到钱"。
                  </>
                )}
              </SectionNote>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* ---------- ② 各模型观点（不做平均） ---------- */}
      <Card className="mt-3" testId="conflict-opinions">
        <CardHeader icon={<IconNodes size={15} />} title="各模型观点总览（不做平均）" dense />
        <CardBody className="!py-2">
          <div className="grid grid-cols-1 gap-2 md:grid-cols-3" data-testid="opinion-cards">
            {ENGINES.map((key) => {
              const op = opinions[key];
              const ok = op && op.availability === "ok" && op.score !== null;
              return (
                <div
                  key={key}
                  className="rounded border px-3 py-2"
                  style={{ borderColor: "var(--color-border)" }}
                  data-testid={`opinion-${key}`}
                  data-available={ok ? "1" : "0"}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[13px] font-semibold">{engineCn(key)}</span>
                    {ok ? (
                      <Chip tone="flat">{op!.confidence.toFixed(2)} 置信度</Chip>
                    ) : (
                      <Chip tone="flat">未产出</Chip>
                    )}
                  </div>
                  {ok ? (
                    <>
                      <div
                        className="mt-1 text-[21px] font-bold leading-tight"
                        style={{ color: DIR_TONE[String(op!.direction)] ?? "var(--color-flat)" }}
                      >
                        {DIR_CN[String(op!.direction)] ?? "—"}
                      </div>
                      <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                        规则强度 {op!.score}/100（不是预期收益率）
                      </div>
                    </>
                  ) : (
                    <div className="mt-1.5 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                      不可用（score = null，不计入共识分母）
                      <br />
                      {op?.note ?? "本次未产出该引擎观点"}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </CardBody>
      </Card>

      {/* ---------- ③ 左：对比矩阵 / 右：归因与假设 ---------- */}
      <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="space-y-3">
          <Card testId="conflict-matrix">
            <CardHeader
              icon={<IconNodes size={15} />}
              title="模型结论对比矩阵"
              dense
              right={
                <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                  逐模型并列，不取平均
                </span>
              }
            />
            <CardBody className="!py-1.5">
              <table className="w-full text-[11.5px]" data-testid="major-conflicts">
                <thead>
                  <tr style={{ color: "var(--color-ink-muted)" }}>
                    <th className="px-2 text-left font-medium">模型</th>
                    <th className="px-2 text-left font-medium">方向</th>
                    <th className="px-2 text-right font-medium">规则强度</th>
                    <th className="px-2 text-right font-medium">置信度</th>
                    <th className="px-2 text-left font-medium">主要依据</th>
                  </tr>
                </thead>
                <tbody>
                  {ENGINES.map((key) => {
                    const op = opinions[key];
                    const ok = op && op.availability === "ok" && op.score !== null;
                    const tops = ok
                      ? [...(op!.top_positive_reasons ?? []), ...(op!.top_negative_reasons ?? [])]
                          .map((r) => r.text)
                          .slice(0, 2)
                      : [];
                    return (
                      <tr
                        key={key}
                        style={{ borderTop: "1px solid var(--color-border)" }}
                        data-testid={`matrix-row-${key}`}
                      >
                        <td className="px-2 py-[3px]">{engineCn(key)}</td>
                        <td
                          className="px-2"
                          style={{ color: ok ? DIR_TONE[String(op!.direction)] : "var(--color-ink-faint)" }}
                        >
                          {ok ? (DIR_CN[String(op!.direction)] ?? "—") : "未产出"}
                        </td>
                        <td className="smp-num px-2 text-right">{ok ? op!.score : "—"}</td>
                        <td className="smp-num px-2 text-right">{ok ? op!.confidence.toFixed(2) : "—"}</td>
                        <td className="max-w-[280px] truncate px-2" style={{ color: "var(--color-ink-muted)" }}>
                          {tops.join("；") || (ok ? "该引擎无明细理由" : (op?.note ?? "—"))}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </CardBody>
          </Card>

          <Card testId="factor-conflicts">
            <CardHeader
              icon={<IconWarning size={15} />}
              title="因子级冲突（跨引擎同主题反向）"
              dense
              right={
                <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                  同一引擎内部不对比
                </span>
              }
            />
            <CardBody className="!py-2">
              {conflict?.factor_conflicts?.length ? (
                <ul className="space-y-1.5 text-[11.5px]" data-testid="factor-conflict-list">
                  {(conflict.factor_conflicts as Record<string, unknown>[]).map((c, i) => (
                    <li key={`${i}-${String(c.tag)}`} className="flex flex-wrap items-center gap-x-2">
                      <Chip tone="gold">{String(c.tag)}</Chip>
                      <code className="smp-num">{String(c.factor_a)}</code>
                      <span style={{ color: DIR_TONE[String(c.direction_a)] }}>
                        {DIR_CN[String(c.direction_a)]}
                      </span>
                      <span style={{ color: "var(--color-ink-faint)" }}>vs</span>
                      <code className="smp-num">{String(c.factor_b)}</code>
                      <span style={{ color: DIR_TONE[String(c.direction_b)] }}>
                        {DIR_CN[String(c.direction_b)]}
                      </span>
                      <span style={{ color: "var(--color-ink-muted)" }}>
                        （{engineCn(String(c.engine_a))} vs {engineCn(String(c.engine_b))}）
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                  未检出跨引擎的同主题反向因子。这不等于"各引擎在因子层完全一致"：
                  只有带相同主题标签、且方向相反的因子才会被检出。
                </p>
              )}
            </CardBody>
          </Card>
        </div>

        <div className="space-y-3">
          <Card testId="conflict-attribution">
            <CardHeader icon={<IconWarning size={15} />} title="冲突归因" dense />
            <CardBody className="!py-2">
              {conflict?.has_conflict ? (
                <ul className="space-y-1.5 text-[12px]" data-testid="conflict-reasons">
                  {conflict.reasons.map((r, i) => (
                    <li key={`${i}-${r.slice(0, 12)}`} className="flex gap-2">
                      <span style={{ color: "var(--color-warn)" }}>▸</span>
                      <span>{r}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-[12px]" data-testid="no-conflict-note">
                  {conflict?.reasons?.length ? (
                    <ul className="space-y-1.5">
                      {conflict.reasons.map((r, i) => (
                        <li key={`${i}-${r.slice(0, 12)}`} className="flex gap-2">
                          <span style={{ color: "var(--color-flat)" }}>▸</span>
                          <span>{r}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <p className="mt-1" style={{ color: "var(--color-ink-muted)" }}>
                    <b style={{ color: "var(--color-ink-sub)" }}>「无冲突」的准确含义</b>
                    ：只表示本页比较的四个维度（方向 / 因子主题 / 时间尺度 / 假设）
                    没有检出不一致，<b>不代表</b>模型都正确、也不代表后续不会出现分歧；
                    更<b>不代表</b>历史统计支持这些结论（那要看 ② 的统计与负对照）。
                  </p>
                </div>
              )}
            </CardBody>
          </Card>

          <Card testId="conflict-horizon">
            <CardHeader icon={<IconNodes size={15} />} title="时间尺度与假设差异" dense />
            <CardBody className="!py-2 space-y-2">
              <ConflictList
                title="时间尺度不一致（同一引擎短周期 vs 长周期反向）"
                items={conflict?.time_horizon_conflicts as Record<string, unknown>[] | undefined}
                field="description"
              />
              <ConflictList
                title="假设差异（解释分歧来源，不代表谁对）"
                items={conflict?.assumption_conflicts as Record<string, unknown>[] | undefined}
                field="description"
              />
            </CardBody>
          </Card>

          <Card testId="historical-conflict">
            <CardHeader icon={<IconWarning size={15} />} title="历史类似冲突" dense />
            <CardBody className="!py-2 space-y-2">
              <ResearchStatusBadge status={histStatus} />
              <SectionNote>
                当前状态：{researchStatusLabel(histStatus)}。未运行时，本页面
                <strong>不会</strong>给出任何「历史上冲突后如何」的说法 ——
                那属于研究结论，必须由研究流水线产出，不能由页面补造。
              </SectionNote>
              {histStats && Object.keys(histStats).length > 1 ? (
                <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                  {Object.entries(histStats)
                    .filter(([k]) => k !== "status")
                    .map(([k, v]) => (
                      <div key={k}>
                        {k}：{typeof v === "object" ? JSON.stringify(v) : String(v)}
                      </div>
                    ))}
                </div>
              ) : (
                <p className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                  没有可用的历史冲突统计字段（响应里只有状态，没有样本量与结果分布）。
                </p>
              )}
              <SourceMethod label="来源与方法" testId="conflict-source-method">
                <RawField label="historical_conflict_stats.status" value={histStatus} />
                <RawField label="产出接口" value="POST /api/v1/research/consensus" />
                <RawField label="analysis_id" value={analysis?.analysis_id ?? "（尚未加载）"} />
                {ENGINES.map((key) => (
                  <RawField
                    key={key}
                    label={`${engineCn(key)} engine_version`}
                    value={opinions[key]?.engine_version ?? "（本次未产出）"}
                  />
                ))}
                <RawField label="分歧判定来源" value="ConflictDetector（src/core/orchestration/consensus.py）" />
              </SourceMethod>
            </CardBody>
          </Card>
        </div>
      </div>
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
      <div className="text-[11.5px] font-semibold" style={{ color: "var(--color-ink-sub)" }}>
        {title}
      </div>
      {items?.length ? (
        <ul className="mt-1 space-y-1 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          {items.slice(0, 6).map((it, i) => (
            <li key={`${i}-${String(it[field] ?? "").slice(0, 10)}`}>· {String(it[field] ?? JSON.stringify(it))}</li>
          ))}
        </ul>
      ) : (
        <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
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
