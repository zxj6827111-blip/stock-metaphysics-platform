"use client";

/**
 * 综合研判页（复刻 doc/ui-reference/02_integrated_analysis.png）。
 *
 * 首屏必须同时回答（uiux_spec §7）：
 *   A. 各术数模型怎么看    → EngineScoreCard ×3
 *   B. 是否形成共振        → ConsensusCard
 *   C. 是否存在明显冲突    → ConflictCard
 *   D. 历史统计支持强不强  → BacktestMetricCard + 分布图
 *   E. 数据质量如何        → DataQualityBadge
 *
 * 生产 runtime 读真实 API；`?fixture=ui-reference` 时用固定演示数据。
 */

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHero } from "@/components/shell/TopBar";
import { StockContextBar } from "@/components/stock/StockContextBar";
import { Card, CardHeader } from "@/components/cards/Card";
import {
  BacktestMetricCard,
  ConflictCard,
  ConsensusCard,
  DataQualityBadge,
  EngineScoreCard,
  EvidenceRow,
} from "@/components/cards/EngineCards";
import { DistributionChart, TimeWindowChart } from "@/components/charts/Charts";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import {
  IconBook,
  IconChart,
  IconGrid,
  IconTarget,
  IconTrend,
} from "@/components/shell/Icons";
import { FIXTURE_QUERY_VALUE, overviewFixture } from "@/lib/fixture";
import {
  buildContext,
  buildEngineCards,
  buildOverview,
  toConflictView,
  toConsensusView,
  toDataQualityView,
} from "@/lib/dataSource";
import { api, endpoints, type ApiConsensus, type ApiConflict } from "@/lib/api";
import { loadAnalysis } from "@/lib/dataSource";
import type { OverviewPageData } from "@/lib/types";

function OverviewInner() {
  const routeParams = useParams<{ code: string }>();
  const code = routeParams?.code ?? "600519";
  const search = useSearchParams();
  const fixture = search.get("fixture") === FIXTURE_QUERY_VALUE;

  const [data, setData] = useState<OverviewPageData | null>(
    fixture ? overviewFixture : null,
  );
  const [loading, setLoading] = useState(!fixture);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [drawerData, setDrawerData] = useState<{
    supporting: never[];
    counter: never[];
    neutral: never[];
    note?: string;
    method?: string;
  }>({ supporting: [], counter: [], neutral: [] });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await loadAnalysis(code);
      const ctx = buildContext(res.analysis);
      const engines = buildEngineCards(res.analysis, {
        ziweiAvailable: false,
        huangliOpinion: null,
        stockCode: code,
        fixtureSuffix: "",
      });

      const [consensus, conflict] = await Promise.allSettled([
        api.get<ApiConsensus>(endpoints.consensus(res.analysis.analysis_id)),
        api.get<ApiConflict>(endpoints.conflicts(res.analysis.analysis_id)),
      ]);

      // 黄历 opinion 来自因子集（前缀 H_），不走引擎 API
      const huangliFactors = res.factors?.observations.filter((o) => o.factor_id.startsWith("H_")) ?? [];
      const huangliAvailable = huangliFactors.length > 0;
      if (huangliAvailable) {
        const w = huangliFactors.reduce((a, o) => a + Math.max(o.confidence, 1e-6), 0);
        const raw = huangliFactors.reduce((a, o) => a + (o.normalized_value ?? 0) * Math.max(o.confidence, 1e-6), 0) / (w || 1);
        const score = Math.max(0, Math.min(100, 50 + raw * 50));
        engines[2] = {
          ...engines[2],
          score: Number(score.toFixed(2)),
          direction: score >= 58 ? 1 : score <= 42 ? -1 : 0,
          directionLabel: score >= 58 ? "偏强" : score <= 42 ? "偏弱" : "中性",
          confidence: w / huangliFactors.length,
          positiveCount: huangliFactors.filter((o) => o.direction === 1).length,
          negativeCount: huangliFactors.filter((o) => o.direction === -1).length,
          available: true,
        };
      }

      const consensusView =
        consensus.status === "fulfilled"
          ? toConsensusView(consensus.value)
          : overviewFixture.consensus;
      const conflictView =
        conflict.status === "fulfilled" ? toConflictView(conflict.value) : overviewFixture.conflict;

      const dq = toDataQualityView(
        ctx.quality,
        res.analysis.birth_profile.data_quality?.notes ?? [],
        `v${res.analysis.versions?.engine_version ?? "-"}`,
      );

      setData(
        buildOverview(
          code,
          ctx,
          engines,
          consensusView,
          conflictView,
          res.backtest,
          res.evidence,
          dq,
        ),
      );
      if (res.evidence) {
        setDrawerData({
          supporting: res.evidence.evidence.supporting_evidence as never[],
          counter: res.evidence.evidence.counter_evidence as never[],
          neutral: res.evidence.evidence.neutral_evidence as never[],
          note: res.evidence.evidence.note,
          method: res.evidence.evidence.retrieval_method,
        });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      if (fixture) setData(overviewFixture);
    } finally {
      setLoading(false);
    }
  }, [code, fixture]);

  useEffect(() => {
    if (!fixture) void load();
  }, [fixture, load]);

  // fixture 模式下同样准备抽屉数据（用演示条目）
  useEffect(() => {
    if (!fixture) return;
    setDrawerData({
      supporting: [],
      counter: [],
      neutral: [],
      note: "UI 复刻模式下不加载真实古籍检索结果。移除 URL 中的 fixture 参数即可查看真实证据。",
      method: "bm25 + topic_match + authority_weight + domain_filter",
    });
  }, [fixture]);

  const metrics = useMemo(() => data?.backtestMetrics ?? [], [data]);

  return (
    <AppShell activeNav="overview" dataStatus={error ? "bad" : "ok"} statusText={error ? "后端未连接" : "数据正常"}>
      <PageHero
        title="综合研判"
        subtitle="多模型交叉验证 · 识别趋势共识 · 提示关键风险"
        seal="正"
      />

      {data ? <StockContextBar context={data.context} activeTab="overview" onRecalculate={load} recalculating={loading} /> : null}

      {error && !fixture ? (
        <Card className="mb-3 p-4" testId="overview-error">
          <div className="text-[13px]" style={{ color: "var(--color-warn)" }}>
            后端数据加载失败：{error}
          </div>
          <p className="mt-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            请确认 API 已启动（<code className="smp-num">uvicorn apps.api.main:app --port 8000</code>）。
            如需查看参考图复刻效果，请访问{" "}
            <code className="smp-num">?fixture=ui-reference</code>。
          </p>
        </Card>
      ) : null}

      {loading && !data ? <SkeletonOverview /> : null}

      {data ? (
        <>
          {/* A + B + C */}
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,2.35fr)_minmax(0,1fr)_minmax(0,1fr)]">
            <Card testId="engine-scores">
              <CardHeader
                icon={<IconGrid size={14} />}
                title="模型评分与判断"
                right={
                  <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                    分数 = 传统规则强度聚合（非收益预测）
                  </span>
                }
              />
              <div className="grid grid-cols-1 gap-3 p-3.5 md:grid-cols-3">
                {data.engines.map((e) => (
                  <EngineScoreCard key={e.engine} engine={e} />
                ))}
              </div>
            </Card>

            <ConsensusCard consensus={data.consensus} />
            <ConflictCard conflict={data.conflict} />
          </div>

          {/* D + E：时间窗口 + 关键证据 */}
          <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card testId="time-window">
              <CardHeader
                icon={<IconChart size={14} />}
                title="未来时间窗口"
                right={
                  <div className="flex items-center gap-1">
                    {["近1月", "近3月", "近6月", "未来1年"].map((t, i) => (
                      <span
                        key={t}
                        className="rounded-[4px] border px-2 py-[2px] text-[11px]"
                        style={{
                          borderColor: i === 3 ? "var(--color-gold-dim)" : "var(--color-border)",
                          background: i === 3 ? "var(--color-gold-ghost)" : "transparent",
                          color: i === 3 ? "var(--color-gold)" : "var(--color-ink-muted)",
                        }}
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                }
                action={{ label: "查看详情" }}
              />
              <div className="px-3 py-2">
                <div className="mb-1 flex items-center gap-4 px-1">
                  {data.timeWindow.series.map((s2) => (
                    <span key={s2.key} className="flex items-center gap-1.5 text-[11.5px]">
                      <span
                        className="inline-block h-[3px] w-[14px] rounded-full"
                        style={{ background: s2.color }}
                      />
                      <span style={{ color: "var(--color-ink-sub)" }}>{s2.name}</span>
                    </span>
                  ))}
                  <span className="ml-3 flex items-center gap-1.5 text-[11.5px]">
                    <span
                      className="inline-block h-[10px] w-[14px] rounded-[2px]"
                      style={{ background: "rgba(79,211,155,0.22)", border: "1px solid rgba(79,211,155,0.45)" }}
                    />
                    <span style={{ color: "var(--color-ink-sub)" }}>高共识区</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-[11.5px]">
                    <span
                      className="inline-block h-[10px] w-[14px] rounded-[2px]"
                      style={{ background: "rgba(176,124,214,0.22)", border: "1px solid rgba(176,124,214,0.45)" }}
                    />
                    <span style={{ color: "var(--color-ink-sub)" }}>高冲突区</span>
                  </span>
                </div>
                <TimeWindowChart data={data.timeWindow} height={252} />
                <p className="px-1 pb-2 text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
                  纵轴为术数研究指数（0-100 规则强度），非收益率预测。曲线为基于当前引擎分数的
                  展示层平滑示意；正式时间窗口预测属 Phase 2。
                </p>
              </div>
            </Card>

            <Card testId="key-evidence">
              <CardHeader
                icon={<IconBook size={14} />}
                title="关键证据"
                action={{ label: "查看更多", onClick: () => setDrawer(true) }}
              />
              <div className="space-y-2 p-3.5">
                {data.evidence.length === 0 ? (
                  <div className="py-6 text-center text-[12px]" style={{ color: "var(--color-ink-faint)" }}>
                    暂无证据条目
                  </div>
                ) : (
                  data.evidence.map((ev) => <EvidenceRow key={ev.id} item={ev} />)
                )}
              </div>
            </Card>
          </div>

          {/* F：历史验证 + 数据质量 */}
          <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card testId="backtest-summary">
              <CardHeader
                icon={<IconTrend size={14} />}
                title="历史验证摘要"
                action={{ label: "历史验证详情" }}
              />
              <div className="grid grid-cols-2 gap-2.5 p-3.5 md:grid-cols-5">
                {metrics.map((m) => (
                  <BacktestMetricCard key={m.key} metric={m} />
                ))}
              </div>
              <div className="grid grid-cols-1 gap-4 px-3.5 pb-3.5 md:grid-cols-[minmax(0,1fr)_300px]">
                <div>
                  <div className="smp-metric-label mb-1">收益分布（示意）</div>
                  {data.distribution.length ? (
                    <DistributionChart bins={data.distribution} height={124} />
                  ) : (
                    <div className="py-6 text-center text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
                      尚无历史验证数据
                    </div>
                  )}
                </div>
                <div>
                  <div className="smp-metric-label mb-1">历史验证结论</div>
                  <p className="text-[11.5px] leading-[18px]" style={{ color: "var(--color-ink-sub)" }}>
                    {data.backtestConclusion}
                  </p>
                </div>
              </div>
            </Card>

            <DataQualityBadge quality={data.dataQuality} />
          </div>

          <div className="mt-3 flex items-center justify-center gap-2 text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
            <IconTarget size={13} />
            本页不显示"综合总分"，共识与历史有效性分列展示；任一模型失败不影响其他模型。
          </div>
        </>
      ) : null}

      <EvidenceDrawer
        open={drawer}
        onClose={() => setDrawer(false)}
        supporting={drawerData.supporting}
        counter={drawerData.counter}
        neutral={drawerData.neutral}
        note={drawerData.note}
        retrievalMethod={drawerData.method}
      />
    </AppShell>
  );
}

function SkeletonOverview() {
  return (
    <div className="space-y-3">
      <div className="smp-skeleton h-[74px] w-full" />
      <div className="grid grid-cols-3 gap-3">
        <div className="smp-skeleton h-[210px]" />
        <div className="smp-skeleton h-[210px]" />
        <div className="smp-skeleton h-[210px]" />
      </div>
      <div className="smp-skeleton h-[300px]" />
    </div>
  );
}

export default function OverviewPage() {
  return (
    <Suspense fallback={<div className="p-6 text-[13px]">加载中…</div>}>
      <OverviewInner />
    </Suspense>
  );
}
