"use client";

/** 卡片基元：所有页面统一复用的容器与标题栏。 */

import Link from "next/link";
import type { ReactNode } from "react";

import { IconArrowRight } from "../shell/Icons";

export function Card({
  children,
  className = "",
  quiet,
  testId,
  anchor,
}: {
  children: ReactNode;
  className?: string;
  quiet?: boolean;
  testId?: string;
  /** 结构测量锚点（见 scripts/visual-anchors.mjs）。 */
  anchor?: string;
}) {
  return (
    <section
      className={`smp-card ${quiet ? "smp-card--quiet" : ""} ${className}`}
      data-testid={testId}
      data-anchor={anchor}
    >
      {children}
    </section>
  );
}

export function CardBody({
  children,
  className = "",
  dense = false,
}: {
  children: ReactNode;
  className?: string;
  dense?: boolean;
}) {
  return (
    <div className={`smp-card-body ${dense ? "smp-card-body--dense" : ""} ${className}`}>
      {children}
    </div>
  );
}

/**
 * 卡片右上角的动作。
 *
 * `href` 与 `onClick` 至少要有一个：都没有时**不渲染任何可点样式**。
 * 之前这里只要传了 `label` 就画出一个带箭头的 `<button>`，于是页面上出现
 * 一批"查看详情 / 历史验证详情"点下去毫无反应的假按钮（研究终端里这属于
 * 能力虚报，不只是样式问题）。
 */
export interface CardHeaderAction {
  label: string;
  href?: string;
  onClick?: () => void;
  testId?: string;
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
  action?: CardHeaderAction;
  dense?: boolean;
}) {
  const actionable = action && (action.href || action.onClick);
  const actionStyle = {
    color: "var(--color-ink-muted)",
  } as const;
  return (
    <header className={`smp-card-header ${dense ? "py-2" : ""}`}>
      <h2 className="smp-card-title">
        {icon ? <span className="smp-card-title-icon">{icon}</span> : null}
        {title}
      </h2>
      <div className="ml-auto flex items-center gap-3">
        {right}
        {actionable && action?.href ? (
          <Link
            href={action.href}
            className="flex items-center gap-1 text-[11.5px] transition-opacity hover:opacity-80"
            style={actionStyle}
            data-testid={action.testId}
          >
            {action.label}
            <IconArrowRight size={13} />
          </Link>
        ) : actionable ? (
          <button
            type="button"
            onClick={action?.onClick}
            className="flex items-center gap-1 text-[11.5px] transition-opacity hover:opacity-80"
            style={actionStyle}
            data-testid={action?.testId}
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
