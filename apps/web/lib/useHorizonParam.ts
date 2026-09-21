"use client";

/**
 * 从 URL 读研究窗口标签（`horizon`）。
 *
 * **语义边界（重要，不要误读）**
 * ----------------------------
 * `horizon` 在本平台是**登记用的研究窗口标签**：
 *  * 它会被写进 `analysis_run.horizon` 并在响应里回传，因此属于"这次分析的身份"；
 *  * 它**不参与因子计算** —— 三个模型的分数、共识、分歧都不随它变化；
 *    事件研究（历史验证）使用自己的持有期集合（`label_horizons` / `event_study_horizons`）。
 *
 * 所以界面上必须同时说明这一点：切换它改的是**登记窗口**，
 * 不是"换一条预测曲线"。把它包装成"20 日/60 日预测切换"会是虚假能力宣称。
 */

import { useSearchParams } from "next/navigation";

import { DEFAULT_HORIZON, HORIZON_OPTIONS } from "./analysisStore";

export function normalizeHorizon(raw: string | null | undefined): string {
  if (!raw) return DEFAULT_HORIZON;
  const v = raw.trim();
  return (HORIZON_OPTIONS as readonly string[]).includes(v) ? v : DEFAULT_HORIZON;
}

export function useHorizonParam(): string {
  const params = useSearchParams();
  return normalizeHorizon(params?.get("horizon"));
}

export { HORIZON_OPTIONS, DEFAULT_HORIZON };
