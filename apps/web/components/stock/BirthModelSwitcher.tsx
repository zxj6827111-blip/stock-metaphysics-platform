"use client";

/**
 * 出生模型切换器（研究假设切换）。
 *
 * 为什么这是一个"分析上下文"而不是"显示选项"
 * ------------------------------------------
 * 股票的"出生时间"本身是**研究假设**（股票不存在传统意义的出生时刻）。
 * 换一个基准 → 出生时刻变了 → 四柱变了 → 紫微盘面变了 → 三个模型的分数都变了。
 * 因此它是一个真实的重新分析动作，而不是纯前端筛选。
 *
 * 诚实边界
 * --------
 * * 只有 `listing_open` 与 `ipo_date` 能算；后者用上市日近似发行日，
 *   数据质量为 C 级，**切换后必须在界面上看到这个降级说明**。
 * * `company_foundation` / `first_trade` 缺数据源，后端按契约返回
 *   `422 BIRTH_PROFILE_ERROR`；这里显示为**不可用 + 原因**，
 *   而不是"点一下就报错"或"点了没反应"。
 * * 不改变任何排盘规则：切换只是把不同的假设传给后端，计算仍然后端做。
 */

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { birthBasisLabel } from "@/lib/dataSource";
import type { AnalysisBirthBasis } from "@/lib/analysisStore";
import {
  AVAILABLE_BIRTH_BASES,
  BIRTH_BASIS_UNAVAILABLE_REASON,
  BIRTH_BASIS_VALUES,
  normalizeBirthBasis,
} from "@/lib/useBirthBasisParam";
import { HORIZON_OPTIONS, normalizeHorizon } from "@/lib/useHorizonParam";

export function BirthModelSwitcher({ compact = false }: { compact?: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const current = normalizeBirthBasis(params?.get("birthBasis"));

  const select = (basis: AnalysisBirthBasis) => {
    if (!AVAILABLE_BIRTH_BASES.includes(basis)) return;
    if (basis === current) return;
    const next = new URLSearchParams(params?.toString() ?? "");
    next.set("birthBasis", basis);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  return (
    <div className="flex flex-wrap items-center gap-x-2 gap-y-1" data-testid="birth-model-switcher">
      <span className="smp-metric-label">出生模型（研究假设）</span>
      <span className="inline-flex overflow-hidden rounded border" style={{ borderColor: "var(--color-border)" }}>
        {BIRTH_BASIS_VALUES.map((b) => {
          const available = AVAILABLE_BIRTH_BASES.includes(b);
          const active = b === current;
          return (
            <button
              key={b}
              type="button"
              onClick={() => select(b)}
              disabled={!available}
              aria-pressed={active}
              title={available ? `切换到「${birthBasisLabel(b)}」并重新分析` : BIRTH_BASIS_UNAVAILABLE_REASON[b]}
              className="px-2 py-[1px] text-[11px] transition-opacity hover:opacity-80 disabled:cursor-not-allowed disabled:opacity-40"
              style={{
                background: active ? "rgba(212,184,122,0.18)" : "transparent",
                color: active ? "var(--color-gold)" : "var(--color-ink-muted)",
              }}
              data-testid={`birth-basis-${b}`}
              data-available={available ? "1" : "0"}
            >
              {birthBasisLabel(b)}
              {available ? "" : "（不可用）"}
            </button>
          );
        })}
      </span>
      {!compact ? (
        <span className="text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
          切换会重新分析（出生时刻不同 → 四柱与紫微盘面不同）
        </span>
      ) : null}
    </div>
  );
}

/**
 * 研究窗口（登记窗口）切换器。
 *
 * **这不是"预测周期切换"**：后端会把该值登记进 `analysis_run.horizon` 并回传，
 * 但它**不参与因子计算** —— 三个模型的分数、共识、分歧都不随之变化；
 * 事件研究（历史验证）用自己的持有期集合。界面上必须把这一点写清楚，
 * 否则用户会以为切到 60 日就得到"60 日预测"，那是虚假能力宣称。
 */
export function HorizonSwitcher() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const current = normalizeHorizon(params?.get("horizon"));

  const select = (h: string) => {
    if (h === current) return;
    const next = new URLSearchParams(params?.toString() ?? "");
    next.set("horizon", h);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };

  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-1" data-testid="horizon-switcher">
      <span className="smp-metric-label">研究窗口（登记）</span>
      <span className="inline-flex overflow-hidden rounded border" style={{ borderColor: "var(--color-border)" }}>
        {HORIZON_OPTIONS.map((h) => {
          const active = h === current;
          return (
            <button
              key={h}
              type="button"
              onClick={() => select(h)}
              aria-pressed={active}
              className="px-2 py-[1px] text-[11px] transition-opacity hover:opacity-80"
              style={{
                background: active ? "rgba(212,184,122,0.18)" : "transparent",
                color: active ? "var(--color-gold)" : "var(--color-ink-muted)",
              }}
              data-testid={`horizon-${h}`}
            >
              {h}
            </button>
          );
        })}
      </span>
      <span className="text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
        只登记进本次分析记录，**不改变**三个模型的分数（事件研究用自己的持有期集合）
      </span>
    </span>
  );
}
