"use client";

/** 卡片基元：所有页面统一复用的容器与标题栏。 */

import type { ReactNode } from "react";

import { IconArrowRight } from "../shell/Icons";

export function Card({
  children,
  className = "",
  quiet,
  testId,
}: {
  children: ReactNode;
  className?: string;
  quiet?: boolean;
  testId?: string;
}) {
  return (
    <section
      className={`smp-card ${quiet ? "smp-card--quiet" : ""} ${className}`}
      data-testid={testId}
    >
      {children}
    </section>
  );
}

export function CardHeader({
  icon,
  title,
  right,
  action,
  dense,
}: {
  icon?: ReactNode;
  title: string;
  right?: ReactNode;
  action?: { label: string; onClick?: () => void };
  dense?: boolean;
}) {
  return (
    <header className={`smp-card-header ${dense ? "py-2" : ""}`}>
      <h2 className="smp-card-title">
        {icon ? <span className="smp-card-title-icon">{icon}</span> : null}
        {title}
      </h2>
      <div className="ml-auto flex items-center gap-3">
        {right}
        {action ? (
          <button
            type="button"
            onClick={action.onClick}
            className="flex items-center gap-1 text-[11.5px] transition-opacity hover:opacity-80"
            style={{ color: "var(--color-ink-muted)" }}
          >
            {action.label}
            <IconArrowRight size={13} />
          </button>
        ) : null}
      </div>
    </header>
  );
}

/** 方向指示器：颜色 + 箭头/符号双重编码（不依赖颜色单独传达信息，uiux_spec §31）。 */
export function DirectionMark({
  direction,
  size = 12,
}: {
  direction: number;
  size?: number;
}) {
  const symbol = direction > 0 ? "↑" : direction < 0 ? "↓" : "→";
  const color =
    direction > 0 ? "var(--color-up)" : direction < 0 ? "var(--color-down)" : "var(--color-flat)";
  return (
    <span style={{ color, fontSize: size, lineHeight: 1 }} aria-hidden="true">
      {symbol}
    </span>
  );
}

export function Chip({
  tone = "flat",
  children,
  testId,
}: {
  tone?: "up" | "down" | "flat" | "warn" | "info" | "conflict" | "gold";
  children: ReactNode;
  testId?: string;
}) {
  return (
    <span className={`smp-chip smp-chip--${tone}`} data-testid={testId}>
      {children}
    </span>
  );
}

/** 可用性徽标：把 unavailable/partial 明确画出来，绝不用 0 分。 */
export function AvailabilityChip({ available, reason }: { available: boolean; reason?: string }) {
  if (available) {
    return <Chip tone="down">已启用</Chip>;
  }
  return (
    <span title={reason}>
      <Chip tone="flat">未启用</Chip>
    </span>
  );
}

export function StatPair({
  label,
  value,
  tone = "flat",
}: {
  label: string;
  value: string;
  tone?: "up" | "down" | "flat" | "gold";
}) {
  const color =
    tone === "up"
      ? "var(--color-up)"
      : tone === "down"
        ? "var(--color-down)"
        : tone === "gold"
          ? "var(--color-gold)"
          : "var(--color-ink)";
  return (
    <span className="flex items-center gap-1">
      <span className="smp-metric-label">{label}</span>
      <span className="smp-num text-[12.5px]" style={{ color }}>
        {value}
      </span>
    </span>
  );
}
