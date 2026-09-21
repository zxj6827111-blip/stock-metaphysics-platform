"use client";

/**
 * 紫微斗数详情页（复刻 doc/ui-reference/04_ziwei_detail.png）。
 *
 * 与 Phase 1 占位页的区别：这里是**真正的 ZiweiChart 组件** ——
 * 十二宫 / 主星 / 辅星 / 煞曜 / 四化 / 三方四正 / 流年流月全部来自后端确定性排盘，
 * 不是"紫微分数 + 一段文字"。
 *
 * 两条硬约束：
 * 1. **前端不重算术数**（AGENTS.md §9.12）：星曜分类、庙旺、四化都直接用后端字段；
 * 2. **变体必须显式**（ADR-0010）：顺行/逆行是两个假设，UI 必须让用户自己选，
 *    并把 `variant_basis` 摆在盘面旁边。
 */

import { useParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, ResearchStatusBadge, UnavailableBlock } from "@/components/shell/PageState";
import { IconGrid, IconSpark } from "@/components/shell/Icons";
import {
  VariantSwitcher,
  ZiweiChartGrid,
  ZiweiHoroscope,
  ZiweiMeta,
  ZiweiTrine,
} from "@/components/ziwei/ZiweiChart";
import { useAnalysis, type AnalysisVariant } from "@/lib/analysisStore";

function ZiweiInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const [variant, setVariant] = useState<AnalysisVariant>("forward");
  const { analysis, loading, error, reload } = useAnalysis(code, variant);

  const chart = analysis?.ziwei_charts?.[variant];
  const opinion = analysis?.opinions?.ziwei;

  return (
    <ResearchPage
      activeNav="ziwei"
      title="紫微斗数详情"
      subtitle="以紫微之理，观市场之机 · 星曜映照，洞察结构流转"
      seal="微"
      code={code}
      analysis={analysis}
      loading={loading}
      error={error}
      onReload={reload}
      loadingLabel="正在排紫微盘（十二宫 / 星曜 / 四化 / 运限）…"
    >
      <Card>
        <CardHeader
          icon={<IconGrid size={15} />}
          title="紫微斗数命盘（十二宫）"
          right={<VariantSwitcher value={variant} onChange={setVariant} />}
          dense
        />
        {chart ? (
          <div className="space-y-3">
            <ZiweiMeta
              chart={chart}
              variantLabel={variant === "forward" ? "顺行（Variant A）" : "逆行（Variant B）"}
            />
            <ZiweiChartGrid chart={chart} highlightTrine />
          </div>
        ) : (
          <div className="space-y-3">
            <UnavailableBlock
              what="紫微盘面"
              testId="ziwei-unavailable"
              reason={
                opinion?.note ||
                "本次分析未产出紫微盘面：可能是紫微排盘服务不可用，或未指定方向 variant。" +
                  "系统不会用空盘面或 0 分冒充结果。"
              }
            />
            <div className="flex items-center justify-center pb-2">
              <button
                type="button"
                className="smp-btn smp-btn--primary px-4 py-1.5 text-[12.5px] font-medium"
                onClick={reload}
              >
                刷新缓存并重新排盘
              </button>
            </div>
          </div>
        )}
      </Card>

      {chart ? (
        <>
          <Card>
            <CardHeader icon={<IconSpark size={15} />} title="三方四正（命 / 迁 / 财 / 官）" dense />
            <ZiweiTrine chart={chart} />
            <div className="mt-2">
              <SectionNote>
                三方四正由宫位索引固定推出（本宫 / 对宫 +6 / 财帛位 +8 / 官禄位 +4），
                后端已对拍 iztro 的 <code>surroundedPalaces</code>。
              </SectionNote>
            </div>
          </Card>

          <Card>
            <CardHeader
              icon={<IconGrid size={15} />}
              title="运限（大限 / 小限 / 流年 / 流月 / 流日 / 流时）"
              dense
            />
            <ZiweiHoroscope chart={chart} />
            <div className="mt-2">
              <SectionNote>
                小限层在 iztro 中<strong>不提供流曜</strong>，因此该层的星曜为空 —— 这是如实保留的缺失，
                不用其他层的星曜补全（见 docs/calculation-differences-phase2-ziwei.md D1）。
              </SectionNote>
            </div>
          </Card>
        </>
      ) : null}

      <Card>
        <CardHeader icon={<IconSpark size={15} />} title="结论与状态" dense />
        <div className="space-y-2 text-[12.5px]">
          <ResearchStatusBadge status={analysis?.consensus?.research_status ?? "NOT_RUN"} />
          <SectionNote>
            {opinion?.note ??
              "紫微观点由紫微因子聚合而成；分数是传统规则强度，不代表预期收益率，也不代表上涨概率。"}
          </SectionNote>
          {opinion?.assumptions?.length ? (
            <ul className="space-y-1 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
              {opinion.assumptions.map((a) => (
                <li key={a}>· {a}</li>
              ))}
            </ul>
          ) : null}
          {chart?.warnings?.length ? (
            <ul className="space-y-1 text-[12px]" style={{ color: "var(--color-warn)" }}>
              {chart.warnings.map((w) => (
                <li key={w.code}>
                  · [{w.severity}] {w.code}: {w.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </Card>
    </ResearchPage>
  );
}

export default function ZiweiPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <ZiweiInner />
    </Suspense>
  );
}
