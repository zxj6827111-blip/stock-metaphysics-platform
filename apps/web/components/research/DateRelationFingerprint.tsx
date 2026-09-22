"use client";

import { Card, CardHeader, Chip } from "@/components/cards/Card";
import { IconCalendar } from "@/components/shell/Icons";
import type { ApiDateRelationFingerprint } from "@/lib/api";

const GROUPS: [string, string][] = [
  ["天干关系", "stem_targets"],
  ["地支关系", "branch_targets"],
  ["三合", "三合"],
  ["半合", "半合"],
  ["三会", "三会"],
];

export function DateRelationFingerprint({ fingerprint }: { fingerprint: ApiDateRelationFingerprint }) {
  return (
    <Card testId="date-relation-fingerprint">
      <CardHeader icon={<IconCalendar size={15} />} title="当天关系指纹" right={<Chip tone="gold">{fingerprint.relation_rule_version}</Chip>} dense />
      <div className="grid gap-2 p-3 md:grid-cols-4">
        <div className="rounded border p-2" style={{ borderColor: "var(--color-border)" }}>
          <div className="smp-metric-label">年 / 月 / 日</div>
          <div className="mt-1 font-serif text-[17px]" style={{ color: "var(--color-gold-strong)" }}>
            {fingerprint.year} · {fingerprint.month} · {fingerprint.day}
          </div>
        </div>
        {GROUPS.map(([label, key]) => {
          const values = key in fingerprint.candidates
            ? fingerprint.candidates[key] ?? []
            : Object.entries((fingerprint as unknown as Record<string, Record<string, string[]>>)[key] ?? {}).flatMap(([source, targets]) => targets.map((target) => `${source} ${target}`));
          return (
            <div key={label} className="rounded border p-2" style={{ borderColor: "var(--color-border)" }}>
              <div className="smp-metric-label">{label}</div>
              <div className="mt-1 flex min-h-[24px] flex-wrap gap-1">
                {values.length ? values.slice(0, 5).map((value) => <Chip key={value} tone="flat">{value}</Chip>) : <span style={{ color: "var(--color-ink-faint)" }}>—</span>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="px-3 pb-3 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
        已支持 {fingerprint.supported_relations.length} 类关系 · 不可用 {fingerprint.unavailable_relations.length || "无"} · 日期模板只计算一次
      </div>
    </Card>
  );
}
