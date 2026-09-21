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
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import type { StockContext } from "@/lib/types";
import { FIXTURE_QUERY_VALUE } from "@/lib/fixture";
import { variantModeLabel } from "@/lib/dataSource";
import { exportReport, type ExportFormat, type ExportTarget } from "@/lib/reportExport";
import { useWatchlist, WATCHLIST_MAX } from "@/lib/watchlistStore";
import { IconExport, IconRefresh, IconStar, IconTaiji } from "../shell/Icons";
import { BirthModelSwitcher, HorizonSwitcher } from "./BirthModelSwitcher";
import { StockSwitchModal } from "./StockSwitchModal";
import { KNOWN_STOCK_NAMES } from "@/lib/stockCatalog";

export function StockContextBar({
  context,
  activeTab,
  onRecalculate,
  recalculating,
  exportTarget,
}: {
  context: StockContext;
  activeTab?: string;
  onRecalculate?: () => void;
  recalculating?: boolean;
  /**
   * 导出目标（调用时已冻结的上下文快照）。
   *
   * 传 `undefined` 表示"本次分析尚无可导出的结果"——此时按钮显示为禁用并给出
   * 原因，不做"点了没反应"的假按钮。
   */
  exportTarget?: ExportTarget | null;
}) {
  const params = useSearchParams();
  const fixture = params.get("fixture") === FIXTURE_QUERY_VALUE;
  const suffix = fixture ? `?fixture=${FIXTURE_QUERY_VALUE}` : "";

  const { stock, birthProfile, asOf, horizon, quality } = context;

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
              <WatchStar code={stock.code} name={displayName} activeTab={activeTab} suffix={suffix} />
            </div>

            <Divider />

            <Field label="上市" value={displayListing} />
            {/* 次要出生档案字段：宽屏显示在主行，窄屏收进「详情」 */}
            <Field
              label="出生模型"
              value={birthProfile.basisLabel}
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
            <ExportMenu target={exportTarget} />
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
            {/* 中文标签 + 原始码并列：正文可读，同时保留可追溯的内部码 */}
            <Field
              label="出生模型"
              value={`${birthProfile.basisLabel}（${birthProfile.basis}）`}
            />
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
            {/* 出生模型切换：真实切换研究假设并重新分析（不再是被禁用的占位按钮） */}
            <span className="w-full">
              <BirthModelSwitcher />
            </span>
            {/* 研究窗口：只登记，不改分数 —— 文案里写明，避免被读成"预测周期" */}
            <span className="w-full">
              <HorizonSwitcher />
            </span>
            {/* 假设降级必须可见：ipo_date 用上市日近似发行日，是 C 级数据质量 */}
            {birthProfile.quality !== "A" ? (
              <span
                className="w-full rounded border px-2 py-1 text-[11px]"
                style={{ borderColor: "rgba(224,164,88,0.45)", color: "var(--color-warn)" }}
                data-testid="birth-basis-quality-note"
              >
                当前出生模型的数据质量等级为 {birthProfile.quality}
                {birthProfile.quality === "C"
                  ? "（例：ipo_date 以上市日近似发行日）—— 该基准的出生时刻精度不足，结论仅供参考，不得作为正式研究结论。"
                  : "（存在降级：见下方推导说明）。"}
              </span>
            ) : null}
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

/**
 * 导出报告菜单。
 *
 * 三种格式都对应真实可打开的产物：
 *  * Markdown / 可打印 HTML：后端 `render_report` 渲染的完整研究报告；
 *  * 结构化 JSON：同一份上下文的机器可读快照（本机生成）。
 * 演示模式（`?fixture=ui-reference`）下由前端就地生成，**逐份标注"演示数据"**。
 * 没有可导出结果时按钮禁用并说明原因，不保留"点了没反应"的交互。
 */
export function ExportMenu({ target }: { target?: ExportTarget | null }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [msg, setMsg] = useState<{ tone: "ok" | "bad"; text: string } | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const disabled = !target;
  const run = useCallback(
    async (format: ExportFormat) => {
      if (!target) return;
      setBusy(format);
      setMsg(null);
      try {
        await exportReport(target, format);
        setMsg({
          tone: "ok",
          text: target.fixture ? "已生成演示报告（本机下载）" : "已生成报告（本机下载）",
        });
        setOpen(false);
      } catch (e) {
        setMsg({ tone: "bad", text: e instanceof Error ? e.message : String(e) });
      } finally {
        setBusy(null);
      }
    },
    [target],
  );

  const items: { format: ExportFormat; label: string; hint: string }[] = [
    { format: "markdown", label: "Markdown（.md）", hint: "完整报告文本，便于归档与引用" },
    { format: "html", label: "可打印 HTML（.html）", hint: "自包含页面，可浏览器打印（非服务端 PDF）" },
    { format: "json", label: "结构化 JSON（.json）", hint: "同一份上下文的机器可读快照" },
  ];

  return (
    <div className="relative" ref={boxRef}>
      <button
        type="button"
        className="smp-btn px-2.5 py-1 text-[11.5px] disabled:opacity-40"
        onClick={() => setOpen((v) => !v)}
        disabled={disabled}
        aria-haspopup="menu"
        aria-expanded={open}
        title={
          disabled
            ? "本次分析尚未产生可导出的结果"
            : target?.fixture
              ? "导出演示报告（会明确标注演示数据）"
              : "导出研究报告"
        }
        data-testid="export-report-btn"
      >
        <IconExport size={12} />
        {busy ? "导出中…" : "导出报告"}
      </button>
      {open && target ? (
        <div
          className="absolute right-0 z-40 mt-1 w-[252px] overflow-hidden rounded-[8px] border py-1"
          style={{
            borderColor: "var(--color-border-strong)",
            background: "linear-gradient(180deg, rgba(14,26,38,0.98), rgba(9,19,29,0.98))",
            boxShadow: "0 18px 40px rgba(0,0,0,0.6)",
          }}
          role="menu"
          data-testid="export-report-menu"
        >
          {target.fixture ? (
            <div
              className="px-3 pb-1.5 pt-1 text-[10.5px] leading-[15px]"
              style={{ color: "var(--color-warn)" }}
            >
              演示模式：导出内容为冻结样本，文件内会逐份标注「演示数据」
            </div>
          ) : (
            <div
              className="px-3 pb-1.5 pt-1 text-[10.5px] leading-[15px]"
              style={{ color: "var(--color-ink-faint)" }}
            >
              分析 ID：{target.analysisId}
            </div>
          )}
          {items.map((it) => (
            <button
              key={it.format}
              type="button"
              role="menuitem"
              onClick={() => void run(it.format)}
              disabled={busy !== null}
              className="block w-full px-3 py-1.5 text-left transition-colors hover:bg-white/[0.05] disabled:opacity-40"
              data-testid={`export-${it.format}`}
            >
              <span className="block text-[12.5px]" style={{ color: "var(--color-ink)" }}>
                {busy === it.format ? "导出中…" : it.label}
              </span>
              <span className="block text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
                {it.hint}
              </span>
            </button>
          ))}
        </div>
      ) : null}
      {msg ? (
        <div
          className="absolute right-0 z-40 mt-1 w-[252px] rounded-[6px] border px-2.5 py-1.5 text-[11px]"
          style={{
            borderColor: msg.tone === "ok" ? "rgba(79,211,155,0.45)" : "rgba(232,88,90,0.5)",
            color: msg.tone === "ok" ? "var(--color-down)" : "var(--color-up)",
            background: "var(--color-surface-2)",
          }}
          data-testid="export-feedback"
        >
          {msg.text}
        </div>
      ) : null}
    </div>
  );
}

/**
 * 自选星标 + 本机自选列表。
 *
 * 没有账户体系 → 只做**本机**自选（localStorage），文案明确写「本机」，
 * 不声称云端同步。支持加入 / 移除 / 去重 / 刷新恢复。
 */
function WatchStar({
  code,
  name,
  activeTab,
  suffix,
}: {
  code: string;
  name: string;
  activeTab?: string;
  suffix: string;
}) {
  const router = useRouter();
  const { items, watching, toggle, remove } = useWatchlist();
  const [open, setOpen] = useState(false);
  const watched = watching(code);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span className="relative flex items-center gap-1" ref={boxRef}>
      <button
        type="button"
        onClick={() => toggle(code, name)}
        title={watched ? "从本机自选中移除" : "加入本机自选（仅保存在本机浏览器）"}
        aria-pressed={watched}
        style={{ color: watched ? "var(--color-gold)" : "var(--color-ink-muted)" }}
        data-testid="watch-toggle"
      >
        <IconStar size={12} />
      </button>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-[10.5px]"
        style={{ color: "var(--color-ink-faint)" }}
        aria-expanded={open}
        data-testid="watchlist-toggle"
      >
        本机自选 {items.length}
      </button>
      {open ? (
        <div
          className="absolute left-0 top-full z-40 mt-1 w-[240px] overflow-hidden rounded-[8px] border"
          style={{
            borderColor: "var(--color-border-strong)",
            background: "linear-gradient(180deg, rgba(14,26,38,0.98), rgba(9,19,29,0.98))",
            boxShadow: "0 18px 40px rgba(0,0,0,0.6)",
          }}
          data-testid="watchlist-panel"
        >
          <div
            className="border-b px-2.5 py-1.5 text-[10.5px]"
            style={{ borderColor: "var(--color-border)", color: "var(--color-ink-faint)" }}
          >
            本机自选（浏览器本地保存，最多 {WATCHLIST_MAX} 只，不跨设备同步）
          </div>
          {items.length === 0 ? (
            <div className="px-2.5 py-2 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
              暂无自选。点击左侧星标加入当前标的。
            </div>
          ) : (
            <ul className="max-h-[240px] overflow-y-auto">
              {items.map((it) => (
                <li
                  key={it.code}
                  className="flex items-center gap-2 px-2.5 py-1.5 text-[12px]"
                  style={{ color: "var(--color-ink)" }}
                  data-testid={`watch-item-${it.code}`}
                >
                  <button
                    type="button"
                    className="min-w-0 flex-1 truncate text-left hover:opacity-80"
                    onClick={() => {
                      setOpen(false);
                      router.push(`/stock/${it.code}/${activeTab ?? "overview"}${suffix}`);
                    }}
                  >
                    {it.name ? `${it.name} · ` : ""}
                    {it.code}
                  </button>
                  <button
                    type="button"
                    onClick={() => remove(it.code)}
                    className="shrink-0 text-[11px]"
                    style={{ color: "var(--color-ink-muted)" }}
                    aria-label={`从自选移除 ${it.code}`}
                    data-testid={`watch-remove-${it.code}`}
                  >
                    移除
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </span>
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
