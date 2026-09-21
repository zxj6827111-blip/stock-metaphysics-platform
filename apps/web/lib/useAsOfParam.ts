"use client";

/**
 * 从 URL 读研究参数（`asOf`）。
 *
 * 为什么需要它
 * ------------
 * 分析基准日默认取"服务器当前时间"。但研究终端必须能**指定基准日**：
 *
 * * 复核一份结论时要能回到当时的时点，否则同一只股票每天看到的分数都不同；
 * * 交易日历等数据源有覆盖边界，基准日落在边界之外时页面只能给空态 ——
 *   能被显式指定，用户才知道"换个基准日就能看到结果"；
 * * 端到端验收需要一个**确定的**基准日，才能把页面输出与后端结果对齐。
 *
 * 实现纪律：查询参数一律经 `useSearchParams()` 读取（服务端与客户端同源），
 * 不使用 `window.location`，避免 SSR/CSR 分支不一致导致的 hydration 差异。
 */

import { useSearchParams } from "next/navigation";

/** `YYYY-MM-DD` 或 `YYYY-MM-DDTHH:mm[:ss]`；非法值一律忽略（不猜测、不静默取今天）。 */
export function normalizeAsOf(raw: string | null | undefined): string | undefined {
  if (!raw) return undefined;
  const value = raw.trim();
  const ok = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$/.test(value);
  return ok ? value : undefined;
}

export function useAsOfParam(): string | undefined {
  const params = useSearchParams();
  return normalizeAsOf(params?.get("asOf"));
}
