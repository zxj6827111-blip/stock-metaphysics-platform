/**
 * 会话级分析历史存储器。
 *
 * 契约与规则：
 * - 正常模式下，当一次分析成功完成时记录到当前会话（sessionStorage）；
 * - 最多保留 3 条记录，最新记录排在最前（按代码去重）；
 * - 纯会话持久化，页面刷新后仍存在，新标签页或关闭浏览器后重置；
 * - 提供明确的空态与只读查询接口。
 */

import type { ApiMultiAnalysis } from "./api";
import { KNOWN_STOCK_NAMES } from "@/components/stock/StockSwitchModal";

export interface RecentAnalysisItem {
  code: string;
  name: string;
  analyzedAt: string;
  price: string;
  changePct: string;
  trend: "up" | "down" | "flat";
  engines: { key: string; label: string; direction: number }[];
  status: string;
  statusTone: "up" | "down" | "flat" | "conflict";
}

const STORAGE_KEY = "smp_recent_analyses_session";
const MAX_RECENT_ITEMS = 3;

export function getRecentAnalyses(): RecentAnalysisItem[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.slice(0, MAX_RECENT_ITEMS);
    }
  } catch {
    // 忽略解析异常
  }
  return [];
}

export function recordAnalysis(analysis: ApiMultiAnalysis): void {
  if (typeof window === "undefined" || !analysis?.stock?.stock_code) return;
  try {
    const code = analysis.stock.stock_code;
    const name =
      analysis.stock.name ||
      KNOWN_STOCK_NAMES[code]?.name ||
      "A股标的";

    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, "0");
    const analyzedAt = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;

    // 提取三模型方向
    const baziDir = analysis.opinions?.bazi?.direction ?? 0;
    const ziweiDir = analysis.opinions?.ziwei?.direction ?? 0;
    const huangliDir = analysis.opinions?.huangli?.direction ?? 0;

    const hasConflict = analysis.conflict?.has_conflict ?? false;
    let status = analysis.consensus?.label_cn || "分析完成";
    let statusTone: "up" | "down" | "flat" | "conflict" = "flat";
    let trend: "up" | "down" | "flat" = "flat";

    if (hasConflict) {
      statusTone = "conflict";
      status = "模型分歧";
    } else if (baziDir > 0 || ziweiDir > 0 || huangliDir > 0) {
      statusTone = "up";
      trend = "up";
    } else if (baziDir < 0 || ziweiDir < 0 || huangliDir < 0) {
      statusTone = "down";
      trend = "down";
    }

    const newItem: RecentAnalysisItem = {
      code,
      name,
      analyzedAt,
      price: "—",
      changePct: "—",
      trend,
      engines: [
        { key: "bazi", label: "八字", direction: baziDir },
        { key: "ziwei", label: "紫微", direction: ziweiDir },
        { key: "huangli", label: "黄历", direction: huangliDir },
      ],
      status,
      statusTone,
    };

    const existing = getRecentAnalyses();
    // 过滤掉当前股票旧记录，将新记录置顶，保留至多 3 条
    const updated = [newItem, ...existing.filter((item) => item.code !== code)].slice(
      0,
      MAX_RECENT_ITEMS,
    );
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
  } catch {
    // 忽略 sessionStorage 超限异常
  }
}

export function clearRecentAnalyses(): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
}
