"use client";

/**
 * 历史验证页（复刻 doc/ui-reference/05_backtest_validation.png）。
 *
 * **本页最重要的一条纪律**：
 *   术数规则强度 与 统计有效性 必须**视觉分区**，不能混在一起看。
 *
 * 结构（复核任务书 §R3 / 05 参考图）
 * --------------------------------
 * ① 研究状态与条件 → ② 统计摘要 → ③ 持有期对比与负对照 → ④ 明细。
 *
 * 四件**不做**的事（参考图里有、但我们没有数据支撑）：
 * 1. **不画收益分布**：需要逐样本收益序列，接口只给聚合量；
 * 2. **不画策略净值**：没有可复现的组合规则、仓位与交易成本模型；
 * 3. **不做逐因子胜率/IC**：本页数据源不含这些字段，缺失就显示空态；
 * 4. **不触发任何研究计算**：页面只读已有结果（EventStudy + 已入库实验），
 *    绝不因为"打开页面"就跑全市场研究。
 *
 * 反过来必须醒目的：**负对照失效**（Jaccard > 0.9 记 INVALID_CONTROL）、
 * 样本不足、数据降级、以及"未做样本外验证"这一事实。
 */

import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { HorizonComparisonChart } from "@/components/charts/Charts";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, ResearchStatusBadge, UnavailableBlock, researchStatusLabel } from "@/components/shell/PageState";
import { RawField, SourceMethod } from "@/components/shell/SourceMethod";
import { IconBook, IconChart, IconTarget } from "@/components/shell/Icons";
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

function BacktestInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const birthBasis = useBirthBasisParam();
  const horizon = useHorizonParam();
  const { analysis, loading, error, reload } = useAnalysis(code, "forward", undefined, birthBasis, horizon);

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
      const data = await api.get<{ items: ApiExperimentSummary[] }>(endpoints.researchExperiments());
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
      code={code}
      analysis={analysis}
      loading={loading}
      error={error}
      onReload={reload}
      loadingLabel="正在读取历史验证结果…"
    >
      {/* ============ ① 术数规则强度（确定性结果） ============ */}
      <div
        className="rounded border-l-4 px-4 py-2"
        style={{ borderColor: "var(--color-gold)", background: "rgba(212,160,74,0.06)" }}
        data-testid="section-deterministic"
      >
        <div className="text-[13px] font-semibold" style={{ color: "var(--color-gold)" }}>
          ① 术数规则强度（确定性结果）
        </div>
        <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          以下数字由确定性代码产生，含义是「传统规则怎么看」，<strong>与收益无关</strong>；
          它们与 ② 的统计有效性必须分开读。
        </div>
      </div>

      {/* 规则强度一行读完：与 ② 的统计严格分开，但不占用首屏高度 ——
          首屏要让位给真实持有期对比图（参考图 05 的构图重点）。 */}
      <div
        className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 rounded border px-3 py-1.5 text-[11.5px]"
        style={{ borderColor: "var(--color-border)" }}
        data-testid="rule-strength"
      >
        {(["bazi", "ziwei", "huangli"] as const).map((k) => {
          const op = analysis?.opinions?.[k];
          const ok = op && op.availability === "ok" && op.score !== null;
          return (
            <span key={k} className="flex items-baseline gap-1.5" data-testid={`rule-strength-${k}`}>
              <span style={{ color: "var(--color-ink-muted)" }}>{engineCn(k)}</span>
              <b className="smp-num text-[13px]">{ok ? `${op!.score}/100` : "不可用"}</b>
              <span style={{ color: "var(--color-ink-muted)" }}>
                {ok ? `方向 ${op!.direction} · 置信度 ${op!.confidence.toFixed(2)}` : "不以 0 分聚合"}
              </span>
            </span>
          );
        })}
        <span className="flex items-baseline gap-1.5">
          <span style={{ color: "var(--color-ink-muted)" }}>共识</span>
          <b className="text-[13px]">{analysis?.consensus?.label_cn ?? "—"}</b>
          <span style={{ color: "var(--color-ink-muted)" }}>
            一致度 {analysis?.consensus?.agreement_score?.toFixed(2) ?? "—"}
          </span>
        </span>
        <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
          （规则强度不是上涨概率；历史有效性只能由 ② 回答）
        </span>
      </div>

      {/* ============ ② 研究状态与条件 ============ */}
      <div
        className="mt-3 rounded border-l-4 px-4 py-2"
        style={{ borderColor: "var(--color-flat)", background: "rgba(124,143,163,0.06)" }}
        data-testid="section-empirical"
      >
        <div className="text-[13px] font-semibold">② 统计有效性（历史数据）</div>
        <div className="mt-0.5 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          以下数字来自事件研究 + 负对照，含义是「这些规则在历史上有没有信息量」。
        </div>
      </div>

      <Card className="mt-2" testId="research-status-card">
        <CardHeader
          icon={<IconTarget size={15} />}
          title="研究状态与条件"
          dense
          right={
            <div className="flex items-center gap-1">
              <Chip tone={isRealData ? "flat" : "gold"} data-testid="data-source-chip">
                数据源 {isRealData ? "真实" : "非真实（合成/降级）"}
              </Chip>
              {es?.data_source?.benchmark_degraded ? <Chip tone="gold">基准降级</Chip> : null}
            </div>
          }
        />
        <CardBody className="!py-1.5">
          <ResearchStatusBadge status={status} reasons={es?.research_status_reasons ?? []} />
          <div className="mt-1.5 grid grid-cols-2 gap-x-6 gap-y-0.5 text-[11px] md:grid-cols-4">
            <Stat label="实验标识" value={es?.experiment_id || "（尚未运行）"} />
            <Stat label="事件数" value={es ? String(es.event_count) : "—"} />
            <Stat label="股票池" value={es ? String(es.universe_size) : "—"} />
            <Stat
              label="因子"
              value={es?.factor_ids?.length ? es.factor_ids.join("、") : "（无）"}
            />
          </div>
          <div className="mt-1.5 text-[11px] leading-[16px]" style={{ color: "var(--color-ink-muted)" }}>
            <code>NO_SIGNAL</code> 表示<strong>真实因子未优于随机对照</strong>，是如实输出而非故障；
            某个持有期平均收益为正<strong>不构成</strong>"验证有效"。本页<strong>只读</strong>已有结果，
            打开页面不触发任何全市场重算。
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

      <Card testId="stats-summary">
        <CardHeader icon={<IconChart size={15} />} title="统计摘要（主持有期）" dense />
        <CardBody className="!py-1.5">
          {btLoading ? (
            <div className="py-3 text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
              正在加载…
            </div>
          ) : primary ? (
            <>
              <div className="grid grid-cols-3 gap-2 md:grid-cols-5 xl:grid-cols-9" data-testid="stats-metrics">
                <Metric label={`样本数（${primary.horizon}D）`} value={String(primary.sample_count)} />
                <Metric label="上涨率" value={pct(primary.up_rate)} />
                <Metric label="平均收益" value={pct(primary.mean_return)} tone="num" />
                <Metric label="中位数收益" value={pct(primary.median_return)} />
                <Metric label="超额收益" value={pct(primary.mean_excess_return)} />
                <Metric label="最大回撤" value={pct(primary.max_drawdown)} />
                <Metric label="IC（信息系数）" value="—" />
                <Metric label="稳定性" value="—" />
                <Metric label="样本外表现" value="未验证" />
              </div>
              {primary.sample_count === 0 ? (
                <div
                  className="mt-1.5 rounded border px-2.5 py-1.5 text-[11.5px]"
                  style={{ borderColor: "rgba(224,164,88,0.45)", color: "var(--color-warn)" }}
                  data-testid="small-sample-warning"
                >
                  <b>可用样本为 0</b>：事件研究没有取到样本（观测为空 / 激活条件过严 /
                  as_of 之后无标签数据三者之一）。没有样本就没有统计，指标一律显示「—」，
                  不以 0 或占位数字填充。
                </div>
              ) : primary.sample_count < MIN_SAMPLES ? (
                <div
                  className="mt-1.5 rounded border px-2.5 py-1.5 text-[11.5px]"
                  style={{ borderColor: "rgba(224,164,88,0.45)", color: "var(--color-warn)" }}
                  data-testid="small-sample-warning"
                >
                  样本量 {primary.sample_count} 低于 {MIN_SAMPLES}：这类统计的抽样波动很大，
                  不应据此判断规则有效性。
                </div>
              ) : null}
            </>
          ) : (
            <UnavailableBlock
              what="统计摘要"
              reason="尚无逐标的 EventStudy 结果（该标的历史验证未运行或没有标签样本）。本页不显示任何未运行的统计数字。"
            />
          )}
        </CardBody>
      </Card>

      <div className="grid gap-2 md:grid-cols-2" data-testid="backtest-reference-panels">
        {[
          ["收益分布", "暂无逐样本收益序列"],
          ["持有期收益", "暂无可比策略序列"],
          ["年度稳定性", "未计算"],
          ["牛 / 熊 / 震荡分组", "未计算"],
          ["随机对照", "等待实验结果"],
          ["出生日期平移对照", "等待实验结果"],
        ].map(([title, note]) => (
          <Card key={title} testId={`backtest-panel-${title}`}>
            <CardHeader title={title} dense right={<span className="text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>研究卡位</span>} />
            <CardBody className="!py-0">
              <div className="flex h-[112px] items-center justify-center text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
                {note}
              </div>
            </CardBody>
          </Card>
        ))}
      </div>

      {/* ============ ③ 持有期对比与负对照 ============ */}
      <Card className="mt-2" testId="horizon-comparison">
        <CardHeader
          icon={<IconChart size={15} />}
          title="持有期对比（真实入库结果，只读）"
          dense
          right={
            <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
              不画收益分布 / 不画净值曲线
            </span>
          }
        />
        <CardBody className="!py-2">
          {experiments.length ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <label className="flex items-center gap-1 text-[11.5px]">
                  <span style={{ color: "var(--color-ink-muted)" }}>研究实验</span>
                  <select
                    value={expId}
                    onChange={(e) => setExpId(e.target.value)}
                    className="max-w-[460px] rounded border px-2 py-1 text-[11.5px] outline-none"
                    style={{
                      borderColor: "var(--color-border)",
                      background: "transparent",
                      color: "var(--color-ink)",
                    }}
                    data-testid="experiment-select"
                  >
                    {experiments.map((s) => (
                      <option key={s.experiment_id} value={s.experiment_id}>
                        [{s.kind}] {s.name} · {s.status} · {s.created_at.slice(0, 10)}
                      </option>
                    ))}
                  </select>
                </label>
                {detail?.experiment.status ? (
                  <Chip tone={detail.experiment.status === "INVALID_CONTROL" ? "gold" : "flat"}>
                    {detail.experiment.status}
                  </Chip>
                ) : null}
                {detail?.experiment.date_from ? (
                  <span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
                    区间 {detail.experiment.date_from} ~ {detail.experiment.date_to ?? "—"} · 基准{" "}
                    {detail.experiment.benchmark_code ?? "—"}
                  </span>
                ) : null}
              </div>

              {detail ? (
                <>
                  {grid.labels.length ? (
                    <div className="mt-2" data-testid="horizon-chart-wrap">
                      <HorizonComparisonChart labels={grid.labels} series={grid.series} />
                    </div>
                  ) : (
                    <UnavailableBlock what="持有期对比图" reason="该实验没有可用的持有期结果。" />
                  )}

                  <div className="mt-2 overflow-x-auto">
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
                          <tr key={`${r.variant}-${r.horizon}`} style={{ borderTop: "1px solid var(--color-border)" }}>
                            <td className="px-2 py-[3px]">{variantLabel(r.variant)}</td>
                            <td className="px-2">{r.horizon}D</td>
                            <td className="smp-num px-2 text-right">{r.sample_count}</td>
                            <td className="smp-num px-2 text-right">{pct(r.up_rate)}</td>
                            <td className="smp-num px-2 text-right">{pct(r.mean_return)}</td>
                            <td className="smp-num px-2 text-right">{pct(r.mean_excess_return)}</td>
                            <td className="max-w-[320px] px-2" style={{ color: "var(--color-ink-muted)" }}>
                              {r.verdict ? (
                                <b style={{ color: r.verdict === "tie" ? "var(--color-ink-sub)" : "var(--color-warn)" }}>
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

                  {grid.invalidControls.length ? (
                    <div
                      className="mt-2 rounded border px-2.5 py-2 text-[11.5px] leading-relaxed"
                      style={{ borderColor: "rgba(224,164,88,0.5)", color: "var(--color-warn)" }}
                      data-testid="invalid-control-warning"
                    >
                      <b>负对照失效：</b>
                      {grid.invalidControls.join("、")}。这些对照与真实事件集合的重合度过高
                      （Jaccard &gt; 0.9），
                      <strong>不能用来证明因子有效</strong> —— 对照必须与真实集合足够不同，
                      否则"跑赢随机"根本没有被检验。
                    </div>
                  ) : null}

                  {grid.hasOutperform ? (
                    <div className="mt-2">
                      <SectionNote>
                        存在对照判决为 <code>outperform</code> / <code>underperform</code> 的组：
                        这仍可能来自市场环境差异与多重检验，需样本外验证后才可作为研究结论。
                      </SectionNote>
                    </div>
                  ) : null}
                </>
              ) : (
                <div className="mt-2 py-3 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
                  正在读取实验详情…（只读接口，不触发重算）
                </div>
              )}
            </>
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

      <Card className="mt-2" testId="negative-control">
        <CardHeader icon={<IconTarget size={15} />} title="负对照" dense />
        <CardBody className="!py-2 space-y-1.5">
          <SectionNote>
            没有负对照的"回测有效"在本项目中<strong>不被承认</strong>。
            负对照必须与真实事件集合不同（Jaccard &gt; 0.9 判为对照失效，研究状态记为
            <code>INVALID_CONTROL</code>）。
          </SectionNote>
          {grid.controlVariants.length ? (
            <div className="text-[11.5px]">
              <span style={{ color: "var(--color-ink-muted)" }}>本实验包含的对照：</span>
              {grid.controlVariants.map((v) => (
                <Chip key={v} tone="flat">
                  {variantLabel(v)}
                </Chip>
              ))}
            </div>
          ) : (
            <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              该实验的 variant 明细里没有对照组合。
            </div>
          )}
          <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            对照结果与 Jaccard 逐行见上方表格的「对照判决 / 备注」列 —— 不做汇总成一句话的结论。
          </div>
        </CardBody>
      </Card>

      {/* ============ ④ 明细 ============ */}
      <Card className="mt-3" testId="backtest-detail">
        <CardHeader icon={<IconBook size={15} />} title="明细与方法限制" dense />
        <CardBody className="!py-2 space-y-1.5">
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
                      <td className="max-w-[280px] truncate px-2" style={{ color: "var(--color-ink-muted)" }}>
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
            本页<strong>没有</strong>收益分布图与净值曲线：前者需要逐样本收益序列，
            后者需要可复现的组合规则、仓位与交易成本模型 —— 两者当前都不存在，
            用聚合均值反推一张曲线会把"不存在的证据"画出来。
          </SectionNote>
          <SourceMethod testId="backtest-source-method">
            <RawField label="逐标的读取接口" value="GET /api/v1/analysis/{analysis_id}/backtest" />
            <RawField label="实验列表接口" value="GET /api/v1/research/experiments" />
            <RawField label="实验详情接口" value="GET /api/v1/research/experiments/{experiment_id}" />
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
          </SourceMethod>
        </CardBody>
      </Card>
    </ResearchPage>
  );
}

/** 实验详情 → 图表序列与表格行（纯展示映射，不做任何统计计算）。 */
function buildExperimentGrid(detail: ApiExperimentDetail | null) {
  if (!detail) {
    return { labels: [] as string[], series: [], rows: [], invalidControls: [] as string[], controlVariants: [] as string[], hasOutperform: false };
  }
  const variants = Object.keys(detail.results_by_variant).sort();
  const horizonSet = new Set<string>();
  for (const v of variants) {
    for (const r of detail.results_by_variant[v]) horizonSet.add(String(r.horizon));
  }
  const labels = Array.from(horizonSet).sort((a, b) => Number(a) - Number(b)).map((h) => `${h}D`);

  const CONTROL_KEYS = ["random_birth_date", "shift_plus_7d", "shift_minus_7d", "random_factor"];
  const isControl = (v: string) => CONTROL_KEYS.some((k) => v.includes(k));

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

  const invalidControls = variants.filter(
    (v) =>
      isControl(v) &&
      detail.results_by_variant[v].some(
        (r) => (r.extra as Record<string, unknown>)?.research_status === "INVALID_CONTROL",
      ),
  );

  return {
    labels,
    series,
    rows,
    invalidControls,
    controlVariants: variants.filter(isControl),
    hasOutperform: rows.some((r) => r.verdict === "outperform" || r.verdict === "underperform"),
  };
}

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

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div style={{ color: "var(--color-ink-muted)" }}>{label}</div>
      <div className="truncate" title={value}>
        {value}
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: "num" }) {
  return (
    <div className="rounded border px-2 py-1.5" style={{ borderColor: "var(--color-border)" }}>
      <div className="text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>
        {label}
      </div>
      <div className={`text-[17px] font-semibold leading-tight ${tone === "num" ? "smp-num" : ""}`}>
        {value}
      </div>
    </div>
  );
}

export default function BacktestPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <BacktestInner />
    </Suspense>
  );
}
