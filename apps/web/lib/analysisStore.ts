"use client";

/**
 * 分析结果的会话级缓存。
 *
 * 为什么需要它
 * ------------
 * Phase 2 的 `/analysis/multi` 会同时跑八字 + 黄历 + 紫微（紫微是 Node 子进程排盘），
 * 一次约 0.5–1.5 秒。而 Phase 2 有 7 个页面都需要同一份分析结果：
 * 如果每个页面各自 POST 一次，用户点 7 次页面就要算 7 次，既慢又浪费。
 *
 * 设计
 * ----
 * * 以 `code|variant|asOf` 为键在内存 + sessionStorage 中缓存；
 * * 显式 `reload()` 才重新计算（用户主动刷新时用）；
 * * **不做静默后台刷新** —— 研究系统的结论必须是"这一份"，而不是"大概这一份"。
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { api, endpoints, type ApiMultiAnalysis } from "./api";
import { isFixtureActive, multiAnalysisFixture } from "./fixture";
import { recordAnalysis } from "./historyStore";

const STORAGE_PREFIX = "smp-analysis:";
const memory = new Map<string, ApiMultiAnalysis>();

export type AnalysisVariant = "forward" | "reverse";

export interface AnalysisKey {
  code: string;
  variant: AnalysisVariant;
  asOf?: string;
}

function keyOf({ code, variant, asOf }: AnalysisKey): string {
  return `${code}|${variant}|${asOf ?? ""}`;
}

export async function loadMultiAnalysis(
  key: AnalysisKey,
  opts: { persist?: boolean; isFixture?: boolean } = {},
): Promise<ApiMultiAnalysis> {
  const isFix = opts.isFixture ?? isFixtureActive();
  if (isFix) {
    // 演示模式规则：仅 600519 提供完整离线视觉复刻；
    // 其他标的在演示模式下统一阻断真实分析与持久化，绝不静默发起网络请求
    if (key.code === "600519") {
      return multiAnalysisFixture;
    }
    throw new Error(
      `演示模式（UI 复刻）仅支持 600519（贵州茅台）。标的 ${key.code} 在演示模式下不可用；为保证数据隔离，系统已统一阻断对真实后端的排盘分析与持久化请求，请移除 URL 中的 fixture 参数以进入真实分析模式。`,
    );
  }

  const k = keyOf(key);
  const hit = memory.get(k);
  if (hit) return hit;

  if (typeof window !== "undefined") {
    try {
      const raw = window.sessionStorage.getItem(STORAGE_PREFIX + k);
      if (raw) {
        const parsed = JSON.parse(raw) as ApiMultiAnalysis;
        memory.set(k, parsed);
        return parsed;
      }
    } catch {
      // 解析失败就当缓存不存在，重新取
    }
  }

  const body = {
    as_of: key.asOf ?? null,
    variant_mode: key.variant,
    persist: opts.persist ?? true,
  };
  const res = await api.post<ApiMultiAnalysis>(endpoints.analyzeMulti(key.code), body);
  memory.set(k, res);
  recordAnalysis(res);
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.setItem(STORAGE_PREFIX + k, JSON.stringify(res));
    } catch {
      // 超出配额（紫微盘面较大）时只保留内存缓存，不影响功能
    }
  }
  return res;
}

export function invalidateAnalysis(key: AnalysisKey): void {
  const k = keyOf(key);
  memory.delete(k);
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.removeItem(STORAGE_PREFIX + k);
    } catch {
      /* ignore */
    }
  }
}

export interface UseAnalysisResult {
  analysis: ApiMultiAnalysis | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

/**
 * 分析数据 Hook。
 *
 * `variant` 默认 `forward`：Phase 2 的紫微需要显式方向，
 * 而"顺行"只是**两个假设之一**，UI 必须同时提供切换（见 ZiweiChart 组件）。
 */
export function useAnalysis(
  code: string,
  variant: AnalysisVariant = "forward",
  asOf?: string,
): UseAnalysisResult {
  const [analysis, setAnalysis] = useState<ApiMultiAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  const alive = useRef(true);
  /**
   * 当前"上下文令牌"。
   *
   * 为什么需要：切换股票/变体/as_of 时上一只股票的请求可能还没回来。
   * 如果只看 `cancelled`（渲染期闭包变量），在 effect 清理后**旧 Promise 仍会
   * 走到 `setAnalysis`**吗？—— 不会；但这里再加一层显式令牌，是因为
   * "上一条请求晚于新请求返回"正是会把 B 股票的页面填成 A 股票数据的场景，
   * 而这种错误在屏幕上看起来完全正常（分数、四柱都在，只是属于另一只股票）。
   * 令牌比较是这类竞态唯一可靠的判据。
   */
  const tokenRef = useRef(0);
  const contextKey = `${code}|${variant}|${asOf ?? ""}`;

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const token = ++tokenRef.current;
    setLoading(true);
    setError(null);
    // 标的变了 → 立刻清空上一只股票的结果，任何区块都不会短暂显示"别人的"数据。
    // 同一标的只换变体/基准日时保留旧值（盘面仍在），由 loading 覆盖层提示刷新，
    // 避免整页闪空；竞态本身由 token 比较兜住。
    setAnalysis((prev) => (prev && prev.stock?.stock_code === code ? prev : null));
    loadMultiAnalysis({ code, variant, asOf })
      .then((res) => {
        if (cancelled) return;
        if (!alive.current) return;
        if (token !== tokenRef.current) return; // 已被更新的上下文取代，丢弃
        // 双保险：响应自带的标的必须与当前上下文一致
        if (res.stock?.stock_code && res.stock.stock_code !== code) return;
        setAnalysis(res);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if (!alive.current) return;
        if (token !== tokenRef.current) return;
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (cancelled) return;
        if (!alive.current) return;
        if (token !== tokenRef.current) return;
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [contextKey, code, variant, asOf, tick]);

  const reload = useCallback(() => {
    invalidateAnalysis({ code, variant, asOf });
    setTick((t) => t + 1);
  }, [code, variant, asOf]);

  return { analysis, loading, error, reload };
}
