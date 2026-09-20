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

function RecentCard({ item }: { item: (typeof homeFixture.recent)[number] }) {
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
    <Card className="p-3.5" testId={`recent-${item.code}`}>
      <div className="flex items-center gap-2">
        <span className="smp-num text-[14px]" style={{ color: "var(--color-gold)" }}>
          {item.code}
        </span>
        <span className="text-[14px]" style={{ color: "var(--color-ink)" }}>
          {item.name}
        </span>
        <span className="ml-auto">
          <Chip tone={tone as "up" | "down" | "flat" | "conflict"}>{item.status}</Chip>
        </span>
      </div>

      <div className="mt-1 flex items-center gap-2 text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
        <span className="smp-num">{item.analyzedAt}</span>
      </div>

      <div className="mt-2 flex items-end gap-2">
        <span className="smp-num text-[22px] font-semibold leading-none" style={{ color: priceColor }}>
          {item.price}
        </span>
        <span className="smp-num text-[12.5px]" style={{ color: priceColor }}>
          {item.changePct}
        </span>
      </div>

      <div className="mt-1.5">
        <MiniTrend values={spark} tone={item.trend} height={54} />
      </div>

      <div className="mt-1.5 flex items-center gap-4 border-t pt-2" style={{ borderColor: "var(--color-border)" }}>
        {item.engines.map((e) => (
          <span key={e.key} className="flex items-center gap-1 text-[11.5px]">
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

  const recent = fixture ? homeFixture.recent : [];

  return (
    <AppShell activeNav="home" dataStatus={dataStatus} statusText={statusText}>
      {/* Hero */}
      <section className="relative mb-3 overflow-hidden rounded-[12px] border px-7 py-6"
        style={{
          borderColor: "var(--color-border)",
          background:
            "radial-gradient(900px 320px at 82% 20%, rgba(212,184,122,0.10), transparent 60%), linear-gradient(180deg, rgba(16,31,43,0.72), rgba(10,21,31,0.72))",
        }}
      >
        {/* 右侧装饰性太极星图（纯 CSS/SVG，不是位图） */}
        <div
          className="pointer-events-none absolute right-10 top-1/2 hidden -translate-y-1/2 opacity-[0.5] xl:block"
          aria-hidden="true"
        >
          <div
            className="flex h-[240px] w-[240px] items-center justify-center rounded-full"
            style={{
              border: "1px solid rgba(212,184,122,0.22)",
              background:
                "radial-gradient(circle, rgba(212,184,122,0.10), transparent 68%)",
            }}
          >
            <div
              className="flex h-[168px] w-[168px] items-center justify-center rounded-full"
              style={{ border: "1px solid rgba(212,184,122,0.16)" }}
            >
              <div
                className="flex h-[104px] w-[104px] items-center justify-center rounded-full"
                style={{ color: "rgba(212,184,122,0.5)" }}
              >
                <IconTaiji size={104} />
              </div>
            </div>
          </div>
        </div>

        <div
          className="pointer-events-none absolute right-[330px] top-8 hidden text-right leading-[26px] tracking-[0.36em] xl:block"
          style={{ color: "rgba(212,184,122,0.42)", fontSize: 13 }}
          aria-hidden="true"
        >
          观天时
          <br />
          察地利
          <br />
          究人道
          <br />
          明真理
        </div>

        <div className="relative max-w-[1000px]">
          <h1
            className="text-[50px] font-bold leading-[1.15] tracking-[0.05em]"
            style={{ color: "var(--color-gold-strong)", textShadow: "0 3px 26px rgba(212,184,122,0.22)" }}
            data-testid="home-title"
          >
            股票玄学多模型研究平台
          </h1>
          <p className="mt-2.5 text-[13.5px] tracking-[0.16em]" style={{ color: "var(--color-ink-sub)" }}>
            融贯东方智慧 · 结合现代量化 · 探索市场的多维可能
          </p>

          <div
            className="mt-5 rounded-[10px] border px-5 py-4"
            style={{ borderColor: "var(--color-border-strong)", background: "rgba(6,14,21,0.5)" }}
          >
            <div className="mb-2.5 flex items-center gap-1.5 text-[12.5px]" style={{ color: "var(--color-ink-sub)" }}>
              <IconSearch size={14} style={{ color: "var(--color-ink-muted)" }} />
              输入股票代码，查看八字、紫微、黄历与历史回测综合研究
            </div>
            <div className="flex items-center gap-2.5">
              <div className="min-w-0 flex-1">
                <StockSearch variant="hero" defaultValue="600519" />
              </div>
              <button type="button" className="smp-btn h-[52px] px-5" disabled title="Phase 2">
                <IconGrid size={15} />
                高级设置
              </button>
            </div>
            <div className="mt-2.5 flex items-center gap-4 text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
              <span>示例：</span>
              <span className="smp-num">600519 贵州茅台</span>
              <span className="smp-num">000001 平安银行</span>
              <span className="smp-num">300750 宁德时代</span>
            </div>
          </div>
        </div>

        <div
          className="relative mt-4 text-right text-[11.5px] tracking-[0.14em]"
          style={{ color: "var(--color-ink-faint)" }}
        >
          东方智慧 · 现代方法 · 更深入的认知
        </div>
      </section>

      {/* 最近分析 + 系统状态 */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1fr_400px]">
        <Card testId="recent-analysis">
          <CardHeader
            icon={<IconDatabase size={14} />}
            title="最近分析"
            action={fixture ? { label: "查看更多" } : undefined}
          />
          {recent.length > 0 ? (
            <div className="grid grid-cols-1 gap-3 p-3.5 md:grid-cols-3">
              {recent.map((r) => (
                <RecentCard key={r.code} item={r} />
              ))}
            </div>
          ) : (
            <div className="flex h-[180px] flex-col items-center justify-center p-6 text-center" data-testid="recent-empty">
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
                className="text-[11.5px]"
                style={{ color: systemSummaryColor }}
                data-testid="system-summary"
              >
                {systemSummary}
              </span>
            }
            action={{ label: "" }}
          />
          <div className="px-3.5 py-2">
            {systemStatus.map((s) => {
              const Icon = SYSTEM_ICONS[s.key] ?? IconTaiji;
              const ok = s.state === "ok";
              return (
                <div
                  key={s.key}
                  className="flex items-center gap-2.5 border-b py-[9px] last:border-b-0"
                  style={{ borderColor: "rgba(30,52,68,0.55)" }}
                  data-testid={`system-${s.key}`}
                >
                  <span style={{ color: ok ? "var(--color-gold-dim)" : "var(--color-ink-faint)" }}>
                    <Icon size={15} />
                  </span>
                  <span className="text-[12.5px]" style={{ color: ok ? "var(--color-ink-sub)" : "var(--color-ink-faint)" }}>
                    {s.label}
                  </span>
                  <span
                    className="ml-auto flex h-[17px] w-[17px] items-center justify-center rounded-full"
                    style={{
                      color: ok ? "var(--color-down)" : "var(--color-ink-faint)",
                      border: `1px solid ${ok ? "rgba(79,211,155,0.5)" : "var(--color-border-strong)"}`,
                      background: ok ? "var(--color-down-bg)" : "transparent",
                    }}
                  >
                    {ok ? "✓" : "—"}
                  </span>
                  <span className="w-[104px] text-[12px]" style={{ color: ok ? "var(--color-ink-sub)" : "var(--color-ink-faint)" }}>
                    {s.note}
                  </span>
                  <span className="smp-num w-[46px] text-right text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                    {s.latency}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* 平台能力 */}
      <Card className="mt-3" testId="capabilities">
        <CardHeader
          icon={<IconGrid size={14} />}
          title="平台能力"
          action={{ label: "探索更多研究可能" }}
        />
        <div className="grid grid-cols-1 gap-3 p-3.5 md:grid-cols-2 xl:grid-cols-4">
          {homeFixture.capabilities.map((c) => {
            const Icon = CAP_ICONS[c.key] ?? IconLayers;
            const t = CAP_TONE[c.tone];
            return (
              <div
                key={c.key}
                className="flex items-center gap-3 rounded-[8px] border px-3.5 py-3.5"
                style={{ borderColor: "var(--color-border)", background: t.bg }}
              >
                <span
                  className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full"
                  style={{ color: t.color, border: `1px solid ${t.color}55`, background: `${t.color}14` }}
                >
                  <Icon size={21} />
                </span>
                <div className="min-w-0">
                  <div className="text-[14px]" style={{ color: "var(--color-ink)" }}>
                    {c.title}
                  </div>
                  <div className="mt-0.5 text-[11.5px] leading-[17px]" style={{ color: "var(--color-ink-muted)" }}>
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

      <div className="mt-3 flex items-center justify-center gap-2 text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
        <IconArrowRight size={13} />
        本平台为研究实验系统，不构成任何投资建议；术数因子与股票收益的关系必须由历史数据检验。
      </div>
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
