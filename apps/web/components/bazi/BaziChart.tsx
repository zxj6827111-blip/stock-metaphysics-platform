"use client";

/**
 * BaziChart —— 四柱盘（年/月/日/时 × 天干/地支/藏干/十神/纳音）。
 *
 * 原始盘面是一等数据，必须完整可见（architecture §58、§79）。
 * 这是**纯 DOM 表格**，不是图片。
 */

import type { BaziPillarView, WuxingBar, FateSummaryRow, TimelineItem } from "@/lib/types";
import { variantModeLabel } from "@/lib/dataSource";

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
          className="smp-serif-title text-[32px] font-semibold leading-none"
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
          className="smp-serif-title text-[32px] font-semibold leading-none"
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
            className="shrink-0 rounded-[4px] border px-2 py-[2px] text-[12px] font-medium"
            style={{
              color: tone(r.tone),
              borderColor: `${tone(r.tone)}66`,
              background: `color-mix(in srgb, ${tone(r.tone)} 15%, transparent)`,
            }}
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

/** 时间结构四段的固定配色（大运/流年/流月/流日）。
 *  颜色只区分**尺度**，不表达好坏 —— 方向语义在 factor.direction 与正负因素区。 */
const TIMELINE_TONE: Record<string, { fg: string; ring: string; bg: string; dot: string }> = {
  dayun: {
    fg: "var(--color-gold)",
    ring: "rgba(212,184,122,0.55)",
    bg: "rgba(120,92,40,0.16)",
    dot: "#d4b87a",
  },
  year: { fg: "#5ad3c0", ring: "rgba(90,211,192,0.5)", bg: "rgba(40,120,112,0.16)", dot: "#5ad3c0" },
  month: { fg: "#7fb2f0", ring: "rgba(127,178,240,0.5)", bg: "rgba(48,88,150,0.16)", dot: "#7fb2f0" },
  day: { fg: "#e8585a", ring: "rgba(232,88,90,0.5)", bg: "rgba(150,48,52,0.16)", dot: "#e8585a" },
};

export function TimeStructure({ items }: { items: TimelineItem[] }) {
  return (
    <div className="px-3 pb-1 pt-0" data-testid="time-structure-body">
      {/* 四段并排的"尺度卡"：左圆环标尺度名，右列给区间/干支/说明。
          卡下再挂一条贯穿的时间轨与四个色点 —— 轨子表达"这是同一条时间轴"，
          圆环表达"这是四个不同尺度"；两者缺一，时间结构就会被读成四张并列卡片。
          颜色按尺度固定（参考图 03：大运=金、流年=青、流月=蓝、流日=红），
          颜色本身不承载"好坏"语义，方向仍由 factor.direction 表达。 */}
      <div className="grid grid-cols-2 gap-2.5 xl:grid-cols-4">
        {items.map((it) => {
          const t = TIMELINE_TONE[it.key] ?? TIMELINE_TONE.dayun;
          return (
            <div
              key={it.key}
              className="flex items-center gap-3 rounded-[7px] border px-3 py-1.5"
              style={{ borderColor: "var(--color-border)", background: t.bg }}
              data-testid={`timeline-${it.key}`}
            >
              <span
                className="flex h-[50px] w-[50px] shrink-0 select-none items-center justify-center rounded-full text-[14.5px] font-medium"
                style={{
                  color: t.fg,
                  border: `1.5px solid ${t.ring}`,
                  background: `radial-gradient(circle at 36% 30%, ${t.ring}44, rgba(9,19,29,0.92) 78%)`,
                  boxShadow: `inset 0 0 16px ${t.ring}33`,
                  fontFamily: "var(--font-serif-cn)",
                }}
                aria-hidden="true"
              >
                {it.key === "dayun"
                  ? "大运"
                  : it.key === "year"
                    ? "流年"
                    : it.key === "month"
                      ? "流月"
                      : "流日"}
              </span>
              <div className="min-w-0">
                <div className="truncate text-[13.5px] font-semibold" style={{ color: t.fg }}>
                  {it.title}
                </div>
                <div className="smp-num text-[12.5px]" style={{ color: "var(--color-ink)" }}>
                  {it.primary}
                </div>
                <div className="text-[12.5px] font-medium" style={{ color: "var(--color-gold)" }}>
                  {it.secondary}
                </div>
                <div
                  className="line-clamp-1 text-[11px] leading-[15px]"
                  style={{ color: "var(--color-ink-muted)" }}
                  title={it.note}
                >
                  {it.note}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      {/* 贯穿轨 + 四个色点：色点与上方四张卡的色相一一对应。 */}
      <div className="relative mt-1.5 h-[10px]" aria-hidden="true">
        <div
          className="absolute left-0 right-0 top-1/2 h-[1px]"
          style={{
            background:
              "linear-gradient(90deg, rgba(212,184,122,0.5), rgba(90,211,192,0.4) 38%, rgba(127,178,240,0.4) 68%, rgba(232,88,90,0.5))",
          }}
        />
        {items.map((it, i) => {
          const t = TIMELINE_TONE[it.key] ?? TIMELINE_TONE.dayun;
          return (
            <span
              key={it.key}
              className="absolute top-1/2 h-[9px] w-[9px] -translate-y-1/2 rounded-full"
              style={{
                left: `${((i + 0.5) / items.length) * 100}%`,
                background: t.dot,
                boxShadow: `0 0 8px ${t.dot}aa`,
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
