"use client";

/**
 * 黄历 / 日课详情页（复刻 doc/ui-reference/08_huangli_detail.png）。
 *
 * 视觉分区（uiux_spec §19 的要求）：
 *   ① **传统黄历数据**（建除十二值 / 十二神 / 黄黑道 / 冲煞 / 彭祖百忌 / 吉神方位）
 *      —— 这是历法与通书口径，不是对股票的判断；
 *   ② **与该股票原局的关系**（H_DAY_* / H_MONTH_* 因子）—— 这是本项目的研究映射。
 *
 * 两区之间必须视觉分离，避免读者把"今日宜开市"当成"该股今天会上涨"。
 */

import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, UnavailableBlock } from "@/components/shell/PageState";
import { IconCalendar, IconBook, IconTrend } from "@/components/shell/Icons";
import { api, endpoints } from "@/lib/api";
import { useAnalysis } from "@/lib/analysisStore";
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
  const { analysis, loading, error, reload } = useAnalysis(code);

  const [hl, setHl] = useState<HuangliResponse | null>(isMoutaiFixture ? (huangliFixture as unknown as HuangliResponse) : null);
  const [hlLoading, setHlLoading] = useState(!isMoutaiFixture);
  const [hlError, setHlError] = useState<string | null>(null);

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
  }, [analysis?.analysis_id, isMoutaiFixture, load]);

  const h = (hl?.huangli ?? {}) as Record<string, unknown>;
  const primary = (h.primary ?? h.today ?? h.day ?? h) as Record<string, unknown>;

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
      code={code}
      analysis={analysis}
      loading={loading}
      error={error}
      onReload={reload}
      loadingLabel="正在读取黄历与日课数据…"
    >
      {hlError ? (
        <Card testId="huangli-error">
          <div className="py-3 text-[13px]" style={{ color: "var(--color-warn)" }}>
            黄历数据加载失败：{hlError}
          </div>
        </Card>
      ) : null}

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
        {hlLoading ? (
          <div className="py-3 text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
            正在加载…
          </div>
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
                  style={{ borderColor: "var(--color-border)", background: "rgba(79,211,155,0.04)" }}
                >
                  <div className="text-[11.5px] font-semibold" style={{ color: "var(--color-down)" }}>
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
                  style={{ borderColor: "var(--color-border)", background: "rgba(232,88,90,0.04)" }}
                >
                  <div className="text-[11.5px] font-semibold" style={{ color: "var(--color-up)" }}>
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
        ) : !hlLoading ? (
          <UnavailableBlock
            what="黄历快照"
            reason="本次分析未保存黄历原始快照（可能分析未落库）。"
          />
        ) : null}
        <div className="mt-2">
          <SectionNote>
            <b>注意：</b>「宜开市 / 忌动土」这类通书条目描述的是传统择日观念，
            与证券价格没有任何已确认的因果关系。系统把它们作为<strong>研究变量</strong>，
            其历史有效性由历史验证页回答。
          </SectionNote>
        </div>
      </Card>

      {/* ===================== 分区二：与原局的关系（研究映射） ===================== */}
      <div
        className="rounded border-l-4 px-4 py-3"
        style={{ borderColor: "var(--color-flat)", background: "rgba(124,143,163,0.06)" }}
        data-testid="section-huangli-factors"
      >
        <div className="text-[13px] font-semibold" style={{ color: "var(--color-ink)" }}>
          ② 与股票原局的关系（本项目研究映射）
        </div>
        <div className="mt-0.5 text-[12px]" style={{ color: "var(--color-ink-muted)" }}>
          以下因子把「当日干支 / 建除 / 黄黑道」与股票原局交叉，属于本项目的<strong>研究变量</strong>，
          不是传统定论。
        </div>
      </div>

      <Card>
        <CardHeader icon={<IconTrend size={15} />} title={`黄历相关因子（${huangliFactors.length} 个）`} dense />
        {huangliFactors.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]" data-testid="huangli-factor-table">
              <thead>
                <tr style={{ color: "var(--color-ink-muted)" }}>
                  <th className="text-left">因子 ID</th>
                  <th className="text-left">名称</th>
                  <th className="text-right">归一化</th>
                  <th className="text-right">规则分</th>
                  <th className="text-left">说明</th>
                </tr>
              </thead>
              <tbody>
                {huangliFactors.map((f) => (
                  <tr key={f.factor_id} style={{ borderTop: "1px solid var(--color-border)" }}>
                    <td className="py-1">
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

export default function HuangliPage() {
  return (
    <Suspense fallback={<PageLoading />}>
      <HuangliInner />
    </Suspense>
  );
}
