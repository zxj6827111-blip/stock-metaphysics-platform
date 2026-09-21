"use client";

/**
 * 黄历 / 日课详情页（复刻 doc/ui-reference/08_huangli_detail.png）。
 *
 * 视觉分区（uiux_spec §19 的要求）
 * -------------------------------
 *   ① **传统黄历数据**（建除十二值 / 十二神 / 黄黑道 / 冲煞 / 彭祖百忌 / 吉神方位）
 *      —— 这是历法与通书口径，不是对股票的判断；
 *   ② **未来交易日黄历**（基准日之后的前 N 个交易日，来自实测交易日历）；
 *   ③ **黄历证据与历史表现**（按版本化日课分类的描述性统计）；
 *   ④ **与该股票原局的关系**（H_DAY_* / H_MONTH_* 因子）—— 本项目的研究映射。
 *
 * 各区之间必须视觉分离，避免读者把"今日宜开市"当成"该股今天会上涨"。
 * 每一块都是**区块级三态**：某一块慢或失败不会吞掉其它已加载的数据。
 */

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { HuangliPerformancePanel } from "@/components/huangli/HuangliPerformancePanel";
import { HuangliTradingDayGrid } from "@/components/huangli/HuangliTradingDayGrid";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, ResearchStatusBadge, UnavailableBlock } from "@/components/shell/PageState";
import { SectionError, SectionLoading } from "@/components/shell/SectionState";
import { IconCalendar, IconBook, IconTrend } from "@/components/shell/Icons";
import { api, endpoints } from "@/lib/api";
import { useAnalysis } from "@/lib/analysisStore";
import { useAsOfParam } from "@/lib/useAsOfParam";
import { FIXTURE_QUERY_VALUE, huangliFixture } from "@/lib/fixture";

interface HuangliResponse {
  chart_id: string;
  engine_version: string;
  config_version: string;
  as_of: string;
  huangli: Record<string, unknown>;
}

function HuangliInner() {
  const params = useParams<{ code: string }>();
  const searchParams = useSearchParams();
  const fixture = searchParams?.get("fixture") === FIXTURE_QUERY_VALUE;
  const code = params?.code ?? "600519";
  const isMoutaiFixture = fixture && code === "600519";
  // 基准日可由 URL 指定（研究复核 / 验收需要确定的时点）
  const asOf = useAsOfParam();
  const { analysis, loading, error, reload } = useAnalysis(code, "forward", asOf);

  const [hl, setHl] = useState<HuangliResponse | null>(
    isMoutaiFixture ? (huangliFixture as unknown as HuangliResponse) : null,
  );
  const [hlLoading, setHlLoading] = useState(!isMoutaiFixture);
  const [hlError, setHlError] = useState<string | null>(null);
  const [hlNonce, setHlNonce] = useState(0);

  const load = useCallback(async (analysisId: string) => {
    if (isMoutaiFixture) {
      setHl(huangliFixture as unknown as HuangliResponse);
      setHlLoading(false);
      return;
    }
    setHlLoading(true);
    setHlError(null);
    try {
      setHl((await api.get(endpoints.huangli(analysisId))) as HuangliResponse);
    } catch (e) {
      setHlError(e instanceof Error ? e.message : String(e));
    } finally {
      setHlLoading(false);
    }
  }, [isMoutaiFixture]);

  useEffect(() => {
    if (isMoutaiFixture) {
      setHl(huangliFixture as unknown as HuangliResponse);
      setHlLoading(false);
      return;
    }
    if (analysis?.analysis_id) void load(analysis.analysis_id);
  }, [analysis?.analysis_id, isMoutaiFixture, load, hlNonce]);

  const h = (hl?.huangli ?? {}) as Record<string, unknown>;
  const primary = (h.primary ?? h.today ?? h.day ?? h) as Record<string, unknown>;
  const analysisId = analysis?.analysis_id ?? null;

  // 黄历相关因子（H_*）—— 与传统黄历数据分区展示
  const huangliFactors = (analysis?.factors?.observations ?? []).filter((o) =>
    o.factor_id.startsWith("H_"),
  );

  const ganzhiText = primary.day_ganzhi
    ? `${String(primary.day_ganzhi)} · 农历${String(primary.lunar_text ?? "")}`
    : joinText(primary, ["ganzhi", "lunar", "lunar_text", "lunar_date"]);

  const zodiacText = primary.zodiac
    ? `${String(primary.zodiac)}年`
    : joinText(primary, ["zodiac", "year_zodiac"]);

  const nayinText = primary.day_nayin
    ? String(primary.day_nayin)
    : joinText(primary, ["nayin", "day_nayin"]);

  const dutyText = primary.duty_officer
    ? `值日：${String(primary.duty_officer)}日`
    : joinText(primary, ["duty_officer", "zhi_shen", "jian_chu"]);

  const tianShenText = primary.day_tian_shen
    ? `${String(primary.day_tian_shen)}（${String(primary.day_tian_shen_type ?? "")}·${String(primary.day_tian_shen_luck ?? "")}）`
    : joinText(primary, ["day_tian_shen", "tian_shen", "huang_dao", "tian_shen_type"]);

  const chongText = primary.chong_desc
    ? `冲${String(primary.chong_desc)}${primary.sha_direction ? ` 煞${String(primary.sha_direction)}` : ""}`
    : joinText(primary, ["chong", "sha", "chong_sha"]);

  const pengzuText = primary.pengzu_gan
    ? `${String(primary.pengzu_gan)}；${String(primary.pengzu_zhi ?? "")}`
    : joinText(primary, ["peng_zu", "pengzu"]);

  const jishenText =
    [
      primary.cai_shen_direction ? `财神${String(primary.cai_shen_direction)}` : "",
      primary.xi_shen_direction ? `喜神${String(primary.xi_shen_direction)}` : "",
      primary.fu_shen_direction ? `福神${String(primary.fu_shen_direction)}` : "",
    ]
      .filter(Boolean)
      .join(" · ") || joinText(primary, ["ji_shen_fang_wei", "cai_shen", "xi_shen", "fu_shen"]);

  const jieqiText = primary.jieqi
    ? String(primary.jieqi)
    : joinText(primary, ["jieqi", "jie_qi"]);

  return (
    <ResearchPage
      activeNav="huangli"
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
      {/* ===================== 分区一：传统黄历数据 ===================== */}
      <div
        className="rounded border-l-4 px-4 py-3"
        style={{ borderColor: "var(--color-gold)", background: "rgba(212,160,74,0.06)" }}
        data-testid="section-traditional-huangli"
      >
        <div className="text-[13px] font-semibold" style={{ color: "var(--color-gold)" }}>
          ① 传统黄历数据（历法与通书口径）
        </div>
        <div className="mt-0.5 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          这些字段来自 lunar-python 的通书口径，<strong>不是</strong>对股票收益的判断。
          不同通书之间宜忌存在差异。
        </div>
      </div>

      <Card testId="traditional-huangli">
        <CardHeader
          icon={<IconCalendar size={15} />}
          title="今日黄历简要"
          right={
            <span className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
              {hl?.engine_version ?? ""}
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
          <div>
            <div className="grid grid-cols-3 gap-3 text-[12.5px]" data-testid="huangli-fields">
              <Field label="干支 / 农历" value={ganzhiText} />
              <Field label="生肖" value={zodiacText} />
              <Field label="纳音" value={nayinText} />
              <Field label="建除十二值" value={dutyText} />
              <Field label="十二神 / 黄黑道" value={tianShenText} />
              <Field label="冲煞" value={chongText} />
              <Field label="彭祖百忌" value={pengzuText} />
              <Field label="吉神方位" value={jishenText} />
              <Field label="节气" value={jieqiText} />
            </div>

            {Array.isArray(primary.day_yi) || Array.isArray(primary.day_ji) ? (
              <div className="mt-3 grid grid-cols-1 gap-2.5 md:grid-cols-2" data-testid="traditional-matters">
                <div
                  className="rounded border p-2.5"
                  style={{ borderColor: "var(--color-border)", background: "rgba(212,184,122,0.05)" }}
                >
                  <div className="text-[11.5px] font-semibold" style={{ color: "var(--color-gold)" }}>
                    宜（通书事宜）
                  </div>
                  <div className="mt-1 text-[12px] leading-relaxed" style={{ color: "var(--color-ink-sub)" }}>
                    {Array.isArray(primary.day_yi) && primary.day_yi.length
                      ? primary.day_yi.join("、")
                      : "无特定事宜"}
                  </div>
                </div>
                <div
                  className="rounded border p-2.5"
                  style={{ borderColor: "var(--color-border)", background: "rgba(124,143,163,0.05)" }}
                >
                  <div className="text-[11.5px] font-semibold" style={{ color: "var(--color-flat)" }}>
                    忌（通书禁忌）
                  </div>
                  <div className="mt-1 text-[12px] leading-relaxed" style={{ color: "var(--color-ink-sub)" }}>
                    {Array.isArray(primary.day_ji) && primary.day_ji.length
                      ? primary.day_ji.join("、")
                      : "诸事不忌"}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        ) : !hlLoading && !hlError ? (
          <UnavailableBlock
            what="黄历快照"
            reason="本次分析未保存黄历原始快照（可能分析未落库）。"
          />
        ) : null}
        <div className="mt-2">
          <SectionNote>
            <b>注意：</b>「宜开市 / 忌动土」这类通书条目描述的是传统择日观念，
            与证券价格没有任何已确认的因果关系。系统把它们作为<strong>研究变量</strong>，
            其历史有效性由下方「黄历证据与历史表现」回答。
          </SectionNote>
        </div>
      </Card>

      {/* ===================== 分区二：未来交易日黄历 ===================== */}
      <div
        className="rounded border-l-4 px-4 py-3"
        style={{ borderColor: "var(--color-gold)", background: "rgba(212,160,74,0.06)" }}
        data-testid="section-future-huangli"
      >
        <div className="text-[13px] font-semibold" style={{ color: "var(--color-gold)" }}>
          ② 未来交易日黄历（基准日之后的实际交易日）
        </div>
        <div className="mt-0.5 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          日期来自<strong>实测</strong>指数成交日序列，不是"排除周末"的近似：长假、休市日不会出现在卡片里。
          默认口径为「基准日当日或之后的前 20 个有效交易日」。
        </div>
      </div>

      <HuangliTradingDayGrid analysisId={analysisId} />

      {/* ===================== 分区三：证据与历史表现 ===================== */}
      <div
        className="rounded border-l-4 px-4 py-3"
        style={{ borderColor: "var(--color-info)", background: "rgba(107,143,212,0.06)" }}
        data-testid="section-huangli-performance"
      >
        <div className="text-[13px] font-semibold" style={{ color: "var(--color-info)" }}>
          ③ 黄历证据与历史表现（本项目研究统计）
        </div>
        <div className="mt-0.5 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          把交易日按<strong>版本化的传统日课分类</strong>分组，统计其后持有期收益的分布。
          这是<strong>描述性统计</strong>，不是策略回测：没有组合规则、仓位与交易成本，
          因此不提供净值或累计收益曲线。
        </div>
      </div>

      <HuangliPerformancePanel analysisId={analysisId} />

      {/* ===================== 分区四：与原局的关系（研究映射） ===================== */}
      <div
        className="rounded border-l-4 px-4 py-3"
        style={{ borderColor: "var(--color-flat)", background: "rgba(124,143,163,0.06)" }}
        data-testid="section-huangli-factors"
      >
        <div className="text-[13px] font-semibold" style={{ color: "var(--color-ink)" }}>
          ④ 与股票原局的关系（本项目研究映射）
        </div>
        <div className="mt-0.5 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          以下因子把「当日干支 / 建除 / 黄黑道」与股票原局交叉，属于本项目的<strong>研究变量</strong>，
          不是传统定论。
        </div>
      </div>

      <Card>
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
          <UnavailableBlock
            what="黄历因子"
            reason="本次分析未产出 H_* 因子（因子层不可用或分析未落库）。"
          />
        )}
        <div className="mt-2">
          <ResearchStatusBadge
            status={analysis?.consensus?.research_status ?? "NOT_RUN"}
            reasons={consensusReasons(analysis?.consensus)}
          />
        </div>
      </Card>

      <Card>
        <CardHeader icon={<IconBook size={15} />} title="数据来源与版本" dense />
        <div className="space-y-1 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          <div>chart_id：<code>{hl?.chart_id ?? "—"}</code></div>
          <div>engine_version：<code>{hl?.engine_version ?? "—"}</code></div>
          <div>config_version：<code>{hl?.config_version ?? "—"}</code></div>
          <div>as_of：<code>{hl?.as_of ?? "—"}</code></div>
        </div>
        <div className="mt-2">
          <SectionNote>
            原始黄历快照（raw_huangli）已落 <code>chart_artifact</code>，
            可用于审计与复算；业务层只消费结构化字段。
            未来交易日与历史表现分别由
            <code> /huangli/outlook </code>与<code> /huangli/performance </code>读出，
            二者都带口径版本与缓存标识。
          </SectionNote>
        </div>
      </Card>
    </ResearchPage>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border p-2" style={{ borderColor: "var(--color-border)" }}>
      <div className="text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
        {label}
      </div>
      <div className="mt-0.5">{value || "—"}</div>
    </div>
  );
}

function joinText(obj: Record<string, unknown>, keys: string[]): string {
  const out: string[] = [];
  for (const k of keys) {
    const v = obj[k];
    if (v === undefined || v === null) continue;
    out.push(typeof v === "string" ? v : JSON.stringify(v));
  }
  return out.join(" · ");
}

/** 研究状态的原因列表在 `historical_consensus_stats.reasons` 里（后端原样透出）。 */
function consensusReasons(consensus: { historical_consensus_stats?: Record<string, unknown> } | null | undefined): string[] {
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
