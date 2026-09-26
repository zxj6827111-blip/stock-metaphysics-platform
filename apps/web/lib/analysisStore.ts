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

/**: 默认出生模型 —— 与后端 `BirthBasis.LISTING_OPEN` 一致（研究约定，非事实）。 */
export const DEFAULT_BIRTH_BASIS: AnalysisBirthBasis = "listing_open";

/** 可选研究窗口标签（与后端 `BaziAnalysisRequest.horizon` 的默认值一致）。 */
export const HORIZON_OPTIONS = ["20d", "60d"] as const;
export const DEFAULT_HORIZON = "20d";

export type AnalysisVariant = "forward" | "reverse";

/**
 * 出生模型（研究假设）。
 *
 * 与后端 `BirthBasis` 枚举一一对应。**不是所有取值都能算**：
 * `company_foundation` / `first_trade` 缺少数据源，后端按契约返回
 * `422 BIRTH_PROFILE_ERROR`（不猜测），前端据此把它们标为不可用并给出原因。
 */
export type AnalysisBirthBasis =
  | "listing_open"
  | "ipo_date"
  | "company_foundation"
  | "first_trade";

/**: 可实际计算的出生模型（其余会在切换器里显示为"不可用 + 原因"）。 */
export const SUPPORTED_BIRTH_BASES: AnalysisBirthBasis[] = ["listing_open", "ipo_date"];

export interface AnalysisKey {
  code: string;
  variant: AnalysisVariant;
  asOf?: string;
  /**
   * 出生模型。
   *
   * **必须进缓存键**：不同基准给出不同的出生时刻 → 不同的四柱与紫微盘面
   * （实测 600519：listing_open 09:30 与 ipo_date 00:00 的八字日主/紫微星曜都不同）。
   * 少了它就会把「假设 A 的盘」当「假设 B 的盘」返回。
   */
  birthBasis?: AnalysisBirthBasis;
  /**
   * 研究窗口标签（如 ``20d``）。
   *
   * 后端会把它登记进 `analysis_run.horizon` 并在响应里回传，但**不参与因子计算**
   * （三个模型的分数与它无关，事件研究用自己的持有期集合）。仍进缓存键，
   * 因为登记值属于"这一份分析的身份"：同一标的不同登记窗口是两次不同的分析记录。
   */
  horizon?: string;
}

function keyOf({ code, variant, asOf, birthBasis, horizon }: AnalysisKey): string {
  return `${code}|${variant}|${asOf ?? ""}|${birthBasis ?? ""}|${horizon ?? ""}`;
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
      const basis = key.birthBasis ?? DEFAULT_BIRTH_BASIS;
      if (basis !== DEFAULT_BIRTH_BASIS) {
        // 夹具是**冻结在默认出生模型上的**一份样本。用别的假设请求时返回它，
        // 等于把「假设 A 的盘」标成「假设 B 的盘」—— 这比报错糟得多。
        throw new Error(
          `演示模式（UI 复刻）的样本冻结在默认出生模型「上市首日正式开盘」上，` +
            `无法提供「${basis}」假设下的结果。请移除 URL 中的 fixture 参数以进入真实分析模式，` +
            `届时切换出生模型会真实重新分析（出生时刻不同 → 四柱与紫微盘面不同）。`,
        );
      }
      return {
        ...multiAnalysisFixture,
        // `horizon` 是**登记标签**，不参与任何计算（见 lib/useHorizonParam 的语义边界）：
        // 同一份冻结盘面在不同登记窗口下就是同一份盘面，所以这里如实回显请求的窗口，
        // 让"页面显示 / 请求上下文 / 导出快照"三处指向同一个值。
        // 出生模型不一样 —— 那会真的换一张盘，因此上面按不支持直接拒绝。
        horizon: key.horizon ?? DEFAULT_HORIZON,
      };
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
    birth_basis: key.birthBasis ?? DEFAULT_BIRTH_BASIS,
    horizon: key.horizon ?? DEFAULT_HORIZON,
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
  /**
   * 出生模型（研究假设）。默认 `listing_open`。
   *
   * 它必须进请求体与缓存键：不同基准给出不同出生时刻，四柱与紫微盘面随之改变
   * （实测 600519：`listing_open` 09:30 与 `ipo_date` 00:00 的八字与紫微结果不同）。
   */
  birthBasis: AnalysisBirthBasis = DEFAULT_BIRTH_BASIS,
  horizon: string = DEFAULT_HORIZON,
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
  const contextKey = `${code}|${variant}|${asOf ?? ""}|${birthBasis}|${horizon}`;

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
    loadMultiAnalysis({ code, variant, asOf, birthBasis, horizon })
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
  }, [contextKey, code, variant, asOf, birthBasis, horizon, tick]);

  const reload = useCallback(() => {
    invalidateAnalysis({ code, variant, asOf, birthBasis, horizon });
    setTick((t) => t + 1);
  }, [code, variant, asOf, birthBasis, horizon]);

  return { analysis, loading, error, reload };
}
