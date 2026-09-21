"use client";

/**
 * Phase 2 研究页面的统一外壳。
 *
 * 7 个新页面共用同一套：
 *   AppShell（导航/顶栏） + PageHero（标题） + StockContextBar（股票上下文）
 *   + Loading / Empty / Error 三态
 *
 * 为什么要抽出来：如果每个页面各写一套，很快就会出现"某个页面忘了显示
 * 数据质量徽标""某个页面没有错误态"这类不一致 —— 而研究终端里，
 * **漏掉一个状态提示就等于漏掉一条风险信息**。
 */

import Link from "next/link";
import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageError, PageLoading } from "@/components/shell/PageState";
import { PageHero } from "@/components/shell/TopBar";
import { StockContextBar } from "@/components/stock/StockContextBar";
import { Card } from "@/components/cards/Card";
import { FIXTURE_QUERY_VALUE, isFixtureActive } from "@/lib/fixture";
import { buildContextFromMulti } from "@/lib/dataSource";
import type { ApiMultiAnalysis } from "@/lib/api";

export interface ResearchPageProps {
  activeNav: string;
  title: string;
  subtitle: string;
  seal?: string;
  code: string;
  analysis: ApiMultiAnalysis | null;
  loading: boolean;
  error: string | null;
  onReload?: () => void;
  /** loading 时显示的说明（不同页面的计算量差异很大） */
  loadingLabel?: string;
  children: ReactNode;
}

export function ResearchPage({
  activeNav,
  title,
  subtitle,
  seal,
  code,
  analysis,
  loading,
  error,
  onReload,
  loadingLabel,
  children,
}: ResearchPageProps) {
  const isUnsupportedFixture = isFixtureActive() && code !== "600519";
  if (isUnsupportedFixture) {
    return (
      <AppShell activeNav={activeNav} dataStatus="bad" statusText="演示模式受限">
        <PageHero title={title} subtitle={subtitle} seal={seal} />
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
                  href={`/stock/${code}/${activeNav}`}
                  className="smp-btn smp-btn--primary"
                  data-testid="enter-real-mode-btn"
                >
                  移除 fixture 参数并进入真实分析模式
                </Link>
                <Link
                  href={`/stock/600519/${activeNav}?fixture=${FIXTURE_QUERY_VALUE}`}
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

  const ctx = analysis ? buildContextFromMulti(analysis) : null;
  return (
    <AppShell
      activeNav={activeNav}
      dataStatus={error ? "bad" : "ok"}
      statusText={error ? "后端未连接" : "数据正常"}
    >
      <PageHero title={title} subtitle={subtitle} seal={seal} />
      {ctx ? (
        <StockContextBar
          context={ctx}
          activeTab={activeNav}
          onRecalculate={onReload}
          recalculating={loading}
        />
      ) : null}
      {loading ? <PageLoading label={loadingLabel ?? "加载中…"} /> : null}
      {error ? <PageError message={error} onRetry={onReload} /> : null}
      {!loading && !error ? <div className="space-y-3">{children}</div> : null}
    </AppShell>
  );
}

/** 页面内的次级小标题（与 Card 搭配使用）。 */
export function SectionNote({ children }: { children: ReactNode }) {
  return (
    <p
      className="rounded border px-3 py-2 text-[12px] leading-relaxed"
      style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
    >
      {children}
    </p>
  );
}
