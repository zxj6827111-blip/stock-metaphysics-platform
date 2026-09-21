"use client";

/**
 * **分区级**三态（Loading / Empty / Error）。
 *
 * 为什么不用整页的 `PageLoading` / `PageError`：
 * 黄历与时间窗口页都是"多个独立数据源拼在一页"（单日快照 / 未来交易日 /
 * 历史表现 / 月窗口 / 周窗口 / 逐日窗口）。任何一个源慢或失败时，
 * 用整页三态会把已经拿到的数据一起吞掉 —— 这违反
 * "单一模型或区块失败不能拖垮整页"（AGENTS.md §9.7、用户要求 §六.7）。
 *
 * 因此这里提供**卡片内部**的三态：失败只在那一块显示，并可单独重试。
 */

import { Card } from "@/components/cards/Card";

export function SectionLoading({ label = "加载中…", rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div className="space-y-1.5 py-1" data-testid="section-loading" aria-busy="true">
      <div className="text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
        {label}
      </div>
      {Array.from({ length: Math.max(1, rows) }).map((_, i) => (
        <div
          key={i}
          className="smp-skeleton"
          style={{ height: 14, width: `${100 - i * 12}%` }}
        />
      ))}
    </div>
  );
}

export function SectionError({
  what,
  message,
  onRetry,
  testId = "section-error",
}: {
  what: string;
  message: string;
  onRetry?: () => void;
  testId?: string;
}) {
  return (
    <div
      className="rounded border px-3 py-2 text-[12.5px]"
      style={{
        borderColor: "rgba(232,88,90,0.4)",
        background: "rgba(232,88,90,0.07)",
        color: "var(--color-ink-sub)",
      }}
      data-testid={testId}
      role="alert"
    >
      <div className="font-semibold" style={{ color: "var(--color-warn)" }}>
        {what}加载失败
      </div>
      <div className="mt-0.5" style={{ color: "var(--color-ink-muted)" }}>
        {message}
      </div>
      {onRetry ? (
        <button type="button" className="smp-btn mt-1.5 px-2.5 py-1 text-[11.5px]" onClick={onRetry}>
          重试本区
        </button>
      ) : null}
    </div>
  );
}

export function SectionEmpty({
  what,
  hint,
  testId = "section-empty",
}: {
  what: string;
  hint: string;
  testId?: string;
}) {
  return (
    <div
      className="rounded border px-3 py-2 text-[12.5px]"
      style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
      data-testid={testId}
    >
      <span className="font-semibold" style={{ color: "var(--color-ink-sub)" }}>
        {what}：暂无数据
      </span>
      <br />
      {hint}
    </div>
  );
}

/** 卡片内的不可用提示（保留结构，不补齐数值）。 */
export function SectionUnavailable({
  what,
  reason,
  testId = "section-unavailable",
}: {
  what: string;
  reason: string;
  testId?: string;
}) {
  return (
    <div
      className="rounded border px-3 py-2 text-[12.5px]"
      style={{
        borderColor: "rgba(224,164,88,0.42)",
        background: "rgba(224,164,88,0.07)",
        color: "var(--color-ink-sub)",
      }}
      data-testid={testId}
    >
      <div className="font-semibold" style={{ color: "var(--color-warn)" }}>
        {what}：不可用
      </div>
      <div className="mt-0.5" style={{ color: "var(--color-ink-muted)" }}>
        {reason}
      </div>
    </div>
  );
}

/** 供分区卡片复用：一个自带三态外壳的 Card。 */
export function SectionCard({
  title,
  right,
  testId,
  children,
}: {
  title: string;
  right?: React.ReactNode;
  testId?: string;
  children: React.ReactNode;
}) {
  return (
    <Card testId={testId}>
      <div className="flex items-center justify-between gap-3">
        <div className="text-[13px] font-medium" style={{ color: "var(--color-ink)" }}>
          {title}
        </div>
        {right}
      </div>
      <div className="mt-2">{children}</div>
    </Card>
  );
}
