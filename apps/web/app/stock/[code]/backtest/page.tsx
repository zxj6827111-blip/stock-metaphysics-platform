"use client";

/**
 * 历史验证页（复刻 doc/ui-reference/05_backtest_validation.png）。
 *
 * **本页最重要的一条纪律**：
 *   术数规则强度 与 统计有效性 必须**视觉分区**，不能混在一起看。
 *
 * 因此页面分成上下两块：
 *   ① 上：确定性结果（盘面 / 因子 / 观点 / 共识）—— 它们的含义是"传统规则怎么看"；
 *   ② 下：历史统计（样本数 / 上涨率 / 平均收益 / 超额 / 回撤 / 负对照 / ResearchStatus）
 *      —— 它们的含义是"这些规则在历史数据上有没有信息量"。
 *
 * 并且：**NO_SIGNAL 就明确显示 NO SIGNAL**，不能因为某个平均收益为正就染成"验证有效"。
 */

import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, ResearchStatusBadge, UnavailableBlock } from "@/components/shell/PageState";
import { IconBook, IconChart, IconTarget } from "@/components/shell/Icons";
import { api, endpoints, type ApiEventStudy } from "@/lib/api";
import { useAnalysis } from "@/lib/analysisStore";
import { CONTROL_RESULT_LABEL, pct } from "@/lib/dataSource";

interface HorizonRow {
  horizon: number;
  sample_count: number;
  up_rate: number | null;
  mean_return: number | null;
  median_return: number | null;
  mean_excess_return: number | null;
  max_drawdown: number | null;
}

function BacktestInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const { analysis, loading, error, reload } = useAnalysis(code);

  const [es, setEs] = useState<ApiEventStudy | null>(null);
  const [btLoading, setBtLoading] = useState(false);
  const [btError, setBtError] = useState<string | null>(null);

  const loadBacktest = useCallback(async (analysisId: string) => {
    setBtLoading(true);
    setBtError(null);
    try {
      setEs(await api.get<ApiEventStudy>(endpoints.backtest(analysisId)));
    } catch (e) {
      setBtError(e instanceof Error ? e.message : String(e));
    } finally {
      setBtLoading(false);
    }
  }, []);

  useEffect(() => {
    if (analysis?.analysis_id) void loadBacktest(analysis.analysis_id);
  }, [analysis?.analysis_id, loadBacktest]);

  const status = es?.research_status ?? "NOT_RUN";
  const horizons = (es?.horizons ?? []) as unknown as HorizonRow[];
  const h20 = horizons.find((h) => h.horizon === 20);
  const topReasons = es?.research_status_reasons ?? [];

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
      {/* ================= 分区一：术数规则强度（确定性结果） ================= */}
      <div
        className="rounded border-l-4 px-4 py-3"
        style={{ borderColor: "var(--color-gold)", background: "rgba(212,160,74,0.06)" }}
        data-testid="section-deterministic"
      >
        <div className="text-[13px] font-semibold" style={{ color: "var(--color-gold)" }}>
          ① 术数规则强度（确定性结果）
        </div>
        <div className="mt-0.5 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          以下数字由确定性代码产生，含义是「传统规则怎么看」，**与收益无关**。
        </div>
      </div>

      <Card>
        <CardHeader icon={<IconBook size={15} />} title="三模型观点与共识（规则强度）" dense />
        <div className="grid grid-cols-4 gap-3 text-[12.5px]">
          {["bazi", "ziwei", "huangli"].map((k) => {
            const op = analysis?.opinions?.[k];
            const ok = op && op.availability === "ok";
            return (
              <div key={k} className="rounded border p-2" style={{ borderColor: "var(--color-line)" }}>
                <div style={{ color: "var(--color-ink-muted)" }}>{k}</div>
                <div className="text-[18px] font-semibold">{ok ? `${op!.score}/100` : "不可用"}</div>
                <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                  方向 {ok ? op!.direction : "—"} · 置信度 {ok ? op!.confidence.toFixed(2) : "—"}
                </div>
              </div>
            );
          })}
          <div className="rounded border p-2" style={{ borderColor: "var(--color-line)" }}>
            <div style={{ color: "var(--color-ink-muted)" }}>共识</div>
            <div className="text-[18px] font-semibold">
              {analysis?.consensus?.label_cn ?? "—"}
            </div>
            <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              一致度 {analysis?.consensus?.agreement_score?.toFixed(2) ?? "—"}
            </div>
          </div>
        </div>
        <div className="mt-2">
          <SectionNote>
            规则强度**不是**上涨概率、不是预期收益率。它的历史有效性只能由下方统计回答。
          </SectionNote>
        </div>
      </Card>

      {/* ================= 分区二：统计有效性（历史数据） ================= */}
      <div
        className="rounded border-l-4 px-4 py-3"
        style={{ borderColor: "var(--color-flat)", background: "rgba(124,143,163,0.06)" }}
        data-testid="section-empirical"
      >
        <div className="text-[13px] font-semibold" style={{ color: "var(--color-ink)" }}>
          ② 统计有效性（历史数据）
        </div>
        <div className="mt-0.5 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          以下数字来自事件研究 + 负对照，含义是「这些规则在历史上有没有信息量」。
        </div>
      </div>

      <Card testId="research-status-card">
        <CardHeader
          icon={<IconTarget size={15} />}
          title="研究状态（ResearchStatus）"
          right={
            <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              数据源 {String(es?.data_source && (es.data_source as Record<string, unknown>).is_real === false ? "非真实" : "真实")}
            </span>
          }
          dense
        />
        <ResearchStatusBadge status={status} reasons={topReasons} />
        <div className="mt-2">
          <SectionNote>
            若状态为 <code>NO_SIGNAL</code>，表示**真实因子未优于随机对照** ——
            这是如实输出，不是系统故障。某个持有期平均收益为正**不构成**"验证有效"。
          </SectionNote>
        </div>
      </Card>

      {btError ? (
        <Card testId="backtest-error">
          <div className="py-3 text-[13px]" style={{ color: "var(--color-warn)" }}>
            历史验证加载失败：{btError}
          </div>
        </Card>
      ) : null}

      <Card>
        <CardHeader icon={<IconChart size={15} />} title="持有期统计" dense />
        {btLoading ? (
          <div className="py-3 text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
            正在加载…
          </div>
        ) : null}
        {horizons.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]" data-testid="horizon-table">
              <thead>
                <tr style={{ color: "var(--color-ink-muted)" }}>
                  <th className="text-left">持有期</th>
                  <th className="text-right">样本数</th>
                  <th className="text-right">上涨率</th>
                  <th className="text-right">平均收益</th>
                  <th className="text-right">中位数</th>
                  <th className="text-right">超额收益</th>
                  <th className="text-right">最大回撤</th>
                </tr>
              </thead>
              <tbody>
                {horizons.map((h) => (
                  <tr key={h.horizon} style={{ borderTop: "1px solid var(--color-line)" }}>
                    <td className="py-1">{h.horizon}D</td>
                    <td className="smp-num text-right">{h.sample_count}</td>
                    <td className="smp-num text-right">{pct(h.up_rate)}</td>
                    <td className="smp-num text-right">{pct(h.mean_return)}</td>
                    <td className="smp-num text-right">{pct(h.median_return)}</td>
                    <td className="smp-num text-right">{pct(h.mean_excess_return)}</td>
                    <td className="smp-num text-right">{pct(h.max_drawdown)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : !btLoading ? (
          <UnavailableBlock
            what="持有期统计"
            reason="尚无历史验证样本。需要先运行 POST /api/v1/research/run（事件研究 + 四类负对照）积累观测与标签。"
          />
        ) : null}
        <div className="mt-2">
          <SectionNote>
            {h20
              ? `20 日持有期：样本 ${h20.sample_count}，上涨率 ${pct(h20.up_rate)}，` +
                `平均收益 ${pct(h20.mean_return)}，超额收益 ${pct(h20.mean_excess_return)}。`
              : "超额收益 / 最大回撤只在 20 日持有期给出（指标口径不混用）。"}
            <br />
            这些统计**没有交易成本假设**，且 Phase 1/2 均未做样本外验证。
          </SectionNote>
        </div>
      </Card>

      <Card>
        <CardHeader icon={<IconTarget size={15} />} title="负对照" dense />
        <SectionNote>
          没有负对照的"回测有效"在本项目中**不被承认**。
          负对照必须与真实事件集合不同（Jaccard &gt; 0.9 判为对照失效）。
        </SectionNote>
        <div className="mt-2 text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
          验证结论：
          <span
            className="ml-2 rounded px-2 py-0.5 text-[11.5px] font-semibold"
            style={{
              background: `${CONTROL_RESULT_LABEL[
                status === "NO_SIGNAL" ? "underperform" : status === "INVALID_CONTROL" ? "invalid" : "tie"
              ].tone === "up"
                ? "rgba(232,88,90,0.16)"
                : CONTROL_RESULT_LABEL[
                    status === "NO_SIGNAL" ? "underperform" : status === "INVALID_CONTROL" ? "invalid" : "tie"
                  ].tone === "down"
                  ? "rgba(79,211,155,0.16)"
                  : "rgba(124,143,163,0.16)"}`,
              color:
                CONTROL_RESULT_LABEL[
                  status === "NO_SIGNAL" ? "underperform" : status === "INVALID_CONTROL" ? "invalid" : "tie"
                ].tone === "up"
                  ? "var(--color-up)"
                  : CONTROL_RESULT_LABEL[
                      status === "NO_SIGNAL" ? "underperform" : status === "INVALID_CONTROL" ? "invalid" : "tie"
                    ].tone === "down"
                    ? "var(--color-down)"
                    : "var(--color-flat)",
            }}
            data-testid="negative-control-verdict"
          >
            {
              CONTROL_RESULT_LABEL[
                status === "NO_SIGNAL" ? "underperform" : status === "INVALID_CONTROL" ? "invalid" : "tie"
              ].label
            }
          </span>
        </div>
        <div className="mt-2">
          <UnavailableBlock
            what="逐类对照明细"
            reason="详细对照结果（随机出生日 / ±7 天 / 随机因子）由 POST /api/v1/research/run 产出；本页只显示汇总状态，避免把未运行的对照显示成『通过』。"
          />
        </div>
      </Card>

      <Card>
        <CardHeader icon={<IconBook size={15} />} title="方法与限制" dense />
        <SectionNote>
          {es?.methodology || "（缺少方法论说明）"}
        </SectionNote>
      </Card>
    </ResearchPage>
  );
}

export default function BacktestPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <BacktestInner />
    </Suspense>
  );
}
