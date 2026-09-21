"use client";

/**
 * StockContextBar —— 所有股票分析页必须持续显示的上下文栏（uiux_spec §5）。
 *
 * 包含：股票名称/代码/交易所、上市日期、出生模型、出生时刻、分析基准、
 * 预测周期、数据质量，以及右侧操作按钮。
 *
 * 布局纪律（UI 复核任务书 §P1）：
 *  - **不靠横向滚动藏按钮**：信息区可伸缩（flex-1 min-w-0）并允许合理分行，
 *    操作区固定（shrink-0），「重新计算 / 导出报告」在任何支持宽度下默认可见；
 *  - 次要出生档案字段（出生模型/出生时刻）在 ≥1536px 显示在主行，
 *    窄于此宽度收进「详情」折叠区 —— 但**原始字段一个都不丢**；
 *  - 折叠区用原生 <details>，服务端与客户端初始状态一致，无 hydration 风险。
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import type { StockContext } from "@/lib/types";
import { FIXTURE_QUERY_VALUE } from "@/lib/fixture";
import { variantModeLabel } from "@/lib/dataSource";
import { IconClock, IconExport, IconRefresh, IconStar, IconTaiji } from "../shell/Icons";
import { StockSwitchModal } from "./StockSwitchModal";
import { KNOWN_STOCK_NAMES } from "@/lib/stockCatalog";

export function StockContextBar({
  context,
  activeTab,
  onRecalculate,
  recalculating,
  onExport,
  showTabs = false,
}: {
  context: StockContext;
  activeTab?: string;
  onRecalculate?: () => void;
  recalculating?: boolean;
  onExport?: () => void;
  /** 参考图 02 的上下文栏是单行；03 额外带一行股票切换条。 */
  showTabs?: boolean;
}) {
  const params = useSearchParams();
  const fixture = params.get("fixture") === FIXTURE_QUERY_VALUE;
  const suffix = fixture ? `?fixture=${FIXTURE_QUERY_VALUE}` : "";

  const { stock, birthProfile, asOf, horizon, quality } = context;

  // Phase 2：七个页面全部落地，标签不再有 disabled 项
  const TABS: { key: string; label: string; href: string; disabled?: boolean }[] = [
    { key: "overview", label: "综合研判", href: `/stock/${stock.code}/overview${suffix}` },
    { key: "bazi", label: "八字", href: `/stock/${stock.code}/bazi${suffix}` },
    { key: "ziwei", label: "紫微斗数", href: `/stock/${stock.code}/ziwei${suffix}` },
    { key: "huangli", label: "黄历", href: `/stock/${stock.code}/huangli${suffix}` },
    { key: "timeline", label: "时间窗口", href: `/stock/${stock.code}/timeline${suffix}` },
    { key: "backtest", label: "历史验证", href: `/stock/${stock.code}/backtest${suffix}` },
    { key: "evidence", label: "古籍证据", href: `/stock/${stock.code}/evidence${suffix}` },
    { key: "conflicts", label: "模型分歧", href: `/stock/${stock.code}/conflicts${suffix}` },
  ];

  const [switchModalOpen, setSwitchModalOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const displayName = stock.name || KNOWN_STOCK_NAMES[stock.code]?.name || "未知名称";
  const displayListing = stock.listingDate || KNOWN_STOCK_NAMES[stock.code]?.listingDate || "未知";

  return (
    <>
      <div
        className={`smp-card mb-2.5 px-3.5 py-1`}
        data-testid="stock-context-bar"
        style={{ background: "var(--color-surface-1)" }}
      >
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {/* 标的信息区：可伸缩，允许在窄宽度下合理分行 */}
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2.5 gap-y-1">
            {/* 股票标识 */}
            <div className="flex items-center gap-2">
              <span
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full"
                style={{
                  color: "var(--color-gold)",
                  border: "1px solid var(--color-gold-dim)",
                  background: "var(--color-gold-ghost)",
                }}
              >
                <IconTaiji size={13} />
              </span>
              <span className="text-[15px] font-semibold tracking-wide" style={{ color: "var(--color-ink)" }}>
                {displayName}
              </span>
              <span className="smp-num text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
                {stock.windCode || stock.code}
              </span>
              <button
                type="button"
                title="加入自选（Phase 2）"
                style={{ color: "var(--color-ink-muted)" }}
                disabled
              >
                <IconStar size={12} />
              </button>
            </div>

            <Divider />

            <Field label="上市" value={displayListing} />
            {/* 次要出生档案字段：宽屏显示在主行，窄屏收进「详情」 */}
            <Field
              label="出生模型"
              value={birthProfile.basis}
              mono
              className="hidden 2xl:flex"
            />
            <Field
              label="出生时刻"
              value={birthProfile.datetime}
              mono
              title={`时区：${birthProfile.timezone}`}
              className="hidden 2xl:flex"
            />
            <Field label="分析基准" value={asOf} mono />

            <Divider />

            {/* 数据质量 */}
            <div className="flex items-center gap-1.5">
              <span className="smp-metric-label">数据质量</span>
              <span
                className="rounded-[3px] border px-1.5 text-[11px] font-semibold"
                style={{
                  color: quality === "A" ? "var(--color-down)" : "var(--color-warn)",
                  borderColor:
                    quality === "A" ? "rgba(79,211,155,0.45)" : "rgba(224,164,88,0.45)",
                }}
                data-testid="context-quality"
              >
                {quality}
              </span>
            </div>

            <button
              type="button"
              className="rounded-[4px] border px-1.5 py-[1px] text-[11px]"
              style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
              onClick={() => setDetailsOpen((v) => !v)}
              aria-expanded={detailsOpen}
              data-testid="context-details-toggle"
            >
              详情 {detailsOpen ? "▴" : "▾"}
            </button>
          </div>

          {/* 主要操作区：固定宽度，默认可见，不参与横向滚动 */}
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              className="smp-btn px-2.5 py-1 text-[11.5px]"
              onClick={() => setSwitchModalOpen(true)}
              data-testid="switch-stock-btn"
            >
              切换股票
            </button>
            <button
              type="button"
              className="smp-btn smp-btn--primary px-3 py-1 text-[11.5px] font-semibold"
              onClick={onRecalculate}
              disabled={recalculating}
              data-testid="recalculate"
            >
              <IconRefresh size={12} />
              {recalculating ? "计算中…" : "重新计算"}
            </button>
            <button
              type="button"
              className="smp-btn px-2.5 py-1 text-[11.5px]"
              onClick={onExport}
              title="导出研究报告"
            >
              <IconExport size={12} />
              导出报告
            </button>
          </div>
        </div>

        {/* 出生档案详情：默认收起（保证上下文栏默认高度紧凑），展开后给出全部原始字段 ——
            窄屏不再依赖横向滚动，且原始值一个不丢。 */}
        {detailsOpen ? (
          <div
            className="mt-1.5 flex flex-wrap gap-x-5 gap-y-1 border-t pt-1.5 text-[11.5px]"
            style={{ borderColor: "var(--color-border)" }}
            data-testid="context-birth-fields"
          >
            <Field label="出生模型" value={birthProfile.basis} mono />
            <Field
              label="出生时刻"
              value={birthProfile.datetime}
              mono
              title={`时区：${birthProfile.timezone}`}
            />
            <Field label="时区" value={birthProfile.timezone} mono />
            <Field label="预测周期" value={horizon} />
            <Field label="运限假设" value={variantModeLabel(birthProfile.variantMode)} />
            {birthProfile.sessionKey ? (
              <Field label="开市口径" value={birthProfile.sessionKey} mono />
            ) : null}
            {birthProfile.derivation ? (
              <Field label="推导" value={birthProfile.derivation} />
            ) : null}
            <span className="flex items-center gap-1.5">
              {/* Phase 2 占位：保留入口但明确标注未实现，避免"看起来能点" */}
              <button
                type="button"
                className="smp-btn px-2 py-[1px] text-[11px] opacity-60"
                disabled
                title="Phase 2：切换出生模型会生成新版本，不覆盖历史结果"
              >
                切换出生模型
              </button>
              <button
                type="button"
                className="smp-btn px-2 py-[1px] text-[11px] opacity-60"
                disabled
                title="Phase 2：预测周期切换需要重跑事件研究"
              >
                切换预测周期
              </button>
            </span>
          </div>
        ) : null}

        {showTabs ? (
          <div
            className="mt-1 flex flex-wrap items-center gap-1 border-t pt-1"
            style={{ borderColor: "var(--color-border)" }}
          >
            <IconClock size={12} style={{ color: "var(--color-ink-faint)" }} />
            {TABS.map((t) =>
              t.disabled ? (
                <span
                  key={t.key}
                  className="rounded-[4px] px-2.5 py-[3px] text-[11.5px]"
                  style={{ color: "var(--color-ink-faint)" }}
                  title="Phase 2 实现"
                >
                  {t.label}
                </span>
              ) : (
                <Link
                  key={t.key}
                  href={t.href}
                  className="rounded-[4px] px-2.5 py-[3px] text-[11.5px] transition-colors"
                  style={{
                    color: activeTab === t.key ? "var(--color-gold)" : "var(--color-ink-sub)",
                    background: activeTab === t.key ? "var(--color-gold-ghost)" : "transparent",
                    border:
                      activeTab === t.key
                        ? "1px solid var(--color-gold-dim)"
                        : "1px solid transparent",
                  }}
                >
                  {t.label}
                </Link>
              ),
            )}
            <span
              className="ml-auto text-[10.5px]"
              style={{ color: "var(--color-ink-faint)" }}
              data-testid="variant-note"
              data-variant-mode={birthProfile.variantMode}
            >
              运限假设：{variantModeLabel(birthProfile.variantMode)}
            </span>
          </div>
        ) : null}
      </div>
      <StockSwitchModal
        isOpen={switchModalOpen}
        onClose={() => setSwitchModalOpen(false)}
        currentCode={stock.code}
      />
    </>
  );
}

function Divider() {
  return <span style={{ color: "var(--color-border-strong)" }}>|</span>;
}

function Field({
  label,
  value,
  mono,
  title,
  className = "",
}: {
  label: string;
  value: string;
  mono?: boolean;
  title?: string;
  className?: string;
}) {
  return (
    <span className={`flex items-center gap-1.5 ${className}`} title={title}>
      <span className="smp-metric-label">{label}：</span>
      <span
        className={mono ? "smp-num text-[12px]" : "text-[12px]"}
        style={{ color: "var(--color-ink)" }}
      >
        {value}
      </span>
    </span>
  );
}
