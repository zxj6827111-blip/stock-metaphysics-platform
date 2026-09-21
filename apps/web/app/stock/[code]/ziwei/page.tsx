"use client";

/**
 * 紫微斗数详情页（复刻 doc/ui-reference/04_ziwei_detail.png）。
 *
 * 与 Phase 1 占位页的区别：这里是**真正的 ZiweiChart 组件** ——
 * 十二宫 / 主星 / 辅星 / 煞曜 / 四化 / 三方四正 / 流年流月全部来自后端确定性排盘，
 * 不是"紫微分数 + 一段文字"。
 *
 * 布局（复核任务书 §R2 / 04 参考图）
 * --------------------------------
 * 左侧 8/12（≈63%）是**完整十二宫环形盘**，右侧 4/12（≈37%）是命身摘要、
 * 生年四化、运限假设与研究状态。三方四正与运限明细放在盘面**下方**。
 * 1672×941 下十二宫必须整盘可见（含底排），因此宫格高度是**定量**的
 * （`ZiweiChartGrid` 的 4×116px + 间距），不靠缩字体去挤。
 *
 * 两条硬约束：
 * 1. **前端不重算术数**（AGENTS.md §9.12）：星曜分类、庙旺、四化都直接用后端字段；
 * 2. **变体必须显式**（ADR-0010）：顺行/逆行是两个假设，UI 必须让用户自己选，
 *    并把 `variant_basis` 摆在盘面旁边。
 */

import { useParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Card, CardBody, CardHeader, Chip } from "@/components/cards/Card";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, ResearchStatusBadge, UnavailableBlock } from "@/components/shell/PageState";
import { IconGrid, IconSpark } from "@/components/shell/Icons";
import { RawField, SourceMethod } from "@/components/shell/SourceMethod";
import {
  VariantSwitcher,
  ZiweiChartGrid,
  ZiweiHoroscope,
  ZiweiTrine,
} from "@/components/ziwei/ZiweiChart";
import type { ApiZiweiChart } from "@/lib/api";
import { useAnalysis, type AnalysisVariant } from "@/lib/analysisStore";

const MUTAGEN_TONE: Record<string, string> = {
  禄: "#4FD39B",
  权: "#7FB3F0",
  科: "#D4A04A",
  忌: "#E8585A",
};

function ZiweiInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const [variant, setVariant] = useState<AnalysisVariant>("forward");
  const { analysis, loading, error, reload } = useAnalysis(code, variant);

  const chart = analysis?.ziwei_charts?.[variant];
  const opinion = analysis?.opinions?.ziwei;
  const variantLabel = variant === "forward" ? "顺行（Variant A）" : "逆行（Variant B）";

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
      {chart ? (
        <div className="grid grid-cols-12 gap-3" data-testid="ziwei-layout">
          {/* ---------- 左 8/12：完整十二宫 ---------- */}
          <div className="col-span-12 xl:col-span-8">
            <Card testId="ziwei-chart-card">
              <CardHeader
                icon={<IconGrid size={15} />}
                title="紫微斗数命盘（十二宫）"
                right={<VariantSwitcher value={variant} onChange={setVariant} />}
                dense
              />
              <div className="px-2 pb-2">
                <ZiweiChartGrid
                  chart={chart}
                  highlightTrine
                  center={<CenterIdentity chart={chart} variantLabel={variantLabel} />}
                />
              </div>
            </Card>

            <Card className="mt-3" testId="ziwei-trine-card">
              <CardHeader
                icon={<IconSpark size={15} />}
                title="三方四正与四化"
                dense
                right={
                  <span className="text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
                    命 / 迁 / 财 / 官
                  </span>
                }
              />
              <CardBody>
                <ZiweiTrine chart={chart} />
                <div className="mt-2">
                  <SectionNote>
                    三方四正由宫位索引固定推出（本宫 / 对宫 +6 / 财帛位 +8 / 官禄位 +4），
                    后端已对拍 iztro 的 <code>surroundedPalaces</code>。
                  </SectionNote>
                </div>
              </CardBody>
            </Card>
          </div>

          {/* ---------- 右 4/12：观察栏 ---------- */}
          <div className="col-span-12 space-y-3 xl:col-span-4">
            <Card testId="ziwei-observation">
              <CardHeader
                icon={<IconSpark size={15} />}
                title="核心观察"
                dense
                right={
                  <span className="text-[10.5px]" style={{ color: "var(--color-ink-faint)" }}>
                    基于星曜组合
                  </span>
                }
              />
              <CardBody className="!px-0 !py-0">
                <CoreObservation chart={chart} />
              </CardBody>
            </Card>

            <Card testId="ziwei-horoscope">
              <CardHeader icon={<IconGrid size={15} />} title="运限（大限 / 流年 / 流月 / 流日）" dense />
              <CardBody>
                <ZiweiHoroscope chart={chart} />
                <div className="mt-2">
                  <SectionNote>
                    小限层在 iztro 中<strong>不提供流曜</strong>，因此该层的星曜为空 —— 这是如实保留的缺失，
                    不用其他层的星曜补全（见 docs/calculation-differences-phase2-ziwei.md D1）。
                  </SectionNote>
                </div>
              </CardBody>
            </Card>

            <Card testId="ziwei-status">
              <CardHeader icon={<IconSpark size={15} />} title="假设与研究状态" dense />
              <CardBody>
                <div className="space-y-2 text-[12px]">
                  <ResearchStatusBadge status={analysis?.consensus?.research_status ?? "NOT_RUN"} />
                  <p style={{ color: "var(--color-warn)" }} data-testid="variant-note">
                    {chart.variant_basis || "（缺少变体说明）"}
                  </p>
                  <SectionNote>
                    {opinion?.note ??
                      "紫微观点由紫微因子聚合而成；分数是传统规则强度，不代表预期收益率，也不代表上涨概率。"}
                  </SectionNote>
                  {opinion?.assumptions?.length ? (
                    <ul className="space-y-0.5 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                      {opinion.assumptions.map((a) => (
                        <li key={a}>· {a}</li>
                      ))}
                    </ul>
                  ) : null}
                  {chart.assumptions?.length ? (
                    <ul className="space-y-0.5 text-[11.5px]" data-testid="ziwei-assumptions">
                      {chart.assumptions.map((a) => (
                        <li key={a.key}>
                          <span style={{ color: "var(--color-ink-muted)" }}>{a.key}：</span>
                          {a.value}
                          {a.impact ? (
                            <span style={{ color: "var(--color-ink-faint)" }}>（{a.impact}）</span>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {chart.warnings?.length ? (
                    <ul className="space-y-0.5 text-[11.5px]" style={{ color: "var(--color-warn)" }}>
                      {chart.warnings.map((w) => (
                        <li key={w.code}>· [{w.severity}] {w.code}: {w.message}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              </CardBody>
            </Card>

            <SourceMethod label="原始盘面与来源" testId="ziwei-source-method">
              <RawField label="排盘引擎" value="ziwei-service（iztro）" />
              <RawField label="变体" value={chart.variant_mode} />
              <RawField label="性别参数" value={chart.gender_parameter} />
              <RawField label="公历" value={chart.solar_date} />
              <RawField label="农历" value={chart.lunar_date} />
              <RawField label="四柱" value={chart.chinese_date} />
              <RawField label="时辰" value={`${chart.time_name} ${chart.time_range}`} />
              <RawField label="命宫索引" value={`${chart.soul_palace_index}（${chart.soul_palace_branch}）`} />
              <RawField label="身宫索引" value={String(chart.body_palace_index)} />
              <RawField label="命主 / 身主" value={`${chart.soul} / ${chart.body}`} />
              <RawField label="五行局" value={chart.five_elements_class} />
              <RawField label="数据端点" value="GET /api/v1/analysis/{id}/charts/ziwei" />
            </SourceMethod>
          </div>
        </div>
      ) : (
        <Card>
          <CardHeader icon={<IconGrid size={15} />} title="紫微斗数命盘（十二宫）" dense
            right={<VariantSwitcher value={variant} onChange={setVariant} />} />
          <CardBody>
            <UnavailableBlock
              what="紫微盘面"
              testId="ziwei-unavailable"
              reason={
                opinion?.note ||
                "本次分析未产出紫微盘面：可能是紫微排盘服务不可用，或未指定方向 variant。" +
                  "系统不会用空盘面或 0 分冒充结果。"
              }
            />
            <div className="flex items-center justify-center pt-2">
              <button
                type="button"
                className="smp-btn smp-btn--primary px-4 py-1.5 text-[12.5px] font-medium"
                onClick={reload}
              >
                刷新缓存并重新排盘
              </button>
            </div>
          </CardBody>
        </Card>
      )}
    </ResearchPage>
  );
}

/** 盘面中央：命盘身份（公历 / 农历 / 四柱 / 时辰 / 命身 / 五行局 / 生年四化）。 */
function CenterIdentity({ chart, variantLabel }: { chart: ApiZiweiChart; variantLabel: string }) {
  return (
    <div className="space-y-1 text-[11px] leading-[15px]" data-testid="ziwei-center-identity">
      <div className="flex items-center justify-between">
        <span className="text-[12.5px] font-semibold" style={{ color: "var(--color-gold)" }}>
          命盘身份
        </span>
        <span style={{ color: "var(--color-ink-faint)" }}>{variantLabel}</span>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5" style={{ color: "var(--color-ink-muted)" }}>
        <span>公历：{chart.solar_date}</span>
        <span>农历：{chart.lunar_date}</span>
        <span className="col-span-2">四柱：{chart.chinese_date}</span>
        <span className="col-span-2">时辰：{chart.time_name} {chart.time_range}</span>
      </div>
      <div className="border-t pt-1" style={{ borderColor: "var(--color-border)" }}>
        <div style={{ color: "var(--color-ink-muted)" }}>
          命宫 <b style={{ color: "var(--color-ink)" }}>{chart.palaces[chart.soul_palace_index]?.name ?? "—"}</b>
          （{chart.soul_palace_branch}） · 身宫{" "}
          <b style={{ color: "var(--color-ink)" }}>{chart.palaces[chart.body_palace_index]?.name ?? "—"}</b>
        </div>
        <div style={{ color: "var(--color-ink-muted)" }}>
          命主 {chart.soul} · 身主 {chart.body} · 五行局 {chart.five_elements_class}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1">
        <span style={{ color: "var(--color-ink-muted)" }}>生年四化</span>
        {(chart.natal_mutagens ?? []).map((m) => (
          <span
            key={m.mutagen}
            className="rounded-[3px] px-1 text-[10.5px]"
            style={{ background: `${MUTAGEN_TONE[m.mutagen]}22`, color: MUTAGEN_TONE[m.mutagen] }}
            data-testid={`natal-mutagen-${m.mutagen}`}
          >
            化{m.mutagen} {m.star}→{m.palace_name}
          </span>
        ))}
      </div>
    </div>
  );
}

/** 右栏「核心观察」：命身与关键宫位的**实际星曜**（不生成解释性标签）。 */
function CoreObservation({ chart }: { chart: ApiZiweiChart }) {
  const rows: { label: string; palaceIndex: number; note?: string }[] = [
    { label: "命宫", palaceIndex: chart.soul_palace_index },
    { label: "身宫", palaceIndex: chart.body_palace_index },
    ...(chart.palaces[chart.soul_palace_index]?.trine_indices ?? [])
      .slice(1)
      .map((i) => ({ label: chart.palaces[i]?.name ? `${chart.palaces[i].name}宫` : "对宫", palaceIndex: i, note: "三方四正" })),
  ];
  const seen = new Set<number>();

  return (
    <div data-testid="ziwei-core-observation">
      {rows.map((row) => {
        if (seen.has(row.palaceIndex)) return null;
        seen.add(row.palaceIndex);
        const p = chart.palaces[row.palaceIndex];
        if (!p) return null;
        const stars = [
          ...(p.major_stars ?? []).map((s) => ({ name: s.name, mutagen: s.mutagen })),
          ...(p.minor_stars ?? []).map((s) => ({ name: s.name, mutagen: s.mutagen })),
        ].filter((s) => s.name);
        return (
          <div
            key={`${row.label}-${row.palaceIndex}`}
            className="flex items-center gap-2 border-b px-3 py-[7px] text-[12px] last:border-b-0"
            style={{ borderColor: "var(--color-border)" }}
            data-testid={`ziwei-observation-${row.palaceIndex}`}
          >
            <span className="w-[52px] shrink-0" style={{ color: "var(--color-ink-muted)" }}>
              {row.label}（{p.earthly_branch}）
            </span>
            <span className="min-w-0 flex-1 truncate" style={{ color: "var(--color-ink)" }}>
              {stars.length ? (
                stars.map((s) => (
                  <span
                    key={s.name}
                    className="mr-1.5"
                    style={{ color: s.mutagen ? MUTAGEN_TONE[s.mutagen] : undefined }}
                  >
                    {s.name}
                    {s.mutagen ? `（化${s.mutagen}）` : ""}
                  </span>
                ))
              ) : (
                <span style={{ color: "var(--color-ink-muted)" }}>（空宫 · 借对宫安星）</span>
              )}
            </span>
            {row.note ? <Chip tone="flat">{row.note}</Chip> : null}
          </div>
        );
      })}
    </div>
  );
}

export default function ZiweiPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <ZiweiInner />
    </Suspense>
  );
}
