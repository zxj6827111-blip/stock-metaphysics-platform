"use client";

/**
 * FactorBadge / FactorTable —— 因子展示组件。
 *
 * 纪律：因子分数是**传统规则强度**，不是收益率预测。
 * 组件里必须带说明文案，避免被误读成"上涨概率"。
 */

import { useState } from "react";

import type { FactorRowView } from "@/lib/types";
import { Chip } from "../cards/Card";
import { IconArrowDown, IconArrowUp, IconMinus } from "../shell/Icons";

export function FactorBadge({ factor }: { factor: FactorRowView }) {
  const pos = factor.direction > 0;
  const color = pos
    ? "var(--color-up)"
    : factor.direction < 0
      ? "var(--color-down)"
      : "var(--color-flat)";
  const bg = pos
    ? "var(--color-up-bg)"
    : factor.direction < 0
      ? "var(--color-down-bg)"
      : "var(--color-flat-bg)";

  return (
    <span
      className="inline-flex items-center gap-1 rounded-[4px] border px-1.5 py-[1px] text-[11px]"
      style={{ color, borderColor: `${color}66`, background: bg }}
      title={factor.name}
      data-testid={`factor-badge-${factor.factorId}`}
    >
      {pos ? <IconArrowUp size={11} /> : factor.direction < 0 ? <IconArrowDown size={11} /> : <IconMinus size={11} />}
      <span className="smp-num">{factor.ruleScore.toFixed(1)}</span>
    </span>
  );
}

/**
 * 因子列表。
 *
 * `initialVisible` 让首屏只占前 N 条（复核任务书 §R1：八字页首屏各 3 条 + 展开），
 * 其余条目仍在 DOM 中可达（点击展开），不隐藏也不删改任何因子。
 */
export function FactorList({
  factors,
  tone,
  emptyText,
  initialVisible,
}: {
  factors: FactorRowView[];
  tone: "positive" | "negative";
  emptyText: string;
  initialVisible?: number;
}) {
  const [expanded, setExpanded] = useState(false);

  if (factors.length === 0) {
    return (
      <div className="px-4 py-6 text-center text-[12px]" style={{ color: "var(--color-ink-faint)" }}>
        {emptyText}
      </div>
    );
  }

  const color = tone === "positive" ? "var(--color-up)" : "var(--color-down)";
  const clipped = !!initialVisible && factors.length > initialVisible;
  const shown = clipped && !expanded ? factors.slice(0, initialVisible) : factors;

  return (
    <div className="px-3.5 py-1" data-testid={`factor-list-${tone}`}>
      {shown.map((f) => (
        <div
          key={f.factorId}
          className="flex items-start gap-2.5 border-b py-[2px] last:border-b-0"
          style={{ borderColor: "rgba(30,52,68,0.55)" }}
          data-testid={`factor-row-${f.factorId}`}
        >
          <span className="mt-[2px] shrink-0" style={{ color }}>
            {tone === "positive" ? <IconArrowUp size={12} /> : <IconArrowDown size={12} />}
          </span>
          <span
            className="smp-num mt-[2px] w-[108px] shrink-0 text-[11px]"
            style={{ color: "var(--color-ink-sub)" }}
          >
            {f.factorId}
          </span>
          <span className="min-w-0 flex-1 text-[11.5px] leading-[16px]" style={{ color: "var(--color-ink)" }}>
            {f.explanation || f.name}
          </span>
          <FactorBadge factor={f} />
        </div>
      ))}
      {clipped ? (
        <button
          type="button"
          className="mt-1 w-full rounded-[6px] border py-[2px] text-[11px] transition-opacity hover:opacity-80"
          style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
          onClick={() => setExpanded((v) => !v)}
          data-testid={`factor-toggle-${tone}`}
        >
          {expanded ? "收起因子明细" : `展开其余 ${factors.length - initialVisible!} 条因子`}
        </button>
      ) : null}
    </div>
  );
}

export function FactorTable({ factors }: { factors: FactorRowView[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="smp-table" data-testid="factor-table">
        <thead>
          <tr>
            <th className="w-[132px]">Factor ID</th>
            <th className="w-[168px]">名称</th>
            <th className="w-[76px]">术数</th>
            <th className="w-[72px]">层级</th>
            <th className="w-[64px]">方向</th>
            <th className="w-[72px]">规则分</th>
            <th className="w-[64px]">置信</th>
            <th>说明</th>
          </tr>
        </thead>
        <tbody>
          {factors.map((f) => (
            <tr key={f.factorId}>
              <td className="smp-num" style={{ color: "var(--color-gold)" }}>
                {f.factorId}
              </td>
              <td>{f.name}</td>
              <td>{f.engine}</td>
              <td>{f.category}</td>
              <td>
                <Chip tone={f.direction > 0 ? "up" : f.direction < 0 ? "down" : "flat"}>
                  {f.direction > 0 ? "+1" : f.direction < 0 ? "-1" : "0"}
                </Chip>
              </td>
              <td className="smp-num">{f.ruleScore.toFixed(1)}</td>
              <td className="smp-num">{f.confidence.toFixed(2)}</td>
              <td className="max-w-[520px] truncate" title={f.explanation}>
                {f.explanation}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function FactorDisclaimer() {
  return (
    <div
      className="rounded-[6px] border px-3 py-1 text-[11px] leading-[15px]"
      style={{
        borderColor: "rgba(224,164,88,0.26)",
        background: "rgba(224,164,88,0.06)",
        color: "var(--color-ink-sub)",
      }}
      data-testid="factor-disclaimer"
    >
      因子的 <span className="smp-num">direction</span> / <span className="smp-num">rule_score</span>{" "}
      表达的是<span style={{ color: "var(--color-gold)" }}>传统规则认为的方向与强度</span>
      ，<strong>不是预期收益率，也不是上涨概率</strong>。财星 ≠ 股票上涨；食神生财 ≠
      股票一定上涨；三合 ≠ 股票上涨。所有因子都只是研究变量，其统计有效性由历史回测回答。
    </div>
  );
}
