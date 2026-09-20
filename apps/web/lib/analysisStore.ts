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
    return multiAnalysisFixture;
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

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loadMultiAnalysis({ code, variant, asOf })
      .then((res) => {
        if (!cancelled && alive.current) setAnalysis(res);
      })
      .catch((err: unknown) => {
        if (!cancelled && alive.current) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled && alive.current) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [code, variant, asOf, tick]);

  const reload = useCallback(() => {
    invalidateAnalysis({ code, variant, asOf });
    setTick((t) => t + 1);
  }, [code, variant, asOf]);

  return { analysis, loading, error, reload };
}
