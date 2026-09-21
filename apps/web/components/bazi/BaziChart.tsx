"use client";

/**
 * BaziChart —— 四柱盘（年/月/日/时 × 天干/地支/藏干/十神/纳音）。
 *
 * 原始盘面是一等数据，必须完整可见（architecture §58、§79）。
 * 这是**纯 DOM 表格**，不是图片。
 */

import type { BaziPillarView, WuxingBar, FateSummaryRow, TimelineItem } from "@/lib/types";
import { variantModeLabel } from "@/lib/dataSource";
import { Chip } from "../cards/Card";
import { IconDiamond, IconLayers, IconTaiji } from "../shell/Icons";

const WUXING_COLOR_MAP: Record<string, string> = {
  // 木 (Wood) -> 绿
  甲: "var(--color-wood)",
  乙: "var(--color-wood)",
  寅: "var(--color-wood)",
  卯: "var(--color-wood)",
  // 火 (Fire) -> 红
  丙: "var(--color-fire)",
  丁: "var(--color-fire)",
  巳: "var(--color-fire)",
  午: "var(--color-fire)",
  // 土 (Earth) -> 黄/褐
  戊: "var(--color-earth)",
  己: "var(--color-earth)",
  辰: "var(--color-earth)",
  戌: "var(--color-earth)",
  丑: "var(--color-earth)",
  未: "var(--color-earth)",
  // 金 (Metal) -> 白灰/银
  庚: "var(--color-metal)",
  辛: "var(--color-metal)",
  申: "var(--color-metal)",
  酉: "var(--color-metal)",
  // 水 (Water) -> 蓝
  壬: "var(--color-water)",
  癸: "var(--color-water)",
  亥: "var(--color-water)",
  子: "var(--color-water)",
};

export function getWuxingColor(char: string): string {
  return WUXING_COLOR_MAP[char] ?? "var(--color-ink)";
}

export function BaziChart({ pillars }: { pillars: BaziPillarView[] }) {
  const rows: { label: string; render: (p: BaziPillarView) => React.ReactNode }[] = [
    {
      label: "天干",
      render: (p) => (
        <span
          className="smp-serif-title text-[26px] font-semibold leading-none"
          style={{ color: getWuxingColor(p.stem), fontFamily: "var(--font-serif-cn)" }}
          data-testid={`stem-${p.position}`}
          data-char={p.stem}
        >
          {p.stem}
        </span>
      ),
    },
    {
      label: "地支",
      render: (p) => (
        <span
          className="smp-serif-title text-[26px] font-semibold leading-none"
          style={{ color: getWuxingColor(p.branch), fontFamily: "var(--font-serif-cn)" }}
          data-testid={`branch-${p.position}`}
          data-char={p.branch}
        >
          {p.branch}
        </span>
      ),
    },
    {
      label: "藏干",
      render: (p) => (
        <span className="smp-num text-[11.5px]" style={{ color: "var(--color-ink-sub)" }}>
          {p.hiddenStems}
        </span>
      ),
    },
    {
      label: "十神",
      render: (p) => (
        <span className="text-[11.5px] font-medium" style={{ color: "var(--color-gold)" }}>
          {p.hiddenTenGods}
        </span>
      ),
    },
    {
      label: "纳音",
      render: (p) => (
        <span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
          {p.nayin}
        </span>
      ),
    },
    {
      label: "长生",
      render: (p) => (
        <span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
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
              className="w-[56px] border-b px-2 py-[1px] text-left text-[11px] font-normal"
              style={{ borderColor: "var(--color-border)", color: "var(--color-ink-faint)" }}
            />
            {pillars.map((p) => (
              <th
                key={p.position}
                className="border-b border-l px-2 py-[1px] text-center text-[11.5px] font-medium"
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
                className="border-b px-2 py-[1px] text-[11px]"
                style={{ borderColor: "var(--color-border)", color: "var(--color-ink-faint)" }}
              >
                {row.label}
              </td>
              {pillars.map((p) => (
                <td
                  key={p.position}
                  className="border-b border-l px-2 py-[1px] text-center"
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
    <div className="space-y-2 px-3 py-2.5" data-testid="wuxing-distribution">
      {bars.map((b) => (
        <div key={b.element} className="flex items-center gap-2.5">
          <span className="w-[16px] text-[12.5px]" style={{ color: "var(--color-ink)" }}>
            {b.element}
          </span>
          <div
            className="relative h-[11px] flex-1 overflow-hidden rounded-[2px]"
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
            className="smp-num w-[34px] text-right text-[11.5px]"
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
    <div className="px-3 py-2" data-testid="fate-summary">
      {rows.map((r) => (
        <div
          key={r.label}
          className="flex items-center gap-2.5 border-b py-[6px] last:border-b-0"
          style={{ borderColor: "rgba(30,52,68,0.6)" }}
        >
          <span className="w-[40px] shrink-0 text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
            {r.label}
          </span>
          <span
            className="shrink-0 rounded-[3px] border px-1.5 py-[1px] text-[11.5px]"
            style={{ color: tone(r.tone), borderColor: `${tone(r.tone)}55`, background: "rgba(0,0,0,0.2)" }}
          >
            {r.value}
          </span>
          <span className="min-w-0 truncate text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
            {r.note}
          </span>
        </div>
      ))}
    </div>
  );
}

export function TimeStructure({ items }: { items: TimelineItem[] }) {
  const iconFor: Record<string, React.ReactNode> = {
    dayun: <IconLayers size={13} />,
    year: <IconTaiji size={13} />,
    month: <IconDiamond size={13} />,
    day: <IconDiamond size={13} />,
  };
  return (
    <div className="px-3 pb-2 pt-0.5">
      {/* 时间节点 + 连接线：大运 → 流年 → 流月 → 流日 是同一条时间轴的推进，
          用贯穿线表达"顺序"，比四张并列卡片更贴近参考图（复核任务书 §R1）；
          变体说明与运限假设标签在卡头，不占数据区高度。 */}
      <div className="relative px-1 pt-0.5">
        <div
          className="pointer-events-none absolute left-[12.5%] right-[12.5%] top-[14px] h-[1px]"
          style={{
            background:
              "linear-gradient(90deg, rgba(212,184,122,0.55), rgba(212,184,122,0.22) 55%, rgba(212,184,122,0.55))",
          }}
          aria-hidden="true"
        />
        <div className="relative grid grid-cols-4 gap-3">
          {items.map((it) => (
            <div
              key={it.key}
              className="flex flex-col items-center text-center"
              data-testid={`timeline-${it.key}`}
            >
              <span
                className="flex h-[28px] w-[28px] items-center justify-center rounded-full"
                style={{
                  color: it.tone === "gold" ? "var(--color-gold)" : "var(--color-ink-sub)",
                  border: `1px solid ${
                    it.tone === "gold" ? "var(--color-gold-dim)" : "var(--color-border-strong)"
                  }`,
                  background:
                    it.tone === "gold"
                      ? "radial-gradient(circle, rgba(212,184,122,0.20), rgba(9,19,29,0.95) 75%)"
                      : "var(--color-surface-1)",
                }}
              >
                {iconFor[it.key]}
              </span>
              <div className="mt-1 text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>
                {it.title}
              </div>
              <div className="text-[13px] font-medium" style={{ color: "var(--color-ink)" }}>
                {it.primary}
              </div>
              <div className="text-[11px]" style={{ color: "var(--color-gold)" }}>
                {it.secondary}
              </div>
              <div
                className="line-clamp-1 text-[10px] leading-[14px]"
                style={{ color: "var(--color-ink-muted)" }}
                title={it.note}
              >
                {it.note}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
