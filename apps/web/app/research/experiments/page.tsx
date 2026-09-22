"use client";

import { AppShell } from "@/components/shell/AppShell";
import { PageHero } from "@/components/shell/TopBar";
import { ResearchNav } from "@/components/research/ResearchNav";
import { Card, CardHeader } from "@/components/cards/Card";

export default function ExperimentsPage() {
  return (
    <AppShell activeNav="research" statusText="只读实验模块">
      <PageHero title="历史实验" subtitle="查看既有 Event Study、负对照与样本外实验" seal="验" />
      <ResearchNav />
      <Card><CardHeader title="历史实验目录" dense /><div className="p-4"><div className="smp-disclaimer">既有实验仍通过个股历史验证页与 `/api/v1/research/experiments` 只读接口查看。本路由先保留研究实验室的信息架构，不复制或伪造实验结果。</div></div></Card>
    </AppShell>
  );
}
