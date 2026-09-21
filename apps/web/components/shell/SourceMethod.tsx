"use client";

/**
 * 「来源与方法」可展开区。
 *
 * 为什么需要它：接口路径、脚本名、引擎版本、原始状态码（如 `forward` /
 * `not_applicable` / `NO_REAL_DATA`）是**可追溯性凭据**，必须保留；
 * 但它们同时是**面向实现的语言**，直接铺在正文里会淹没结论、
 * 让研究者以为在读代码文档（见 docs/UI_REAUDIT_2026-09-21.md §2）。
 *
 * 使用原生 `<details>`：服务端与客户端初始状态一致，不引入 JS 状态，
 * 因此不会产生 hydration 差异；内容仍在 DOM 中（可搜索、可截图）。
 */

import type { ReactNode } from "react";

export function SourceMethod({
  children,
  label = "来源与方法",
  testId = "source-method",
  className = "",
}: {
  children: ReactNode;
  label?: string;
  testId?: string;
  className?: string;
}) {
  return (
    <details
      className={`group rounded-[6px] border px-3 py-1.5 text-[11.5px] ${className}`}
      style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
      data-testid={testId}
    >
      <summary
        className="cursor-pointer select-none list-none font-medium outline-none"
        style={{ color: "var(--color-ink-sub)" }}
      >
        <span className="inline-block transition-transform group-open:rotate-90">▸</span>{" "}
        {label}
      </summary>
      <div className="mt-1.5 space-y-1 leading-[17px]">{children}</div>
    </details>
  );
}

/** 「来源与方法」里的一行原始字段（等宽展示，保留可追溯性）。 */
export function RawField({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2">
      <span style={{ color: "var(--color-ink-muted)" }}>{label}：</span>
      <code className="smp-num break-all" style={{ color: "var(--color-ink-sub)" }}>
        {value}
      </code>
    </div>
  );
}
