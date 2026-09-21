"use client";

/**
 * 八字详情页（复刻 doc/ui-reference/03_bazi_detail.png）。
 *
 * 结构：五行分布 | 四柱八字 | 命局摘要 → 时间结构 → 正向/负向因素 → 古籍证据与历史统计。
 * 四柱盘必须是真实 DOM（禁止图片），且四柱数值全部来自后端 `chart_artifact.raw_chart`。
 */

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHero } from "@/components/shell/TopBar";
import { StockContextBar } from "@/components/stock/StockContextBar";
import { Card, CardHeader, Chip } from "@/components/cards/Card";
import { BookRow } from "@/components/cards/EngineCards";
import { BaziChart, FateSummary, TimeStructure, WuxingDistribution } from "@/components/bazi/BaziChart";
import { FactorList, FactorDisclaimer } from "@/components/factor/Factor";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import {
  IconBook,
  IconDiamond,
  IconGrid,
  IconLayers,
  IconTaiji,
} from "@/components/shell/Icons";
import { FIXTURE_QUERY_VALUE, baziFixture } from "@/lib/fixture";
import {
  buildBaziPage,
  buildBaziPageFromMulti,
  buildContext,
  loadAnalysis,
  invalidateBaziAnalysisCache,
  variantModeLabel,
} from "@/lib/dataSource";
import { useAnalysis } from "@/lib/analysisStore";
import { api, endpoints, type ApiEvidence, type ApiEventStudy } from "@/lib/api";
import type { BaziPageData } from "@/lib/types";

function BaziInner() {
  const routeParams = useParams<{ code: string }>();
  const code = routeParams?.code ?? "600519";
  const search = useSearchParams();
  const fixture = search.get("fixture") === FIXTURE_QUERY_VALUE;
  const isMoutaiFixture = fixture && code === "600519";
  const isUnsupportedFixture = fixture && code !== "600519";

  const { analysis, loading: multiLoading, error: multiError, reload } = useAnalysis(code);

  const [data, setData] = useState<BaziPageData | null>(isMoutaiFixture ? baziFixture : null);
  const [loading, setLoading] = useState(!isMoutaiFixture && !isUnsupportedFixture);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [drawerData, setDrawerData] = useState<{
    supporting: never[];
    counter: never[];
    neutral: never[];
    note?: string;
    method?: string;
  }>({ supporting: [], counter: [], neutral: [] });

  const prevEvidenceRef = useRef<ApiEvidence | null>(null);
  const prevBacktestRef = useRef<ApiEventStudy | null>(null);

  // 1. 优先使用会话级缓存的 analysis 数据（0ms 瞬间秒开）
  useEffect(() => {
    if (isMoutaiFixture || isUnsupportedFixture) return;
    if (!analysis) return;

    if (analysis.bazi_chart) {
      setData(buildBaziPageFromMulti(analysis, prevEvidenceRef.current, prevBacktestRef.current));
      setLoading(false);
      setError(null);
    }

    let active = true;
    const aid = analysis.analysis_id;
    Promise.allSettled([
      api.get<ApiEvidence>(endpoints.evidence(aid)),
      api.get<ApiEventStudy>(endpoints.backtest(aid)),
    ]).then(([evRes, btRes]) => {
      if (!active) return;
      const ev = evRes.status === "fulfilled" ? evRes.value : null;
      const bt = btRes.status === "fulfilled" ? btRes.value : null;
      prevEvidenceRef.current = ev;
      prevBacktestRef.current = bt;
      if (analysis.bazi_chart) {
        setData(buildBaziPageFromMulti(analysis, ev, bt));
      }
      if (ev) {
        setDrawerData({
          supporting: ev.evidence.supporting_evidence as never[],
          counter: ev.evidence.counter_evidence as never[],
          neutral: ev.evidence.neutral_evidence as never[],
          note: ev.evidence.note,
          method: ev.evidence.retrieval_method,
        });
      }
    });

    return () => {
      active = false;
    };
  }, [analysis, isMoutaiFixture, isUnsupportedFixture]);

  // 2. 独立兜底加载（若 multi 出错时尝试单模型分析）
  const fallbackLoad = useCallback(async () => {
    if (isMoutaiFixture || isUnsupportedFixture) return;
    setLoading(true);
    setError(null);
    try {
      const res = await loadAnalysis(code);
      setData(
        buildBaziPage(
          buildContext(res.analysis),
          res.analysis.chart as Record<string, unknown>,
          res.factors,
          res.evidence,
          res.backtest,
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
    } finally {
      setLoading(false);
    }
  }, [code, isMoutaiFixture, isUnsupportedFixture]);

  useEffect(() => {
    if (multiError && !data) {
      void fallbackLoad();
    }
  }, [multiError, data, fallbackLoad]);

  const handleRecalculate = useCallback(() => {
    invalidateBaziAnalysisCache(code);
    prevEvidenceRef.current = null;
    prevBacktestRef.current = null;
    reload();
  }, [code, reload]);


  if (isUnsupportedFixture) {
    return (
      <AppShell activeNav="bazi" dataStatus="bad" statusText="演示模式受限">
        <PageHero
          title="八字详情"
          subtitle="以天地之数，观市场之机"
          seal="命"
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
                  href={`/stock/${code}/bazi`}
                  className="smp-btn smp-btn--primary"
                  data-testid="enter-real-mode-btn"
                >
                  移除 fixture 参数并进入真实分析模式
                </Link>
                <Link
                  href={`/stock/600519/bazi?fixture=${FIXTURE_QUERY_VALUE}`}
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
    <AppShell activeNav="bazi" dataStatus={error ? "bad" : "ok"} statusText={error ? "后端未连接" : "数据正常"}>
      <PageHero
        title="八字详情"
        subtitle="以天地之数，观市场之机"
        seal="命"
        right={
          <div className="hidden text-right text-[12px] leading-[24px] tracking-[0.3em] xl:block"
            style={{ color: "rgba(212,184,122,0.4)" }}
            aria-hidden="true"
          >
            天行有常
            <br />
            数理为镜
          </div>
        }
      />

      {data ? (
        <StockContextBar
          context={data.context}
          activeTab="bazi"
          onRecalculate={handleRecalculate}
          recalculating={multiLoading || loading}
          showTabs
        />
      ) : null}


      {error ? (
        <Card className="mb-3 p-4" testId="bazi-error">
          <div className="text-[13px]" style={{ color: "var(--color-warn)" }}>
            后端数据加载失败：{error}
          </div>
          <p className="mt-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            请确认 API 已启动。如需查看参考图复刻效果，请访问{" "}
            <code className="smp-num">?fixture=ui-reference</code>。
          </p>
        </Card>
      ) : null}

      {loading && !data ? <div className="smp-skeleton h-[640px] w-full" /> : null}

      {data ? (
        <>
          {/* 第一层：五行分布 | 四柱八字 | 命局摘要 (26:45:29) */}
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.73fr)_minmax(0,1.11fr)]">
            <Card testId="wuxing-card">
              <CardHeader icon={<IconGrid size={14} />} title="五行分布" dense />
              <WuxingDistribution bars={data.wuxing} />
              <div className="px-3 pb-2">
                <p className="text-[10px] leading-[15px]" style={{ color: "var(--color-ink-faint)" }}>
                  五行力量为工程估算（天干 1.0、月支 ×1.5、日支 ×1.2，藏干按本气/中气/余气赋权），
                  属研究性近似，非传统定论。
                </p>
              </div>
            </Card>

            <Card testId="bazi-chart-card">
              <CardHeader
                icon={<IconTaiji size={14} />}
                title="四柱八字"
                dense
                action={{ label: "八字排盘详情" }}
              />
              <div className="p-2.5">
                <BaziChart pillars={data.pillars} />
                <div className="mt-1.5 flex items-center gap-1.5 text-[10px]" style={{ color: "var(--color-ink-faint)" }}>
                  <IconLayers size={11} />
                  原始盘面已保存至 chart_artifact.raw_chart，含 engine_version / config_version。
                </div>
              </div>
            </Card>

            <Card testId="fate-summary-card">
              <CardHeader icon={<IconDiamond size={14} />} title="命局摘要" dense />
              <FateSummary rows={data.summary} />
            </Card>
          </div>

          {/* 第二层：时间结构（说明与运限假设并入卡头，把首屏留给数据） */}
          <Card className="mt-2" testId="time-structure">
            <CardHeader
              icon={<IconDiamond size={14} />}
              title="时间结构"
              dense
              right={
                <div className="flex flex-wrap items-center gap-2 text-[10.5px]">
                  <span style={{ color: "var(--color-warn)" }}>
                    {data.variantNote || "股票无天然性别，运限推演基于假设规则"}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span className="smp-metric-label text-[10px]">运限假设</span>
                    <span
                      className="rounded-[3px] border px-1.5 text-[10px]"
                      style={{ borderColor: "var(--color-border-strong)", color: "var(--color-ink-sub)" }}
                      data-testid="variant-mode"
                      data-variant-mode={data.variantMode}
                      title={`后端原值：${data.variantMode}`}
                    >
                      {variantModeLabel(data.variantMode)}
                    </span>
                  </span>
                </div>
              }
            />
            <TimeStructure items={data.timeline} />
          </Card>

          {/* 第三层：正负因素（首屏各 3 条，其余可展开） */}
          <div className="mt-2 grid grid-cols-1 gap-3 xl:grid-cols-2">
            <Card testId="positive-factors">
              <CardHeader
                icon={<span style={{ color: "var(--color-up)" }}>↑</span>}
                title="正向因素（利多）"
                right={<span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>按规则强度排序</span>}
              />
              <FactorList
                factors={data.positiveFactors}
                tone="positive"
                emptyText="暂无正向因子"
                initialVisible={3}
              />
            </Card>

            <Card testId="negative-factors">
              <CardHeader
                icon={<span style={{ color: "var(--color-down)" }}>↓</span>}
                title="负向因素（利空）"
                right={<span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>按规则强度排序</span>}
              />
              <FactorList
                factors={data.negativeFactors}
                tone="negative"
                emptyText="暂无负向因子"
                initialVisible={3}
              />
            </Card>
          </div>

          <div className="mt-1" data-testid="factor-disclaimer-card">
            <FactorDisclaimer />
          </div>

          {/* 第四层：古籍证据 + 历史统计 */}
          <div className="mt-1.5 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card testId="bazi-evidence">
              <CardHeader
                icon={<IconBook size={14} />}
                title="古籍证据"
                action={{ label: "更多古籍证据", onClick: () => setDrawer(true) }}
              />
              <div className="space-y-2 p-3">
                {data.evidence.length === 0 ? (
                  <div className="py-4 text-center text-[12px]" style={{ color: "var(--color-ink-faint)" }}>
                    暂无可展示的古籍条目
                  </div>
                ) : (
                  data.evidence.map((ev) => (
                    <BookRow
                      key={ev.id}
                      title={ev.title}
                      detail={ev.detail.slice(0, 60) + (ev.detail.length > 60 ? "…" : "")}
                      tag={ev.source}
                    />
                  ))
                )}
              </div>
            </Card>

            <Card testId="bazi-statistics">
              <CardHeader icon={<IconLayers size={14} />} title="历史统计" />
              <div className="p-3">
                {data.statistics.map((s) => (
                  <div
                    key={s.label}
                    className="flex items-center justify-between border-b py-2.5 last:border-b-0"
                    style={{ borderColor: "rgba(30,52,68,0.55)" }}
                  >
                    <span className="text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
                      {s.label}
                    </span>
                    <span className="smp-num text-[13px]" style={{ color: "var(--color-ink)" }}>
                      {s.value}
                    </span>
                  </div>
                ))}
                <p className="mt-3 text-[11px] leading-[17px]" style={{ color: "var(--color-ink-faint)" }}>
                  历史统计来自事件研究（factor_observation × 未来收益标签）。
                  样本不足时会如实显示"—"，不会用 0 或猜测值填充。
                </p>
              </div>
            </Card>
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

export default function BaziPage() {
  return (
    <Suspense fallback={<div className="p-6 text-[13px]">加载中…</div>}>
      <BaziInner />
    </Suspense>
  );
}
