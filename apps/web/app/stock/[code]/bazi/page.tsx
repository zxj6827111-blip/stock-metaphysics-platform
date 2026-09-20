"use client";

/**
 * 八字详情页（复刻 doc/ui-reference/03_bazi_detail.png）。
 *
 * 结构：五行分布 | 四柱八字 | 命局摘要 → 时间结构 → 正向/负向因素 → 古籍证据与历史统计。
 * 四柱盘必须是真实 DOM（禁止图片），且四柱数值全部来自后端 `chart_artifact.raw_chart`。
 */

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

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
  buildContext,
  loadAnalysis,
} from "@/lib/dataSource";
import type { BaziPageData } from "@/lib/types";

function BaziInner() {
  const routeParams = useParams<{ code: string }>();
  const code = routeParams?.code ?? "600519";
  const search = useSearchParams();
  const fixture = search.get("fixture") === FIXTURE_QUERY_VALUE;
  const isMoutaiFixture = fixture && code === "600519";

  const [data, setData] = useState<BaziPageData | null>(isMoutaiFixture ? baziFixture : null);
  const [loading, setLoading] = useState(!isMoutaiFixture);
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
    if (isMoutaiFixture) return;
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
  }, [code, isMoutaiFixture]);

  useEffect(() => {
    void load();
  }, [load]);

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
        <StockContextBar context={data.context} activeTab="bazi" onRecalculate={load} recalculating={loading} showTabs />
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
          {/* 第一层：五行分布 | 四柱八字 | 命局摘要 */}
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-[300px_minmax(0,1.5fr)_360px]">
            <Card testId="wuxing-card">
              <CardHeader icon={<IconGrid size={14} />} title="五行分布" />
              <WuxingDistribution bars={data.wuxing} />
              <div className="px-4 pb-3">
                <p className="text-[10.5px] leading-[16px]" style={{ color: "var(--color-ink-faint)" }}>
                  五行力量为工程估算（天干 1.0、月支 ×1.5、日支 ×1.2，藏干按本气/中气/余气赋权），
                  属研究性近似，非传统定论。
                </p>
              </div>
            </Card>

            <Card testId="bazi-chart-card">
              <CardHeader
                icon={<IconTaiji size={14} />}
                title="四柱八字"
                action={{ label: "八字排盘详情" }}
              />
              <div className="p-3.5">
                <BaziChart pillars={data.pillars} />
                <div className="mt-2.5 flex items-center gap-2 text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
                  <IconLayers size={12} />
                  原始盘面已保存至 chart_artifact.raw_chart，含 engine_version / config_version，可审计、可复算。
                </div>
              </div>
            </Card>

            <Card testId="fate-summary-card">
              <CardHeader icon={<IconDiamond size={14} />} title="命局摘要" />
              <FateSummary rows={data.summary} />
            </Card>
          </div>

          {/* 第二层：时间结构 */}
          <Card className="mt-3" testId="time-structure-card">
            <CardHeader
              icon={<IconDiamond size={14} />}
              title="时间结构"
              right={
                <div className="flex items-center gap-2">
                  <Chip tone="gold">Variant A（阳男）</Chip>
                  <Chip tone="flat">Variant B（阴女）</Chip>
                  <span className="text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
                    Phase 2 将并行回测两种假设
                  </span>
                </div>
              }
            />
            <TimeStructure
              items={data.timeline}
              variantMode={data.variantMode}
              variantNote={data.variantNote}
            />
          </Card>

          {/* 第三层：正负因素 */}
          <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
            <Card testId="positive-factors">
              <CardHeader
                icon={<span style={{ color: "var(--color-up)" }}>↑</span>}
                title="正向因素（利多）"
                right={<span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>按规则强度排序</span>}
              />
              <FactorList factors={data.positiveFactors} tone="positive" emptyText="暂无正向因子" />
            </Card>

            <Card testId="negative-factors">
              <CardHeader
                icon={<span style={{ color: "var(--color-down)" }}>↓</span>}
                title="负向因素（利空）"
                right={<span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>按规则强度排序</span>}
              />
              <FactorList factors={data.negativeFactors} tone="negative" emptyText="暂无负向因子" />
            </Card>
          </div>

          <div className="mt-3">
            <Card testId="factor-disclaimer-card">
              <FactorDisclaimer />
            </Card>
          </div>

          {/* 第四层：古籍证据 + 历史统计 */}
          <div className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card testId="bazi-evidence">
              <CardHeader
                icon={<IconBook size={14} />}
                title="古籍证据"
                action={{ label: "更多古籍证据", onClick: () => setDrawer(true) }}
              />
              <div className="space-y-3 p-4">
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
              <div className="p-4">
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
