"use client";

import { AppShell } from "@/components/shell/AppShell";
import { PageHero } from "@/components/shell/TopBar";
import { ResearchNav } from "@/components/research/ResearchNav";
import { Card, CardHeader } from "@/components/cards/Card";

export default function RelationStudyPage() {
  return (
    <AppShell activeNav="research" statusText="模块预留">
      <PageHero title="关系历史研究" subtitle="按关系类型登记假设，比较历史行为与样本外结果" seal="验" />
      <ResearchNav />
      <Card><CardHeader title="关系级 Event Study" dense /><div className="p-4"><PageStateUnavailable /></div></Card>
    </AppShell>
  );
}

function PageStateUnavailable() {
  return <div className="smp-disclaimer">本模块已预留路由，但关系级标签、TRAIN / VALIDATION / OOS 与多重比较校正尚未全部接入。当前不显示胜率、IC、收益或“适合交易”等结论。</div>;
}
