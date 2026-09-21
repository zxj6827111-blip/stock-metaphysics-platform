"use client";

/**
 * 「未来 N 个交易日黄历」日期网格（复刻 doc/ui-reference/08_huangli_detail.png）。
 *
 * 与参考图的**结构性差异（必须如实展示，不得补齐）**
 * ------------------------------------------------
 * 参考图的日期卡分「吉 / 平 / 凶」三级，卡面写"宜交易 / 宜观望 / 忌追涨"。
 * 本系统两样都不做：
 *
 * 1. 后端通书口径（十二神所属黄黑道）只有**吉 / 凶**两级，没有可解释、
 *    可版本化的第三类规则，因此不产出「平」（见 `class_rule.difference_note_cn`）；
 * 2. 卡面的"简短依据"直接取**通书宜忌原文**，不改写成交易建议 ——
 *    「宜开市」是传统择日观念，不是买入信号。
 *
 * 交易日来自后端实测日历：周末、长假、休市日不会出现在卡里；
 * 日历覆盖不足时组件保留结构并说明实际覆盖天数与原因（不补造日期）。
 */

import { useEffect, useMemo, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { CLASS_TONE, CLASS_TONE_CN } from "@/components/charts/Charts";
import { IconCalendar } from "@/components/shell/Icons";
import { SectionNote } from "@/components/shell/ResearchPage";
import { SectionEmpty, SectionError, SectionLoading } from "@/components/shell/SectionState";import { api, endpoints, type ApiHuangliOutlook } from "@/lib/api";
import {
  huangliOutlook20dFixture,
  huangliOutlook3mFixture,
  huangliOutlookTodayFixture,
  isFixtureActive,
} from "@/lib/fixture";
import { stripMdEmphasis } from "@/lib/text";

type Mode = "today" | "trading_days" | "months";

const TABS: { key: string; label: string; mode: Mode; value: number }[] = [
  { key: "today", label: "今日", mode: "today", value: 1 },
  { key: "20d", label: "近20个交易日", mode: "trading_days", value: 20 },
  { key: "3m", label: "近3个月", mode: "months", value: 3 },
];

/** 传统分类的语义色（与行情涨跌色完全分离，避免读成买卖信号）。 */
function classTone(code: string | null): string {
  if (code === "auspicious") return CLASS_TONE.auspicious;
  if (code === "inauspicious") return CLASS_TONE.inauspicious;
  return CLASS_TONE.unknown;
}

function classLabel(card: { class_code: string | null; class_label_cn: string | null }): string {
  if (card.class_label_cn) return card.class_label_cn;
  return "未给出分类";
}

/** 日期卡判定来源分布的文字摘要（"多少天是事实、多少天是公告"）。 */
function daySourceSummary(sources?: Record<string, number>): string {
  if (!sources) return "";
  const parts: string[] = [];
  const observed = sources.observed_index_days ?? 0;
  const published = sources.published_exchange_calendar ?? 0;
  if (observed) parts.push(`${observed} 天来自实测成交`);
  if (published) parts.push(`${published} 天来自官方已公布安排`);
  return parts.length ? `（${parts.join("，")}）` : "";
}

/** 日期卡的判定来源短标签。 */
function sourceLabel(source?: string): string {
  if (source === "published_exchange_calendar") return "公布";
  if (source === "observed_index_days") return "实测";
  return "";
}

export function HuangliTradingDayGrid({
  analysisId,
  onSelectDate,
  selectedDate,
}: {
  analysisId: string | null;
  onSelectDate?: (date: string) => void;
  selectedDate?: string | null;
}) {
  const [tab, setTab] = useState<string>("20d");
  const [data, setData] = useState<ApiHuangliOutlook | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [internalSelected, setInternalSelected] = useState<string | null>(null);

  const active = TABS.find((t) => t.key === tab) ?? TABS[1];
  const selection = selectedDate ?? internalSelected;

  useEffect(() => {
    let cancelled = false;
    // 演示模式：直接读固定样本，绝不发起真实请求
    if (isFixtureActive()) {
      // 每个档位读**自己**那份固定样本。用同一份样本顶替所有档位等于把
      // 「今日」渲染成 20 天、「近 3 个月」渲染成 20 天 —— 读者看到的是错的粒度。
      const byTab: Record<string, ApiHuangliOutlook> = {
        today: huangliOutlookTodayFixture,
        "20d": huangliOutlook20dFixture,
        "3m": huangliOutlook3mFixture,
      };
      setData(byTab[active.key]);
      setError(null);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    if (!analysisId) {
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }
    setLoading(true);
    setError(null);
    api
      .get<ApiHuangliOutlook>(endpoints.huangliOutlook(analysisId, active.mode, active.value))
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [analysisId, active.key, active.mode, active.value]);

  const days = data?.days ?? [];
  const firstDate = days[0]?.date ?? null;

  // 默认选中第一张卡（"今日"即基准日当天）
  useEffect(() => {
    if (!selection && firstDate) setInternalSelected(firstDate);
  }, [firstDate, selection]);

  const selected = useMemo(
    () => days.find((d) => d.date === selection) ?? days[0] ?? null,
    [days, selection],
  );

  const pick = (date: string) => {
    setInternalSelected(date);
    onSelectDate?.(date);
  };

  const coverage = data?.coverage;

  return (
    <Card testId="huangli-outlook">
      <CardHeader
        icon={<IconCalendar size={15} />}
        title={`未来交易日黄历（${labelForTabs(active.key)}）`}
        right={
          <div className="flex items-center gap-1" data-testid="huangli-outlook-tabs">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className="rounded-[4px] px-2 py-[3px] text-[11.5px] transition-colors"
                style={
                  t.key === tab
                    ? {
                        color: "#241c0c",
                        background:
                          "linear-gradient(180deg, var(--color-gold-strong), var(--color-gold))",
                        fontWeight: 600,
                      }
                    : { color: "var(--color-ink-sub)", border: "1px solid var(--color-border)" }
                }
                data-testid={`huangli-tab-${t.key}`}
                aria-pressed={t.key === tab}
              >
                {t.label}
              </button>
            ))}
          </div>
        }
        dense
      />

      {/* 口径说明：交易日从哪来、基准日怎么处理 */}
      <div
        className="mb-2 rounded border-l-2 px-2.5 py-1.5 text-[11.5px] leading-relaxed"
        style={{
          borderColor: "var(--color-gold-dim)",
          background: "rgba(212,184,122,0.05)",
          color: "var(--color-ink-sub)",
        }}
        data-testid="huangli-outlook-rule"
      >
        {loading ? "正在按交易日历取黄历…" : stripMdEmphasis(data?.rule_cn) || "—"}
        {data && !loading ? (
          <>
            {" "}
            <span style={{ color: "var(--color-ink-muted)" }} data-testid="huangli-calendar-scope">
              交易日历：{data.exchange} 实测成交日
              {coverage?.calendar_coverage
                ? `（${coverage.calendar_coverage.start} ~ ${coverage.calendar_coverage.end}）`
                : "（不可用）"}
              {coverage?.published_coverage
                ? `；官方已公布安排（${coverage.published_coverage.start} ~ ${coverage.published_coverage.end}）`
                : ""}
              ；本区共返回 {data.returned_days} 张日期卡{daySourceSummary(coverage?.day_sources)}。
            </span>
          </>
        ) : null}
      </div>

      {loading ? <SectionLoading label="正在按实测交易日历取黄历…" rows={3} /> : null}

      {!loading && error ? (
        <SectionError what="未来交易日黄历" message={error} testId="huangli-outlook-error" />
      ) : null}

      {!loading && !error && coverage && coverage.status !== "complete" ? (
        <div
          className="mb-2 rounded border px-2.5 py-2 text-[12px] leading-relaxed"
          style={{
            borderColor: "rgba(224,164,88,0.42)",
            background: "rgba(224,164,88,0.08)",
            color: "var(--color-ink-sub)",
          }}
          data-testid="huangli-outlook-coverage"
        >
          <b style={{ color: "var(--color-warn)" }}>
            {coverage.status === "unavailable" ? "日历覆盖不足" : "部分覆盖"}
          </b>
          ：{stripMdEmphasis(coverage.explanation_cn)}
        </div>
      ) : null}

      {!loading && !error && !days.length && coverage?.status !== "unavailable" ? (
        <SectionEmpty
          what="未来交易日黄历"
          hint="后端未返回任何交易日。日期卡不会用自然日或周末规则补足。"
        />
      ) : null}

      {!loading && days.length ? (
        active.key === "3m" ? (
          <MonthGroupedGrid
            data={data!}
            selected={selection}
            onPick={pick}
          />
        ) : (
          <DayCardGrid days={days} selected={selection} onPick={pick} columns={10} />
        )
      ) : null}

      {/* 图例：颜色不能是唯一信息载体（文字 + 图例同时给出） */}
      <div className="mt-2 flex flex-wrap items-center gap-3 text-[11.5px]">
        <span style={{ color: "var(--color-ink-muted)" }}>图例（传统分类）：</span>
        {(["auspicious", "inauspicious"] as const).map((code) => (
          <span key={code} className="flex items-center gap-1">
            <span
              className="inline-block h-2.5 w-2.5 rounded-[2px]"
              style={{ background: CLASS_TONE[code] }}
            />
            <span style={{ color: "var(--color-ink-sub)" }}>{CLASS_TONE_CN[code]}</span>
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span
            className="inline-block h-2.5 w-2.5 rounded-[2px]"
            style={{ background: CLASS_TONE.unknown }}
          />
          <span style={{ color: "var(--color-ink-sub)" }}>未给出分类</span>
        </span>
        <span style={{ color: "var(--color-ink-faint)" }}>
          · 分类描述传统择日观念，不是买入/卖出建议
        </span>
      </div>

      {/* 选中日的详情联动 */}
      {selected ? <SelectedDayDetail card={selected} rule={data?.class_rule} /> : null}

      {/* 分类口径差异：把"为什么没有平"讲在前面，而不是让读者以为漏了一类 */}
      {data?.class_rule ? (
        <div className="mt-2">
          <SectionNote>
            <b>分类口径（{data.class_rule.rule_id}）：</b>
            {stripMdEmphasis(data.class_rule.difference_note_cn)}
            <br />
            依据字段：<code>{data.class_rule.basis_field}</code>（{data.class_rule.basis_source}）。
            {stripMdEmphasis(data.class_rule.not_a_recommendation_cn)}
          </SectionNote>
        </div>
      ) : null}
    </Card>
  );
}

function labelForTabs(key: string): string {
  return TABS.find((t) => t.key === key)?.label ?? "近20个交易日";
}

function DayCardGrid({
  days,
  selected,
  onPick,
  columns,
}: {
  days: ApiHuangliOutlook["days"];
  selected: string | null;
  onPick: (date: string) => void;
  columns: number;
}) {
  return (
    <div
      className="grid gap-1.5"
      style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      data-testid="huangli-day-grid"
    >
      {days.map((d) => (
        <DayCard key={d.date} card={d} active={d.date === selected} onPick={onPick} />
      ))}
    </div>
  );
}

function DayCard({
  card,
  active,
  onPick,
}: {
  card: ApiHuangliOutlook["days"][number];
  active: boolean;
  onPick: (date: string) => void;
}) {
  const tone = classTone(card.class_code);
  const basis = card.day_yi.length
    ? `宜：${card.day_yi.slice(0, 3).join(" · ")}`
    : card.day_ji.length
      ? `忌：${card.day_ji.slice(0, 3).join(" · ")}`
      : card.class_basis_cn.slice(0, 18);
  return (
    <button
      type="button"
      onClick={() => onPick(card.date)}
      className="flex flex-col items-stretch rounded-[6px] border px-1.5 py-1.5 text-left transition-colors"
      style={{
        borderColor: active ? "var(--color-gold)" : "var(--color-border)",
        background: active ? "rgba(212,184,122,0.10)" : "rgba(255,255,255,0.012)",
        boxShadow: active ? "inset 0 0 0 1px rgba(212,184,122,0.35)" : undefined,
      }}
      data-testid={`huangli-day-${card.date}`}
      aria-pressed={active}
    >
      <div className="smp-num text-[11.5px] leading-tight" style={{ color: "var(--color-ink)" }}>
        {card.date.slice(5)}
      </div>
      <div className="flex items-center gap-1 text-[10.5px] leading-tight" style={{ color: "var(--color-ink-muted)" }}>
        <span>{card.weekday_cn.replace("星期", "周")}</span>
        {/* 这一天凭什么算交易日：实测成交 / 官方已公布安排 */}
        {sourceLabel(card.calendar_source) ? (
          <span
            className="rounded-[3px] border px-[3px]"
            style={{ borderColor: "var(--color-border)", fontSize: 9.5 }}
            data-testid={`huangli-day-source-${card.date}`}
          >
            {sourceLabel(card.calendar_source)}
          </span>
        ) : null}
      </div>
      <div
        className="mt-1 inline-flex w-fit items-center rounded-[3px] px-1 py-[1px] text-[10.5px] font-semibold"
        style={{ color: "#0d1a25", background: tone }}
        data-testid={`huangli-class-${card.date}`}
      >
        {classLabel(card)}
      </div>
      <div
        className="mt-1 line-clamp-2 text-[10px] leading-[13px]"
        style={{ color: "var(--color-ink-muted)" }}
        title={basis}
      >
        {basis}
      </div>
    </button>
  );
}

/** 「近 3 个月」用月分组，避免 60+ 张卡无限撑高页面。 */
function MonthGroupedGrid({
  data,
  selected,
  onPick,
}: {
  data: ApiHuangliOutlook;
  selected: string | null;
  onPick: (date: string) => void;
}) {
  const byDate = useMemo(() => new Map(data.days.map((d) => [d.date, d])), [data.days]);
  return (
    <div className="space-y-2" data-testid="huangli-month-groups">
      {data.month_groups.map((group) => (
        <div key={group.month}>
          <div
            className="mb-1 flex items-center gap-2 text-[11.5px]"
            style={{ color: "var(--color-ink-sub)" }}
          >
            <span className="font-semibold">{group.month}</span>
            <span style={{ color: "var(--color-ink-muted)" }}>
              {group.dates.length} 个交易日
            </span>
            <span className="h-px flex-1" style={{ background: "var(--color-border)" }} />
          </div>
          <div
            className="grid gap-1.5"
            style={{ gridTemplateColumns: "repeat(12, minmax(0, 1fr))" }}
          >
            {group.dates.map((date) => {
              const card = byDate.get(date);
              if (!card) return null;
              return (
                <DayCard
                  key={date}
                  card={card}
                  active={date === selected}
                  onPick={onPick}
                />
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

/** 选中日的完整传统字段（与参考图右栏「今日结论」位置对应，但只讲传统口径）。 */
function SelectedDayDetail({
  card,
  rule,
}: {
  card: ApiHuangliOutlook["days"][number];
  rule?: ApiHuangliOutlook["class_rule"];
}) {
  return (
    <div
      className="mt-2 rounded border p-2.5"
      style={{ borderColor: "var(--color-border-strong)", background: "rgba(0,0,0,0.18)" }}
      data-testid="huangli-selected-day"
    >
      <div className="flex flex-wrap items-baseline gap-2">
        <span className="smp-serif-title text-[16px]" style={{ color: "var(--color-gold-strong)" }}>
          {card.date}
        </span>
        <span className="text-[12px]" style={{ color: "var(--color-ink-sub)" }}>
          {card.weekday_cn} · {card.lunar_text || "农历（未返回）"}
        </span>
        <span
          className="rounded-[3px] px-1.5 py-[1px] text-[11.5px] font-semibold"
          style={{ color: "#0d1a25", background: classTone(card.class_code) }}
        >
          {classLabel(card)}
        </span>
        <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          {card.day_ganzhi}日 · {card.zodiac ? `${card.zodiac}年` : ""}
          {card.jieqi ? ` · 节气 ${card.jieqi}` : ""}
        </span>
      </div>

      <div className="mt-1.5 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
        {stripMdEmphasis(card.class_basis_cn)}
      </div>

      <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-4">
        <Detail label="建除十二值" value={`${card.duty_officer || "—"}日`} />
        <Detail
          label="十二神 / 黄黑道"
          value={
            card.day_tian_shen
              ? `${card.day_tian_shen}（${card.day_tian_shen_type || "—"}）`
              : "—"
          }
        />
        <Detail label="星宿" value={card.xiu ? `${card.xiu}（${card.xiu_luck || "—"}）` : "—"} />
        <Detail label="纳音" value={card.day_nayin || "—"} />
        <Detail
          label="冲煞"
          value={card.chong_desc ? `冲${card.chong_desc} 煞${card.sha_direction || "—"}` : "—"}
        />
        <Detail
          label="彭祖百忌"
          value={card.pengzu_gan ? `${card.pengzu_gan}；${card.pengzu_zhi}` : "—"}
        />
        <Detail
          label="吉神方位"
          value={
            [
              card.cai_shen_direction ? `财神${card.cai_shen_direction}` : "",
              card.xi_shen_direction ? `喜神${card.xi_shen_direction}` : "",
              card.fu_shen_direction ? `福神${card.fu_shen_direction}` : "",
            ]
              .filter(Boolean)
              .join(" · ") || "—"
          }
        />
        <Detail label="干支" value={`${card.year_ganzhi} ${card.month_ganzhi} ${card.day_ganzhi}`} />
      </div>

      <div className="mt-2 grid grid-cols-1 gap-2 md:grid-cols-2">
        <Matters label="宜（通书事宜）" items={card.day_yi} fallback="无特定事宜" tone="gold" />
        <Matters label="忌（通书禁忌）" items={card.day_ji} fallback="诸事不忌" tone="muted" />
      </div>

      <div className="mt-1.5 text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
        通书宜忌为传统择日观念，与证券价格没有已确认的因果关系；系统把它作为研究变量，
        历史表现见下方「黄历证据与历史表现」。
        {rule ? ` 分类口径：${rule.rule_id}。` : ""}
      </div>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border px-2 py-1" style={{ borderColor: "var(--color-border)" }}>
      <div className="text-[10.5px]" style={{ color: "var(--color-ink-muted)" }}>
        {label}
      </div>
      <div className="text-[12px]" style={{ color: "var(--color-ink)" }}>
        {value || "—"}
      </div>
    </div>
  );
}

function Matters({
  label,
  items,
  fallback,
  tone,
}: {
  label: string;
  items: string[];
  fallback: string;
  tone: "gold" | "muted";
}) {
  return (
    <div
      className="rounded border px-2 py-1.5"
      style={{
        borderColor: "var(--color-border)",
        background: tone === "gold" ? "rgba(212,184,122,0.05)" : "rgba(124,143,163,0.05)",
      }}
    >
      <div
        className="text-[11px] font-semibold"
        style={{ color: tone === "gold" ? "var(--color-gold)" : "var(--color-flat)" }}
      >
        {label}
      </div>
      <div className="mt-0.5 text-[12px] leading-relaxed" style={{ color: "var(--color-ink-sub)" }}>
        {items.length ? items.join("、") : fallback}
      </div>
    </div>
  );
}
