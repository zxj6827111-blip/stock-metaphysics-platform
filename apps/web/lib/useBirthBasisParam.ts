"use client";

/**
 * 从 URL 读出生模型参数（`birthBasis`）。
 *
 * 为什么放在 URL 而不是组件状态
 * ----------------------------
 * 出生模型是**研究假设**，不是页面显示选项：换一个基准就是换一次分析
 * （出生时刻变了 → 四柱变了 → 紫微盘面变了 → 三个模型的分数都变了）。
 * 放进 URL 有三个好处：
 *  * **可分享/可复核**：把链接给别人，对方看到的是同一个假设下的结果；
 *  * **刷新不丢**：基线选择属于结论的一部分，不该刷新就回到默认；
 *  * **导出可追溯**：导出报告里的上下文快照与 URL 一致。
 *
 * 与 `asOf` 同样走 `useSearchParams()`（服务端与客户端同源），避免 hydration 差异。
 */

import { useSearchParams } from "next/navigation";

import { DEFAULT_BIRTH_BASIS, type AnalysisBirthBasis } from "./analysisStore";

/** 全部取值（与后端 `BirthBasis` 枚举一致）。 */
export const BIRTH_BASIS_VALUES: AnalysisBirthBasis[] = [
  "listing_open",
  "ipo_date",
  "company_foundation",
  "first_trade",
];

/**
 * 能真正算出结果的取值。
 *
 * 其余取值**不是"还没做"**：`company_foundation` 需要公司成立日期数据源、
 * `first_trade` 需要历史逐笔成交数据，本项目都没有接入，后端按契约返回
 * `422 BIRTH_PROFILE_ERROR`（不猜测、不静默降级）。UI 因此把它们显示为
 * **不可用 + 原因**，而不是"点了没反应"或"点了报错"。
 */
export const AVAILABLE_BIRTH_BASES: AnalysisBirthBasis[] = ["listing_open", "ipo_date"];

export const BIRTH_BASIS_UNAVAILABLE_REASON: Partial<Record<AnalysisBirthBasis, string>> = {
  company_foundation: "需要公司成立日期数据源，本项目尚未接入（后端按契约返回错误，不猜测）",
  first_trade: "需要历史逐笔成交数据，本项目尚未接入（后端按契约返回错误，不猜测）",
};

/** 非法/缺省值一律回落到默认基准（不猜测用户意图）。 */
export function normalizeBirthBasis(raw: string | null | undefined): AnalysisBirthBasis {
  if (!raw) return DEFAULT_BIRTH_BASIS;
  const v = raw.trim() as AnalysisBirthBasis;
  return BIRTH_BASIS_VALUES.includes(v) ? v : DEFAULT_BIRTH_BASIS;
}

export function useBirthBasisParam(): AnalysisBirthBasis {
  const params = useSearchParams();
  return normalizeBirthBasis(params?.get("birthBasis"));
}
