"use client";

/**
 * 综合研判页（复刻 doc/ui-reference/02_integrated_analysis.png）。
 *
 * 首屏必须同时回答（uiux_spec §7）：
 *   A. 各术数模型怎么看    → EngineScoreCard ×3
 *   B. 是否形成共振        → ConsensusCard
 *   C. 是否存在明显冲突    → ConflictCard
 *   D. 历史统计支持强不强  → BacktestMetricCard + 分布图
 *   E. 数据质量如何        → DataQualityBadge
 *
 * 生产 runtime 读真实 API；`?fixture=ui-reference` 时用固定演示数据。
 */

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/shell/AppShell";
import { PageHero } from "@/components/shell/TopBar";
import { ExportMenu, StockContextBar } from "@/components/stock/StockContextBar";
import { Card, CardHeader } from "@/components/cards/Card";
import {
  BacktestMetricCard,
  ConflictCard,
  ConsensusCard,
  DataQualityBadge,
  EngineScoreCard,
  EvidenceRow,
} from "@/components/cards/EngineCards";
import { DistributionChart, TimeWindowChart } from "@/components/charts/Charts";
import { EvidenceDrawer } from "@/components/evidence/EvidenceDrawer";
import {
  IconBook,
  IconChart,
  IconGrid,
  IconTarget,
  IconTrend,
} from "@/components/shell/Icons";
import { FIXTURE_QUERY_VALUE, multiAnalysisFixture, overviewFixture } from "@/lib/fixture";
import {
  buildContextFromMulti,
  buildOverview,
  horizonLabel,
  pickEvidenceSummary,
  toConflictView,
  toConsensusView,
  toDataQualityView,
  toEngineCardsFromOpinions,
} from "@/lib/dataSource";
import {
  api,
  endpoints,
  type ApiConsensus,
  type ApiConflict,
  type ApiEventStudy,
  type ApiEvidence,
  type ApiMultiAnalysis,
} from "@/lib/api";
import { buildExportTarget } from "@/lib/reportExport";
import {
  DEFAULT_BIRTH_BASIS,
  DEFAULT_HORIZON,
  invalidateAnalysis,
  loadMultiAnalysis,
  type AnalysisKey,
} from "@/lib/analysisStore";
import { analysisContextSuffix, withAnalysisContext } from "@/lib/analysisContext";
import { useAsOfParam } from "@/lib/useAsOfParam";
import { useBirthBasisParam } from "@/lib/useBirthBasisParam";
import { useHorizonParam } from "@/lib/useHorizonParam";
import { researchStatusLabel } from "@/components/shell/PageState";
import type { OverviewPageData } from "@/lib/types";

function OverviewInner() {
  const routeParams = useParams<{ code: string }>();
  const code = routeParams?.code ?? "600519";
  const search = useSearchParams();
  const fixture = search.get("fixture") === FIXTURE_QUERY_VALUE;
  const isMoutaiFixture = fixture && code === "600519";
  const isUnsupportedFixture = fixture && code !== "600519";
  // 出生模型同样属于分析上下文：切换即重新分析
  const birthBasis = useBirthBasisParam();
  const horizon = useHorizonParam();
  // 基准日也是分析身份的一部分：不带 asOf 就无法复核"当时那个时点的盘"
  const asOf = useAsOfParam();
  /**
   * 这份分析的唯一身份。
   *
   * 强制重算与读取**必须用同一个对象**：之前 force 分支只传
   * `{ code, variant }`，读取却带 `birthBasis` / `horizon`，两个 key 不同，
   * 于是点「重新计算」清掉的是另一条缓存，页面照样命中旧分析结果。
   *
   * `variant` 用 `"forward"` —— 与 `useAnalysis` 的默认值一致，
   * 否则页面加载走 A 键、点重算走 B 键，身份又对不上。
   */
  const analysisKey = useMemo<AnalysisKey>(
    () => ({ code, variant: "forward", asOf, birthBasis, horizon }),
    [code, asOf, birthBasis, horizon],
  );
  // 演示样本冻结在默认出生模型上：换成别的假设时**不能用它冒充**，
  // 明确显示为「演示模式不适用」并给出进入真实模式的入口。
  const isFixtureContextUnsupported = fixture && birthBasis !== DEFAULT_BIRTH_BASIS;

  const [data, setData] = useState<OverviewPageData | null>(
    isMoutaiFixture ? fixtureOverview(horizon) : null,
  );
  const [loading, setLoading] = useState(!isMoutaiFixture && !isUnsupportedFixture);
  const [error, setError] = useState<string | null>(null);
  const [drawer, setDrawer] = useState(false);
  const [evidenceExpanded, setEvidenceExpanded] = useState(false);
  const [analysisId, setAnalysisId] = useState<string>("");
  // 导出报告冻结**这一次**的上下文快照，因此保留整份 multi 结果：
  // 只留 analysis_id 时，导出过程中切标的会把新股票的数据混进报告。
  const [multiAnalysis, setMultiAnalysis] = useState<ApiMultiAnalysis | null>(null);
  const [researchStatus, setResearchStatus] = useState<string>("NOT_RUN");
  const [drawerData, setDrawerData] = useState<{
    supporting: never[];
    counter: never[];
    neutral: never[];
    note?: string;
    method?: string;
  }>({ supporting: [], counter: [], neutral: [] });

  const load = useCallback(async (force = false) => {
    if (isFixtureContextUnsupported) {
      setLoading(false);
      return;
    }
    if (isMoutaiFixture) {
      // `horizon` 只是登记标签、不改变盘面，所以演示样本按当前登记的窗口回显，
      // 保证「页面显示 / 请求上下文 / 导出快照」三处是同一个值。
      setData(fixtureOverview(horizon));
      // 演示模式同样要有可导出的上下文快照：`multiAnalysisFixture` 是
      // 与真实接口同结构的冻结样本，导出时会逐份标注"演示数据"。
      setMultiAnalysis({ ...multiAnalysisFixture, horizon });
      setLoading(false);
      return;
    }
    if (isUnsupportedFixture) {
      setLoading(false);
      return;
    }
    if (force) {
      invalidateAnalysis(analysisKey);
    }
    setLoading(true);
    setError(null);
    try {
      // Phase 2：综合页的数据源改为 `/analysis/multi` —— 它同时产出
      // BaziOpinion / ZiweiOpinion / HuangliOpinion / Consensus / Conflict，
      // 全部来自正式 ConsensusEngine 与 ConflictDetector，
      // **不再是展示层 fixture aggregation**。
      const multi = await loadMultiAnalysis(analysisKey);
      const aid = multi.analysis_id;

      // 三模型观点：直接消费后端 opinion，前端**不重算分数**
      const base = buildContextFromMulti(multi);
      // 引擎卡跳转必须带上整份分析上下文，否则落地页会静默换假设
      const suffix = analysisContextSuffix(search);
      const engines = toEngineCardsFromOpinions(multi, suffix);

      const [consensusRes, conflictRes, backtestRes, evidenceRes] = await Promise.allSettled([
        api.get<ApiConsensus>(endpoints.consensus(aid)),
        api.get<ApiConflict>(endpoints.conflicts(aid)),
        api.get<ApiEventStudy>(endpoints.backtest(aid)),
        api.get<ApiEvidence>(endpoints.evidence(aid)),
      ]);

      const consensusData =
        consensusRes.status === "fulfilled"
          ? consensusRes.value
          : multi.consensus ?? null;
      const consensusView = consensusData
        ? toConsensusView(consensusData)
        : isMoutaiFixture
          ? overviewFixture.consensus
          : null;

      const conflictData =
        conflictRes.status === "fulfilled"
          ? conflictRes.value
          : multi.conflict ?? null;
      const conflictView = conflictData
        ? toConflictView(conflictData)
        : isMoutaiFixture
          ? overviewFixture.conflict
          : null;

      // 数据质量卡的每一项都要能指回真实字段：出生档案、版本戳、古籍检索结果。
      // 证据接口失败时 `evidenceItems` 传 null ⇒ 卡片显示「未验证」而不是绿勾。
      const dq = toDataQualityView({
        grade: base.quality,
        notes: multi.birth_profile.data_quality?.notes ?? [],
        engineVersion: multi.versions?.engine_version || null,
        birthProfile: multi.birth_profile,
        evidenceItems:
          evidenceRes.status === "fulfilled"
            ? [
                ...evidenceRes.value.evidence.supporting_evidence,
                ...evidenceRes.value.evidence.counter_evidence,
                ...evidenceRes.value.evidence.neutral_evidence,
              ]
            : null,
      });

      setData(
        buildOverview(
          code,
          base,
          engines,
          consensusView,
          conflictView,
          backtestRes.status === "fulfilled" ? backtestRes.value : null,
          evidenceRes.status === "fulfilled" ? evidenceRes.value : null,
          dq,
          isMoutaiFixture,
        ),
      );
      if (evidenceRes.status === "fulfilled") {
        setDrawerData({
          supporting: evidenceRes.value.evidence.supporting_evidence as never[],
          counter: evidenceRes.value.evidence.counter_evidence as never[],
          neutral: evidenceRes.value.evidence.neutral_evidence as never[],
          note: evidenceRes.value.evidence.note,
          method: evidenceRes.value.evidence.retrieval_method,
        });
      }
      setResearchStatus(
        consensusRes.status === "fulfilled"
          ? (consensusRes.value.research_status ?? "NOT_RUN")
          : (multi.consensus?.research_status ?? "NOT_RUN"),
      );
      setAnalysisId(aid);
      setMultiAnalysis(multi);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      if (isMoutaiFixture) {
        setData(overviewFixture);
      } else {
        setData(null);
      }
    } finally {
      setLoading(false);
    }
  }, [code, fixture, isMoutaiFixture, isUnsupportedFixture, analysisKey, horizon]);

  useEffect(() => {
    if (!isMoutaiFixture && !isUnsupportedFixture) void load();
  }, [isMoutaiFixture, isUnsupportedFixture, isFixtureContextUnsupported, load]);

  /**
   * 演示模式下也要准备导出快照。
   *
   * 上面那条 effect 在 fixture 时**故意不调用 `load()`**（演示面板直接读固定样本），
   * 因此 `multiAnalysis` 会一直是 null，导出按钮就成了永久禁用的假按钮。
   * 这里补上：把同结构的冻结样本放进 `multiAnalysis`，导出时逐份标注「演示数据」。
   */
  useEffect(() => {
    if (isMoutaiFixture) setMultiAnalysis({ ...multiAnalysisFixture, horizon });
  }, [isMoutaiFixture, horizon]);

  // 演示面板由 useEffect 之外的初始 state 提供，
  // 切换登记窗口时这里补一次同步（load() 在演示模式下不会被调用）。
  useEffect(() => {
    if (isMoutaiFixture) setData(fixtureOverview(horizon));
  }, [isMoutaiFixture, horizon]);

  // fixture 模式下同样准备抽屉数据（用演示条目）
  useEffect(() => {
    if (!isMoutaiFixture) return;
    setDrawerData({
      supporting: [],
      counter: [],
      neutral: [],
      note: "UI 复刻模式下不加载真实古籍检索结果。移除 URL 中的 fixture 参数即可查看真实证据。",
      method: "bm25 + topic_match + authority_weight + domain_filter",
    });
  }, [isMoutaiFixture]);

  /**
   * 冻结的导出目标。
   *
   * 报告正文由后端 `render_report` 渲染（含版本 / 假设 / 限制 / ResearchStatus /
   * 负对照），前端只负责触发下载，不参与内容拼装。
   */
  const exportTarget = useMemo(
    () => buildExportTarget(multiAnalysis, multiAnalysis?.analysis_id, fixture),
    [multiAnalysis, fixture],
  );

  const metrics = useMemo(() => data?.backtestMetrics ?? [], [data]);

  /**
   * 页内跳转统一带分析上下文（见 lib/analysisContext.ts）。
   *
   * 演示夹具里的 `detailHref` 是冻结时拼好的，带的是**当时**的上下文，
   * 所以这里用 URL 上此刻的选择逐项覆盖 —— 否则"选了 60d 点进详情却回到 20d"。
   */
  const contextSuffix = analysisContextSuffix(search);
  const engines = useMemo(
    () => (data?.engines ?? []).map((e) => ({ ...e, detailHref: withAnalysisContext(e.detailHref, search) })),
    [data, search],
  );

  if (isFixtureContextUnsupported) {
    return (
      <AppShell activeNav="overview" dataStatus="bad" statusText="演示模式受限">
        <PageHero
          title="综合研判"
          subtitle="八字 · 紫微 · 黄历三模型共识与分歧研究"
          seal="研"
        />
        <Card className="my-4 p-6" testId="fixture-basis-unsupported">
          <div className="flex items-start gap-3">
            <span className="text-[24px]">⚠️</span>
            <div className="space-y-2">
              <h3 className="text-[16px] font-semibold" style={{ color: "var(--color-warn)" }}>
                演示模式不提供该上下文下的结果
              </h3>
              <p className="text-[13px] leading-relaxed" style={{ color: "var(--color-ink-sub)" }}>
                演示样本冻结在默认上下文<strong>「上市首日正式开盘 + 20d 研究窗口」</strong>上。
                当前 URL 指定的是出生模型 <code className="smp-num">{birthBasis}</code> /
                研究窗口 <code className="smp-num">{horizon}</code>；拿别的上下文的请求返回这份
                样本，等于把「假设 A 的盘」标成「假设 B 的盘」—— 系统不会这样做。
              </p>
              <div className="flex items-center gap-3 pt-2">
                <Link
                  href={`/stock/${code}/overview?fixture=${FIXTURE_QUERY_VALUE}&birthBasis=${DEFAULT_BIRTH_BASIS}&horizon=${DEFAULT_HORIZON}`}
                  className="smp-btn smp-btn--primary"
                  data-testid="reset-birth-basis-btn"
                >
                  回到默认上下文（演示样本）
                </Link>
                <Link href={`/stock/${code}/overview`} className="smp-btn">
                  移除 fixture 参数并进入真实分析模式
                </Link>
              </div>
            </div>
          </div>
        </Card>
      </AppShell>
    );
  }

  if (isUnsupportedFixture) {
    return (
      <AppShell activeNav="overview" dataStatus="bad" statusText="演示模式受限">
        <PageHero
          title="综合研判"
          subtitle="八字 · 紫微 · 黄历三模型共识与分歧研究"
          seal="研"
        />
        <Card className="my-4 p-6" testId="unsupported-fixture-error">
          <div className="flex items-start gap-3">
            <span className="text-[24px]">⚠️</span>
            <div className="space-y-2">
              <h3 className="text-[16px] font-semibold" style={{ color: "var(--color-warn)" }}>
                演示模式（UI 复刻）仅支持 600519（贵州茅台）
              </h3>
              <p className="text-[13px] leading-relaxed" style={{ color: "var(--color-ink-sub)" }}>
                当前访问标的为 <code className="smp-num rounded border px-1.5 py-0.5">{code}</code>。
                为严格保证数据隔离，系统在演示模式下<strong>已统一阻断对真实后端的排盘分析与持久化请求</strong>，
                禁止静默进入真实模式。
              </p>
              <div className="flex items-center gap-3 pt-2">
                <Link
                  href={`/stock/${code}/overview`}
                  className="smp-btn smp-btn--primary"
                  data-testid="enter-real-mode-btn"
                >
                  移除 fixture 参数并进入真实分析模式
                </Link>
                <Link
                  href={`/stock/600519/overview?fixture=${FIXTURE_QUERY_VALUE}`}
                  className="smp-btn"
                >
                  返回 600519 演示标的
                </Link>
              </div>
            </div>
          </div>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell activeNav="overview" dataStatus={error ? "bad" : "ok"} statusText={error ? "后端未连接" : "数据正常"}>
      <PageHero
        variant="research"
        title="综合研判"
        subtitle="多模型交叉验证 · 识别趋势共识 · 提示关键风险"
        seal="正"
        right={
          <div className="flex items-center gap-2" data-testid="report-export">
            <ExportMenu target={exportTarget} />
            <span className="text-[11px]" style={{ color: "var(--color-ink-muted)" }}>
              研究状态：{researchStatusLabel(researchStatus)}
            </span>
          </div>
        }
      />

      {data ? (
        <StockContextBar
          context={data.context}
          activeTab="overview"
          onRecalculate={() => void load(true)}
          recalculating={loading}
          exportTarget={exportTarget}
        />
      ) : null}

      {error && !fixture ? (
        <Card className="mb-3 p-4" testId="overview-error">
          <div className="text-[13px]" style={{ color: "var(--color-warn)" }}>
            后端数据加载失败：{error}
          </div>
          <p className="mt-2 text-[11.5px]" style={{ color: "var(--color-ink-muted)" }}>
            请确认 API 已启动（<code className="smp-num">uvicorn apps.api.main:app --port 8000</code>）。
            如需查看参考图复刻效果，请访问{" "}
            <code className="smp-num">?fixture=ui-reference</code>。
          </p>
        </Card>
      ) : null}

      {loading && !data ? <SkeletonOverview /> : null}

      {/* 数据可用性横幅：合成/降级行情时必须显著告警（P0-1 验收要求） */}
      {data?.researchStatus === "NO_REAL_DATA" ? (
        <div
          data-testid="synthetic-data-banner"
          className="mb-3 flex items-start gap-3 border px-4 py-3 text-[12.5px] leading-relaxed"
          style={{
            borderColor: "var(--color-warn)",
            background: "color-mix(in srgb, var(--color-warn) 11%, transparent)",
            color: "var(--color-warn)",
          }}
        >
          <span className="mt-[1px] shrink-0 text-[15px]" aria-hidden>
            ⚠
          </span>
          <div>
            <div className="font-semibold">
              当前为合成/降级行情，仅用于系统联调，不构成历史研究证据（RESEARCH_DATA_UNAVAILABLE）
            </div>
            <div className="mt-1 text-[11.5px] opacity-85">
              历史验证卡片、上涨率与事件研究仅代表前端/链路测试输出；真实研究结论必须基于
              真实历史行情运行 <code className="smp-num">POST /api/v1/research/run</code>。
              {(data.researchStatusReasons ?? []).map((r, i) => (
                <span key={i} className="mt-1 block">{r}</span>
              ))}
            </div>
          </div>
        </div>
      ) : null}

      {data ? (
        <>
          {/* A + B + C (约 50:29:21 比例) */}
          <div className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(0,2fr)_minmax(0,1.16fr)_minmax(0,0.84fr)]">
            <Card testId="engine-scores" anchor="primary-card">
              <CardHeader
                icon={<IconGrid size={14} />}
                title="模型评分与判断"
                dense
                right={
                  <span className="text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                    分数 = 传统规则强度聚合（非收益预测）
                  </span>
                }
              />
              <div className="grid grid-cols-1 gap-2 p-2.5 md:grid-cols-3">
                {engines.map((e) => (
                  <EngineScoreCard key={e.engine} engine={e} />
                ))}
              </div>
            </Card>

            <ConsensusCard consensus={data.consensus} />
            <ConflictCard conflict={data.conflict} />
          </div>

          {/* D + E + F：下部双列独立垂直堆叠 (58% : 42%) */}
          <div className="mt-3 grid grid-cols-1 items-start gap-3 xl:grid-cols-[minmax(0,1.38fr)_minmax(0,1fr)]">
            {/* 左列 (58%)：未来时间窗口 + 历史验证摘要（保障 y <= 760px 进入首屏） */}
            <div className="flex flex-col gap-3">
              <Card testId="time-window">
                <CardHeader
                  icon={<IconChart size={14} />}
                  title="未来时间窗口"
                  dense
                  right={
                    <div className="flex items-center gap-1">
                      {["近1月", "近3月", "近6月", "未来1年"].map((t, i) => (
                        <span
                          key={t}
                          className="rounded-[4px] border px-2 py-[1px] text-[10.5px]"
                          style={{
                            borderColor: i === 3 ? "var(--color-gold-dim)" : "var(--color-border)",
                            background: i === 3 ? "var(--color-gold-ghost)" : "transparent",
                            color: i === 3 ? "var(--color-gold)" : "var(--color-ink-muted)",
                          }}
                        >
                          {t}
                        </span>
                      ))}
                    </div>
                  }
                  action={{
                    label: "打开时间窗口页",
                    href: `/stock/${code}/timeline${contextSuffix}`,
                    testId: "time-window-open-link",
                  }}
                />
                <div className="px-3 py-1.5">
                  {data.timeWindow.series.length > 0 ? (
                    <>
                      <div className="mb-1 flex items-center gap-3 px-1 text-[11.5px]">
                        {data.timeWindow.series.map((s2) => (
                          <span key={s2.key} className="flex items-center gap-1">
                            <span
                              className="inline-block h-[3px] w-[12px] rounded-full"
                              style={{ background: s2.color }}
                            />
                            <span style={{ color: "var(--color-ink-sub)" }}>{s2.name}</span>
                          </span>
                        ))}
                        <span className="ml-2 flex items-center gap-1">
                          <span
                            className="inline-block h-[8px] w-[12px] rounded-[2px]"
                            style={{ background: "rgba(79,211,155,0.22)", border: "1px solid rgba(79,211,155,0.45)" }}
                          />
                          <span style={{ color: "var(--color-ink-sub)" }}>高共识区</span>
                        </span>
                        <span className="flex items-center gap-1">
                          <span
                            className="inline-block h-[8px] w-[12px] rounded-[2px]"
                            style={{ background: "rgba(176,124,214,0.22)", border: "1px solid rgba(176,124,214,0.45)" }}
                          />
                          <span style={{ color: "var(--color-ink-sub)" }}>高冲突区</span>
                        </span>
                      </div>
                      <TimeWindowChart data={data.timeWindow} height={122} />
                      <p className="px-1 pb-1 pt-1 text-[11px]" style={{ color: "var(--color-ink-faint)" }}>
                        纵轴为术数研究指数（0-100 规则强度），不是收益率或上涨概率。逐窗口的完整解读在
                        <Link
                          href={`/stock/${code}/timeline${contextSuffix}`}
                          style={{ color: "var(--color-gold)" }}
                        >
                          时间窗口
                        </Link>
                        页。
                      </p>
                    </>
                  ) : (
                    <div className="flex h-[122px] flex-col items-center justify-center text-center">
                      <p className="text-[12.5px]" style={{ color: "var(--color-ink-muted)" }}>
                        未来时间窗口外推尚未运行（系统不提供伪造预测曲线）
                      </p>
                      <p className="mt-1 text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
                        时间窗口页已上线，可查看基于实测交易日历的窗口与排名：
                        <Link
                          href={`/stock/${code}/timeline${contextSuffix}`}
                          style={{ color: "var(--color-gold)" }}
                          data-testid="time-window-empty-link"
                        >
                          前往时间窗口页
                        </Link>
                      </p>
                    </div>
                  )}
                </div>
              </Card>

              <Card testId="backtest-summary">
                <CardHeader
                  icon={<IconTrend size={14} />}
                  title="历史验证摘要"
                  action={{
                    label: "历史验证详情",
                    href: `/stock/${code}/backtest${contextSuffix}`,
                    testId: "backtest-detail-link",
                  }}
                  dense
                />
                <div className="grid grid-cols-2 gap-2.5 p-3 md:grid-cols-5">
                  {metrics.map((m) => (
                    <BacktestMetricCard key={m.key} metric={m} />
                  ))}
                </div>
                <div className="grid grid-cols-1 gap-4 px-3 pb-3 md:grid-cols-[minmax(0,1fr)_280px]">
                  <div>
                    <div className="smp-metric-label mb-1">收益分布（示意）</div>
                    {data.distribution.length ? (
                      <DistributionChart bins={data.distribution} height={96} />
                    ) : (
                      <div className="py-5 text-center text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
                        尚无历史验证样本分布数据（不采用正态假设伪造分箱）
                      </div>
                    )}
                  </div>
                  <div>
                    <div className="smp-metric-label mb-1">历史验证结论</div>
                    <p className="text-[11.5px] leading-[17px]" style={{ color: "var(--color-ink-sub)" }}>
                      {data.backtestConclusion}
                    </p>
                  </div>
                </div>
              </Card>
            </div>

            {/* 右列 (42%)：关键证据 + 数据质量与风险 */}
            <div className="flex flex-col gap-3">
              <Card testId="key-evidence" anchor="right-summary">
                <CardHeader
                  icon={<IconBook size={14} />}
                  title={`关键证据${data.evidence.length > 3 ? `（摘要 3 / 共 ${data.evidence.length}）` : ""}`}
                  action={{ label: "查看更多", onClick: () => setDrawer(true), testId: "evidence-more-btn" }}
                />
                <div className="space-y-2 p-3">
                  {data.evidence.length === 0 ? (
                    <div className="py-6 text-center text-[12px]" style={{ color: "var(--color-ink-faint)" }}>
                      暂无证据条目
                    </div>
                  ) : (
                    <>
                      {(evidenceExpanded
                        ? data.evidence
                        : pickEvidenceSummary(data.evidence, 3)
                      ).map((ev) => (
                        <EvidenceRow key={ev.id} item={ev} />
                      ))}
                      {data.evidence.length > 3 ? (
                        <button
                          type="button"
                          className="w-full rounded-[6px] border py-1 text-[11.5px] transition-opacity hover:opacity-80"
                          style={{ borderColor: "var(--color-border)", color: "var(--color-ink-muted)" }}
                          onClick={() => setEvidenceExpanded((v) => !v)}
                          data-testid="evidence-toggle"
                        >
                          {evidenceExpanded
                            ? "收起证据摘要"
                            : `展开其余 ${data.evidence.length - 3} 条证据`}
                        </button>
                      ) : null}
                    </>
                  )}
                </div>
              </Card>

              <DataQualityBadge quality={data.dataQuality} />
            </div>
          </div>

          <div className="mt-3 flex items-center justify-center gap-2 text-[11.5px]" style={{ color: "var(--color-ink-faint)" }}>
            <IconTarget size={13} />
            本页不显示"综合总分"：共识与历史有效性分列展示，任一模型失败不影响其他模型。
          </div>
        </>
      ) : null}

      <EvidenceDrawer
        open={drawer}
        onClose={() => setDrawer(false)}
        supporting={drawerData.supporting}
        counter={drawerData.counter}
        neutral={drawerData.neutral}
        note={drawerData.note}
        retrievalMethod={drawerData.method}
      />
    </AppShell>
  );
}

/**
 * 演示面板按当前登记的窗口出一份。
 *
 * `horizon` 只是登记标签、不参与计算（见 `lib/useHorizonParam` 的语义边界），
 * 所以同一份冻结盘面在不同窗口下就是同一份盘面 —— 但页面显示与导出快照
 * 必须跟着登记值走，不能永远写死「20 交易日」。
 */
function fixtureOverview(horizon: string): OverviewPageData {
  return {
    ...overviewFixture,
    context: { ...overviewFixture.context, horizon: horizonLabel(horizon) },
  };
}

function SkeletonOverview() {
  return (
    <div className="space-y-3" data-testid="page-loading">
      <div className="smp-skeleton h-[74px] w-full" />
      <div className="grid grid-cols-3 gap-3">
        <div className="smp-skeleton h-[210px]" />
        <div className="smp-skeleton h-[210px]" />
        <div className="smp-skeleton h-[210px]" />
      </div>
      <div className="smp-skeleton h-[300px]" />
    </div>
  );
}

export default function OverviewPage() {
  return (
    <Suspense fallback={<div className="p-6 text-[13px]">加载中…</div>}>
      <OverviewInner />
    </Suspense>
  );
}
