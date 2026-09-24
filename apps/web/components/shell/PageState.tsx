"use client";

/**
 * 页面三态（Loading / Empty / Error）。
 *
 * uiux_spec 要求所有关键组件都必须有这三种状态；Phase 2 的 7 个新页面
 * 统一用这个组件，避免每个页面各写一套、风格漂移。
 *
 * **错误必须可读**：把后端结构化错误的 code / message / detail / retryable
 * 都展示出来，并给出"下一步该做什么"，而不是只显示"出错了"。
 */

import type { ReactNode } from "react";

import { Card } from "../cards/Card";
import { RawField, SourceMethod } from "./SourceMethod";

export function PageLoading({ label = "加载中…" }: { label?: string }) {
  return (
    <Card testId="page-loading">
      <div className="flex items-center gap-3 py-6 text-[13px]" style={{ color: "var(--color-ink-muted)" }}>
        <span className="smp-spinner" aria-hidden />
        {label}
      </div>
    </Card>
  );
}

export function PageError({
  title = "加载失败",
  message,
  detail,
  code,
  retryable,
  onRetry,
}: {
  title?: string;
  message: string;
  detail?: string;
  code?: string;
  retryable?: boolean;
  onRetry?: () => void;
}) {
  return (
    <Card testId="page-error">
      <div className="py-4">
        <div className="mb-2 flex items-center gap-2">
          <span
            className="rounded px-2 py-0.5 text-[11px] font-semibold"
            style={{ background: "rgba(232,88,90,0.15)", color: "var(--color-up)" }}
          >
            ERROR
          </span>
          <span className="text-[14px] font-semibold">{title}</span>
        </div>
        <p className="text-[13px]" style={{ color: "var(--color-ink)" }}>{message}</p>
        {code ? (
          <p className="mt-1 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
            错误码：<code>{code}</code>
            {retryable === false ? "（不可重试）" : ""}
          </p>
        ) : null}
        {detail ? (
          <pre
            className="mt-2 max-h-[160px] overflow-auto rounded p-2 text-[11.5px]"
            style={{ background: "var(--color-surface-2, rgba(255,255,255,0.03))" }}
          >
            {detail}
          </pre>
        ) : null}
        <p className="mt-2 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          {retryable === false
            ? "该错误不可重试，请检查输入或数据来源。"
            : "可以重试；若持续失败，请确认后端 apps/api 已启动（默认 http://127.0.0.1:8000）。"}
        </p>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="mt-3 rounded border px-3 py-1 text-[12px] transition-opacity hover:opacity-80"
            style={{ borderColor: "var(--color-border)", color: "var(--color-ink)" }}
          >
            重试
          </button>
        ) : null}
      </div>
    </Card>
  );
}

export function PageEmpty({
  title = "暂无数据",
  hint,
  children,
}: {
  title?: string;
  hint?: string;
  children?: ReactNode;
}) {
  return (
    <Card testId="page-empty">
      <div className="py-6 text-center">
        <p className="text-[14px] font-semibold" style={{ color: "var(--color-ink)" }}>
          {title}
        </p>
        {hint ? (
          <p className="mt-1 text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
            {hint}
          </p>
        ) : null}
        {children}
      </div>
    </Card>
  );
}

/** 「不可用」的统一表达：**绝不用 0 或空白冒充**。 */
export function UnavailableBlock({
  what,
  reason,
  testId,
}: {
  what: string;
  reason: string;
  testId?: string;
}) {
  return (
    <div
      className="rounded border px-3 py-2 text-[12.5px]"
      style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
      data-testid={testId}
    >
      <span className="font-semibold" style={{ color: "var(--color-ink)" }}>
        {what}：不可用
      </span>
      <br />
      {reason}
      <br />
      <span style={{ opacity: 0.8 }}>
        系统不会用 0 分或占位数值代替不可用结果。
      </span>
    </div>
  );
}

/**
 * 研究状态徽标：把 ResearchStatus 显式地摆在读者眼前。
 *
 * 展示纪律（UI 复核任务书 §2）：
 *  - 面向人的主标签一律用中文（`INSUFFICIENT_SAMPLE` → 「样本不足」）；
 *  - 原始状态码 **不丢**，收进「原始状态码与来源」折叠区，保持可追溯；
 *  - 覆盖后端 `src/research/status.py` 的全部合法枚举值；
 *    非法/未知状态显式标注为「未知状态」而不是把裸码当结论展示。
 */
const RESEARCH_STATUS_TONE: Record<string, { bg: string; fg: string; label: string }> = {
  NOT_RUN: { bg: "rgba(124,143,163,0.18)", fg: "#9FB0C0", label: "未运行" },
  NO_REAL_DATA: { bg: "rgba(232,88,90,0.18)", fg: "#E8585A", label: "无真实数据" },
  INSUFFICIENT_SAMPLE: { bg: "rgba(212,160,74,0.18)", fg: "#D4A04A", label: "样本不足" },
  INVALID_CONTROL: { bg: "rgba(232,88,90,0.18)", fg: "#E8585A", label: "负对照失效" },
  NO_SIGNAL: { bg: "rgba(212,160,74,0.18)", fg: "#D4A04A", label: "未发现稳定信号" },
  INCONCLUSIVE: { bg: "rgba(212,160,74,0.18)", fg: "#D4A04A", label: "结论不明确" },
  WEAK_EVIDENCE: { bg: "rgba(79,211,155,0.15)", fg: "#4FD39B", label: "弱证据（样本内）" },
  SUPPORTED_IN_SAMPLE: { bg: "rgba(79,211,155,0.18)", fg: "#4FD39B", label: "样本内支持" },
  OOS_CANDIDATE_SUPPORTED: {
    bg: "rgba(79,211,155,0.20)",
    fg: "#4FD39B",
    label: "样本外候选（未做 FDR 校正）",
  },
  EXPLORATORY_NOT_GATED: {
    bg: "rgba(124,143,163,0.18)",
    fg: "#9FB0C0",
    label: "探索性对象（不套用状态门）",
  },
  SUPPORTED_OUT_OF_SAMPLE: { bg: "rgba(79,211,155,0.25)", fg: "#4FD39B", label: "样本外支持" },
};

/** 研究状态码 → 中文标签（其他页面需要在正文里引用状态时复用同一套映射）。 */
export function researchStatusLabel(status: string | null | undefined): string {
  if (!status) return "未运行";
  const t = RESEARCH_STATUS_TONE[status];
  return t ? t.label : `未知状态（${status}）`;
}

export function ResearchStatusBadge({
  status,
  reasons = [],
  compact,
  showCode,
}: {
  status: string;
  reasons?: string[];
  compact?: boolean;
  /** 紧凑档里仍把后端原始状态码带在徽标上（05 历史验证首屏只有一行预算，
   *  但 §2.4/§16 要求状态可追溯，不能只剩中文标签）。 */
  showCode?: boolean;
}) {
  const t = RESEARCH_STATUS_TONE[status];
  const unknown = !t;
  const shown = t ?? { bg: "rgba(124,143,163,0.18)", fg: "#9FB0C0", label: "未知状态" };
  return (
    <div data-testid="research-status-badge" data-status={status}>
      <span
        className="rounded px-2 py-0.5 text-[11.5px] font-semibold"
        style={{ background: shown.bg, color: shown.fg }}
        title={reasons.join("\n")}
      >
        研究状态：{shown.label}
        {showCode ? <code className="ml-1 font-normal opacity-85">{status}</code> : null}
        {unknown ? `（无法识别的状态码 ${status}）` : ""}
      </span>
      {!compact && reasons.length ? (
        <ul className="mt-2 space-y-1 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          {reasons.slice(0, 4).map((r) => (
            <li key={r}>· {r}</li>
          ))}
        </ul>
      ) : null}
      {!compact ? (
        <SourceMethod className="mt-2" label="原始状态码与来源" testId="research-status-source">
          <RawField label="research_status（后端原值）" value={status} />
          <div>历史有效性由研究流水线（事件研究 + 四类负对照）判定，不由本页前端推断。</div>
        </SourceMethod>
      ) : null}
    </div>
  );
}
