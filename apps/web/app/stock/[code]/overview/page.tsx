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

import Link from "next/link";
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
  buildContextFromMulti,
  buildOverview,
  toConflictView,
  toConsensusView,
  toDataQualityView,
  toEngineCardsFromOpinions,
} from "@/lib/dataSource";
import { api, endpoints, type ApiConsensus, type ApiConflict, type ApiEventStudy, type ApiEvidence } from "@/lib/api";
import { loadMultiAnalysis } from "@/lib/analysisStore";
import type { OverviewPageData } from "@/lib/types";

function OverviewInner() {
  const routeParams = useParams<{ code: string }>();
  const code = routeParams?.code ?? "600519";
  const search = useSearchParams();
  const fixture = search.get("fixture") === FIXTURE_QUERY_VALUE;
  const isMoutaiFixture = fixture && code === "600519";
  const isUnsupportedFixture = fixture && code !== "600519";

  const [data, setData] = useState<OverviewPageData | null>(
    isMoutaiFixture ? overviewFixture : null,
  );
  const [loading, setLoading] = useState(!isMoutaiFixture && !isUnsupportedFixture);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [analysisId, setAnalysisId] = useState<string>("");
  const [researchStatus, setResearchStatus] = useState<string>("NOT_RUN");
  const [exporting, setExporting] = useState(false);
  const [drawerData, setDrawerData] = useState<{
    supporting: never[];
    counter: never[];
    neutral: never[];
    note?: string;
    method?: string;
  }>({ supporting: [], counter: [], neutral: [] });

  const load = useCallback(async () => {
    if (isMoutaiFixture) {
      setData(overviewFixture);
      setLoading(false);
      return;
    }
    if (isUnsupportedFixture) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // Phase 2：综合页的数据源改为 `/analysis/multi` —— 它同时产出
      // BaziOpinion / ZiweiOpinion / HuangliOpinion / Consensus / Conflict，
      // 全部来自正式 ConsensusEngine 与 ConflictDetector，
      // **不再是展示层 fixture aggregation**。
      const multi = await loadMultiAnalysis({ code, variant: "forward" });
      const aid = multi.analysis_id;

      // 三模型观点：直接消费后端 opinion，前端**不重算分数**
      const base = buildContextFromMulti(multi);
      const engines = toEngineCardsFromOpinions(multi);

      const [consensusRes, conflictRes, backtestRes, evidenceRes] = await Promise.allSettled([
        api.get<ApiConsensus>(endpoints.consensus(aid)),
        api.get<ApiConflict>(endpoints.conflicts(aid)),
        api.get<ApiEventStudy>(endpoints.backtest(aid)),
        api.get<ApiEvidence>(endpoints.evidence(aid)),
      ]);

      const consensusView =
        consensusRes.status === "fulfilled"
          ? toConsensusView(consensusRes.value)
          : isMoutaiFixture
            ? overviewFixture.consensus
            : null;
      const conflictView =
        conflictRes.status === "fulfilled"
          ? toConflictView(conflictRes.value)
          : isMoutaiFixture
            ? overviewFixture.conflict
            : null;

      const dq = toDataQualityView(
        base.quality,
        multi.birth_profile.data_quality?.notes ?? [],
        `v${multi.versions?.engine_version ?? "-"}`,
      );

      setData(
        buildOverview(
          code,
          base,
          engines,
          consensusView,
          conflictView,
          backtestRes.status === "fulfilled" ? backtestRes.value : null,
          evidenceRes.status === "fulfilled" ? evidenceRes.value : null,
          dq,
          isMoutaiFixture,
        ),
      );
      if (evidenceRes.status === "fulfilled") {
        setDrawerData({
          supporting: evidenceRes.value.evidence.supporting_evidence as never[],
          counter: evidenceRes.value.evidence.counter_evidence as never[],
          neutral: evidenceRes.value.evidence.neutral_evidence as never[],
          note: evidenceRes.value.evidence.note,
          method: evidenceRes.value.evidence.retrieval_method,
        });
      }
      setResearchStatus(consensusRes.status === "fulfilled"
        ? (consensusRes.value.research_status ?? "NOT_RUN")
        : "NOT_RUN");
      setAnalysisId(aid);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      if (isMoutaiFixture) {
        setData(overviewFixture);
      } else {
        setData(null);
      }
    } finally {
      setLoading(false);
    }
  }, [code, isMoutaiFixture, isUnsupportedFixture]);

  useEffect(() => {
    if (!isMoutaiFixture && !isUnsupportedFixture) void load();
  }, [isMoutaiFixture, isUnsupportedFixture, load]);

  // fixture 模式下同样准备抽屉数据（用演示条目）
  useEffect(() => {
    if (!isMoutaiFixture) return;
    setDrawerData({
      supporting: [],
      counter: [],
      neutral: [],
      note: "UI 复刻模式下不加载真实古籍检索结果。移除 URL 中的 fixture 参数即可查看真实证据。",
      method: "bm25 + topic_match + authority_weight + domain_filter",
    });
  }, [isMoutaiFixture]);

  const metrics = useMemo(() => data?.backtestMetrics ?? [], [data]);

  /**
   * 导出研究报告（Markdown / HTML）。
   *
   * 报告内容由后端 `render_report` 生成，包含版本 / 假设 / 限制 /
   * ResearchStatus / 负对照 —— 前端只负责触发下载，不参与内容拼装。
   */
  const exportReport = useCallback(
    async (format: "markdown" | "html") => {
      if (!analysisId) return;
      setExporting(true);
      try {
        const text = await api.raw(endpoints.report(analysisId, format));
        const blob = new Blob([text], {
          type: format === "html" ? "text/html;charset=utf-8" : "text/markdown;charset=utf-8",
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `report-${analysisId}.${format === "html" ? "html" : "md"}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setExporting(false);
      }
    },
    [analysisId],
  );


  if (isUnsupportedFixture) {
    return (
      <AppShell activeNav="overview" dataStatus="bad" statusText="演示模式受限">
        <PageHero
          title="综合研判"
          subtitle="八字 · 紫微 · 黄历三模型共识与分歧研究"
          seal="研"
        />
        <Card className="my-4 p-6" testId="unsupported-fixture-error">
          <div className="flex items-start gap-3">
            <span className="text-[24px]">⚠️</span>
            <div className="space-y-2">
              <h3 className="text-[16px] font-semibold" style={{ color: "var(--color-warn)" }}>
                演示模式（UI 复刻）仅支持 600519（贵州茅台）
              </h3>
              <p className="text-[13px] leading-relaxed" style={{ color: "var(--color-ink-sub)" }}>
                当前访问标的为 <code className="smp-num rounded border px-1.5 py-0.5">{code}</code>。
                为严格保证数据隔离，系统在演示模式下<strong>已统一阻断对真实后端的排盘分析与持久化请求</strong>，
                禁止静默进入真实模式。
              </p>
              <div className="flex items-center gap-3 pt-2">
                <Link
                  href={`/stock/${code}/overview`}
                  className="smp-btn smp-btn--primary"
                  data-testid="enter-real-mode-btn"
                >
                  移除 fixture 参数并进入真实分析模式
                </Link>
                <Link
                  href={`/stock/600519/overview?fixture=${FIXTURE_QUERY_VALUE}`}
                  className="smp-btn"
                >
                  返回 600519 演示标的
                </Link>
              </div>
            </div>
          </div>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell activeNav="overview" dataStatus={error ? "bad" : "ok"} statusText={error ? "后端未连接" : "数据正常"}>
      <PageHero
        title="综合研判"
        subtitle="多模型交叉验证 · 识别趋势共识 · 提示关键风险"
        seal="正"
        right={
          <div className="flex items-center gap-2" data-testid="report-export">
            <button
              type="button"
              disabled={!analysisId || exporting}
              onClick={() => void exportReport("markdown")}
              className="rounded border px-3 py-1 text-[12px] transition-opacity hover:opacity-80 disabled:opacity-40"
              style={{ borderColor: "var(--color-border)", color: "var(--color-ink)" }}
            >
              {exporting ? "导出中…" : "导出 Markdown"}
            </button>
            <button
              type="button"
              disabled={!analysisId || exporting}
              onClick={() => void exportReport("html")}
              className="rounded border px-3 py-1 text-[12px] transition-opacity hover:opacity-80 disabled:opacity-40"
              style={{ borderColor: "var(--color-border)", color: "var(--color-ink)" }}
            >
              导出 HTML
            </button>
            <span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
              ResearchStatus {researchStatus}
            </span>
          </div>
        }
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

      {/* 数据可用性横幅：合成/降级行情时必须显著告警（P0-1 验收要求） */}
      {data?.researchStatus === "NO_REAL_DATA" ? (
        <div
          data-testid="synthetic-data-banner"
          className="mb-3 flex items-start gap-3 border px-4 py-3 text-[12.5px] leading-relaxed"
          style={{
            borderColor: "var(--color-warn)",
            background: "color-mix(in srgb, var(--color-warn) 11%, transparent)",
            color: "var(--color-warn)",
          }}
        >
          <span className="mt-[1px] shrink-0 text-[15px]" aria-hidden>
            ⚠
          </span>
          <div>
            <div className="font-semibold">
              当前为合成/降级行情，仅用于系统联调，不构成历史研究证据（RESEARCH_DATA_UNAVAILABLE）
            </div>
            <div className="mt-1 text-[11.5px] opacity-85">
              历史验证卡片、上涨率与事件研究仅代表前端/链路测试输出；真实研究结论必须基于
              真实历史行情运行 <code className="smp-num">POST /api/v1/research/run</code>。
              {(data.researchStatusReasons ?? []).map((r, i) => (
                <span key={i} className="mt-1 block">{r}</span>
              ))}
            </div>
          </div>
        </div>
      ) : null}

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
                {data.timeWindow.series.length > 0 ? (
                  <>
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
                  </>
                ) : (
                  <div className="flex h-[252px] flex-col items-center justify-center text-center">
                    <p className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
                      未来时间窗口外推尚未运行（系统不提供伪造预测曲线）
                    </p>
                    <p className="mt-1 text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                      正式时间序列外推与共振窗口分析将在 Phase 2 完整上线
                    </p>
                  </div>
                )}
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
                      尚无历史验证样本分布数据（不采用正态假设伪造分箱）
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
