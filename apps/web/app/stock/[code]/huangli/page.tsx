"use client";

/**
 * 黄历 / 日课详情页（复刻 doc/ui-reference/08_huangli_detail.png）。
 *
 * 首屏结构（本轮整改的核心）
 * --------------------------
 * 参考图的第一屏是**左右双栏**：左 ~60% 紧凑今日摘要 + 20 交易日卡（首屏看得到
 * 两行日期卡），右 ~40% 选中日详情。改造前这里是四段全宽纵向堆叠 + 三条大横幅，
 * 今日摘要独占整行、右栏消失，日期卡被推到 y≈849（选中日详情 y≈1075），
 * 两样都在 941px 首屏之外 —— 视觉差异 57.15%，十页中最大。
 *
 * 视觉分区（uiux_spec §19 的要求）依然保留，只是从"大横幅 + 长说明"
 * 改成"一行区段标签 + 可展开口径"：
 *   ① **传统黄历数据**（建除十二值 / 十二神 / 黄黑道 / 冲煞 / 彭祖百忌 / 吉神方位）
 *      —— 历法与通书口径，不是对股票的判断；
 *   ② **未来交易日黄历**（基准日之后的前 N 个交易日，来自实测交易日历）；
 *   ③ **黄历证据与历史表现**（按版本化日课分类的描述性统计）；
 *   ④ **与该股票原局的关系**（H_DAY_* / H_MONTH_* 因子）—— 本项目的研究映射。
 *
 * 每一块都是**区块级三态**：某一块慢或失败不会吞掉其它已加载的数据。
 * 风险与不可用状态（研究状态 / 日历覆盖不足 / 时辰不可用 / 因子缺失）
 * 一律常驻可见，不随折叠消失。
 */

import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import {
  HuangliOutlookGridCard,
  HuangliSelectedDayCard,
  HUANGLI_DEFAULT_TAB,
  useHuangliOutlook,
} from "@/components/huangli/HuangliTradingDayGrid";
import { HuangliPerformancePanel } from "@/components/huangli/HuangliPerformancePanel";
import { ResearchPage } from "@/components/shell/ResearchPage";
import { PageLoading, ResearchStatusBadge } from "@/components/shell/PageState";
import { SectionError, SectionLoading } from "@/components/shell/SectionState";
import { IconBook, IconCalendar, IconTrend } from "@/components/shell/Icons";
import { api, endpoints } from "@/lib/api";
import { useAnalysis } from "@/lib/analysisStore";
import { useBirthBasisParam } from "@/lib/useBirthBasisParam";
import { useHorizonParam } from "@/lib/useHorizonParam";
import { useAsOfParam } from "@/lib/useAsOfParam";
import { FIXTURE_QUERY_VALUE, huangliFixture } from "@/lib/fixture";

interface HuangliResponse {
  chart_id: string;
  engine_version: string;
  config_version: string;
  as_of: string;
  huangli: Record<string, unknown>;
}

/** 区段标签：一行、带序号与色标，替代改造前的全宽横幅。 */
function SectionLabel({
  index,
  title,
  tone,
  hint,
  testId,
}: {
  index: string;
  title: string;
  tone: "gold" | "info" | "muted";
  hint?: string;
  /** 分区身份必须可被测试与审计指认：沿用改造前的 data-testid，不换名。 */
  testId: string;
}) {
  const color =
    tone === "gold"
      ? "var(--color-gold)"
      : tone === "info"
        ? "var(--color-info)"
        : "var(--color-ink-sub)";
  return (
    <div className="flex flex-wrap items-baseline gap-2 pt-1" data-testid={testId}>
      <span
        className="rounded-[3px] px-1.5 py-[1px] text-[11px] font-semibold"
        style={{ color: "#0d1a25", background: color }}
      >
        {index}
      </span>
      <span
        className="text-[13.5px] font-semibold"
        style={{ color, fontFamily: "var(--font-serif-cn)" }}
      >
        {title}
      </span>
      {hint ? (
        <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
          {hint}
        </span>
      ) : null}
    </div>
  );
}

function HuangliInner() {
  const params = useParams<{ code: string }>();
  const searchParams = useSearchParams();
  const fixture = searchParams?.get("fixture") === FIXTURE_QUERY_VALUE;
  const code = params?.code ?? "600519";
  const isMoutaiFixture = fixture && code === "600519";
  // 基准日可由 URL 指定（研究复核 / 验收需要确定的时点）
  const asOf = useAsOfParam();
  const birthBasis = useBirthBasisParam();
  const horizon = useHorizonParam();
  const { analysis, loading, error, reload } = useAnalysis(
    code,
    "forward",
    asOf,
    birthBasis,
    horizon,
  );

  const [hl, setHl] = useState<HuangliResponse | null>(
    isMoutaiFixture ? (huangliFixture as unknown as HuangliResponse) : null,
  );
  const [hlLoading, setHlLoading] = useState(!isMoutaiFixture);
  const [hlError, setHlError] = useState<string | null>(null);
  const [hlNonce, setHlNonce] = useState(0);

  const analysisId = analysis?.analysis_id ?? null;

  const load = useCallback(
    async (id: string) => {
      if (isMoutaiFixture) {
        setHl(huangliFixture as unknown as HuangliResponse);
        setHlLoading(false);
        return;
      }
      setHlLoading(true);
      setHlError(null);
      try {
        setHl((await api.get(endpoints.huangli(id))) as HuangliResponse);
      } catch (e) {
        setHlError(e instanceof Error ? e.message : String(e));
      } finally {
        setHlLoading(false);
      }
    },
    [isMoutaiFixture],
  );

  useEffect(() => {
    if (isMoutaiFixture) {
      setHl(huangliFixture as unknown as HuangliResponse);
      setHlLoading(false);
      return;
    }
    if (analysis?.analysis_id) void load(analysis.analysis_id);
  }, [analysis?.analysis_id, isMoutaiFixture, load, hlNonce]);

  /* 未来交易日：取数只在这里发生一次，左右两栏共用同一份数据与选中状态。 */
  const [tab, setTab] = useState<string>(HUANGLI_DEFAULT_TAB);
  const outlook = useHuangliOutlook(analysisId, tab, hlNonce);
  const [pickedDate, setPickedDate] = useState<string | null>(null);
  const outlookSelected = useMemo(() => {
    if (pickedDate) return outlook.days.find((d) => d.date === pickedDate) ?? null;
    return outlook.days[0] ?? null;
  }, [outlook.days, pickedDate]);

  const h = (hl?.huangli ?? {}) as Record<string, unknown>;
  const primary = (h.primary ?? h.today ?? h.day ?? h) as Record<string, unknown>;

  // 黄历相关因子（H_*）—— 与传统黄历数据分区展示
  const huangliFactors = (analysis?.factors?.observations ?? []).filter((o) =>
    o.factor_id.startsWith("H_"),
  );

  const dateText =
    typeof primary.date === "string"
      ? primary.date
      : (hl?.as_of ?? "").slice(0, 10) || "—";

  const ganzhiText = `${String(primary.year_ganzhi ?? "—")}年 ${String(
    primary.month_ganzhi ?? "—",
  )}月 ${String(primary.day_ganzhi ?? "—")}日`;

  const jishenText = [
    primary.cai_shen_direction ? `财神${String(primary.cai_shen_direction)}` : "",
    primary.xi_shen_direction ? `喜神${String(primary.xi_shen_direction)}` : "",
    primary.fu_shen_direction ? `福神${String(primary.fu_shen_direction)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");

  const dayYi = Array.isArray(primary.day_yi) ? (primary.day_yi as string[]) : [];
  const dayJi = Array.isArray(primary.day_ji) ? (primary.day_ji as string[]) : [];

  const scanDate =
    (typeof primary.date === "string" && primary.date) ||
    asOf?.slice(0, 10) ||
    (hl?.as_of ?? "").slice(0, 10) ||
    "";

  return (
    <ResearchPage
      activeNav="huangli"
      heroVariant="research"
      title="黄历 / 日课详情"
      subtitle="观天时、择时机，以交易日历研判短中期节奏"
      seal="历"
      couplet={["观天时", "寻地利", "察人和", "知进退"]}
      motto={["顺势而为", "知行合一"]}
      code={code}
      analysis={analysis}
      loading={loading}
      error={error}
      onReload={reload}
      loadingLabel="正在读取黄历与日课数据…"
    >
      {/* ============ 第一屏：左 58% 今日摘要 + 交易日网格 / 右 42% 选中日详情 ============ */}
      {/* 分栏比按参考图 08 实测量定：左栏 x=233..1044（811px）、右栏 x=1071..1657（586px），
          扣除栏间距后约 58:42，故用 1.38fr:1fr（原先 1.5fr 让左栏宽出约 8px）。 */}
      <div className="grid grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,1.38fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-3" data-anchor="main-column">
          <SectionLabel
            index="①"
            title="传统黄历数据"
            tone="gold"
            hint="历法与通书口径，不是对股票的判断"
            testId="section-traditional-huangli"
          />

          <Card testId="traditional-huangli" anchor="primary-card">
            <CardHeader
              icon={<IconCalendar size={15} />}
              title="今日黄历简要"
              right={
                <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                  {dateText}
                  {hl?.engine_version ? (
                    <span className="smp-num ml-2" style={{ color: "var(--color-ink-faint)" }}>
                      {hl.engine_version}
                    </span>
                  ) : null}
                </span>
              }
              dense
            />
            {hlLoading ? <SectionLoading label="正在加载黄历快照…" rows={2} /> : null}
            {!hlLoading && hlError ? (
              <SectionError
                what="黄历快照"
                message={hlError}
                onRetry={() => {
                  setHlNonce((n) => n + 1);
                  if (analysisId) void load(analysisId);
                }}
                testId="huangli-error"
              />
            ) : null}
            {hl ? (
              <div className="p-3">
                {/* 三格主信息：农历干支 / 宜 / 忌（参考图同一层级） */}
                <div className="grid grid-cols-1 gap-2 md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.05fr)_minmax(0,1.05fr)]">
                  <div
                    className="rounded-[6px] border px-2.5 py-2"
                    style={{
                      borderColor: "var(--color-border)",
                      background: "rgba(158,42,34,0.10)",
                    }}
                  >
                    <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
                      农历 / 干支
                    </div>
                    <div
                      className="mt-0.5 text-[15px] leading-[20px]"
                      style={{ color: "var(--color-up)", fontFamily: "var(--font-serif-cn)" }}
                    >
                      {String(primary.lunar_text || "农历（未返回）")}
                    </div>
                    <div className="smp-num mt-1 text-[12.5px]" style={{ color: "var(--color-ink)" }}>
                      {ganzhiText}
                    </div>
                  </div>
                  <div
                    className="contents"
                    data-testid="traditional-matters"
                  >
                    <MattersTile
                      label="宜（通书事宜）"
                      items={dayYi}
                      fallback="无特定事宜"
                      tone="gold"
                    />
                    <MattersTile
                      label="忌（通书禁忌）"
                      items={dayJi}
                      fallback="诸事不忌"
                      tone="muted"
                    />
                  </div>
                </div>

                {/* 一行次要字段：值来自后端原样字段，缺就显示 —，不补值 */}
                <div
                  className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11.5px] md:grid-cols-4"
                  data-testid="huangli-fields"
                >
                  <MiniField
                    label="建除十二值"
                    value={primary.duty_officer ? `值日：${String(primary.duty_officer)}日` : "—"}
                  />
                  <MiniField
                    label="十二神 / 黄黑道"
                    value={
                      primary.day_tian_shen
                        ? `${String(primary.day_tian_shen)}（${String(
                            primary.day_tian_shen_type ?? "—",
                          )}·${String(primary.day_tian_shen_luck ?? "—")}）`
                        : "—"
                    }
                  />
                  <MiniField
                    label="冲煞"
                    value={
                      primary.chong_desc
                        ? `冲${String(primary.chong_desc)}${
                            primary.sha_direction ? ` 煞${String(primary.sha_direction)}` : ""
                          }`
                        : "—"
                    }
                  />
                  <MiniField
                    label="彭祖百忌"
                    value={
                      primary.pengzu_gan
                        ? `${String(primary.pengzu_gan)}；${String(primary.pengzu_zhi ?? "")}`
                        : "—"
                    }
                  />
                  <MiniField label="吉神方位" value={jishenText || "—"} />
                  <MiniField label="纳音" value={String(primary.day_nayin ?? "—")} />
                  <MiniField label="节气" value={String(primary.jieqi ?? "—")} />
                  <MiniField label="生肖" value={primary.zodiac ? `${String(primary.zodiac)}年` : "—"} />
                </div>

                {/* 完整口径说明收进 details：内容不删，只是不再占用首屏高度 */}
                <details className="mt-2">
                  <summary
                    className="cursor-pointer text-[11.5px]"
                    style={{ color: "var(--color-ink-muted)" }}
                  >
                    这些字段是什么、不是什么（口径与边界）
                  </summary>
                  <p
                    className="mt-1 rounded border px-2.5 py-2 text-[11.5px] leading-relaxed"
                    style={{
                      borderColor: "var(--color-border)",
                      color: "var(--color-ink-sub)",
                      background: "rgba(212,184,122,0.05)",
                    }}
                  >
                    这些字段来自 lunar-python 的通书口径，<strong>不是</strong>对股票收益的判断，
                    不同通书之间宜忌存在差异。「宜开市 / 忌动土」描述的是传统择日观念，与证券价格
                    没有任何已确认的因果关系；系统把它们作为<strong>研究变量</strong>，其历史有效性
                    由下方「③ 黄历证据与历史表现」回答。
                  </p>
                </details>
              </div>
            ) : !hlLoading && !hlError ? (
              <div className="p-3 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
                黄历快照不可用：本次分析未保存黄历原始快照（可能分析未落库）。
              </div>
            ) : null}
          </Card>

          <SectionLabel
            index="②"
            title="未来交易日黄历"
            tone="gold"
            hint="日期来自实测指数成交日序列"
            testId="section-future-huangli"
          />
          <HuangliOutlookGridCard
            state={outlook}
            tab={tab}
            onTab={setTab}
            selected={outlookSelected?.date ?? null}
            onPick={setPickedDate}
            onRetry={() => setHlNonce((n) => n + 1)}
          />
        </div>

        <div className="flex min-w-0 flex-col gap-3" data-anchor="detail-column">
          <HuangliSelectedDayCard
            selected={outlookSelected}
            rule={outlook.data?.class_rule}
            loading={outlook.loading}
            error={outlook.error}
          />

          {/* 数据状态常驻：研究状态 + 分类口径 + 日期来源，不因折叠消失 */}
          <div
            className="rounded border px-2.5 py-2 text-[11.5px] leading-relaxed"
            style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
            data-testid="huangli-data-status"
          >
            <div className="mb-1 font-semibold" style={{ color: "var(--color-ink-sub)" }}>
              数据状态
            </div>
            <div>
              交易日口径：{outlook.data ? `${outlook.data.exchange} 实测成交日` : "未读取"}；
              分类版本：
              <code className="smp-num">{outlook.data?.class_rule_version ?? "—"}</code>
            </div>
            <div className="mt-1">
              快照版本：engine <code className="smp-num">{hl?.engine_version ?? "—"}</code> · config{" "}
              <code className="smp-num">{hl?.config_version ?? "—"}</code> · as_of{" "}
              <code className="smp-num">{hl?.as_of ?? "—"}</code>
            </div>
            <div className="mt-1.5">
              <ResearchStatusBadge
                status={analysis?.consensus?.research_status ?? "NOT_RUN"}
                reasons={consensusReasons(analysis?.consensus)}
              />
            </div>
          </div>

          <div
            className="flex flex-wrap items-center justify-between gap-2 rounded border px-3 py-2 text-[12px]"
            style={{ borderColor: "var(--color-border)", background: "rgba(212,184,122,0.04)" }}
            data-testid="date-scan-link"
          >
            <span style={{ color: "var(--color-ink-muted)" }}>从指定日期查看全市场股票八字关系？</span>
            <Link
              className="smp-btn px-2.5 py-1"
              href={`/research/date-scan?date=${encodeURIComponent(scanDate)}`}
            >
              进入全市场择日研究 →
            </Link>
          </div>
        </div>
      </div>

      {/* ============ 第二屏：历史描述与统计 ============ */}
      <SectionLabel
        index="③"
        title="黄历证据与历史表现"
        tone="info"
        hint="本项目研究统计 · 描述性，不是策略回测"
        testId="section-huangli-performance"
      />
      <HuangliPerformancePanel analysisId={analysisId} />

      {/* ============ 后续区域：与原局的关系（研究映射） ============ */}
      <SectionLabel
        index="④"
        title="与股票原局的关系"
        tone="muted"
        hint="本项目研究映射，不是传统定论"
        testId="section-huangli-factors"
      />
      <Card testId="huangli-factors">
        <CardHeader
          icon={<IconTrend size={15} />}
          title={`黄历相关因子（${huangliFactors.length} 个）`}
          dense
        />
        {huangliFactors.length ? (
          <div className="overflow-x-auto">
            <table className="smp-table" data-testid="huangli-factor-table">
              <thead>
                <tr>
                  <th>因子 ID</th>
                  <th>名称</th>
                  <th className="text-right">归一化</th>
                  <th className="text-right">规则分</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                {huangliFactors.map((f) => (
                  <tr key={f.factor_id}>
                    <td>
                      <code>{f.factor_id}</code>
                    </td>
                    <td>{f.name}</td>
                    <td className="smp-num text-right">
                      {f.normalized_value === null ? "—" : f.normalized_value.toFixed(3)}
                    </td>
                    <td className="smp-num text-right">{f.rule_score.toFixed(2)}</td>
                    <td style={{ color: "var(--color-ink-muted)" }}>{f.explanation.slice(0, 60)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="p-3 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
            黄历因子不可用：本次分析未产出 H_* 因子（因子层不可用或分析未落库）。
          </div>
        )}
      </Card>

      <details className="mt-1">
        <summary
          className="cursor-pointer text-[12px]"
          style={{ color: "var(--color-ink-muted)" }}
          data-testid="huangli-provenance-toggle"
        >
          数据来源与版本（chart_id / engine_version / config_version / as_of）
        </summary>
        <Card className="mt-2">
          <CardHeader icon={<IconBook size={15} />} title="数据来源与版本" dense />
          <div className="space-y-1 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
            <div>chart_id：<code>{hl?.chart_id ?? "—"}</code></div>
            <div>engine_version：<code>{hl?.engine_version ?? "—"}</code></div>
            <div>config_version：<code>{hl?.config_version ?? "—"}</code></div>
            <div>as_of：<code>{hl?.as_of ?? "—"}</code></div>
          </div>
          <div className="px-3.5 pb-3 pt-2 text-[11.5px] leading-relaxed" style={{ color: "var(--color-ink-muted)" }}>
            原始黄历快照（raw_huangli）已落 <code>chart_artifact</code>，可用于审计与复算；
            业务层只消费结构化字段。未来交易日与历史表现分别由
            <code> /huangli/outlook </code>与<code> /huangli/performance </code>读出，
            二者都带口径版本与缓存标识。
          </div>
        </Card>
      </details>
    </ResearchPage>
  );
}

function MattersTile({
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
  const color = tone === "gold" ? "var(--color-gold)" : "var(--color-flat)";
  return (
    <div
      className="rounded-[6px] border px-2.5 py-2"
      style={{
        borderColor: tone === "gold" ? "rgba(79,211,155,0.30)" : "rgba(232,88,90,0.28)",
        background: tone === "gold" ? "rgba(79,211,155,0.07)" : "rgba(232,88,90,0.07)",
      }}
      data-testid={tone === "gold" ? "huangli-today-yi" : "huangli-today-ji"}
    >
      <div className="text-[11.5px] font-semibold" style={{ color }}>
        {label}
      </div>
      <div className="mt-0.5 text-[12.5px] leading-[18px]" style={{ color: "var(--color-ink-sub)" }}>
        {items.length ? items.join(" · ") : fallback}
      </div>
    </div>
  );
}

function MiniField({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 items-baseline gap-1.5">
      <span className="shrink-0" style={{ color: "var(--color-ink-muted)" }}>
        {label}
      </span>
      <span className="truncate" style={{ color: "var(--color-ink)" }} title={value}>
        {value || "—"}
      </span>
    </div>
  );
}

/** 研究状态的原因列表在 `historical_consensus_stats.reasons` 里（后端原样透出）。 */
function consensusReasons(
  consensus: { historical_consensus_stats?: Record<string, unknown> } | null | undefined,
): string[] {
  const raw = consensus?.historical_consensus_stats?.reasons;
  return Array.isArray(raw) ? raw.map((x) => String(x)) : [];
}

export default function HuangliPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <HuangliInner />
    </Suspense>
  );
}
