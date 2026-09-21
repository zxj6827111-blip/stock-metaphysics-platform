"use client";

/**
 * 首页（复刻 doc/ui-reference/01_home.png）。
 *
 * 结构：Hero 标题 + 大搜索框 + 最近分析（3 卡） + 系统状态 + 平台能力（4 卡）。
 * 视觉结构以 PNG 为准；业务数据默认走真实 API，`?fixture=ui-reference` 时用固定演示数据。
 */

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHero } from "@/components/shell/TopBar";
import { Card, CardHeader, Chip } from "@/components/cards/Card";
import { MiniTrend } from "@/components/charts/Charts";
import { StockSearch } from "@/components/stock/StockSearch";
import { Astrolabe, MountainSilhouette, SealStamp } from "@/components/shell/Decorations";
import {
  IconChart,
  IconArrowRight,
  IconBook,
  IconCalendar,
  IconDatabase,
  IconGrid,
  IconLayers,
  IconSearch,
  IconTaiji,
  IconTarget,
  IconTrend,
} from "@/components/shell/Icons";
import { FIXTURE_QUERY_VALUE, homeFixture, homeCapabilitySub } from "@/lib/fixture";
import { api, endpoints, type ApiEnginesResponse } from "@/lib/api";
import { getRecentAnalyses, type RecentAnalysisItem } from "@/lib/historyStore";

const ENGINE_MINILABEL: Record<string, string> = {
  bazi: "八字",
  ziwei: "紫微",
  huangli: "黄历",
  backtest: "回测",
};

const CAP_ICONS: Record<string, React.ComponentType<{ size?: number }>> = {
  multi: IconLayers,
  window: IconCalendar,
  classics: IconBook,
  backtest: IconTrend,
};

const CAP_TONE: Record<string, { color: string; bg: string }> = {
  up: { color: "var(--color-up)", bg: "rgba(232,88,90,0.07)" },
  info: { color: "var(--color-info)", bg: "rgba(107,143,212,0.07)" },
  gold: { color: "var(--color-gold)", bg: "rgba(212,184,122,0.07)" },
  down: { color: "var(--color-down)", bg: "rgba(79,211,155,0.07)" },
};

const SYSTEM_ICONS: Record<string, React.ComponentType<{ size?: number }>> = {
  bazi: IconTaiji,
  ziwei: IconTarget,
  huangli: IconCalendar,
  market: IconChart,
  knowledge: IconBook,
};

function RecentCard({ item }: { item: RecentAnalysisItem }) {
  const tone =
    item.statusTone === "up"
      ? "up"
      : item.statusTone === "down"
        ? "down"
        : item.statusTone === "conflict"
          ? "conflict"
          : "flat";
  const priceColor = item.trend === "up" ? "var(--color-up)" : "var(--color-down)";
  const seed = item.code.charCodeAt(0) + item.code.charCodeAt(2);
  const spark = Array.from({ length: 28 }, (_, i) =>
    50 + Math.sin((i + seed) / 3.1) * 12 + Math.cos((i + seed) / 7.4) * 6 + i * (item.trend === "up" ? 0.5 : -0.4),
  );

  return (
    <Card className="p-3" testId={`recent-${item.code}`}>
      <div className="flex items-center gap-2">
        <span className="smp-num text-[13.5px] font-medium" style={{ color: "var(--color-gold)" }}>
          {item.code}
        </span>
        <span className="text-[13.5px] font-medium" style={{ color: "var(--color-ink)" }}>
          {item.name}
        </span>
        <span className="ml-auto">
          <Chip tone={tone as "up" | "down" | "flat" | "conflict"}>{item.status}</Chip>
        </span>
      </div>

      <div className="mt-1 flex items-center gap-2 text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
        <span className="smp-num">{item.analyzedAt}</span>
      </div>

      <div className="mt-1.5 flex items-end gap-2">
        <span className="smp-num text-[21px] font-semibold leading-none" style={{ color: priceColor }}>
          {item.price}
        </span>
        <span className="smp-num text-[12px]" style={{ color: priceColor }}>
          {item.changePct}
        </span>
      </div>

      {item.price !== "—" ? (
        <div className="mt-1">
          <MiniTrend values={spark} tone={item.trend === "down" ? "down" : "up"} height={44} />
        </div>
      ) : (
        <div
          className="mt-1 flex h-[44px] items-center justify-center rounded border border-dashed text-[11px]"
          style={{ borderColor: "var(--color-border)", color: "var(--color-ink-faint)" }}
        >
          暂无实时分时走势
        </div>
      )}

      <div className="mt-1.5 flex items-center gap-3 border-t pt-1.5" style={{ borderColor: "var(--color-border)" }}>
        {item.engines.map((e) => (
          <span key={e.key} className="flex items-center gap-1 text-[11px]">
            <span style={{ color: "var(--color-ink-muted)" }}>{ENGINE_MINILABEL[e.key] ?? e.label}</span>
            <span
              style={{
                color:
                  e.direction > 0
                    ? "var(--color-up)"
                    : e.direction < 0
                      ? "var(--color-down)"
                      : "var(--color-flat)",
              }}
            >
              {e.direction > 0 ? "+" : e.direction < 0 ? "−" : "0"}
            </span>
          </span>
        ))}
      </div>
    </Card>
  );
}

function HomeInner() {
  const params = useSearchParams();
  const fixture = params.get("fixture") === FIXTURE_QUERY_VALUE;

  const [systemStatus, setSystemStatus] = useState(
    fixture ? homeFixture.systemStatus : [],
  );
  const [statusText, setStatusText] = useState(fixture ? "数据正常" : "正在检查");
  const [dataStatus, setDataStatus] = useState<"ok" | "warn" | "bad">(fixture ? "ok" : "warn");
  const [systemSummary, setSystemSummary] = useState(fixture ? "全部正常" : "检查中…");
  const [systemSummaryColor, setSystemSummaryColor] = useState(
    fixture ? "var(--color-down)" : "var(--color-ink-faint)",
  );

  useEffect(() => {
    if (fixture) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get<ApiEnginesResponse>(endpoints.engineStatus());
        if (cancelled) return;
        const mapped = res.engines
          .filter((e) => ["bazi", "ziwei", "huangli"].includes(e.engine_id) || e.available)
          .slice(0, 5)
          .map((e) => ({
            key: e.engine_id,
            label: e.display_name,
            state: e.available ? ("ok" as const) : ("off" as const),
            note: e.available ? "运行正常" : "未启用（Phase 2）",
            latency: e.available ? (e.engine_version.match(/(\d+\.\d+\.\d+)/)?.[1] ?? "—") : "—",
          }));
        setSystemStatus(mapped);
        const degraded = res.market_provider === "synthetic_demo";
        setDataStatus(degraded ? "warn" : "ok");
        setStatusText(degraded ? "离线合成数据" : "数据正常");
        const allOk = mapped.every((e) => e.state === "ok") && !degraded;
        const hasOff = mapped.some((e) => e.state !== "ok") || degraded;
        if (allOk) {
          setSystemSummary("全部正常");
          setSystemSummaryColor("var(--color-down)");
        } else if (hasOff) {
          setSystemSummary("部分降级/未启用");
          setSystemSummaryColor("var(--color-gold)");
        } else {
          setSystemSummary("运行正常");
          setSystemSummaryColor("var(--color-down)");
        }
      } catch {
        if (cancelled) return;
        setDataStatus("bad");
        setStatusText("后端未连接");
        setSystemSummary("后端未连接");
        setSystemSummaryColor("var(--color-up)");
        setSystemStatus([
          { key: "bazi", label: "八字引擎", state: "off", note: "无法连接后端", latency: "—" },
          { key: "ziwei", label: "紫微引擎", state: "off", note: "无法连接后端", latency: "—" },
          { key: "huangli", label: "择日黄历", state: "off", note: "无法连接后端", latency: "—" },
          { key: "market", label: "行情接入", state: "off", note: "无法连接后端", latency: "—" },
          { key: "knowledge", label: "知识中心", state: "off", note: "无法连接后端", latency: "—" },
        ]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fixture]);

  const [recent, setRecent] = useState<RecentAnalysisItem[]>([]);

  useEffect(() => {
    if (fixture) {
      setRecent(homeFixture.recent);
    } else {
      setRecent(getRecentAnalyses());
    }
  }, [fixture]);

  return (
    <AppShell activeNav="home" dataStatus={dataStatus} statusText={statusText}>
      {/* Hero */}
      <section
        className="relative mb-2.5 overflow-hidden rounded-[10px] border px-6 py-4"
        style={{
          borderColor: "var(--color-border)",
          background:
            "radial-gradient(ellipse 550px 380px at calc(100% - 150px) 45%, rgba(212,184,122,0.18) 0%, rgba(212,184,122,0.05) 50%, transparent 75%), linear-gradient(180deg, rgba(14,28,40,0.95) 0%, rgba(9,19,28,0.98) 100%)",
        }}
      >
        <MountainSilhouette opacity={0.32} />

        {/* 右侧天体星盘与寄语 */}
        <Astrolabe
          size={280}
          glow={true}
          className="pointer-events-none absolute right-8 top-1/2 -translate-y-1/2 hidden xl:block"
        />
        <div
          className="pointer-events-none absolute right-8 bottom-2.5 hidden text-right text-[11px] tracking-[0.14em] xl:block"
          style={{ color: "var(--color-ink-muted)" }}
        >
          东方智慧 · 现代方法 · 更深入的市场认知
        </div>

        <div className="relative max-w-[880px]">
          {/* 主标与四列题词 */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1
                className="smp-serif-title smp-gold-shimmer text-[48px] font-bold leading-[1.08] tracking-[0.04em]"
                style={{
                  color: "var(--color-gold-strong)",
                  fontFamily: "var(--font-serif-cn)",
                  textShadow: "0 3px 24px rgba(212,184,122,0.22)",
                }}
                data-testid="home-title"
              >
                股票玄学多模型研究平台
              </h1>
              <p className="mt-1.5 text-[12.5px] tracking-[0.15em]" style={{ color: "var(--color-ink-sub)" }}>
                融贯东方智慧 · 结合现代量化 · 探索市场的多维可能
              </p>
            </div>

            {/* 四列典雅竖排题词 (观天时/察地利/究人道/研规律) 与朱砂印章 */}
            <div
              className="hidden sm:flex flex-row-reverse items-start gap-2 select-none pt-1 pr-4 shrink-0"
              style={{ fontFamily: "var(--font-serif-cn)" }}
              aria-hidden="true"
            >
              <div
                className="text-[12px] leading-[16px] tracking-[0.22em]"
                style={{ writingMode: "vertical-rl", color: "rgba(212,184,122,0.85)" }}
              >
                观天时
              </div>
              <div
                className="text-[12px] leading-[16px] tracking-[0.22em]"
                style={{ writingMode: "vertical-rl", color: "rgba(212,184,122,0.85)" }}
              >
                察地利
              </div>
              <div
                className="text-[12px] leading-[16px] tracking-[0.22em]"
                style={{ writingMode: "vertical-rl", color: "rgba(212,184,122,0.85)" }}
              >
                究人道
              </div>
              <div className="flex flex-col items-center gap-1.5">
                <div
                  className="text-[12px] leading-[16px] tracking-[0.22em]"
                  style={{ writingMode: "vertical-rl", color: "rgba(212,184,122,0.85)" }}
                >
                  研规律
                </div>
                <SealStamp text="玄" size={20} />
              </div>
            </div>
          </div>

          <div
            className="mt-3 rounded-[8px] border px-4 py-3"
            style={{ borderColor: "var(--color-border-strong)", background: "rgba(6,14,21,0.65)" }}
          >
            <div className="mb-2 flex items-center gap-1.5 text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
              <IconSearch size={13} style={{ color: "var(--color-ink-muted)" }} />
              输入股票代码，查看八字、紫微、黄历与历史回测综合研究
            </div>
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <StockSearch variant="hero" defaultValue="600519" />
              </div>
              <button type="button" className="smp-btn h-[48px] px-4 text-[12px]" disabled title="Phase 2">
                <IconGrid size={14} />
                高级设置
              </button>
            </div>
            <div className="mt-2 flex items-center gap-3.5 text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
              <span>示例：</span>
              <span className="smp-num">600519 贵州茅台</span>
              <span className="smp-num">000001 平安银行</span>
              <span className="smp-num">300750 宁德时代</span>
            </div>
          </div>
        </div>
      </section>

      {/* 最近分析 + 系统状态 (2.1 : 1 比例) */}
      <div className="grid grid-cols-1 gap-2.5 xl:grid-cols-[minmax(0,2.1fr)_minmax(0,1fr)]">
        <Card testId="recent-analysis">
          <CardHeader
            icon={<IconDatabase size={14} />}
            title="最近分析"
            action={fixture ? { label: "查看更多" } : undefined}
          />
          {recent.length > 0 ? (
            <div className="grid grid-cols-1 gap-2.5 p-3 md:grid-cols-3">
              {recent.map((r) => (
                <RecentCard key={r.code} item={r} />
              ))}
            </div>
          ) : (
            <div className="flex h-[160px] flex-col items-center justify-center p-4 text-center" data-testid="recent-empty">
              <p className="text-[13px]" style={{ color: "var(--color-ink-sub)" }}>
                暂无最近分析记录
              </p>
              <p className="mt-1 text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
                在上方搜索框输入股票代码即可发起分析
              </p>
            </div>
          )}
        </Card>

        <Card testId="system-status">
          <CardHeader
            icon={<IconTarget size={14} />}
            title="系统状态"
            right={
              <span
                className="flex items-center gap-1 text-[11.5px]"
                style={{ color: systemSummaryColor }}
                data-testid="system-summary"
              >
                {systemSummary}
                <IconArrowRight size={11} />
              </span>
            }
          />
          <div className="px-3 py-1.5">
            {systemStatus.map((s) => {
              const Icon = SYSTEM_ICONS[s.key] ?? IconTaiji;
              const ok = s.state === "ok";
              return (
                <div
                  key={s.key}
                  className="flex items-center gap-2 border-b py-[6.5px] last:border-b-0"
                  style={{ borderColor: "rgba(30,52,68,0.55)" }}
                  data-testid={`system-${s.key}`}
                >
                  <span style={{ color: ok ? "var(--color-gold-dim)" : "var(--color-ink-faint)" }}>
                    <Icon size={14} />
                  </span>
                  <span className="text-[12px]" style={{ color: ok ? "var(--color-ink-sub)" : "var(--color-ink-faint)" }}>
                    {s.label}
                  </span>
                  <span
                    className="ml-auto flex h-[16px] w-[16px] items-center justify-center rounded-full"
                    style={{
                      color: ok ? "var(--color-down)" : "var(--color-ink-faint)",
                      border: `1px solid ${ok ? "rgba(79,211,155,0.5)" : "var(--color-border-strong)"}`,
                      background: ok ? "var(--color-down-bg)" : "transparent",
                    }}
                  >
                    {ok ? "✓" : "—"}
                  </span>
                  <span className="w-[100px] text-[11.5px]" style={{ color: ok ? "var(--color-ink-sub)" : "var(--color-ink-faint)" }}>
                    {s.note}
                  </span>
                  <span className="smp-num w-[44px] text-right text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
                    {s.latency}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* 平台能力 */}
      <Card className="mt-2.5" testId="capabilities">
        <CardHeader
          icon={<IconGrid size={14} />}
          title="平台能力"
          action={{ label: "探索更多研究可能" }}
        />
        <div className="grid grid-cols-1 gap-2.5 p-3 md:grid-cols-2 xl:grid-cols-4">
          {homeFixture.capabilities.map((c) => {
            const Icon = CAP_ICONS[c.key] ?? IconLayers;
            const t = CAP_TONE[c.tone];
            return (
              <div
                key={c.key}
                className="flex items-center gap-3 rounded-[8px] border px-3 py-2.5"
                style={{ borderColor: "var(--color-border)", background: t.bg }}
              >
                <span
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full"
                  style={{ color: t.color, border: `1px solid ${t.color}55`, background: `${t.color}14` }}
                >
                  <Icon size={19} />
                </span>
                <div className="min-w-0">
                  <div className="text-[13px] font-medium" style={{ color: "var(--color-ink)" }}>
                    {c.title}
                  </div>
                  <div className="mt-0.5 text-[11px] leading-[15px]" style={{ color: "var(--color-ink-muted)" }}>
                    {c.desc}
                    <br />
                    {homeCapabilitySub[c.key] ?? ""}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </AppShell>
  );
}

export default function HomePage() {
  return (
    <Suspense fallback={<div className="p-6 text-[13px]">加载中…</div>}>
      <HomeInner />
    </Suspense>
  );
}
