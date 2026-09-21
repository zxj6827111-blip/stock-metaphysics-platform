"use client";

/**
 * 本机自选（Watchlist）。
 *
 * 存储位置的取舍
 * --------------
 * 本项目**没有账户体系**（AGENTS.md 未定义用户模型，也没有登录态），因此自选
 * 只能存在本机。放在 `localStorage` 而不是 `sessionStorage`，是因为"刷新后还在"
 * 是自选的基本预期；而分析结果缓存用 `sessionStorage` 是另一回事（那一份结果
 * 属于当前研究会话）。
 *
 * **不冒充云端同步**：UI 文案一律写「本机自选」，不写"已同步""云端"。
 *
 * 边界
 * ----
 * * 只存最小字段（代码 / 名称 / 加入时间），不存分析结果 —— 结果过期会让用户
 *   看到与当前基准日不匹配的旧分数；
 * * 读写都做异常兜底：隐私模式或配额超限时退化为内存态，不抛给调用方。
 */

import { useCallback, useEffect, useState } from "react";

import { KNOWN_STOCK_NAMES } from "./stockCatalog";

const STORAGE_KEY = "smp_watchlist_local_v1";
/** 上限：自选是"常看的几只"，不是第二个全市场列表。 */
export const WATCHLIST_MAX = 50;

export interface WatchItem {
  code: string;
  name: string;
  addedAt: string;
}

const memory = new Map<string, string>(); // 兜底：localStorage 不可用时用内存

function readRaw(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return memory.get(STORAGE_KEY) ?? null;
  }
}

function writeRaw(value: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, value);
  } catch {
    memory.set(STORAGE_KEY, value);
  }
}

function normalize(items: unknown): WatchItem[] {
  if (!Array.isArray(items)) return [];
  const seen = new Set<string>();
  const out: WatchItem[] = [];
  for (const raw of items) {
    const it = raw as Partial<WatchItem> | null;
    const code = typeof it?.code === "string" ? it.code.trim() : "";
    if (!code || seen.has(code)) continue; // 去重：同一代码只保留首次出现
    seen.add(code);
    out.push({
      code,
      name: typeof it?.name === "string" && it.name ? it.name : (KNOWN_STOCK_NAMES[code]?.name ?? ""),
      addedAt: typeof it?.addedAt === "string" ? it.addedAt : "",
    });
  }
  return out;
}

export function getWatchlist(): WatchItem[] {
  const raw = readRaw();
  if (!raw) return [];
  try {
    return normalize(JSON.parse(raw));
  } catch {
    // 解析失败（旧格式/被手工改坏）→ 当成空表，不用脏数据覆盖 UI
    return [];
  }
}

function persist(items: WatchItem[]): void {
  writeRaw(JSON.stringify(items.slice(0, WATCHLIST_MAX)));
}

export function isWatched(code: string): boolean {
  return getWatchlist().some((i) => i.code === code);
}

export function addToWatchlist(code: string, name = ""): WatchItem[] {
  const items = getWatchlist();
  if (items.some((i) => i.code === code)) return items; // 幂等：重复加入不产生第二条
  const next = [
    ...items,
    {
      code,
      name: name || KNOWN_STOCK_NAMES[code]?.name || "",
      addedAt: new Date().toISOString(),
    },
  ].slice(-WATCHLIST_MAX);
  persist(next);
  return next;
}

export function removeFromWatchlist(code: string): WatchItem[] {
  const next = getWatchlist().filter((i) => i.code !== code);
  persist(next);
  return next;
}

export function toggleWatchlist(code: string, name = ""): WatchItem[] {
  return isWatched(code) ? removeFromWatchlist(code) : addToWatchlist(code, name);
}

/** 订阅本机自选（跨标签页用 storage 事件，同页用自定义事件）。 */
export function useWatchlist() {
  const [items, setItems] = useState<WatchItem[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    // 首帧之后再读 localStorage：保证服务端渲染与客户端首帧一致（无 hydration 差异）
    setItems(getWatchlist());
    setReady(true);
    const sync = () => setItems(getWatchlist());
    window.addEventListener("storage", sync);
    window.addEventListener("smp-watchlist-changed", sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener("smp-watchlist-changed", sync);
    };
  }, []);

  const notify = useCallback((next: WatchItem[]) => {
    setItems(next);
    try {
      window.dispatchEvent(new Event("smp-watchlist-changed"));
    } catch {
      /* ignore */
    }
  }, []);

  const toggle = useCallback(
    (code: string, name = "") => notify(toggleWatchlist(code, name)),
    [notify],
  );
  const remove = useCallback((code: string) => notify(removeFromWatchlist(code)), [notify]);

  return {
    items,
    ready,
    watching: (code: string) => items.some((i) => i.code === code),
    toggle,
    remove,
  };
}
