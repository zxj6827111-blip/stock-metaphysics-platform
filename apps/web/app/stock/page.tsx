"use client";

import { Suspense } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHero } from "@/components/shell/TopBar";
import { PageLoading } from "@/components/shell/PageState";
import { StockSelectionGate } from "@/components/stock/StockSelectionGate";

function StockEntryPage() {
  return (
    <AppShell activeNav="overview" statusText="等待选择标的">
      <PageHero title="股票研究入口" subtitle="先选择研究标的，再进入对应的分析模块" seal="选" couplet={["先定标的", "再看结构"]} />
      <StockSelectionGate />
    </AppShell>
  );
}

export default function StockPage() {
  return <Suspense fallback={<PageLoading />}><StockEntryPage /></Suspense>;
}
