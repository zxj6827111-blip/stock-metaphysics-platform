"use client";

/**
 * 紫微十二宫盘面组件（复刻 doc/ui-reference/04_ziwei_detail.png 的盘面区）。
 *
 * 设计纪律
 * --------
 * 1. **是真正的盘面组件，不是"紫微分数 + 一段文字"**：
 *    十二宫 / 宫干支 / 主星 / 辅星 / 煞曜 / 四化 / 三方四正 / 流年流月 全部可见。
 * 2. **前端不重算任何术数**：所有内容直接来自后端 `ZiweiChart`；
 *    连"哪些星算煞曜"都不在前端判断（后端已给 `type`）。
 * 3. **变体必须显式切换**：顺行 / 逆行是**两个假设**，不是"一个盘的两个视图"。
 *    UI 上必须同时显示 `variant_basis`，提醒读者差异来源。
 * 4. **不可用就是不可用**：没有盘面时显示原因，不用空网格冒充。
 */

import { useMemo, useState } from "react";

import type { ApiZiweiChart, ApiZiweiPalace, ApiZiweiStar } from "@/lib/api";
import { UnavailableBlock } from "../shell/PageState";

/** 地支顺序（index 0 = 寅）—— 与后端 `ZIWEI_PALACE_BRANCHES` 一一对应。 */
const PALACE_BRANCHES = ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"];

const MUTAGEN_TONE: Record<string, string> = {
  禄: "#4FD39B",
  权: "#7FB3F0",
  科: "#D4A04A",
  忌: "#E8585A",
};

/**
 * 十二宫盘面。
 *
 * 布局遵循**传统紫微盘的环形排布**（与参考图 04 一致）：
 *
 * ```
 *   巳 午 未 申
 *   辰 [ 中 ] 酉
 *   卯 [ 宫 ] 戌
 *   寅 丑 子 亥
 * ```
 *
 * 以本项目的地支索引（0 = 寅）表示即：
 * `[[3,4,5,6],[2,null,null,7],[1,null,null,8],[0,11,10,9]]`
 *
 * 这不是审美选择：紫微的"三方四正"（本宫 / 对宫 / 财帛 / 官禄）只有在
 * 正确的地支环上才直观可读；排错顺序会让读者看到错误的相邻关系。
 */
const RING: (number | null)[][] = [
  [3, 4, 5, 6],
  [2, null, null, 7],
  [1, null, null, 8],
  [0, 11, 10, 9],
];

export function ZiweiChartGrid({
  chart,
  highlightTrine = false,
}: {
  chart: ApiZiweiChart;
  highlightTrine?: boolean;
}) {
  const trine = useMemo(
    () => new Set(chart.palaces[chart.soul_palace_index]?.trine_indices ?? []),
    [chart],
  );
  const cellCls = "min-h-[104px]";

  return (
    <div className="grid grid-cols-4 grid-rows-4 gap-2" data-testid="ziwei-chart-grid">
      {RING.flatMap((row, r) =>
        row.map((idx, c) => {
          if (idx === null) {
            // 中央 2×2：只在左上角渲染一次，其余跳过
            if (r !== 1 || c !== 1) return null;
            return (
              <div
                key="center"
                className="row-span-2 col-span-2 rounded border p-3"
                style={{ borderColor: "rgba(212,160,74,0.35)" }}
                data-testid="ziwei-center"
              >
                <div className="text-[12.5px] font-semibold" style={{ color: "var(--color-gold)" }}>
                  {chart.soul_palace_branch}宫位环 · 命身与四化
                </div>
                <div className="mt-1 space-y-0.5 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                  <div>命宫：{palaceName(chart, chart.soul_palace_index)}（{chart.soul_palace_branch}）</div>
                  <div>身宫：{palaceName(chart, chart.body_palace_index)}</div>
                  <div>命主 {chart.soul} · 身主 {chart.body}</div>
                  <div>五行局 {chart.five_elements_class}</div>
                  <div className="pt-1">
                    生年四化：
                    {(chart.natal_mutagens ?? []).map((m) => (
                      <span key={m.mutagen} className="ml-1">
                        {m.mutagen}
                        {m.star}→{m.palace_name}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            );
          }
          const palace = chart.palaces[idx];
          if (!palace) return null;
          return (
            <div key={idx} className={cellCls}>
              <PalaceCell
                palace={palace}
                isSoul={idx === chart.soul_palace_index}
                isBody={idx === chart.body_palace_index}
                inTrine={highlightTrine && trine.has(idx)}
              />
            </div>
          );
        }),
      )}
    </div>
  );
}

function palaceName(chart: ApiZiweiChart, index: number): string {
  if (index < 0) return "—";
  return `${chart.palaces[index]?.name ?? "—"}宫`;
}

function PalaceCell({
  palace,
  isSoul,
  isBody,
  inTrine,
}: {
  palace: ApiZiweiPalace;
  isSoul: boolean;
  isBody: boolean;
  inTrine: boolean;
}) {
  const major = palace.major_stars ?? [];
  const minor = palace.minor_stars ?? [];
  const bad = minor.filter((s) => s.type === "tough" || s.type === "lucun");
  const good = minor.filter((s) => !(s.type === "tough" || s.type === "lucun"));

  return (
    <div
      className="rounded border p-2 text-[11.5px] leading-[1.5]"
      style={{
        borderColor: isSoul ? "#D4A04A" : inTrine ? "rgba(212,160,74,0.45)" : "var(--color-border)",
        background: isSoul ? "rgba(212,160,74,0.07)" : "var(--color-surface, transparent)",
      }}
      data-testid={`ziwei-palace-${palace.index}`}
      data-palace-name={palace.name}
      data-in-trine={inTrine ? "1" : "0"}
    >
      <div className="mb-1 flex items-center justify-between">
        <span className="font-semibold" style={{ color: "var(--color-ink)" }}>
          {palace.name}
          {isBody ? <span style={{ color: "#D4A04A" }}> ·身</span> : null}
        </span>
        <span style={{ color: "var(--color-ink-muted)" }}>
          {palace.heavenly_stem}
          {palace.earthly_branch}
        </span>
      </div>

      <div className="min-h-[18px]">
        {major.length ? (
          major.map((s) => <StarLine key={s.name} star={s} strong />)
        ) : (
          <span style={{ color: "var(--color-ink-muted)" }}>（空宫 · 借对宫安星）</span>
        )}
      </div>

      {good.length ? (
        <div className="mt-0.5">
          {good.map((s) => (
            <StarLine key={s.name} star={s} />
          ))}
        </div>
      ) : null}

      {bad.length ? (
        <div className="mt-0.5">
          {bad.map((s) => (
            <StarLine key={s.name} star={s} malefic />
          ))}
        </div>
      ) : null}

      <div className="mt-1 flex flex-wrap items-center gap-1" style={{ color: "var(--color-ink-muted)" }}>
        {palace.changsheng12 ? <span>{palace.changsheng12}</span> : null}
      </div>
    </div>
  );
}

function StarLine({
  star,
  strong,
  malefic,
}: {
  star: ApiZiweiStar;
  strong?: boolean;
  malefic?: boolean;
}) {
  const tone = star.mutagen ? MUTAGEN_TONE[star.mutagen] : undefined;
  return (
    <div className="flex items-center gap-1">
      <span
        style={{
          color: tone ?? (malefic ? "#E8585A" : strong ? "var(--color-ink)" : "var(--color-ink-muted)"),
          fontWeight: strong || star.mutagen ? 600 : 400,
        }}
      >
        {star.name}
        {star.brightness ? <span style={{ opacity: 0.75 }}>（{star.brightness}）</span> : null}
      </span>
      {star.mutagen ? (
        <span
          className="rounded px-1 text-[10.5px]"
          style={{ background: `${tone}22`, color: tone }}
        >
          化{star.mutagen}
        </span>
      ) : null}
    </div>
  );
}

/** 盘面元信息（命身 / 五行局 / 四化 / 变体说明）。 */
export function ZiweiMeta({
  chart,
  variantLabel,
}: {
  chart: ApiZiweiChart;
  variantLabel: string;
}) {
  return (
    <div className="space-y-2 text-[12.5px]" data-testid="ziwei-meta">
      <div className="flex flex-wrap gap-x-5 gap-y-1">
        <Field label="变体" value={variantLabel} />
        <Field label="公历" value={chart.solar_date} />
        <Field label="农历" value={chart.lunar_date} />
        <Field label="四柱" value={chart.chinese_date} />
        <Field label="时辰" value={`${chart.time_name} ${chart.time_range}`} />
      </div>
      <div className="flex flex-wrap gap-x-5 gap-y-1">
        <Field label="命宫" value={`${chart.soul_palace_branch}（第 ${chart.soul_palace_index} 宫）`} />
        <Field label="命主" value={chart.soul} />
        <Field label="身主" value={chart.body} />
        <Field label="五行局" value={chart.five_elements_class} />
      </div>
      <div>
        <span style={{ color: "var(--color-ink-muted)" }}>生年四化：</span>
        {(chart.natal_mutagens ?? []).map((m) => (
          <span
            key={m.mutagen}
            className="ml-2 rounded px-1.5 py-0.5 text-[11.5px]"
            style={{
              background: `${MUTAGEN_TONE[m.mutagen]}22`,
              color: MUTAGEN_TONE[m.mutagen],
            }}
          >
            化{m.mutagen} {m.star} → {m.palace_name}
          </span>
        ))}
      </div>
      <p
        className="rounded border px-2 py-1 text-[12px]"
        style={{ borderColor: "rgba(212,160,74,0.45)", color: "var(--color-ink-muted)" }}
      >
        <b style={{ color: "#D4A04A" }}>变体说明：</b>
        {chart.variant_basis || "（缺少变体说明）"}
        <br />
        顺行/逆行的差异**仅限于大限与长生十二神的顺逆**；十二宫、星曜、四化、
        流年流月流日与变体无关 —— 两者不是两条独立证据。
      </p>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <span style={{ color: "var(--color-ink-muted)" }}>{label}：</span>
      <span>{value || "—"}</span>
    </span>
  );
}

/** 三方四正（命宫 / 迁移 / 财帛 / 官禄）。 */
export function ZiweiTrine({ chart }: { chart: ApiZiweiChart }) {
  const soul = chart.palaces[chart.soul_palace_index];
  if (!soul) return <UnavailableBlock what="三方四正" reason="命宫索引越界" />;
  return (
    <div className="grid grid-cols-4 gap-2" data-testid="ziwei-trine">
      {soul.trine_indices.map((i, pos) => {
        const p = chart.palaces[i];
        const role = ["本宫", "对宫", "财帛位", "官禄位"][pos];
        return (
          <div
            key={i}
            className="rounded border p-2 text-[11.5px]"
            style={{ borderColor: "var(--color-border)" }}
            data-testid={`ziwei-trine-${pos}`}
          >
            <div style={{ color: "var(--color-ink-muted)" }}>
              {role} · {p?.name}
            </div>
            <div className="mt-0.5">
              {(p?.major_stars ?? []).map((s) => (
                <StarLine key={s.name} star={s} strong />
              ))}
              {!(p?.major_stars ?? []).length ? (
                <span style={{ color: "var(--color-ink-muted)" }}>（空宫）</span>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/** 运限层（流年 / 流月 / 流日）：显示命宫落在原盘哪一宫。 */
export function ZiweiHoroscope({ chart }: { chart: ApiZiweiChart }) {
  const layers: { key: string; label: string }[] = [
    { key: "decadal", label: "大限" },
    { key: "age", label: "小限" },
    { key: "yearly", label: "流年" },
    { key: "monthly", label: "流月" },
    { key: "daily", label: "流日" },
    { key: "hourly", label: "流时" },
  ];
  const h = chart.horoscope;
  if (!h) return <UnavailableBlock what="运限" reason="后端未返回运限层" />;

  return (
    <div className="grid grid-cols-3 gap-2" data-testid="ziwei-horoscope">
      {layers.map(({ key, label }) => {
        const sec = h[key];
        if (!sec) {
          return (
            <div key={key} className="rounded border p-2 text-[11.5px]"
                 style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}>
              {label}：不可用
            </div>
          );
        }
        const palace = chart.palaces[sec.index];
        const hasStars = (sec.palace_names ?? []).length > 0;
        return (
          <div
            key={key}
            className="rounded border p-2 text-[11.5px]"
            style={{ borderColor: "var(--color-border)" }}
            data-testid={`ziwei-horoscope-${key}`}
          >
            <div className="flex items-center justify-between">
              <span className="font-semibold">{label}</span>
              <span style={{ color: "var(--color-ink-muted)" }}>
                {sec.heavenly_stem}
                {sec.earthly_branch}
              </span>
            </div>
            <div className="mt-0.5" style={{ color: "var(--color-ink-muted)" }}>
              命宫落：{palace ? `${palace.name}宫` : "—"}
              {sec.nominal_age ? ` · 虚岁 ${sec.nominal_age}` : ""}
            </div>
            <div className="mt-0.5" style={{ color: "var(--color-ink-muted)" }}>
              四化：{(sec.mutagen ?? []).join(" / ") || "—"}
            </div>
            {!hasStars ? (
              <div className="mt-0.5" style={{ color: "var(--color-ink-muted)" }}>
                （该层无流曜；iztro 的小限层不提供流曜）
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/** 变体切换器 —— 顺行 / 逆行 必须由用户显式选择。 */
export function VariantSwitcher({
  value,
  onChange,
  disabled,
}: {
  value: "forward" | "reverse";
  onChange: (v: "forward" | "reverse") => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex overflow-hidden rounded border" style={{ borderColor: "var(--color-border)" }}
         data-testid="variant-switcher">
      {(["forward", "reverse"] as const).map((v) => (
        <button
          key={v}
          type="button"
          disabled={disabled}
          onClick={() => onChange(v)}
          className="px-3 py-1 text-[12px] transition-opacity hover:opacity-80 disabled:opacity-40"
          style={{
            background: value === v ? "rgba(212,160,74,0.18)" : "transparent",
            color: value === v ? "#D4A04A" : "var(--color-ink-muted)",
          }}
        >
          {v === "forward" ? "顺行（Variant A）" : "逆行（Variant B）"}
        </button>
      ))}
    </div>
  );
}

export const ZIWEI_PALACE_BRANCHES = PALACE_BRANCHES;
