"use client";

/**
 * 历史验证页（复刻 doc/ui-reference/05_backtest_validation.png）。
 *
 * **本页最重要的一条纪律**：
 *   术数规则强度 与 统计有效性 必须**视觉分区**，不能混在一起看。
 *   分区靠 ① / ② 身份标签与各自的行承载，**不靠把页面拉高**。
 *
 * 结构（参考图 05 实测骨架，见 e2e/fixtures/reference-anchors.json → 05-backtest）
 * --------------------------------------------------------------------------
 * Hero(94) → 上下文栏(54) → 研究条件两行(67) → 九宫格指标(85) →
 * 收益分布 | 持有期对比(194) → 四张对照卡(172) → 实验结果明细(第二屏)。
 *
 * 四件**不做**的事（参考图里有、但我们没有数据支撑）：
 * 1. **不画收益分布**：需要逐样本收益序列，接口只给聚合量；
 * 2. **不画策略净值**：没有可复现的组合规则、仓位与交易成本模型；
 * 3. **不做逐因子胜率/IC**：本页数据源不含这些字段，缺失就显示不可用；
 * 4. **不触发任何研究计算**：页面只读已有结果（EventStudy + 已入库实验），
 *    绝不因为"打开页面"就跑全市场研究。
 *
 * 反过来必须醒目的：**负对照失效**（Jaccard > 0.9 记 INVALID_CONTROL）、
 * 样本不足、数据降级、以及"未做样本外验证"这一事实。
 *
 * V3-A.1 的收口点（独立审核 CHANGES_REQUIRED 的三条）：
 *   * ① 规则强度不再单独占一条横条，与 ② 合并为一张两行紧凑卡；
 *   * 持有期卡回到"图为主角"，大段警告/方法论移到负对照区与第二屏；
 *   * 对照行恢复参考图的**四列**结构，缺数据的列如实标不可用而不是拼两张卡。
 */

import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Card, CardBody, CardHeader, Chip, SectionTag } from "@/components/cards/Card";
import { HorizonComparisonChart } from "@/components/charts/Charts";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import {
  PageLoading,
  ResearchStatusBadge,
  UnavailableBlock,
  researchStatusLabel,
} from "@/components/shell/PageState";
import { RawField, SourceMethod } from "@/components/shell/SourceMethod";
import {
  IconArrowDown,
  IconArrowUp,
  IconBook,
  IconChart,
  IconClock,
  IconDatabase,
  IconDiamond,
  IconFlask,
  IconGauge,
  IconLayers,
  IconTarget,
} from "@/components/shell/Icons";
import {
  api,
  endpoints,
  type ApiEventStudy,
  type ApiExperimentDetail,
  type ApiExperimentSummary,
} from "@/lib/api";
import { useAnalysis } from "@/lib/analysisStore";
import { useBirthBasisParam } from "@/lib/useBirthBasisParam";
import { useHorizonParam } from "@/lib/useHorizonParam";
import { engineCn, pct } from "@/lib/dataSource";
import { isFixtureActive, backtestFixture, experimentFixture } from "@/lib/fixture";

/** 演示模式下也没有真实实验可读时，界面必须明说而不是留白。 */
const MIN_SAMPLES = 30;

/** 参考图 05 对照行的后两列 = 本系统真实存在的负对照 variant（只做字段映射，不重算）。 */
const CONTROL_COLUMNS = [
  {
    testId: "control-random",
    anchor: "control-random",
    title: "随机对照",
    variants: ["random_birth_date", "random_factor"],
    warningTestId: "invalid-control-warning",
    meaning:
      "随机出生日 / 随机因子：把事件集合按随机出生日或随机因子重新挑一遍，看真实因子是否只是运气。",
  },
  {
    testId: "control-shift",
    anchor: "control-shift",
    title: "出生日期平移对照",
    variants: ["shift_plus_7d", "shift_minus_7d"],
    warningTestId: "invalid-control-warning-shift",
    meaning:
      "±7 天平移：把出生日期整体前后挪一周，检验结果是否只对某一个日期敏感（日历效应而非因子效应）。",
  },
] as const;

/** 参考图前两列：本系统没有对应产出，如实标不可用，不用汇总数字拼一张假分组图。 */
const UNAVAILABLE_COLUMNS = [
  {
    testId: "control-yearly",
    anchor: "control-yearly",
    title: "年度稳定性",
    icon: "clock" as const,
    what: "按年度聚合的收益稳定性",
    reason:
      "本页读取的是已入库的逐持有期事件研究与负对照结果，接口没有按年度切分的产出，因此不显示年度柱。",
    detail:
      "要补这一列必须先由研究流水线产出逐年分组（含每年样本量与口径版本），再由本页只读展示。" +
      "用整期均值除以年数、或按现有 4 个持有期反推年度序列，都会画出一张**没有样本支撑**的图。",
  },
  {
    testId: "control-regime",
    anchor: "control-regime",
    title: "牛/熊/震荡分组",
    icon: "layers" as const,
    what: "按市场状态分组的策略/基准收益",
    reason:
      "市场状态（牛/熊/震荡）的区间划分与分组统计没有对应产出；本页不自行按涨跌幅事后划分区间。",
    detail:
      "事后用涨跌幅定义牛熊再回头分组，等于用结果挑样本（AGENTS.md §13 禁止用有利子集修复结论）。" +
      "需要这一列必须先有一份与样本无关的、版本化的市场状态日历。",
  },
] as const;

function BacktestInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const birthBasis = useBirthBasisParam();
  const horizon = useHorizonParam();
  const { analysis, loading, error, reload } = useAnalysis(
    code,
    "forward",
    undefined,
    birthBasis,
    horizon,
  );

  const [es, setEs] = useState<ApiEventStudy | null>(null);
  const [btLoading, setBtLoading] = useState(false);
  const [btError, setBtError] = useState<string | null>(null);

  const [experiments, setExperiments] = useState<ApiExperimentSummary[]>([]);
  const [expId, setExpId] = useState<string>("");
  const [detail, setDetail] = useState<ApiExperimentDetail | null>(null);
  const [expError, setExpError] = useState<string | null>(null);

  const loadBacktest = useCallback(
    async (analysisId: string) => {
      if (isFixtureActive() && code === "600519") {
        setEs(backtestFixture);
        setExperiments(experimentFixture.list);
        setExpId((prev) => prev || experimentFixture.list[0]?.experiment_id || "");
        return;
      }
      setBtLoading(true);
      setBtError(null);
      try {
        setEs(await api.get<ApiEventStudy>(endpoints.backtest(analysisId)));
      } catch (e) {
        setBtError(e instanceof Error ? e.message : String(e));
      } finally {
        setBtLoading(false);
      }
    },
    [code],
  );

  const loadExperiments = useCallback(async () => {
    if (isFixtureActive() && code === "600519") return;
    try {
      const data = await api.get<{ items: ApiExperimentSummary[] }>(
        endpoints.researchExperiments(),
      );
      setExperiments(data.items ?? []);
      setExpId((prev) => prev || data.items?.[0]?.experiment_id || "");
    } catch (e) {
      setExpError(e instanceof Error ? e.message : String(e));
    }
  }, [code]);

  useEffect(() => {
    if (analysis?.analysis_id) void loadBacktest(analysis.analysis_id);
  }, [analysis?.analysis_id, loadBacktest]);

  useEffect(() => {
    void loadExperiments();
  }, [loadExperiments]);

  // 选中实验的详情：只读接口，不触发任何计算
  useEffect(() => {
    if (!expId) return;
    if (isFixtureActive() && code === "600519") {
      setDetail(experimentFixture.details[expId] ?? null);
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const d = await api.get<ApiExperimentDetail>(endpoints.researchExperiment(expId));
        if (!cancelled) setDetail(d);
      } catch (e) {
        if (!cancelled) setExpError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [expId, code]);

  const status = es?.research_status ?? "NOT_RUN";
  const horizons = es?.horizons ?? [];
  const primary = horizons.find((h) => h.horizon === 20) ?? horizons[horizons.length - 1] ?? null;
  const isRealData = es?.data_source?.is_real !== false;

  const grid = useMemo(() => buildExperimentGrid(detail), [detail]);

  return (
    <ResearchPage
      activeNav="backtest"
      title="历史验证"
      subtitle="用历史数据验证术数因子的有效性，让传统智慧经受现代金融的检验"
      seal="验"
      heroVariant="statistics"
      code={code}
      analysis={analysis}
      loading={loading}
      error={error}
      onReload={reload}
      loadingLabel="正在读取历史验证结果…"
    >
      {/* ============ 参考图 05 的「研究条件/筛选条」：① + ② 两行紧凑卡 ============ */}
      {/* 分区语义（AGENTS.md §9.6 / §16.1）由 ① / ② 两行各自的身份标签承载，
          不再额外挂一条整宽 rule-strength 横条 —— 独立横条每行 ≈36px，
          会把图表行整体推下去，而参考图这一带只有 67px。
          两个 data-testid 随标签保留，审计仍可逐字指认分区。 */}
      <Card testId="research-status-card" anchor="filter-bar">
        <CardBody className="!py-1">
          <h2 className="sr-only">研究状态与条件</h2>
          {/* 第一行：① 术数规则强度 —— 只显示分数/不可用 + 方向，置信度与解释进 details */}
          <div
            className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11.5px] leading-[18px]"
            data-testid="rule-strength"
          >
            <SectionTag
              index="①"
              label="术数规则强度 · 确定性结果"
              tone="gold"
              testId="section-deterministic"
            />
            {(["bazi", "ziwei", "huangli"] as const).map((k) => {
              const op = analysis?.opinions?.[k];
              const ok = op && op.availability === "ok" && op.score !== null;
              return (
                <span
                  key={k}
                  className="flex items-baseline gap-1"
                  data-testid={`rule-strength-${k}`}
                >
                  <span style={{ color: "var(--color-ink-muted)" }}>{engineCn(k)}</span>
                  <b className="smp-num text-[12.5px]">{ok ? `${op!.score}/100` : "不可用"}</b>
                  {ok ? (
                    <span
                      style={{
                        color:
                          op!.direction > 0
                            ? "var(--color-up)"
                            : op!.direction < 0
                              ? "var(--color-down)"
                              : "var(--color-flat)",
                      }}
                      title={`方向 ${op!.direction}`}
                    >
                      {op!.direction > 0 ? "↑" : op!.direction < 0 ? "↓" : "→"}
                    </span>
                  ) : null}
                </span>
              );
            })}
            <span className="flex items-baseline gap-1" data-testid="rule-strength-consensus">
              <span style={{ color: "var(--color-ink-muted)" }}>共识</span>
              <b className="text-[12.5px]">{analysis?.consensus?.label_cn ?? "不可用"}</b>
            </span>
            <details className="group" data-testid="rule-strength-detail">
              <summary
                className="cursor-pointer list-none text-[11px]"
                style={{ color: "var(--color-ink-muted)" }}
              >
                一致度 / 置信度与口径
              </summary>
              <div
                className="mt-1 text-[11px] leading-[16px]"
                style={{ color: "var(--color-ink-muted)" }}
              >
                一致度 {analysis?.consensus?.agreement_score?.toFixed(2) ?? "—"}；
                置信度：
                {(["bazi", "ziwei", "huangli"] as const)
                  .map((k) => {
                    const op = analysis?.opinions?.[k];
                    return `${engineCn(k)} ${
                      op && op.availability === "ok" ? op.confidence.toFixed(2) : "不可用"
                    }`;
                  })
                  .join(" · ")}
                。不可用的引擎<strong>不以 0 分聚合</strong>（§2.4）。
                规则强度不是上涨概率；历史有效性只能由 ② 回答。
              </div>
            </details>
          </div>
          {/* 第二行：② 统计有效性 —— 研究状态 + 数据源 + 实验审计字段，详情折叠 */}
          <div
            className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11.5px] leading-[18px]"
            data-testid="research-conditions"
          >
            <SectionTag
              index="②"
              label="统计有效性 · 历史数据"
              tone="muted"
              testId="section-empirical"
            />
            <ResearchStatusBadge status={status} reasons={es?.research_status_reasons ?? []} compact showCode />
            <Chip tone={isRealData ? "flat" : "gold"} testId="data-source-chip">
              数据源 {isRealData ? "真实" : "非真实（合成/降级）"}
            </Chip>
            {es?.data_source?.benchmark_degraded ? <Chip tone="gold">基准降级</Chip> : null}
            <InlineField label="实验标识" value={es?.experiment_id || "（尚未运行）"} />
            <InlineField label="事件数" value={es ? String(es.event_count) : "—"} />
            <InlineField label="股票池" value={es ? String(es.universe_size) : "—"} />
            <InlineField
              label="因子"
              value={es?.factor_ids?.length ? es.factor_ids.join("、") : "（无）"}
            />
            <details data-testid="research-conditions-detail">
              <summary
                className="cursor-pointer list-none text-[11px]"
                style={{ color: "var(--color-ink-muted)" }}
              >
                NO_SIGNAL 是什么意思、本页会不会重算
              </summary>
              <div
                className="mt-1 text-[11px] leading-[16px]"
                style={{ color: "var(--color-ink-muted)" }}
              >
                <code>NO_SIGNAL</code> 表示<strong>真实因子未优于随机对照</strong>，是如实输出而非故障；
                某个持有期平均收益为正<strong>不构成</strong>"验证有效"。本页<strong>只读</strong>已有结果，
                打开页面不触发任何全市场重算。研究状态由
                <code>src/research/status.py</code> 给出，不由本页前端推断。
              </div>
            </details>
          </div>
        </CardBody>
      </Card>

      {btError ? (
        <Card testId="backtest-error">
          <CardBody>
            <div className="text-[13px]" style={{ color: "var(--color-warn)" }}>
              历史验证加载失败：{btError}
            </div>
          </CardBody>
        </Card>
      ) : null}

      {/* ============ 统计指标九宫格（参考图 05：一行 9 块，85px） ============ */}
      {/* 没有真实数据时磁贴**照排**，值显示「— / 不可用 / 未验证」而不是撤掉整行：
          磁贴行是"这一格系统能回答什么"的目录，空槽位本身就是信息（§2.4 不以 0 冒充）。
          警告与解释压成一行可展开的 summary，不再用大型 UnavailableBlock 撑高。 */}
      <Card testId="stats-summary">
        {/* 横向只留 4px：参考图这一带是**贴满内容宽**的九块磁贴（x=224..1657），
            不是卡内再缩一档。纵向仍按 !py 收紧。 */}
        <CardBody className="!px-1 !py-1.5">
          <h2 className="sr-only">统计摘要（主持有期）</h2>
          {btLoading ? (
            <div className="py-3 text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
              正在加载…
            </div>
          ) : (
            <>
              <div
                className="grid grid-cols-3 gap-2 md:grid-cols-5 xl:grid-cols-9"
                data-testid="stats-metrics"
                data-anchor="summary-metrics"
              >
                {buildMetrics(primary).map((m) => (
                  <Metric key={m.label} {...m} />
                ))}
              </div>
              <details
                className="mt-1"
                data-testid="stats-summary-note"
                style={{ color: "var(--color-ink-muted)" }}
              >
                <summary
                  className="cursor-pointer list-none text-[11px]"
                  style={{
                    color: statsWarningTone(primary) === "warn" ? "var(--color-warn)" : "inherit",
                  }}
                  data-testid="small-sample-warning"
                >
                  {statsWarningLine(primary)}
                </summary>
                <div className="mt-1 text-[11px] leading-[16px]">
                  {statsWarningDetail(primary)}
                </div>
              </details>
            </>
          )}
        </CardBody>
      </Card>

      {/* ============ 首屏图表行：收益分布 | 持有期对比（参考图 05 两栏 708:715） ============ */}
      {/* 之前这里排着 6 张「研究卡位」空占位卡（每张 ~160px，共 ~960px），
          把唯一有真实数据的持有期对比推到 y=1255 —— 空卡位假装能力，
          既撑高页面又虚报能力，一并删除。没有真实数据的槽位改为如实标不可用。
          两栏用 items-stretch 拉平：参考图这两张卡同高（都到 y=589）。 */}
      <div
        className="grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.01fr)]"
        data-anchor="chart-row"
      >
        <Card testId="distribution-panel" anchor="primary-chart">
          <CardHeader
            icon={<IconChart size={15} />}
            title="收益分布"
            dense
            right={<Chip tone="flat">不可用</Chip>}
          />
          <CardBody className="!py-1.5">
            <div className="text-[12px]">
              <b style={{ color: "var(--color-ink)" }}>收益分布：不可用</b>
              <span className="ml-2 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
                事件研究接口只回传逐持有期汇总，没有逐样本收益序列。
              </span>
            </div>
            <details className="mt-1" data-testid="distribution-unavailable-detail">
              <summary
                className="cursor-pointer list-none text-[11px]"
                style={{ color: "var(--color-ink-muted)" }}
              >
                为什么不用高斯密度补一张示意分箱，也不能由汇总反推
              </summary>
              <div
                className="mt-1 text-[11px] leading-[16px]"
                style={{ color: "var(--color-ink-muted)" }}
              >
                <p>
                  <strong>不能高斯生成</strong>：接口给出的只有
                  <code>mean_return / median_return / std_return / up_rate</code>
                  这类逐持有期聚合量。用它们配一个正态密度切分箱，画出来的每一根柱子都是假设出来的，
                  却会读成"历史上这 1,248 个样本长这样"—— 这属于把合成数据伪装成真实数据
                  （AGENTS.md §13），也是本页最容易被误用成研究证据的一张图。
                </p>
                <p className="mt-1">
                  <strong>不能反推</strong>：真实收益分布是偏态且有厚尾的，仅凭均值与标准差无法还原分位数、
                  极值与逐样本顺序；反推出来的"最大回撤""分位收益"没有一条可追溯到样本。
                </p>
                <p className="mt-1">
                  要补这张卡，必须由研究流水线额外产出逐样本收益序列（含 <code>as_of</code> 裁剪记录），
                  本页只读展示。
                </p>
              </div>
            </details>
          </CardBody>
        </Card>

        <Card testId="horizon-comparison" anchor="holding-period-card">
          <CardHeader
            icon={<IconChart size={15} />}
            title="持有期对比"
            dense
            right={
              experiments.length ? (
                <div className="flex min-w-0 items-center gap-1.5">
                  <select
                    value={expId}
                    onChange={(e) => setExpId(e.target.value)}
                    className="max-w-[300px] truncate rounded border px-1.5 py-0.5 text-[11px] outline-none"
                    style={{
                      borderColor: "var(--color-border)",
                      background: "transparent",
                      color: "var(--color-ink)",
                    }}
                    data-testid="experiment-select"
                    title={grid.experimentName}
                  >
                    {experiments.map((s) => (
                      <option key={s.experiment_id} value={s.experiment_id}>
                        [{s.kind}] {s.name} · {s.status} · {s.created_at.slice(0, 10)}
                      </option>
                    ))}
                  </select>
                  {detail?.experiment.status ? (
                    <Chip
                      tone={detail.experiment.status === "INVALID_CONTROL" ? "gold" : "flat"}
                      testId="holding-experiment-status"
                    >
                      {detail.experiment.status}
                    </Chip>
                  ) : null}
                </div>
              ) : null
            }
          />
          <CardBody className="!py-1.5">
            {experiments.length ? (
              detail ? (
                grid.labels.length ? (
                  <>
                    <div data-testid="horizon-chart-wrap">
                      <HorizonComparisonChart
                        labels={grid.labels}
                        series={grid.series}
                        height={108}
                        captionLines={1}
                      />
                    </div>
                    {/* 一行 metadata：区间 / 基准 / 取数口径。
                        "这张图只画了什么、没画什么"的完整说明在第二屏「明细与方法限制」，
                        不放首屏卡：参考图这张卡 194px 里只有卡头 + 图。 */}
                    <div
                      className="mt-1 truncate text-[10.5px]"
                      style={{ color: "var(--color-ink-muted)" }}
                      data-testid="holding-meta"
                      title={grid.metaLine}
                    >
                      {grid.metaLine}
                    </div>
                  </>
                ) : (
                  <UnavailableBlock
                    what="持有期对比图"
                    reason="该实验没有可用的持有期结果。"
                  />
                )
              ) : (
                <div className="py-3 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
                  正在读取实验详情…（只读接口，不触发重算）
                </div>
              )
            ) : (
              <UnavailableBlock
                what="已入库研究实验"
                reason={
                  expError ||
                  "本地没有已入库的研究实验。历史验证结果必须由研究流水线产出后才可读取；本页不会自动运行全市场研究。"
                }
              />
            )}
          </CardBody>
        </Card>
      </div>

      {/* ============ 对照行：参考图 05 是四张近似等宽的对照卡 ============ */}
      {/* 前两列（年度稳定性 / 牛熊震荡分组）本系统没有对应产出 ⇒ 如实不可用；
          后两列只做 variant 字段映射（random_birth_date、random_factor、shift_±7d），
          不重新计算、不为了填满四张卡伪造数据。
          负对照失效（INVALID_CONTROL）的大警告从持有期卡移到这里：它讲的是对照是否成立，
          属于对照区，挂在主图卡上只会把首屏唯一的主角图挤成配角。 */}
      <div
        className="grid grid-cols-2 gap-2 xl:grid-cols-4"
        data-anchor="control-row"
        data-testid="negative-control"
      >
        {UNAVAILABLE_COLUMNS.map((col) => (
          <Card key={col.testId} testId={col.testId} anchor={col.anchor}>
            <CardHeader
              icon={col.icon === "clock" ? <IconClock size={15} /> : <IconLayers size={15} />}
              title={col.title}
              dense
              right={<Chip tone="flat">未计算</Chip>}
            />
            <CardBody className="!py-1.5">
              <div className="text-[11.5px]">
                <b style={{ color: "var(--color-ink)" }}>{col.what}：不可用</b>
              </div>
              <div className="mt-0.5 text-[11px] leading-[15px]" style={{ color: "var(--color-ink-muted)" }}>
                {col.reason}
              </div>
              <details className="mt-0.5" data-testid={`${col.testId}-detail`}>
                <summary
                  className="cursor-pointer list-none text-[11px]"
                  style={{ color: "var(--color-ink-muted)" }}
                >
                  为什么不用现有数字拼一张
                </summary>
                <div
                  className="mt-1 text-[11px] leading-[16px]"
                  style={{ color: "var(--color-ink-muted)" }}
                >
                  {col.detail}
                </div>
              </details>
            </CardBody>
          </Card>
        ))}

        {CONTROL_COLUMNS.map((col) => (
          <Card key={col.testId} testId={col.testId} anchor={col.anchor}>
            <CardHeader
              icon={<IconTarget size={15} />}
              title={col.title}
              dense
              right={<Chip tone="flat">负对照</Chip>}
            />
            <CardBody className="!py-1.5">
              {col.variants.map((v) => {
                // 首帧 detail 还是 null（controls 为空），必须给兜底槽位：
                // 兜底值是「不可用」而不是 0/空字符串，避免渲染出假数字。
                const cell = grid.controls[v] ?? UNAVAILABLE_CELL;
                return (
                  <div
                    key={v}
                    className="flex items-baseline justify-between gap-1.5 rounded border px-1.5 py-1 text-[10.5px] leading-[14px]"
                    style={{ borderColor: "var(--color-border)" }}
                    data-testid={`${col.testId}-${v}`}
                    title={
                      cell.available
                        ? `${variantLabel(v)} · 判决 ${cell.verdict || "无"} · Jaccard ${
                            cell.jaccard === null ? "—" : cell.jaccard.toFixed(3)
                          } · 状态 ${cell.researchStatus || "未计算"}（${cell.horizon ?? "—"}D）`
                        : `${variantLabel(v)}：该实验没有这一组对照`
                    }
                  >
                    <span style={{ color: "var(--color-ink-muted)" }}>{variantLabel(v)}</span>
                    <b
                      style={{
                        color: cell.available
                          ? cell.verdict === "tie"
                            ? "var(--color-ink-sub)"
                            : "var(--color-warn)"
                          : "var(--color-ink-faint)",
                      }}
                    >
                      {cell.available ? cell.verdict || "无判决" : "不可用"}
                    </b>
                    <span className="smp-num" style={{ color: "var(--color-ink-muted)" }}>
                      J {cell.jaccard === null ? "—" : cell.jaccard.toFixed(3)}
                    </span>
                    <span style={{ color: "var(--color-ink-muted)" }}>
                      {cell.researchStatus || "未计算"}
                    </span>
                  </div>
                );
              })}
              {grid.invalidByGroup[col.testId]?.length ? (
                <div
                  className="mt-1 rounded border px-1.5 py-1 text-[10.5px] leading-[14px]"
                  style={{
                    borderColor: "rgba(224,164,88,0.5)",
                    color: "var(--color-warn)",
                  }}
                  data-testid={col.warningTestId}
                >
                  <b>对照失效：</b>
                  {grid.invalidByGroup[col.testId].map((v) => variantLabel(v)).join("、")} 与真实事件集合重合度
                  Jaccard &gt; 0.9，<strong>不能用来证明因子有效</strong>。
                </div>
              ) : null}
              <details className="mt-0.5" data-testid={`${col.testId}-meaning`}>
                <summary
                  className="cursor-pointer list-none text-[11px]"
                  style={{ color: "var(--color-ink-muted)" }}
                >
                  这组对照在检验什么
                </summary>
                <div
                  className="mt-1 text-[11px] leading-[16px]"
                  style={{ color: "var(--color-ink-muted)" }}
                >
                  {col.meaning}
                  没有负对照的"回测有效"在本项目中<strong>不被承认</strong>；
                  对照必须与真实集合足够不同（Jaccard &gt; 0.9 判为失效，研究状态记
                  <code>INVALID_CONTROL</code>），否则"跑赢随机"根本没有被检验。
                  逐持有期判决见下方明细表，不做汇总成一句话的结论。
                </div>
              </details>
            </CardBody>
          </Card>
        ))}
      </div>

      {/* ============ 明细与方法限制（第二屏） ============ */}
      <Card testId="backtest-detail" anchor="result-table">
        <CardHeader icon={<IconBook size={15} />} title="明细与方法限制" dense />
        <CardBody className="!py-2 space-y-1.5">
          {/* 持有期逐 variant × 持有期的明细表从首屏卡片移到这里：
              参考图 05 的持有期卡只有图（194px），逐行判决属于「实验结果明细」那一屏。
              内容一行未删，只换承载位置。 */}
          <div data-testid="horizon-detail-block" data-anchor="holding-detail-table">
            <div className="mb-1 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              持有期逐组明细（对照判决 / Jaccard 逐行，不做一句话汇总）
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-[11.5px]" data-testid="horizon-table">
                <thead>
                  <tr style={{ color: "var(--color-ink-muted)" }}>
                    <th className="px-2 text-left font-medium">组</th>
                    <th className="px-2 text-left font-medium">持有期</th>
                    <th className="px-2 text-right font-medium">样本数</th>
                    <th className="px-2 text-right font-medium">上涨率</th>
                    <th className="px-2 text-right font-medium">平均收益</th>
                    <th className="px-2 text-right font-medium">平均超额</th>
                    <th className="px-2 text-left font-medium">对照判决 / 备注</th>
                  </tr>
                </thead>
                <tbody>
                  {grid.rows.map((r) => (
                    <tr
                      key={`${r.variant}-${r.horizon}`}
                      style={{ borderTop: "1px solid var(--color-border)" }}
                    >
                      <td className="px-2 py-[3px]">{variantLabel(r.variant)}</td>
                      <td className="px-2">{r.horizon}D</td>
                      <td className="smp-num px-2 text-right">{r.sample_count}</td>
                      <td className="smp-num px-2 text-right">{pct(r.up_rate)}</td>
                      <td className="smp-num px-2 text-right">{pct(r.mean_return)}</td>
                      <td className="smp-num px-2 text-right">{pct(r.mean_excess_return)}</td>
                      <td
                        className="max-w-[320px] px-2"
                        style={{ color: "var(--color-ink-muted)" }}
                      >
                        {r.verdict ? (
                          <b
                            style={{
                              color: r.verdict === "tie" ? "var(--color-ink-sub)" : "var(--color-warn)",
                            }}
                          >
                            {r.verdict}
                          </b>
                        ) : null}
                        {r.jaccard !== null ? ` · Jaccard ${r.jaccard.toFixed(3)}` : ""}
                        {r.note ? ` · ${r.note.slice(0, 60)}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {horizons.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-[11.5px]" data-testid="event-study-table">
                <thead>
                  <tr style={{ color: "var(--color-ink-muted)" }}>
                    <th className="px-2 text-left font-medium">逐标的 EventStudy 持有期</th>
                    <th className="px-2 text-right font-medium">样本数</th>
                    <th className="px-2 text-right font-medium">上涨率</th>
                    <th className="px-2 text-right font-medium">平均收益</th>
                    <th className="px-2 text-right font-medium">标准差</th>
                    <th className="px-2 text-right font-medium">最大回撤</th>
                    <th className="px-2 text-left font-medium">备注</th>
                  </tr>
                </thead>
                <tbody>
                  {horizons.map((h) => (
                    <tr key={h.horizon} style={{ borderTop: "1px solid var(--color-border)" }}>
                      <td className="px-2 py-[3px]">{h.horizon}D</td>
                      <td className="smp-num px-2 text-right">{h.sample_count}</td>
                      <td className="smp-num px-2 text-right">{pct(h.up_rate)}</td>
                      <td className="smp-num px-2 text-right">{pct(h.mean_return)}</td>
                      <td className="smp-num px-2 text-right">{pct(h.std_return)}</td>
                      <td className="smp-num px-2 text-right">{pct(h.max_drawdown)}</td>
                      <td
                        className="max-w-[280px] truncate px-2"
                        style={{ color: "var(--color-ink-muted)" }}
                      >
                        {h.note || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <UnavailableBlock
              what="逐标的 EventStudy 明细"
              reason="该标的的历史验证未运行或没有标签样本；上方「持有期对比」展示的是<strong>已入库的研究实验</strong>，两者不是同一份数据。"
            />
          )}
          <SectionNote>{es?.methodology || "（缺少方法论说明）"}</SectionNote>
          <SectionNote>
            <span data-testid="holding-chart-scope">
              首屏「持有期对比」<strong>只画</strong>真实因子 + 至多四类负对照的逐持有期
              <code>mean_return</code>（后端已算出的字段）：缺失持有期断开，不插值、不补 0，
              也不由前端派生基准序列。
            </span>
          </SectionNote>
          <SectionNote>
            本页<strong>没有</strong>收益分布图与净值曲线：前者需要逐样本收益序列，
            后者需要可复现的组合规则、仓位与交易成本模型 —— 两者当前都不存在，
            用聚合均值反推一张曲线会把"不存在的证据"画出来。
          </SectionNote>
          {grid.hasOutperform ? (
            <SectionNote>
              <span data-testid="outperform-note">
                存在对照判决为 <code>outperform</code> / <code>underperform</code> 的组：
                这仍可能来自市场环境差异与多重检验，需样本外验证后才可作为研究结论。
                该提醒原先挂在首屏持有期卡上，V3-A.1 起移到第二屏明细，内容未改。
              </span>
            </SectionNote>
          ) : null}
          <SourceMethod testId="backtest-source-method">
            <RawField label="逐标的读取接口" value="GET /api/v1/analysis/{analysis_id}/backtest" />
            <RawField label="实验列表接口" value="GET /api/v1/research/experiments" />
            <RawField
              label="实验详情接口"
              value="GET /api/v1/research/experiments/{experiment_id}"
            />
            <RawField label="产出接口（不由本页触发）" value="POST /api/v1/research/run" />
            <RawField
              label="数据真实性"
              value={
                es?.data_source?.is_real === undefined
                  ? "—"
                  : es.data_source.is_real
                    ? "真实历史行情"
                    : "合成 / 降级行情（不构成研究证据）"
              }
            />
            <RawField label="实验标识" value={es?.experiment_id ?? "（尚未运行）"} />
            <RawField
              label="当前研究状态"
              value={`${status}（${researchStatusLabel(status)}）`}
            />
            <RawField label="持有期对照取数口径" value={grid.metaLine} />
          </SourceMethod>
        </CardBody>
      </Card>
    </ResearchPage>
  );
}

/** 一行「标签 值」审计字段：参考图 05 的筛选条是一行读完，不是纵向堆叠。 */
function InlineField({ label, value }: { label: string; value: string }) {
  return (
    <span className="flex items-baseline gap-1">
      <span style={{ color: "var(--color-ink-muted)" }}>{label}</span>
      <b className="smp-num max-w-[260px] truncate" title={value}>
        {value}
      </b>
    </span>
  );
}

/** 统计磁贴：参考图 05 这一带是 9 块 159px 宽、85px 高的磁贴行。 */
function Metric({
  label,
  value,
  hint,
  icon,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  icon: React.ReactNode;
  tone?: "num";
}) {
  return (
    <div
      className="flex min-h-[72px] items-center gap-1.5 rounded border px-2 py-1.5"
      style={{ borderColor: "var(--color-border)" }}
      data-testid={`metric-${label}`}
    >
      <span className="shrink-0" style={{ color: "var(--color-gold)" }} aria-hidden="true">
        {icon}
      </span>
      <span className="min-w-0">
        <span
          className="block truncate text-[10.5px] leading-[14px]"
          style={{ color: "var(--color-ink-muted)" }}
          title={label}
        >
          {label}
        </span>
        <span
          className={`block truncate text-[19px] font-semibold leading-[24px] ${
            tone === "num" ? "smp-num" : ""
          }`}
          title={value}
        >
          {value}
        </span>
        <span
          className="block truncate text-[10px] leading-[13px]"
          style={{ color: "var(--color-ink-faint)" }}
          title={hint}
        >
          {hint}
        </span>
      </span>
    </div>
  );
}

/**
 * 九个统计槽位（纯展示映射，不做任何统计计算）。
 *
 * 没有真实数据时槽位**照排**，值给「— / 不可用 / 未验证」：
 * §2.4 禁止用 0 冒充不可用，而"这一格答不上来"本身就是读者需要的信息。
 */
function buildMetrics(
  primary: ApiEventStudy["horizons"][number] | null,
): {
  label: string;
  value: string;
  hint: string;
  icon: React.ReactNode;
  tone?: "num";
}[] {
  const has = !!primary;
  const v = (x: string | null): string => (has && x !== null ? x : "—");
  return [
    {
      label: "样本数",
      value: v(primary ? String(primary.sample_count) : null),
      hint: has ? `主持有期 ${primary!.horizon}D` : "无逐标的样本",
      icon: <IconDatabase size={16} />,
    },
    {
      label: "上涨率",
      value: v(primary ? pct(primary.up_rate) : null),
      hint: has ? "上涨样本占比" : "未计算",
      icon: <IconArrowUp size={16} />,
    },
    {
      label: "平均收益",
      value: v(primary ? pct(primary.mean_return) : null),
      hint: has ? "算术平均，非预期收益" : "未计算",
      icon: <IconChart size={16} />,
      tone: "num",
    },
    {
      label: "中位数收益",
      value: v(primary ? pct(primary.median_return) : null),
      hint: has ? "对极值不敏感" : "未计算",
      icon: <IconLayers size={16} />,
    },
    {
      label: "超额收益",
      value: v(primary ? pct(primary.mean_excess_return) : null),
      hint: has ? "相对基准指数" : "未计算",
      icon: <IconDiamond size={16} />,
    },
    {
      label: "最大回撤",
      value: v(primary ? pct(primary.max_drawdown) : null),
      hint: has ? "样本内最深回落" : "未计算",
      icon: <IconArrowDown size={16} />,
    },
    {
      label: "IC（信息系数）",
      value: "不可用",
      hint: "接口无此字段",
      icon: <IconTarget size={16} />,
    },
    {
      label: "稳定性",
      value: "不可用",
      hint: "无年度分组产出",
      icon: <IconGauge size={16} />,
    },
    {
      label: "样本外表现",
      value: "未验证",
      hint: "未做 OOS 支持",
      icon: <IconFlask size={16} />,
    },
  ];
}

function statsWarningLine(
  primary: ApiEventStudy["horizons"][number] | null,
): string {
  if (!primary) {
    return "▸ 尚无逐标的 EventStudy 结果：样本数/上涨率等一律显示「—」，不以 0 或占位数字填充";
  }
  if (primary.sample_count === 0) {
    return "▸ 可用样本为 0：没有样本就没有统计，指标一律显示「—」";
  }
  if (primary.sample_count < MIN_SAMPLES) {
    return `▸ 样本量 ${primary.sample_count} 低于 ${MIN_SAMPLES}：抽样波动很大，不应据此判断规则有效性`;
  }
  return `▸ 主持有期 ${primary.horizon}D 取到 ${primary.sample_count} 个样本；统计描述仅覆盖样本内，样本外表现仍为「未验证」`;
}

function statsWarningDetail(
  primary: ApiEventStudy["horizons"][number] | null,
): string {
  if (!primary) {
    return "本页读的是逐标的 EventStudy 结果（GET /api/v1/analysis/{id}/backtest）。该标的历史验证未运行或 as_of 之后没有标签样本时，接口不会返回 horizons，因此这里不显示任何未运行的统计数字。要出数必须由研究流水线产出（POST /api/v1/research/run），本页不触发重算。";
  }
  if (primary.sample_count === 0) {
    return "事件研究没有取到样本，三者之一：观测为空 / 激活条件过严 / as_of 之后无标签数据。不以 0 填充，也不换窗口凑样本。";
  }
  if (primary.sample_count < MIN_SAMPLES) {
    return `样本量低于 ${MIN_SAMPLES} 时，上涨率与均值的标准误已经大于效应本身；这类数字只作过程记录，不进入研究结论。`;
  }
  return "样本量达标不等于有效：IC 与稳定性没有对应产出、样本外未验证，因此两格分别显示「不可用」与「未验证」。";
}

function statsWarningTone(primary: ApiEventStudy["horizons"][number] | null): "warn" | "ok" {
  if (!primary) return "warn";
  return primary.sample_count < MIN_SAMPLES ? "warn" : "ok";
}

/** 实验详情 → 图表序列、表格行与对照槽位（纯展示映射，不做任何统计计算）。 */
function buildExperimentGrid(detail: ApiExperimentDetail | null) {
  const CONTROL_KEYS = ["random_birth_date", "shift_plus_7d", "shift_minus_7d", "random_factor"];
  const isControl = (v: string) => CONTROL_KEYS.some((k) => v.includes(k));

  if (!detail) {
    return {
      labels: [] as string[],
      series: [],
      rows: [],
      invalidControls: [] as string[],
      controlVariants: [] as string[],
      hasOutperform: false,
      experimentName: "",
      metaLine: "（未读取到实验）",
      controls: {} as Record<string, ControlCell>,
      invalidByGroup: { "control-random": [], "control-shift": [] } as Record<string, string[]>,
    };
  }

  const variants = Object.keys(detail.results_by_variant).sort();
  const horizonSet = new Set<string>();
  for (const v of variants) {
    for (const r of detail.results_by_variant[v]) horizonSet.add(String(r.horizon));
  }
  const labels = Array.from(horizonSet)
    .sort((a, b) => Number(a) - Number(b))
    .map((h) => `${h}D`);

  // 图里最多画 real + 三类对照，避免 variant 多到看不清
  const chartVariants = variants.filter((v) => v === "real" || isControl(v)).slice(0, 5);
  const series = chartVariants.map((v, i) => ({
    name: variantLabel(v),
    tone: (i === 0 ? "up" : i % 2 === 1 ? "flat" : "down") as "up" | "down" | "flat",
    values: labels.map((lab) => {
      const row = detail.results_by_variant[v].find((r) => `${r.horizon}D` === lab);
      return row?.mean_return ?? null;
    }),
  }));

  const rows = variants.flatMap((v) =>
    detail.results_by_variant[v].map((r) => {
      const extra = (r.extra ?? {}) as Record<string, unknown>;
      return {
        variant: v,
        horizon: String(r.horizon),
        sample_count: r.sample_count,
        up_rate: r.up_rate,
        mean_return: r.mean_return,
        mean_excess_return: r.mean_excess_return,
        verdict: typeof extra.verdict === "string" ? extra.verdict : "",
        jaccard:
          typeof extra.jaccard_with_real === "number" ? (extra.jaccard_with_real as number) : null,
        note: typeof extra.note === "string" ? (extra.note as string) : "",
      };
    }),
  );

  // 对照卡取数：优先取实验自身的 20D（与首屏"主持有期"一致），否则取最后一个持有期。
  // 这是**取哪一行**的展示口径，不是重新计算 —— 逐持有期完整判决仍在明细表里。
  const expHorizons = (detail.experiment.horizons ?? []).map(String);
  const refHorizon = expHorizons.includes("20") ? "20" : expHorizons[expHorizons.length - 1] ?? "";

  const controls: Record<string, ControlCell> = {};
  for (const v of CONTROL_KEYS) {
    const list = detail.results_by_variant[v];
    if (!list?.length) {
      controls[v] = { available: false, verdict: "", jaccard: null, researchStatus: "" };
      continue;
    }
    const row = list.find((r) => String(r.horizon) === refHorizon) ?? list[list.length - 1];
    const extra = (row.extra ?? {}) as Record<string, unknown>;
    controls[v] = {
      available: true,
      horizon: String(row.horizon),
      verdict: typeof extra.verdict === "string" ? extra.verdict : "",
      jaccard: typeof extra.jaccard_with_real === "number" ? extra.jaccard_with_real : null,
      researchStatus:
        typeof extra.research_status === "string" ? (extra.research_status as string) : "",
    };
  }

  const invalidControls = variants.filter(
    (v) =>
      isControl(v) &&
      detail.results_by_variant[v].some(
        (r) => (r.extra as Record<string, unknown>)?.research_status === "INVALID_CONTROL",
      ),
  );

  const invalidByGroup: Record<string, string[]> = {
    "control-random": CONTROL_COLUMNS[0].variants.filter((v) => invalidControls.includes(v)),
    "control-shift": CONTROL_COLUMNS[1].variants.filter((v) => invalidControls.includes(v)),
  };

  const metaLine = [
    detail.experiment.date_from
      ? `区间 ${detail.experiment.date_from}~${detail.experiment.date_to ?? "—"}`
      : "区间 未提供",
    `基准 ${detail.experiment.benchmark_code ?? "—"}`,
    `对照取 ${refHorizon ? `${refHorizon}D` : "末个"}持有期`,
    "只读，不触发重算",
  ].join(" · ");

  return {
    labels,
    series,
    rows,
    invalidControls,
    controlVariants: variants.filter(isControl),
    hasOutperform: rows.some(
      (r) => r.verdict === "outperform" || r.verdict === "underperform",
    ),
    experimentName: detail.experiment.name ?? "",
    metaLine,
    controls,
    invalidByGroup,
  };
}

interface ControlCell {
  available: boolean;
  horizon?: string;
  verdict: string;
  jaccard: number | null;
  researchStatus: string;
}

/** 尚未读到实验（首帧 / 接口失败 / 该 variant 不存在）时的槽位值：一律"不可用"，不填 0。 */
const UNAVAILABLE_CELL: ControlCell = {
  available: false,
  verdict: "",
  jaccard: null,
  researchStatus: "",
};

/** variant 代码 → 中文（后端是稳定的英文键）。 */
function variantLabel(v: string): string {
  if (v === "real") return "真实因子";
  if (v === "random_birth_date") return "随机出生日";
  if (v === "random_factor") return "随机因子";
  if (v === "shift_plus_7d") return "日期平移 +7D";
  if (v === "shift_minus_7d") return "日期平移 −7D";
  if (v === "oos_gate") return "样本外闸门";
  return v;
}

export default function BacktestPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <BacktestInner />
    </Suspense>
  );
}
