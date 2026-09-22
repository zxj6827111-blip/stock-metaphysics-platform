"use client";

/**
 * StockSwitchModal —— 标的股票快速切换弹窗。
 *
 * 供 StockContextBar 的「切换股票」按钮调用：
 * - 自动聚焦搜索框；
 * - 提供热门与常见股票快捷标签；
 * - 支持按 6 位代码或中文关键词实时搜索；
 * - 切换时保持当前所在的功能子页面（如从 /stock/600519/huangli 切换到 /stock/002008/huangli）；
 * - 切换至非 600519 标的时自动解除 fixture 锁定，走真实后端排盘与分析。
 */

import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { IconClose, IconSearch, IconTaiji, IconCheck } from "../shell/Icons";
import { api, endpoints, type ApiStockSearchResponse } from "@/lib/api";
import { FIXTURE_QUERY_VALUE } from "@/lib/fixture";
import { getRecentStocks, recordRecentStock } from "@/lib/recentStockStore";

import {
  type StockSuggestion,
  POPULAR_STOCKS,
  KNOWN_STOCK_NAMES,
} from "@/lib/stockCatalog";

export { type StockSuggestion, POPULAR_STOCKS, KNOWN_STOCK_NAMES };

export function StockSwitchModal({
  isOpen,
  onClose,
  currentCode,
}: {
  isOpen: boolean;
  onClose: () => void;
  currentCode: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const isFixture = searchParams?.get("fixture") === FIXTURE_QUERY_VALUE;

  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const [recent, setRecent] = useState<StockSuggestion[]>([]);
  const [results, setResults] = useState<StockSuggestion[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // 从当前路径提取子页面标识（如 overview / bazi / huangli）
  const currentSubpage = useMemo(() => {
    if (!pathname) return "overview";
    const parts = pathname.split("/").filter(Boolean);
    // path 格式通常是 stock / [code] / [subpage]
    if (parts.length >= 3 && parts[0] === "stock") {
      return parts[2];
    }
    return "overview";
  }, [pathname]);

  // 打开时自动聚焦并清空输入
  useEffect(() => {
    if (isOpen) {
      setValue("");
      const recentItems = getRecentStocks().map((item) => ({
        code: item.code,
        name: item.name,
        exchange: item.exchange,
        listingDate: item.listingDate,
      }));
      setRecent(recentItems);
      setResults(isFixture ? POPULAR_STOCKS : recentItems);
      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    }
  }, [isOpen, isFixture]);

  // 监听 ESC 键关闭
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  // 实时搜索逻辑
  const doSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) {
      setResults(isFixture ? POPULAR_STOCKS : recent);
      return;
    }

    const lowered = trimmed.toLowerCase();
    const localHits = (isFixture ? POPULAR_STOCKS : recent).filter(
      (s) => s.code.includes(lowered) || s.name.toLowerCase().includes(lowered),
    );

    // 如果处于 fixture 模式，完全基于本地清单，禁止向后端发起网络请求
    if (isFixture) {
      if (localHits.length > 0) {
        setResults(localHits);
      } else if (/^\d{6}$/.test(trimmed)) {
        const known = KNOWN_STOCK_NAMES[trimmed];
        setResults([
          {
            code: trimmed,
            name: known?.name || "A股标的",
            exchange: trimmed.startsWith("6") || trimmed.startsWith("9") ? "SSE" : "SZSE",
            listingDate: known?.listingDate || "",
          },
        ]);
      } else {
        setResults([]);
      }
      return;
    }

    // 如果匹配到本地常用标的，直接展示
    if (localHits.length > 0) {
      setResults(localHits);
      return;
    }

    // 若本地未命中，发起后端实时检索
    setLoading(true);
    try {
      const res = await api.get<ApiStockSearchResponse>(endpoints.search(trimmed));
      const mapped = res.items.map((i) => {
        const enrichedName = i.name || KNOWN_STOCK_NAMES[i.stock_code]?.name || "";
        const enrichedListing = i.listing_date || KNOWN_STOCK_NAMES[i.stock_code]?.listingDate || "";
        return {
          code: i.stock_code,
          name: enrichedName,
          exchange: i.exchange,
          listingDate: enrichedListing,
        };
      });
      if (mapped.length > 0) {
        setResults(mapped);
      } else if (/^\d{6}$/.test(trimmed)) {
        // 如果是 6 位数字代码但后端未搜索到名称，构建最小对象
        const known = KNOWN_STOCK_NAMES[trimmed];
        const exchange = trimmed.startsWith("6") || trimmed.startsWith("9") ? "SSE" : "SZSE";
        setResults([
          {
            code: trimmed,
            name: known?.name || "A股标的",
            exchange,
            listingDate: known?.listingDate || "",
          },
        ]);
      } else {
        setResults([]);
      }
    } catch {
      if (/^\d{6}$/.test(trimmed)) {
        const known = KNOWN_STOCK_NAMES[trimmed];
        const exchange = trimmed.startsWith("6") || trimmed.startsWith("9") ? "SSE" : "SZSE";
        setResults([
          {
            code: trimmed,
            name: known?.name || "A股标的",
            exchange,
            listingDate: known?.listingDate || "",
          },
        ]);
      } else {
        setResults([]);
      }
    } finally {
      setLoading(false);
    }
  }, [isFixture, recent]);

  useEffect(() => {
    const t = setTimeout(() => void doSearch(value), 180);
    return () => clearTimeout(t);
  }, [value, doSearch]);

  // 标的切换执行
  const handleSelect = (targetCode: string) => {
    if (!targetCode) return;
    const selected = results.find((item) => item.code === targetCode) ?? recent.find((item) => item.code === targetCode);
    if (!isFixture) {
      const updated = recordRecentStock({
        code: targetCode,
        name: selected?.name || KNOWN_STOCK_NAMES[targetCode]?.name || "A股标的",
        exchange: selected?.exchange || (targetCode.startsWith("6") || targetCode.startsWith("9") ? "SSE" : "SZSE"),
        listingDate: selected?.listingDate || KNOWN_STOCK_NAMES[targetCode]?.listingDate || "",
      });
      setRecent(updated.map((item) => ({ code: item.code, name: item.name, exchange: item.exchange, listingDate: item.listingDate })));
    }
    onClose();
    const keepFixture = isFixture && targetCode === "600519";
    const suffix = keepFixture ? `?fixture=${FIXTURE_QUERY_VALUE}` : "";
    router.push(`/stock/${targetCode}/${currentSubpage}${suffix}`);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;

    // 优先匹配首个搜索结果
    if (results.length > 0) {
      handleSelect(results[0].code);
      return;
    }

    // 若直接输入 6 位数字代码
    if (/^\d{6}$/.test(trimmed)) {
      handleSelect(trimmed);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: "rgba(3,8,13,0.72)" }}
      onClick={onClose}
      data-testid="stock-switch-modal-overlay"
    >
      <div
        className="w-full max-w-[560px] overflow-hidden rounded-[12px] border"
        style={{
          borderColor: "var(--color-border-strong)",
          background: "linear-gradient(180deg, rgba(14,26,38,0.98), rgba(9,19,29,0.98))",
          boxShadow: "0 24px 60px rgba(0,0,0,0.65)",
        }}
        onClick={(e) => e.stopPropagation()}
        data-testid="stock-switch-modal"
      >
        {/* 头部 */}
        <div
          className="flex items-center justify-between border-b px-5 py-3.5"
          style={{ borderColor: "var(--color-border)" }}
        >
          <div className="flex items-center gap-2">
            <span style={{ color: "var(--color-gold)" }}>
              <IconTaiji size={17} />
            </span>
            <span className="text-[15px] font-semibold" style={{ color: "var(--color-ink)" }}>
              切换分析标的
            </span>
            <span className="text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
              （当前：{currentCode}）
            </span>
          </div>
          <button
            type="button"
            className="flex h-7 w-7 items-center justify-center rounded-[4px] transition-colors hover:bg-white/[0.06]"
            style={{ color: "var(--color-ink-muted)" }}
            onClick={onClose}
            aria-label="关闭"
            data-testid="stock-switch-close"
          >
            <IconClose size={15} />
          </button>
        </div>

        {/* 输入框区 */}
        <div className="p-5">
          <form onSubmit={handleSubmit}>
            <div
              className="flex h-[46px] items-center gap-2.5 rounded-[8px] border px-3"
              style={{
                borderColor: "var(--color-gold-dim)",
                background: "rgba(6,14,21,0.85)",
              }}
            >
              <IconSearch size={16} style={{ color: "var(--color-gold)" }} />
              <input
                ref={inputRef}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="输入股票代码（如 002008）或名称 / 拼音…"
                className="min-w-0 flex-1 bg-transparent text-[14px] outline-none"
                style={{ color: "var(--color-ink)" }}
                data-testid="stock-switch-input"
              />
              {value ? (
                <button
                  type="button"
                  onClick={() => setValue("")}
                  style={{ color: "var(--color-ink-muted)" }}
                  aria-label="清空"
                >
                  <IconClose size={13} />
                </button>
              ) : null}
              <button
                type="submit"
                className="smp-btn smp-btn--primary h-[32px] px-3.5 text-[12.5px]"
                data-testid="stock-switch-submit"
              >
                切换
              </button>
            </div>
          </form>

          {/* fixture 展示冻结快捷样本；真实模式只显示真实的近期使用记录 */}
          <div className="mt-3.5">
            <div className="mb-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              {isFixture ? "演示样本快捷切换：" : "最近使用："}
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(isFixture ? POPULAR_STOCKS : recent).map((s) => {
                const isActive = s.code === currentCode;
                return (
                  <button
                    key={s.code}
                    type="button"
                    onClick={() => handleSelect(s.code)}
                    className="flex items-center gap-1.5 rounded-[5px] border px-2.5 py-1 text-[12px] transition-colors hover:border-gold hover:bg-white/[0.04]"
                    style={{
                      borderColor: isActive ? "var(--color-gold)" : "var(--color-border)",
                      background: isActive ? "var(--color-gold-ghost)" : "rgba(255,255,255,0.02)",
                      color: isActive ? "var(--color-gold)" : "var(--color-ink-sub)",
                    }}
                    data-testid={`quick-switch-${s.code}`}
                  >
                    <span className="smp-num font-medium">{s.code}</span>
                    <span>{s.name}</span>
                    {isActive ? <IconCheck size={11} /> : null}
                  </button>
                );
              })}
            </div>
          </div>

          {/* 搜索结果列表 */}
          <div className="mt-4 border-t pt-3" style={{ borderColor: "var(--color-border)" }}>
            <div className="mb-2 flex items-center justify-between text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              <span>搜索候选</span>
              {loading ? <span>检索中…</span> : <span>{results.length} 个结果</span>}
            </div>

            <div className="smp-scroll max-h-[220px] space-y-1 overflow-y-auto">
              {results.length > 0 ? (
                results.map((item) => {
                  const isCur = item.code === currentCode;
                  return (
                    <button
                      key={item.code}
                      type="button"
                      onClick={() => handleSelect(item.code)}
                      className="flex w-full items-center justify-between rounded-[6px] px-3 py-2 text-left transition-colors hover:bg-white/[0.05]"
                      style={{
                        background: isCur ? "rgba(212,184,122,0.06)" : "transparent",
                      }}
                      data-testid={`stock-switch-item-${item.code}`}
                    >
                      <div className="flex items-center gap-2.5">
                        <span className="smp-num text-[13px] font-semibold" style={{ color: "var(--color-gold)" }}>
                          {item.code}
                        </span>
                        <span className="text-[13px] font-medium" style={{ color: "var(--color-ink)" }}>
                          {item.name || "—"}
                        </span>
                        {isCur ? (
                          <span
                            className="rounded-[3px] border px-1 text-[10.5px]"
                            style={{ borderColor: "var(--color-gold-dim)", color: "var(--color-gold)" }}
                          >
                            当前标的
                          </span>
                        ) : null}
                      </div>
                      <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                        {item.exchange} {item.listingDate ? `· 上市 ${item.listingDate}` : ""}
                      </div>
                    </button>
                  );
                })
              ) : (
                <div className="py-6 text-center text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
                  {value.trim() ? "未检索到匹配的股票，按回车可用代码发起分析" : "暂无近期搜索股票"}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 底部按钮 */}
        <div
          className="flex items-center justify-end gap-2 border-t px-5 py-3"
          style={{ borderColor: "var(--color-border)", background: "rgba(6,14,21,0.4)" }}
        >
          <button
            type="button"
            className="smp-btn px-4"
            onClick={onClose}
          >
            取消
          </button>
        </div>
      </div>
    </div>
  );
}
