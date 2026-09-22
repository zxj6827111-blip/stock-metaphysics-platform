"use client";

export interface RecentStock {
  code: string;
  name: string;
  exchange: string;
  listingDate: string;
  lastUsedAt: string;
}

const STORAGE_KEY = "smp_recent_stocks";
const MAX_RECENT = 8;

function isRecentStock(value: unknown): value is RecentStock {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<RecentStock>;
  return (
    typeof item.code === "string" &&
    typeof item.name === "string" &&
    typeof item.exchange === "string" &&
    typeof item.listingDate === "string" &&
    typeof item.lastUsedAt === "string"
  );
}

export function getRecentStocks(): RecentStock[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isRecentStock).slice(0, MAX_RECENT);
  } catch {
    return [];
  }
}

export function recordRecentStock(stock: Omit<RecentStock, "lastUsedAt">): RecentStock[] {
  if (typeof window === "undefined" || !stock.code) return [];
  const next: RecentStock = { ...stock, lastUsedAt: new Date().toISOString() };
  const items = [next, ...getRecentStocks().filter((item) => item.code !== stock.code)].slice(0, MAX_RECENT);
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
  } catch {
    // 本机存储不可用时不阻断搜索与分析。
  }
  return items;
}

export function clearRecentStocks(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
