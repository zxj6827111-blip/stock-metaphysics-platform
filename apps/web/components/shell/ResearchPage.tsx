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

import type { ReactNode } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageError, PageLoading } from "@/components/shell/PageState";
import { PageHero } from "@/components/shell/TopBar";
import { StockContextBar } from "@/components/stock/StockContextBar";
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
