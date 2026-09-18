"use client";

/**
 * BaziChart —— 四柱盘（年/月/日/时 × 天干/地支/藏干/十神/纳音）。
 *
 * 原始盘面是一等数据，必须完整可见（architecture §58、§79）。
 * 这是**纯 DOM 表格**，不是图片。
 */

import type { BaziPillarView, WuxingBar, FateSummaryRow, TimelineItem } from "@/lib/types";
import { Chip } from "../cards/Card";
import { IconDiamond, IconLayers, IconTaiji } from "../shell/Icons";

export function BaziChart({ pillars }: { pillars: BaziPillarView[] }) {
  const rows: { label: string; render: (p: BaziPillarView) => React.ReactNode }[] = [
    {
      label: "天干",
      render: (p) => (
        <span
          className="text-[30px] font-semibold leading-none"
          style={{ color: "var(--color-ink)", fontFamily: "var(--font-serif-cn)" }}
        >
          {p.stem}
        </span>
      ),
    },
    {
      label: "地支",
      render: (p) => (
        <span
          className="text-[30px] font-semibold leading-none"
          style={{ color: "var(--color-ink)", fontFamily: "var(--font-serif-cn)" }}
        >
          {p.branch}
        </span>
      ),
    },
    {
      label: "藏干",
      render: (p) => (
        <span className="smp-num text-[13px]" style={{ color: "var(--color-ink-sub)" }}>
          {p.hiddenStems}
        </span>
      ),
    },
    {
      label: "十神",
      render: (p) => (
        <span className="text-[12.5px]" style={{ color: "var(--color-gold)" }}>
          {p.hiddenTenGods}
        </span>
      ),
    },
    {
      label: "纳音",
      render: (p) => (
        <span className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          {p.nayin}
        </span>
      ),
    },
    {
      label: "长生",
      render: (p) => (
        <span className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          {p.diShi}
        </span>
      ),
    },
  ];

  return (
    <div
      className="overflow-hidden rounded-[7px] border"
      style={{ borderColor: "var(--color-border)" }}
      data-testid="bazi-chart"
    >
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th
              className="w-[64px] border-b px-2 py-1.5 text-left text-[11px] font-normal"
              style={{ borderColor: "var(--color-border)", color: "var(--color-ink-faint)" }}
            />
            {pillars.map((p) => (
              <th
                key={p.position}
                className="border-b border-l px-2 py-1.5 text-center text-[12px] font-medium"
                style={{ borderColor: "var(--color-border)", color: "var(--color-ink-sub)" }}
                data-testid={`pillar-${p.position}`}
              >
                {p.positionCn}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr
              key={row.label}
              style={{
                background: ri === 0 || ri === 1 ? "rgba(0,0,0,0.14)" : "transparent",
              }}
            >
              <td
                className="border-b px-2 py-2 text-[11px]"
                style={{ borderColor: "var(--color-border)", color: "var(--color-ink-faint)" }}
              >
                {row.label}
              </td>
              {pillars.map((p) => (
                <td
                  key={p.position}
                  className="border-b border-l px-2 py-2 text-center"
                  style={{ borderColor: "var(--color-border)" }}
                >
                  {row.render(p)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function WuxingDistribution({ bars }: { bars: WuxingBar[] }) {
  return (
    <div className="space-y-3.5 px-4 py-4" data-testid="wuxing-distribution">
      {bars.map((b) => (
        <div key={b.element} className="flex items-center gap-3">
          <span className="w-[16px] text-[13px]" style={{ color: "var(--color-ink)" }}>
            {b.element}
          </span>
          <div
            className="relative h-[13px] flex-1 overflow-hidden rounded-[2px]"
            style={{ background: "rgba(255,255,255,0.045)" }}
            role="img"
            aria-label={`${b.element} ${b.percent}%`}
          >
            <div
              className="h-full rounded-[2px] transition-[width] duration-500"
              style={{
                width: `${Math.max(b.percent, 2) * 1.9}%`,
                background: b.color,
                opacity: 0.9,
              }}
            />
          </div>
          <span
            className="smp-num w-[38px] text-right text-[12.5px]"
            style={{ color: "var(--color-ink-sub)" }}
          >
            {b.percent}%
          </span>
        </div>
      ))}
    </div>
  );
}

export function FateSummary({ rows }: { rows: FateSummaryRow[] }) {
  const tone = (t?: string) =>
    t === "up"
      ? "var(--color-up)"
      : t === "down"
        ? "var(--color-down)"
        : t === "gold"
          ? "var(--color-gold)"
          : "var(--color-ink)";
  return (
    <div className="px-4 py-3" data-testid="fate-summary">
      {rows.map((r) => (
        <div
          key={r.label}
          className="flex items-center gap-3 border-b py-[9px] last:border-b-0"
          style={{ borderColor: "rgba(30,52,68,0.6)" }}
        >
          <span className="w-[44px] shrink-0 text-[12.5px]" style={{ color: "var(--color-ink-sub)" }}>
            {r.label}
          </span>
          <span
            className="shrink-0 rounded-[4px] border px-2 py-[2px] text-[12.5px]"
            style={{ color: tone(r.tone), borderColor: `${tone(r.tone)}55`, background: "rgba(0,0,0,0.2)" }}
          >
            {r.value}
          </span>
          <span className="min-w-0 truncate text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            {r.note}
          </span>
        </div>
      ))}
    </div>
  );
}

export function TimeStructure({
  items,
  variantMode,
  variantNote,
}: {
  items: TimelineItem[];
  variantMode: string;
  variantNote: string;
}) {
  const iconFor: Record<string, React.ReactNode> = {
    dayun: <IconLayers size={16} />,
    year: <IconTaiji size={16} />,
    month: <IconDiamond size={16} />,
    day: <IconDiamond size={16} />,
  };
  return (
    <div className="px-4 py-3" data-testid="time-structure">
      <div className="mb-2.5 flex flex-wrap items-center gap-2">
        <Chip tone="warn">{variantNote || "股票无天然性别，运限推演基于假设规则"}</Chip>
        <div className="ml-auto flex items-center gap-1.5">
          <span className="smp-metric-label">运限假设</span>
          <span
            className="rounded-[4px] border px-2 py-[1px] text-[11px]"
            style={{ borderColor: "var(--color-border-strong)", color: "var(--color-ink-sub)" }}
            data-testid="variant-mode"
          >
            {variantMode}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2.5">
        {items.map((it) => (
          <div
            key={it.key}
            className="rounded-[7px] border px-3 py-2.5"
            style={{
              borderColor: "var(--color-border)",
              background:
                it.tone === "gold"
                  ? "linear-gradient(180deg, rgba(212,184,122,0.10), rgba(212,184,122,0.02))"
                  : "rgba(0,0,0,0.16)",
            }}
            data-testid={`timeline-${it.key}`}
          >
            <div className="flex items-center gap-2">
              <span style={{ color: "var(--color-gold-dim)" }}>{iconFor[it.key]}</span>
              <span className="text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
                {it.title}
              </span>
            </div>
            <div className="mt-2 text-[14px]" style={{ color: "var(--color-ink)" }}>
              {it.primary}
            </div>
            <div className="mt-0.5 text-[12.5px]" style={{ color: "var(--color-gold)" }}>
              {it.secondary}
            </div>
            <div className="mt-1 text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
              {it.note}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
