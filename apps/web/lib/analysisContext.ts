"use client";

/**
 * 分析上下文查询串（跨页面导航与跳转链接的唯一来源）。
 *
 * 纯函数实现已下沉到 `lib/analysisContextCore.ts`（零依赖，Node 侧 e2e 直接测它）；
 * 本文件只保留依赖 `next/navigation` 的客户端 hook，并对既有消费方**再导出**
 * 全部纯函数 —— `@/lib/analysisContext` 的导入路径与语义均不变。
 */

import { useSearchParams } from "next/navigation";

import {
  ANALYSIS_CONTEXT_PARAMS,
  analysisContextSuffix,
  withAnalysisContext,
} from "./analysisContextCore";

export { ANALYSIS_CONTEXT_PARAMS, analysisContextSuffix, withAnalysisContext };

/** 当前 URL 上的分析上下文后缀（客户端组件用）。 */
export function useAnalysisContextSuffix(): string {
  return analysisContextSuffix(useSearchParams());
}
