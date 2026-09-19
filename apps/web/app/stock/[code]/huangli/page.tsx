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

import { useParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import { Card, CardHeader } from "@/components/cards/Card";
import { ResearchPage, SectionNote } from "@/components/shell/ResearchPage";
import { PageLoading, UnavailableBlock } from "@/components/shell/PageState";
import { IconCalendar, IconBook, IconTrend } from "@/components/shell/Icons";
import { api, endpoints } from "@/lib/api";
import { useAnalysis } from "@/lib/analysisStore";

interface HuangliResponse {
  chart_id: string;
  engine_version: string;
  config_version: string;
  as_of: string;
  huangli: Record<string, unknown>;
}

function HuangliInner() {
  const params = useParams<{ code: string }>();
  const code = params?.code ?? "600519";
  const { analysis, loading, error, reload } = useAnalysis(code);

  const [hl, setHl] = useState<HuangliResponse | null>(null);
  const [hlLoading, setHlLoading] = useState(false);
  const [hlError, setHlError] = useState<string | null>(null);

  const load = useCallback(async (analysisId: string) => {
    setHlLoading(true);
    setHlError(null);
    try {
      setHl((await api.get(endpoints.huangli(analysisId))) as HuangliResponse);
    } catch (e) {
      setHlError(e instanceof Error ? e.message : String(e));
    } finally {
      setHlLoading(false);
    }
  }, []);

  useEffect(() => {
    if (analysis?.analysis_id) void load(analysis.analysis_id);
  }, [analysis?.analysis_id, load]);

  const h = (hl?.huangli ?? {}) as Record<string, unknown>;
  const day = (h.day ?? h) as Record<string, unknown>;
  const today = (h.today ?? day) as Record<string, unknown>;

  // 黄历相关因子（H_*）—— 与传统黄历数据分区展示
  const huangliFactors = (analysis?.factors?.observations ?? []).filter((o) =>
    o.factor_id.startsWith("H_"),
  );

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
          这些字段来自 lunar-python 的通书口径，**不是**对股票收益的判断。
          不同通书之间宜忌存在差异。
        </div>
      </div>

      <Card>
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
          <div className="grid grid-cols-3 gap-3 text-[12.5px]" data-testid="huangli-fields">
            <Field label="干支 / 农历" value={joinText(today, ["ganzhi", "lunar", "lunar_text", "lunar_date"])} />
            <Field label="生肖" value={joinText(today, ["zodiac", "year_zodiac"])} />
            <Field label="纳音" value={joinText(today, ["nayin", "day_nayin"])} />
            <Field label="建除十二值" value={joinText(today, ["duty_officer", "zhi_shen", "jian_chu"])} />
            <Field label="十二神 / 黄黑道" value={joinText(today, ["day_tian_shen", "tian_shen", "huang_dao", "tian_shen_type"])} />
            <Field label="冲煞" value={joinText(today, ["chong", "sha", "chong_sha"])} />
            <Field label="彭祖百忌" value={joinText(today, ["peng_zu", "pengzu"])} />
            <Field label="吉神方位" value={joinText(today, ["ji_shen_fang_wei", "cai_shen", "xi_shen", "fu_shen"])} />
            <Field label="节气" value={joinText(today, ["jieqi", "jie_qi"])} />
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
            与证券价格没有任何已确认的因果关系。系统把它们作为**研究变量**，
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
          以下因子把「当日干支 / 建除 / 黄黑道」与股票原局交叉，属于本项目的**研究变量**，
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
                  <tr key={f.factor_id} style={{ borderTop: "1px solid var(--color-line)" }}>
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
    <div className="rounded border p-2" style={{ borderColor: "var(--color-line)" }}>
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
