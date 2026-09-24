"use client";

/**
 * 分析上下文查询串（跨页面导航与跳转链接的唯一来源）。
 *
 * 为什么单独一个文件：一次分析由 `code + variant + birthBasis + horizon + asOf`
 * 共同确定（见 `lib/analysisStore.ts` 的 `keyOf`）。跳转链接如果只带 fixture，
 * 落地页就会静默回落到默认假设 —— 用户在两页看到的是**两次不同的分析**。
 * 把"哪些参数属于分析身份"写在一处，页面与侧栏才不会各记一份、各漏几个。
 */

import { useSearchParams } from "next/navigation";

/** 属于分析身份的 URL 参数（顺序固定，保证同一上下文生成同一串）。 */
export const ANALYSIS_CONTEXT_PARAMS = ["fixture", "birthBasis", "horizon", "asOf"] as const;

/** 由查询参数得到 `?a=b` 形式的后缀；无参数时返回空串。 */
export function analysisContextSuffix(
  params: Pick<URLSearchParams, "get"> | null | undefined,
): string {
  if (!params) return "";
  const q = new URLSearchParams();
  for (const name of ANALYSIS_CONTEXT_PARAMS) {
    const value = params.get(name);
    if (value) q.set(name, value);
  }
  return q.size ? `?${q.toString()}` : "";
}

/** 当前 URL 上的分析上下文后缀（客户端组件用）。 */
export function useAnalysisContextSuffix(): string {
  return analysisContextSuffix(useSearchParams());
}

/**
 * 给一个已有链接补齐分析上下文。
 *
 * 演示夹具里的 `detailHref` 是**冻结时**拼好的，只带当时那份样本的上下文；
 * 直接拿来渲染，就会出现"URL 选了 60d，点进详情却回到默认窗口"。
 *
 * 优先级（不可反过来）：**当前 URL 上的上下文覆盖链接里的旧值**。
 * 链接里的值是"上一次点进来时"的快照，当前 URL 才是用户此刻的选择；
 * 若让链接优先，用户在 URL 上改的假设就会在跳转那一刻被静默撤销。
 * 当前 URL 上不存在该参数时，链接自己带的值原样保留。
 * 与分析上下文无关的查询参数（如 `?date=`）一律不动。
 */
export function withAnalysisContext(href: string, params: URLSearchParams | null): string {
  if (!params || !href) return href;
  const [path, query = ""] = href.split("?");
  const q = new URLSearchParams(query);
  for (const name of ANALYSIS_CONTEXT_PARAMS) {
    const value = params.get(name);
    if (value) q.set(name, value);
  }
  const s = q.toString();
  return s ? `${path}?${s}` : path;
}
