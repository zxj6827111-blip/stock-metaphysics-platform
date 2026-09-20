"use client";

/**
 * StockContextBar —— 所有股票分析页必须持续显示的上下文栏（uiux_spec §5）。
 *
 * 包含：股票名称/代码/交易所、上市日期、出生模型、出生时刻、分析基准、
 * 预测周期、数据质量，以及右侧操作按钮。
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import type { StockContext } from "@/lib/types";
import { FIXTURE_QUERY_VALUE } from "@/lib/fixture";
import { IconClock, IconExport, IconRefresh, IconStar, IconTaiji } from "../shell/Icons";
import { StockSwitchModal, KNOWN_STOCK_NAMES } from "./StockSwitchModal";

export function StockContextBar({
  context,
  activeTab,
  onRecalculate,
  recalculating,
  showTabs = false,
}: {
  context: StockContext;
  activeTab?: string;
  onRecalculate?: () => void;
  recalculating?: boolean;
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
  const displayName = stock.name || KNOWN_STOCK_NAMES[stock.code]?.name || "未知名称";
  const displayListing = stock.listingDate || KNOWN_STOCK_NAMES[stock.code]?.listingDate || "未知";

  return (
    <>
      <div
        className="smp-card mb-3 px-4 py-2.5"
        data-testid="stock-context-bar"
        style={{ background: "var(--color-surface-1)" }}
      >
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          {/* 股票标识 */}
          <div className="flex items-center gap-2.5">
            <span
              className="flex h-7 w-7 items-center justify-center rounded-full"
              style={{
                color: "var(--color-gold)",
                border: "1px solid var(--color-gold-dim)",
                background: "var(--color-gold-ghost)",
              }}
            >
              <IconTaiji size={15} />
            </span>
            <span className="text-[16px] font-semibold" style={{ color: "var(--color-ink)" }}>
              {displayName}
            </span>
            <span className="smp-num text-[13px]" style={{ color: "var(--color-ink-sub)" }}>
              {stock.windCode || stock.code}
            </span>
            <button
              type="button"
              title="加入自选（Phase 2）"
              style={{ color: "var(--color-ink-muted)" }}
              disabled
            >
              <IconStar size={13} />
            </button>
          </div>

          <Divider />

          <Field label="上市" value={displayListing} />
          <Field label="出生模型" value={birthProfile.basis} mono />
          <Field
            label="出生时刻"
            value={birthProfile.datetime}
            mono
            title={`时区：${birthProfile.timezone}`}
          />
          <Field label="分析基准" value={asOf} mono />
          <Field label="预测" value={horizon} />

          {/* 数据质量 */}
          <div className="flex items-center gap-1.5">
            <span className="smp-metric-label">数据质量</span>
            <span
              className="rounded-[3px] border px-1.5 text-[12px] font-semibold"
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

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              className="smp-btn smp-btn--primary"
              onClick={() => setSwitchModalOpen(true)}
              data-testid="switch-stock-btn"
            >
              切换股票
            </button>
            <button type="button" className="smp-btn" disabled title="Phase 2">
              切换出生模型
            </button>
            <button
              type="button"
              className="smp-btn"
              onClick={onRecalculate}
              disabled={recalculating}
              data-testid="recalculate"
            >
              <IconRefresh size={14} />
              {recalculating ? "计算中…" : "重新计算"}
            </button>
            <button type="button" className="smp-btn" disabled title="Phase 2">
              <IconExport size={14} />
              导出报告
            </button>
          </div>
        </div>

      {showTabs ? (
      <div
        className="mt-2 flex items-center gap-1 border-t pt-2"
        style={{ borderColor: "var(--color-border)" }}
      >
        <IconClock size={13} style={{ color: "var(--color-ink-faint)" }} />
        {TABS.map((t) =>
          t.disabled ? (
            <span
              key={t.key}
              className="rounded-[5px] px-3 py-1 text-[12px]"
              style={{ color: "var(--color-ink-faint)" }}
              title="Phase 2 实现"
            >
              {t.label}
            </span>
          ) : (
            <Link
              key={t.key}
              href={t.href}
              className="rounded-[5px] px-3 py-1 text-[12px] transition-colors"
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
          className="ml-auto text-[11px]"
          style={{ color: "var(--color-ink-faint)" }}
          data-testid="variant-note"
        >
          运限假设：{birthProfile.variantMode}（股票无性别）
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
}: {
  label: string;
  value: string;
  mono?: boolean;
  title?: string;
}) {
  return (
    <span className="flex items-center gap-1.5" title={title}>
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
