"use client";

/**
 * Phase 2 占位页。
 *
 * 导航结构里保留了完整信息架构（uiux_spec §3），但 Phase 1 只交付
 * 首页 / 综合研判 / 八字详情三页。其余页面显示**明确的未实现说明**，
 * 而不是伪造内容或直接 404。
 */

import { AppShell } from "./AppShell";
import { PageHero } from "./TopBar";
import { Card, CardHeader, Chip } from "../cards/Card";
import { IconFlame } from "./Icons";

export function Phase2Placeholder({
  title,
  subtitle,
  activeNav,
  planned,
  phase = "Phase 2",
  reason,
  docRef,
}: {
  title: string;
  subtitle: string;
  activeNav?: string;
  planned: string[];
  phase?: string;
  reason: string;
  docRef?: string;
}) {
  return (
    <AppShell activeNav={activeNav} statusText="页面待实现">
      <PageHero title={title} subtitle={subtitle} seal="待" />
      <Card>
        <CardHeader
          icon={<IconFlame size={14} />}
          title={`${phase} 实现`}
          right={<Chip tone="warn">当前未启用</Chip>}
        />
        <div className="p-4">
          <p className="text-[13px] leading-[22px]" style={{ color: "var(--color-ink-sub)" }}>
            {reason}
          </p>
          <div className="mt-4">
            <div className="smp-metric-label mb-2">该页面计划包含</div>
            <ul className="space-y-1.5">
              {planned.map((p) => (
                <li key={p} className="flex items-start gap-2 text-[12.5px]" style={{ color: "var(--color-ink-sub)" }}>
                  <span style={{ color: "var(--color-gold-dim)" }}>·</span>
                  {p}
                </li>
              ))}
            </ul>
          </div>
          {docRef ? (
            <p className="mt-4 text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
              设计依据：{docRef}
            </p>
          ) : null}
          <div className="smp-disclaimer mt-4">
            本系统是研究实验平台，不构成任何投资建议。传统术数与股票未来收益之间
            不存在经现代金融科学确认的稳定因果关系。
          </div>
        </div>
      </Card>
    </AppShell>
  );
}
