"use client";

/**
 * 彩色圆形徽章（参考图的统一身份语言）。
 *
 * 为什么单独抽成基元：参考图里每一个"身份单元"——引擎、能力、模型、结论、
 * 窗口——都由一个**彩色圆形徽章**领起（八字金、紫微紫、黄历青、量化蓝、风险红）。
 * 之前这些位置用的是 15px 金色线性小图标，结果十页的主色体系塌成同一种金色，
 * 一眼看上去"信息都在、但没有层级"。徽章承担两件事：
 *   1. 色彩编码（与引擎/语义一一对应，配合文字标签，不单独承载信息）；
 *   2. 视觉重心（把一排同构卡片的视觉起点钉在左侧同一位置）。
 */

import type { ReactNode } from "react";

export type MedallionTone = "gold" | "up" | "down" | "info" | "conflict" | "flat";

/**
 * 每种色调对应「图标色 / 盘面底色 / 描边 / 内发光」四档。
 * 底色刻意保持很浅（0.10–0.18 alpha）：参考图的圆盘是"透出底色的玻璃珠"，
 * 不是实心色块；实心会压过旁边真正的数据数字。
 */
const TONES: Record<
  MedallionTone,
  { fg: string; bgFrom: string; bgTo: string; ring: string; glow: string }
> = {
  gold: {
    fg: "var(--color-gold-strong)",
    bgFrom: "rgba(212,184,122,0.20)",
    bgTo: "rgba(212,184,122,0.06)",
    ring: "rgba(212,184,122,0.48)",
    glow: "rgba(212,184,122,0.14)",
  },
  up: {
    fg: "var(--color-up)",
    bgFrom: "rgba(232,88,90,0.20)",
    bgTo: "rgba(232,88,90,0.06)",
    ring: "rgba(232,88,90,0.46)",
    glow: "rgba(232,88,90,0.14)",
  },
  down: {
    fg: "var(--color-down)",
    bgFrom: "rgba(79,211,155,0.18)",
    bgTo: "rgba(79,211,155,0.05)",
    ring: "rgba(79,211,155,0.44)",
    glow: "rgba(79,211,155,0.12)",
  },
  info: {
    fg: "var(--color-info)",
    bgFrom: "rgba(107,143,212,0.20)",
    bgTo: "rgba(107,143,212,0.06)",
    ring: "rgba(107,143,212,0.46)",
    glow: "rgba(107,143,212,0.14)",
  },
  conflict: {
    fg: "var(--color-conflict)",
    bgFrom: "rgba(176,124,214,0.20)",
    bgTo: "rgba(176,124,214,0.06)",
    ring: "rgba(176,124,214,0.46)",
    glow: "rgba(176,124,214,0.14)",
  },
  flat: {
    fg: "var(--color-ink-sub)",
    bgFrom: "rgba(124,143,163,0.16)",
    bgTo: "rgba(124,143,163,0.05)",
    ring: "rgba(124,143,163,0.36)",
    glow: "rgba(124,143,163,0.10)",
  },
};

export function Medallion({
  icon,
  tone = "gold",
  size = 56,
  title,
  testId,
  className = "",
}: {
  icon: ReactNode;
  tone?: MedallionTone;
  size?: number;
  /** 无障碍名称：徽章只做视觉编码，含义由相邻文字承担，这里给读屏一个短描述。 */
  title?: string;
  testId?: string;
  className?: string;
}) {
  const t = TONES[tone];
  return (
    <span
      className={`flex shrink-0 select-none items-center justify-center rounded-full ${className}`}
      style={{
        width: size,
        height: size,
        color: t.fg,
        background: `radial-gradient(circle at 34% 28%, ${t.bgFrom} 0%, ${t.bgTo} 68%, transparent 100%)`,
        border: `1px solid ${t.ring}`,
        boxShadow: `inset 0 0 14px ${t.glow}, 0 2px 10px rgba(0,0,0,0.32)`,
      }}
      title={title}
      aria-label={title}
      role={title ? "img" : undefined}
      data-testid={testId}
    >
      {icon}
    </span>
  );
}
