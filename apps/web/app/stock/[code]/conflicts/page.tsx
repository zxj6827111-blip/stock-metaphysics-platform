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
 *
 * 视觉层级（V3-B，对齐 doc/ui-reference/07_model_conflict_center.png 的实测骨架）
 * ---------------------------------------------------------------------------
 * 参考图**不是**一路纵向堆下来的三段卡，而是三条横向带：
 *
 *   conflictBanner  y 250..352  h 102   ← 分歧摘要（级别 / 一致度 / 共识 / 主要原因）
 *   mainRow         y 352..779  h 427   ← 左：观点总览 + 对比矩阵 + 因子级冲突
 *                                          右：冲突归因 + 时间尺度与假设差异
 *   bottomRow       y 779..937  h 158   ← 左：冲突解释与研究限制
 *                                          右：历史类似冲突（NOT_RUN 如实显示）
 *
 * 数值来自 `e2e/fixtures/reference-anchors.json` 的 07 条目（V3-A 用 R1.1 新法重测）。
 * 参考图右半还有一张「多维度能力对比」雷达，**本页不画**（见上面第 5 条）；
 * 参考图的 `columnSplit.right` 因探测强度不唯一而记 null，因此本轮也不断言第二条纵边界。
 *
 * 演示场景切换器（`conflict-scenario-switcher`）是**验收工具**，不是参考图的产品内容。
 * V3-B 起它收进 conflictBanner 的卡头右侧，不再单独占一整行
 * （独立行实测高 37px + 12px 间距，正好把摘要带推到参考位置之外），
 * 三个场景入口与 `scenario-*` testid 全部保留。
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

      {/* ============ conflictBanner（参考图 y 250..352，h 102） ============ */}
      {/* 一行读完"分歧到哪一步了"：级别 / 可用引擎 / 方向一致度 / 共识标签 / 主要原因。
          解释性长文（共识 interpretation、"无冲突"的准确含义）不在这一带，
          它们属于 bottomRow 的「冲突解释与研究限制」—— 摘要带被文字撑高就不是摘要了。
          演示场景切换器收进卡头右侧：它是验收工具，不该新增一整行高度。 */}
      <Card testId="conflict-summary" anchor="conflict-banner">
        <CardHeader
          icon={<IconWarning size={15} />}
          title="分歧摘要"
          dense
          right={
            <div className="flex min-w-0 items-center gap-1.5">
              {isFixtureActive() ? (
                <span
                  className="flex items-center gap-1 text-[11px]"
                  data-testid="conflict-scenario-switcher"
                  title="演示场景：由真实 ConflictDetector 在固定输入上产出"
                >
                  <span style={{ color: "var(--color-ink-faint)" }}>场景</span>
                  {SCENARIOS.map((k) => {
                    const on = scenario === k;
                    return (
                      <Link
                        key={k}
                        href={`/stock/${code}/conflicts?fixture=${FIXTURE_QUERY_VALUE}&scenario=${k}`}
                        className="rounded-[4px] border px-1.5 py-[1px] text-[11px]"
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
                </span>
              ) : null}
              <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                逐模型并列，不取平均
              </span>
            </div>
          }
        />
        <CardBody className="!py-2">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
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
            <div className="min-w-[220px] flex-1">
              <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                主要原因
              </div>
              <div
                className="line-clamp-2 text-[12px] leading-[16px]"
                style={{ color: "var(--color-ink-sub)" }}
                data-testid="conflict-headline"
                title={conflict?.reasons?.[0] ?? "未检出不一致"}
              >
                {conflict?.has_conflict
                  ? (conflict.reasons[0] ?? "已检出分歧，但后端未给出原因文本")
                  : "本页比较的四个维度未检出不一致"}
              </div>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* mainRow 与 bottomRow 一起包进 tight 容器：参考图这两条带是**紧贴**的
          （mainRow 底 = bottomRow 顶 = y779），而外壳统一给 12px 卡间距。
          两条 12px 累起来把 bottomRow 顶边推到参考 +23.9 —— 只剩 0.1px 余量，
          等于一条会随字体渲染抖动的门。收成 4px 后 Δ 降到 +15.9：
          这是"改排布去贴参考"，不是"放宽阈值"。 */}
      <div className="space-y-1">
      {/* ============ mainRow（参考图 y 352..779，h 427） ============ */}
      {/* 左：观点总览 + 对比矩阵 + 因子级冲突；右：冲突归因 + 时间尺度与假设差异。
          分栏比 6:5（≈54.5:45.5）按参考图左边界 x=245..1010（宽 765 / 1411）取；
          参考图的第二条纵边界探测强度不唯一、fixture 里记 null，因此本轮不断言右边界。 */}
      <div
        className="grid grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]"
        data-anchor="main-row"
        data-testid="conflict-main-row"
      >
        <div className="space-y-3">
          {/* ---------- 各模型观点（不做平均） ---------- */}
          <Card testId="conflict-opinions">
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
                          {/* 该引擎的主要依据（后端 top_positive/negative_reasons 原值）。
                              参考图这一格里是"中长期向好 / 格局支撑"这类标签；
                              这里用后端真实理由文本而不是编一个标签词，
                              同时让观点卡读起来有分量（对比矩阵里给的是同一批理由）。 */}
                          <div className="mt-1.5 flex flex-wrap gap-1">
                            {[
                              ...(op!.top_positive_reasons ?? []),
                              ...(op!.top_negative_reasons ?? []),
                            ]
                              .slice(0, 2)
                              .map((r, i) => (
                                <span
                                  key={`${i}-${r.text.slice(0, 8)}`}
                                  className="rounded-[3px] border px-1.5 py-[1px] text-[10.5px] leading-[15px]"
                                  style={{
                                    borderColor: "var(--color-border)",
                                    color: "var(--color-ink-muted)",
                                  }}
                                  data-testid={`opinion-reason-${key}-${i}`}
                                  title={r.text}
                                >
                                  {r.text.length > 14 ? `${r.text.slice(0, 14)}…` : r.text}
                                </span>
                              ))}
                          </div>
                        </>
                      ) : (
                        <div
                          className="mt-1.5 text-[11.5px]"
                          style={{ color: "var(--color-ink-muted)" }}
                        >
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

          {/* ---------- 对比矩阵 ---------- */}
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
              <div className="overflow-x-auto">
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
                            style={{
                              color: ok ? DIR_TONE[String(op!.direction)] : "var(--color-ink-faint)",
                            }}
                          >
                            {ok ? (DIR_CN[String(op!.direction)] ?? "—") : "未产出"}
                          </td>
                          <td className="smp-num px-2 text-right">{ok ? op!.score : "—"}</td>
                          <td className="smp-num px-2 text-right">
                            {ok ? op!.confidence.toFixed(2) : "—"}
                          </td>
                          <td
                            className="max-w-[280px] truncate px-2"
                            style={{ color: "var(--color-ink-muted)" }}
                          >
                            {tops.join("；") || (ok ? "该引擎无明细理由" : (op?.note ?? "—"))}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </CardBody>
          </Card>

          {/* ---------- 因子级冲突 ---------- */}
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
          {/* ---------- 冲突归因 ---------- */}
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
                    本页未检出不一致。<b style={{ color: "var(--color-ink-sub)" }}>准确含义</b>
                    见下方「冲突解释与研究限制」。
                  </p>
                </div>
              )}
            </CardBody>
          </Card>

          {/* ---------- 时间尺度与假设差异 ---------- */}
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
        </div>
      </div>

      {/* ============ bottomRow（参考图 y 779..937，h 158） ============ */}
      {/* 左：冲突解释与研究限制（"无冲突"到底说了什么、共识 interpretation、
          以及"共识 ≠ 历史有效性"这条 Always-on 边界）；
          右：历史类似冲突。参考图这一带右卡是"历史类似分歧案例"表格，
          本系统该统计是 NOT_RUN ⇒ 如实显示未运行，不补造案例。 */}
      <div
        className="grid grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,6fr)_minmax(0,5fr)]"
        data-anchor="bottom-row"
        data-testid="conflict-bottom-row"
      >
        <Card testId="conflict-interpretation">
          <CardHeader icon={<IconNodes size={15} />} title="冲突解释与研究限制" dense />
          <CardBody className="!py-2 space-y-1.5">
            <SectionNote>
              <b style={{ color: "var(--color-ink-sub)" }}>「无冲突」的准确含义</b>
              ：只表示本页比较的四个维度（方向 / 因子主题 / 时间尺度 / 假设）
              没有检出不一致，<b>不代表</b>模型都正确、也不代表后续不会出现分歧；
              更<b>不代表</b>历史统计支持这些结论（那要看历史验证页的统计与负对照）。
            </SectionNote>
            <SectionNote>
              {consensus?.interpretation ?? (
                <>
                  共识与历史有效性是两件事：方向一致度高<strong>不代表</strong>历史统计支持。
                  共识只描述"模型之间是否一致"，不描述"是否赚得到钱"。
                </>
              )}
            </SectionNote>
          </CardBody>
        </Card>

        <Card testId="historical-conflict">
          <CardHeader icon={<IconWarning size={15} />} title="历史类似冲突" dense />
          <CardBody className="!py-2 space-y-1.5">
            {/* 紧凑徽标：状态与原始码常驻，原因清单与来源在下方 SourceMethod 里，
                不用非紧凑版（它会再画一个 reasons 列表 + 第二个 SourceMethod，
                把 bottomRow 从参考的 158px 撑到 220px）。 */}
            <ResearchStatusBadge status={histStatus} reasons={[]} compact showCode />
            <p className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              当前状态：{researchStatusLabel(histStatus)}。未运行时，本页面
              <strong>不会</strong>给出任何「历史上冲突后如何」的说法（历史胜率、
              类似冲突后上涨概率、最佳模型都不补造）——
              那属于研究结论，必须由研究流水线产出，不能由页面补造。
            </p>
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
              <RawField
                label="分歧判定来源"
                value="ConflictDetector（src/core/orchestration/consensus.py）"
              />
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
