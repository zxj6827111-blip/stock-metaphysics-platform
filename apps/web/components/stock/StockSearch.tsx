"use client";

/**
 * StockSearch —— 全局股票搜索（TopBar 内的窄条 / 首页的大输入框）。
 *
 * 真实模式走 API `GET /api/v1/stocks/search`；
 * fixture 模式使用内置演示列表，保证截图可复现。
 */

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { endpoints, api, type ApiStockSearchResponse } from "@/lib/api";
import { FIXTURE_QUERY_VALUE } from "@/lib/fixture";
import { IconArrowRight, IconClose, IconSearch } from "../shell/Icons";

import { KNOWN_STOCK_NAMES } from "@/lib/stockCatalog";

interface Suggestion {
  code: string;
  name: string;
  exchange: string;
  listingDate: string;
}

const DEMO_SUGGESTIONS: Suggestion[] = [
  { code: "600519", name: "贵州茅台", exchange: "SSE", listingDate: "2001-08-27" },
  { code: "000001", name: "平安银行", exchange: "SZSE", listingDate: "1991-04-03" },
  { code: "002008", name: "大族激光", exchange: "SZSE", listingDate: "2004-06-25" },
  { code: "300750", name: "宁德时代", exchange: "SZSE", listingDate: "2018-06-11" },
  { code: "002594", name: "比亚迪", exchange: "SZSE", listingDate: "2011-06-30" },
  { code: "600036", name: "招商银行", exchange: "SSE", listingDate: "2002-04-09" },
  { code: "000858", name: "五粮液", exchange: "SZSE", listingDate: "1998-04-27" },
  { code: "601318", name: "中国平安", exchange: "SSE", listingDate: "2007-03-01" },
  { code: "688981", name: "中芯国际", exchange: "SSE", listingDate: "2020-07-16" },
];

export function StockSearch({
  variant = "bar",
  defaultValue = "",
}: {
  variant?: "bar" | "hero";
  defaultValue?: string;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const fixture = params.get("fixture") === FIXTURE_QUERY_VALUE;

  const [value, setValue] = useState(defaultValue);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<Suggestion[]>(DEMO_SUGGESTIONS);
  const [degraded, setDegraded] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const doSearch = useCallback(
    async (q: string) => {
      const trimmed = q.trim();
      if (!trimmed) {
        setItems(DEMO_SUGGESTIONS);
        return;
      }

      const t = trimmed.toLowerCase();
      const localHits = DEMO_SUGGESTIONS.filter(
        (s) => s.code.includes(t) || s.name.includes(t),
      );

      // 如果处于 fixture 模式，完全基于本地清单，禁止向后端发起网络请求
      if (fixture) {
        if (localHits.length > 0) {
          setItems(localHits);
        } else if (/^\d{6}$/.test(trimmed)) {
          const known = KNOWN_STOCK_NAMES[trimmed];
          setItems([
            {
              code: trimmed,
              name: known?.name || "A股标的",
              exchange: trimmed.startsWith("6") || trimmed.startsWith("9") ? "SSE" : "SZSE",
              listingDate: known?.listingDate || "",
            },
          ]);
        } else {
          setItems([]);
        }
        return;
      }

      // 未命中本地或处于真实模式时，发起后端实时查询
      setLoading(true);
      try {
        const res = await api.get<ApiStockSearchResponse>(endpoints.search(trimmed));
        const mapped = res.items.map((i) => ({
          code: i.stock_code,
          name: i.name || KNOWN_STOCK_NAMES[i.stock_code]?.name || "",
          exchange: i.exchange,
          listingDate: i.listing_date || KNOWN_STOCK_NAMES[i.stock_code]?.listingDate || "",
        }));

        if (mapped.length > 0) {
          setItems(mapped);
        } else if (localHits.length > 0) {
          setItems(localHits);
        } else if (/^\d{6}$/.test(trimmed)) {
          const known = KNOWN_STOCK_NAMES[trimmed];
          setItems([
            {
              code: trimmed,
              name: known?.name || "A股标的",
              exchange: trimmed.startsWith("6") || trimmed.startsWith("9") ? "SSE" : "SZSE",
              listingDate: known?.listingDate || "",
            },
          ]);
        } else {
          setItems([]);
        }

        setDegraded(
          res.is_degraded
            ? "当前运行在离线合成数据模式，股票资料来自内置清单。"
            : null,
        );
      } catch {
        if (localHits.length > 0) {
          setItems(localHits);
        } else if (/^\d{6}$/.test(trimmed)) {
          const known = KNOWN_STOCK_NAMES[trimmed];
          setItems([
            {
              code: trimmed,
              name: known?.name || "A股标的",
              exchange: trimmed.startsWith("6") || trimmed.startsWith("9") ? "SSE" : "SZSE",
              listingDate: known?.listingDate || "",
            },
          ]);
        } else {
          setItems(DEMO_SUGGESTIONS);
        }
        setDegraded("后端服务不可用，已回退到内置演示清单。");
      } finally {
        setLoading(false);
      }
    },
    [fixture],
  );

  useEffect(() => {
    const id = setTimeout(() => void doSearch(value), 220);
    return () => clearTimeout(id);
  }, [value, doSearch]);

  const go = (code: string) => {
    // 关键设计：仅当目标是 600519 且当前是 fixture 模式时才保留 fixture，
    // 任何其他股票（如 002008）坚决去掉 fixture，让页面直接调用真实 API 计算！
    const keepFixture = fixture && code === "600519";
    const suffix = keepFixture ? `?fixture=${FIXTURE_QUERY_VALUE}` : "";
    router.push(`/stock/${code}/overview${suffix}`);
  };

  const submit = () => {
    const t = value.trim();
    if (!t) return;
    const hit = items.find((i) => i.code === t || i.name === t) ?? items[0];
    const code = /^\d{6}$/.test(t) ? t : (hit?.code ?? "");
    if (code) go(code);
    setOpen(false);
  };

  const isHero = variant === "hero";
  const shown = useMemo(() => items.slice(0, 8), [items]);

  return (
    <div ref={boxRef} className="relative w-full">
      <div
        className={`flex items-center gap-2 rounded-[8px] border px-3 ${
          isHero ? "h-[52px]" : "h-[38px]"
        }`}
        style={{
          borderColor: open ? "var(--color-gold-dim)" : "var(--color-border-strong)",
          background: "rgba(6,14,21,0.72)",
        }}
      >
        <IconSearch size={isHero ? 17 : 15} style={{ color: "var(--color-ink-muted)" }} />
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
            if (e.key === "Escape") setOpen(false);
          }}
          placeholder="搜索股票代码 / 名称 / 关键词…"
          className={`min-w-0 flex-1 bg-transparent outline-none ${
            isHero ? "text-[14px]" : "text-[12.5px]"
          }`}
          style={{ color: "var(--color-ink)" }}
          aria-label="股票搜索"
          data-testid="stock-search-input"
        />
        {value ? (
          <button
            type="button"
            onClick={() => setValue("")}
            style={{ color: "var(--color-ink-muted)" }}
            aria-label="清空"
          >
            <IconClose size={14} />
          </button>
        ) : null}
        {isHero ? (
          <button
            type="button"
            className="smp-btn smp-btn--primary h-[38px] px-5"
            onClick={submit}
            data-testid="stock-search-submit"
          >
            开始分析
            <IconArrowRight size={15} />
          </button>
        ) : null}
      </div>

      {open && shown.length > 0 ? (
        <div
          className="smp-scroll absolute left-0 right-0 top-[calc(100%+6px)] z-40 max-h-[286px] overflow-y-auto rounded-[8px] border py-1"
          style={{
            borderColor: "var(--color-border-strong)",
            background: "rgba(9,20,30,0.98)",
            boxShadow: "0 18px 40px rgba(0,0,0,0.55)",
          }}
          data-testid="stock-search-suggestions"
        >
          {loading ? (
            <div className="px-3 py-2 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
              查询中…
            </div>
          ) : null}
          {shown.map((s) => (
            <button
              key={s.code}
              type="button"
              onClick={() => go(s.code)}
              className="flex w-full items-center justify-between px-3 py-[7px] text-left transition-colors hover:bg-white/[0.04]"
            >
              <span className="flex items-center gap-2">
                <span className="smp-num text-[12.5px]" style={{ color: "var(--color-gold)" }}>
                  {s.code}
                </span>
                <span className="text-[12.5px]" style={{ color: "var(--color-ink)" }}>
                  {s.name || "—"}
                </span>
              </span>
              <span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
                {s.exchange} · {s.listingDate || "上市日期未知"}
              </span>
            </button>
          ))}
          {degraded ? (
            <div
              className="mt-1 border-t px-3 py-1.5 text-[11px]"
              style={{ borderColor: "var(--color-border)", color: "var(--color-warn)" }}
            >
              {degraded}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
