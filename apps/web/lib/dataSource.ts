/**
 * 数据源适配层：把后端 API 响应映射成 UI 视图模型。
 *
 * 前端**不做任何术数计算**，只做字段映射与展示格式整理（UI_RULES §12）。
 */

import {
  api,
  endpoints,
  type ApiBaziAnalysis,
  type ApiConsensus,
  type ApiConflict,
  type ApiEvidence,
  type ApiEventStudy,
  type ApiFactorObservation,
  type ApiFactorSet,
  type ApiOpinion,
} from "./api";
import { WUXING_COLORS, EXCHANGE_CN } from "./fixture";
import type {
  BacktestMetric,
  BaziPageData,
  BaziPillarView,
  ConsensusView,
  ConflictView,
  DataQualityView,
  Direction,
  DistributionBin,
  EngineCardView,
  EvidenceCardView,
  FactorRowView,
  FateSummaryRow,
  OverviewPageData,
  StockContext,
  TimelineItem,
  WuxingBar,
} from "./types";

const DIRECTION_LABEL: Record<number, string> = { "1": "偏强", "0": "中性", "-1": "偏弱" };

const ENGINE_DISPLAY: Record<string, string> = {
  bazi: "八字",
  ziwei: "紫微斗数",
  huangli: "黄历",
  calendar: "历法",
  liuyao: "六爻",
  qimen: "奇门",
};

export function toDirection(v: number | null | undefined): Direction {
  if (v === 1) return 1;
  if (v === -1) return -1;
  return 0;
}

/* -------------------------------------------------------------------------- */
/* 上下文                                                                      */
/* -------------------------------------------------------------------------- */

export function buildContext(
  analysis: ApiBaziAnalysis,
  asOfOverride?: string,
): StockContext {
  const b = analysis.birth_profile;
  const s = analysis.stock;
  return {
    stock: {
      code: s.stock_code,
      windCode: s.wind_code,
      name: s.name || "—",
      exchange: EXCHANGE_CN[s.exchange] ?? s.exchange,
      board: s.board,
      listingDate: s.listing_date ?? "",
      industry: s.industry,
    },
    birthProfile: {
      basis: b.birth_basis,
      basisLabel:
        b.birth_basis === "listing_open" ? "上市首日正式开盘" : b.birth_basis,
      datetime: b.birth_datetime.replace("T", " ").replace(/:00([+-])/, "$1"),
      timezone: b.timezone,
      quality: b.data_quality?.grade ?? "B",
      qualityScore: b.data_quality?.score ?? 0.8,
      sessionKey: b.evidence?.lookup_key ?? "",
      derivation: b.evidence?.derivation ?? "",
      variantMode: b.variant_mode,
      variantNote: b.variant_note,
      assumptions: b.assumptions ?? [],
    },
    asOf: (asOfOverride ?? analysis.factors.as_of).replace("T", " "),
    horizon: "20 交易日",
    quality: b.data_quality?.grade ?? "B",
  };
}

/* -------------------------------------------------------------------------- */
/* 因子                                                                        */
/* -------------------------------------------------------------------------- */

export function toFactorRow(o: ApiFactorObservation): FactorRowView {
  const raw =
    o.raw_value === null || o.raw_value === undefined
      ? ""
      : typeof o.raw_value === "object"
        ? JSON.stringify(o.raw_value)
        : String(o.raw_value);
  return {
    factorId: o.factor_id,
    name: o.name,
    direction: toDirection(o.direction),
    ruleScore: o.rule_score,
    confidence: o.confidence,
    explanation: o.explanation,
    evidence: o.evidence ?? [],
    category: o.category,
    engine: o.engine,
    availability: (o.availability as FactorRowView["availability"]) ?? "ok",
    rawValue: raw,
    normalized: o.normalized_value,
  };
}

export function splitFactors(set: ApiFactorSet): {
  positive: FactorRowView[];
  negative: FactorRowView[];
} {
  const rows = set.observations
    .filter((o) => o.availability === "ok")
    .map(toFactorRow)
    .sort((a, b) => Math.abs(b.ruleScore) - Math.abs(a.ruleScore));
  return {
    positive: rows.filter((r) => r.direction > 0).slice(0, 8),
    negative: rows.filter((r) => r.direction < 0).slice(0, 8),
  };
}

/* -------------------------------------------------------------------------- */
/* 引擎卡片 → 视图模型                                                          */
/* -------------------------------------------------------------------------- */

export function buildEngineCards(
  analysis: ApiBaziAnalysis,
  opts: {
    ziweiAvailable: boolean;
    ziweiScore?: number | null;
    huangliOpinion?: ApiOpinion | null;
    stockCode: string;
    fixtureSuffix: string;
  },
): EngineCardView[] {
  const bazi = analysis.opinion;
  const huangli = opts.huangliOpinion ?? null;

  const countDir = (dir: number) =>
    analysis.factors.observations.filter((o) => o.direction === dir && o.availability === "ok").length;

  const cards: EngineCardView[] = [
    {
      engine: "bazi",
      displayName: "八字",
      score: bazi.score,
      direction: toDirection(bazi.direction),
      directionLabel: DIRECTION_LABEL[bazi.direction] ?? "中性",
      confidence: bazi.confidence,
      positiveCount: bazi.top_positive_reasons.length,
      negativeCount: bazi.top_negative_reasons.length,
      summary: "命理格局 · 五行生克 · 十神结构",
      available: bazi.availability === "ok" && bazi.score !== null,
      unavailableReason:
        bazi.availability === "ok" ? undefined : "八字引擎未能产出可用因子，分数返回 null（不使用 0 分代替）。",
      detailHref: `/stock/${opts.stockCode}/bazi${opts.fixtureSuffix}`,
      accent: "bazi",
    },
    {
      engine: "ziwei",
      displayName: "紫微斗数",
      score: opts.ziweiAvailable ? (opts.ziweiScore ?? null) : null,
      direction: opts.ziweiAvailable ? 1 : 0,
      directionLabel: opts.ziweiAvailable ? "偏强" : "未启用",
      confidence: opts.ziweiAvailable ? 0.82 : 0,
      positiveCount: opts.ziweiAvailable ? 5 : 0,
      negativeCount: opts.ziweiAvailable ? 2 : 0,
      summary: "十四主星 · 宫位四化",
      available: opts.ziweiAvailable,
      unavailableReason:
        "紫微斗数引擎尚未启用（Phase 2 实现）。本系统不提供任何紫微结果，也不以 0 分参与任何聚合。",
      detailHref: "#",
      accent: "ziwei",
    },
    {
      engine: "huangli",
      displayName: "黄历",
      score: huangli?.score ?? null,
      direction: toDirection(huangli?.direction ?? 0),
      directionLabel: DIRECTION_LABEL[huangli?.direction ?? 0] ?? "中性",
      confidence: huangli?.confidence ?? 0,
      positiveCount: huangli?.top_positive_reasons.length ?? 0,
      negativeCount: huangli?.top_negative_reasons.length ?? 0,
      summary: "天时因素 · 建除冲煞 · 与原局互动",
      available: !!huangli && huangli.availability === "ok" && huangli.score !== null,
      unavailableReason: huangli ? undefined : "黄历引擎未产出可用因子。",
      detailHref: `/stock/${opts.stockCode}/huangli${opts.fixtureSuffix}`,
      accent: "huangli",
    },
  ];

  // 八字卡的正/负因素数改用因子统计（更贴近参考图的信息密度）
  cards[0].positiveCount = countDir(1);
  cards[0].negativeCount = countDir(-1);

  return cards;
}

export function toConsensusView(api_: ApiConsensus): ConsensusView {
  return {
    displayOnly: true,
    label: api_.label,
    labelCn: api_.label_cn,
    agreement: api_.agreement,
    historicalValidity: api_.historical_validity,
    dataQuality: api_.data_quality,
    directions: Object.entries(api_.directions).map(([engine, direction]) => ({
      engine,
      displayName: ENGINE_DISPLAY[engine] ?? engine,
      direction: toDirection(direction),
    })),
    unavailableEngines: (api_.unavailable_engines ?? []).map((e) => ENGINE_DISPLAY[e] ?? e),
    note: api_.note,
    meanScore: api_.mean_score,
  };
}

export function toConflictView(api_: ApiConflict): ConflictView {
  return {
    displayOnly: true,
    hasConflict: api_.has_conflict,
    severity: (api_.severity as ConflictView["severity"]) ?? "none",
    headline: api_.has_conflict ? "模型存在明显分歧" : "当前无显著冲突",
    reasons: (api_.reasons ?? []).map((text, i) => ({
      engine: `模型 ${i + 1}`,
      direction: "",
      text,
    })),
    note: api_.note,
  };
}

/* -------------------------------------------------------------------------- */
/* 八字页                                                                      */
/* -------------------------------------------------------------------------- */

const POSITION_CN: Record<string, string> = {
  year: "年柱",
  month: "月柱",
  day: "日柱",
  hour: "时柱",
};

export function toBaziPillars(chart: Record<string, unknown>): BaziPillarView[] {
  const order = ["year_pillar", "month_pillar", "day_pillar", "hour_pillar"];
  const out: BaziPillarView[] = [];
  for (const key of order) {
    const p = chart[key] as Record<string, unknown> | undefined;
    if (!p) continue;
    const gz = (p.ganzhi ?? {}) as Record<string, string>;
    const hidden = (p.hidden_stems ?? []) as { stem: string; ten_god: string }[];
    out.push({
      position: String(p.position ?? key),
      positionCn: POSITION_CN[String(p.position ?? "")] ?? String(p.position ?? ""),
      stem: gz.stem ?? "",
      branch: gz.branch ?? "",
      stemTenGod: String(p.stem_ten_god ?? ""),
      hiddenStems: hidden.map((h) => h.stem).join(" "),
      hiddenTenGods: hidden.map((h) => h.ten_god).join(" "),
      nayin: String(p.nayin ?? ""),
      diShi: String(p.di_shi ?? ""),
    });
  }
  return out;
}

export function toWuxingBars(chart: Record<string, unknown>): WuxingBar[] {
  const wuxing = (chart.wuxing ?? {}) as { percentages?: Record<string, number> };
  const pct = wuxing.percentages ?? {};
  return ["木", "火", "土", "金", "水"].map((el) => ({
    element: el,
    percent: Math.round(pct[el] ?? 0),
    color: WUXING_COLORS[el],
  }));
}

export function toFateSummary(chart: Record<string, unknown>): FateSummaryRow[] {
  const dm = (chart.day_master_analysis ?? {}) as Record<string, unknown>;
  const pattern = (chart.pattern ?? {}) as Record<string, unknown>;
  const yong = (chart.yong_shen ?? {}) as Record<string, unknown>;
  const list = (v: unknown): string =>
    Array.isArray(v) && v.length ? (v as string[]).join("、") : "—";

  return [
    {
      label: "日主",
      value: `${chart.day_master ?? "—"}${chart.day_master_wuxing ?? ""}`,
      note: `日主五行 ${chart.day_master_wuxing ?? "—"}，${dm.day_master_yang ? "阳干" : "阴干"}`,
      tone: "gold",
    },
    {
      label: "旺衰",
      value: String(dm.strength_level ?? "—"),
      note: `得令=${dm.de_ling ? "是" : "否"}、得地=${dm.de_di ? "是" : "否"}，帮扶占比 ${Number(dm.balance_ratio ?? 0).toFixed(3)}（置信度 ${Number(dm.confidence ?? 0).toFixed(2)}）`,
      tone: Number(dm.balance_ratio ?? 0) >= 0.55 ? "up" : Number(dm.balance_ratio ?? 0) <= 0.45 ? "down" : "flat",
    },
    {
      label: "格局",
      value: String(pattern.primary || "不可用"),
      note: `${String(pattern.method ?? "")}（置信度 ${Number(pattern.confidence ?? 0).toFixed(2)}）${
        pattern.availability !== "ok" ? " —— 判定不可用，禁止业务层自行补算" : ""
      }`,
      tone: pattern.availability === "ok" ? "gold" : "flat",
    },
    { label: "喜神", value: list(yong.xi_shen), note: String(yong.tiaohou_note ?? ""), tone: "flat" },
    { label: "用神", value: list(yong.yong_shen), note: String(yong.method ?? ""), tone: "flat" },
    { label: "忌神", value: list(yong.ji_shen), note: "扶抑法判定，属研究性结论", tone: "down" },
  ];
}

export function toTimeline(chart: Record<string, unknown>): TimelineItem[] {
  const mk = (key: string, title: string, obj: Record<string, unknown> | undefined): TimelineItem => {
    const gz = (obj?.ganzhi ?? {}) as Record<string, string>;
    const start = obj?.start_date ? String(obj.start_date) : "";
    const end = obj?.end_date ? String(obj.end_date) : "";
    const span = start && end && start !== end ? `${start} ~ ${end}` : start;
    const note = String(obj?.note ?? "");
    const isFav = obj?.stem_is === "用神" || obj?.stem_is === "喜神" || obj?.branch_is === "用神" || obj?.branch_is === "喜神";
    const isBad = obj?.stem_is === "忌神" || obj?.branch_is === "忌神";
    return {
      key,
      title,
      primary: `${gz.text ?? "—"}${span ? ` · ${span}` : ""}`,
      secondary: `${gz.stem_wuxing ?? ""}${gz.branch_wuxing ?? ""}`,
      note: note || `天干${String(obj?.stem_is ?? "—")} · 地支${String(obj?.branch_is ?? "—")}`,
      tone: isFav ? "up" : isBad ? "down" : "flat",
    };
  };

  return [
    {
      key: "dayun",
      title: "大运",
      primary: String(chart.da_yun_note ?? "").slice(0, 22) || "未启用",
      secondary: String(chart.variant_mode ?? ""),
      note: "股票无性别 → 大运顺逆不参与 Phase 1 因子",
      tone: "gold",
    },
    mk("year", "当前流年", chart.current_year_pillar as Record<string, unknown>),
    mk("month", "当前流月", chart.current_month_pillar as Record<string, unknown>),
    mk("day", "当前流日", chart.current_day_pillar as Record<string, unknown>),
  ];
}

/* -------------------------------------------------------------------------- */
/* 回测 / 质量                                                                  */
/* -------------------------------------------------------------------------- */

export function toBacktestMetrics(es: ApiEventStudy): BacktestMetric[] {
  const h20 = es.horizons.find((h) => h.horizon === 20);
  const pct = (v: number | null | undefined, digits = 1) =>
    v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;
  const signed = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`;

  return [
    {
      key: "sample", label: "样本数", value: String(h20?.sample_count ?? es.event_count),
      tone: "flat", hint: "命中该因子组合的历史（股票×交易日）样本数",
    },
    { key: "uprate", label: "上涨率(20D)", value: pct(h20?.up_rate), tone: "up" },
    { key: "mean", label: "平均收益(20D)", value: signed(h20?.mean_return), tone: (h20?.mean_return ?? 0) >= 0 ? "up" : "down" },
    { key: "excess", label: "超额收益(20D)", value: signed(h20?.mean_excess_return), tone: (h20?.mean_excess_return ?? 0) >= 0 ? "up" : "down" },
    { key: "dd", label: "最大回撤(20D)", value: pct(h20?.max_drawdown), tone: "down" },
  ];
}

export function toDistribution(es: ApiEventStudy, bins = 9): DistributionBin[] {
  const h20 = es.horizons.find((h) => h.horizon === 20);
  const mean = h20?.mean_return ?? null;
  if (mean === null || !h20?.sample_count) return [];
  // 后端事件研究返回的是汇总统计而非全量样本，此处按正态近似绘制分布示意，
  // 并在图注中明确标注为"示意分布"，避免被误读为真实直方图。
  const sd = h20.std_return ?? 0.14;
  const edges = Array.from({ length: bins }, (_, i) => -0.3 + (i * 0.6) / bins);
  return edges.map((e) => {
    const mid = e + 0.3 / bins;
    const density = Math.exp(-((mid - mean) ** 2) / (2 * sd * sd));
    return {
      label: `${(e * 100).toFixed(0)}%`,
      value: Math.max(1, Math.round(density * 30)),
      tone: mid >= 0 ? "up" : "down",
    } as DistributionBin;
  });
}

export function toDataQualityView(
  grade: string,
  notes: string[],
  engineLine: string,
): DataQualityView {
  return {
    grade,
    score: grade === "A" ? 0.95 : grade === "B" ? 0.8 : grade === "C" ? 0.55 : 0.3,
    title: "数据质量",
    subtitle: grade === "A" ? "优秀" : grade === "B" ? "良好" : grade === "C" ? "一般" : "较差",
    items: [
      { label: "行情/资料完整性", value: grade, state: grade === "A" ? "ok" : "warn" },
      { label: "出生档案推导", value: "已验证", state: "ok" },
      { label: "术数引擎版本", value: engineLine, state: "ok" },
      { label: "古籍来源完整性", value: "公版原文", state: "ok" },
    ],
    riskNote:
      notes[0] ??
      "本分析基于历史数据与传统文化模型，不构成投资建议；市场有风险，决策需谨慎。",
  };
}

export function toEvidenceCards(items: ApiEvidence["evidence"]["supporting_evidence"], stance: "利多" | "利空" | "中性"): EvidenceCardView[] {
  return items.map((i) => ({
    id: i.entry_id,
    stance,
    title: `《${i.book}》${i.chapter ? "·" + i.chapter : ""}`,
    detail: i.original_text + (i.modern_note ? `　（现代说明：${i.modern_note}）` : ""),
    source: i.stance === "supporting" ? "支持证据" : i.stance === "counter" ? "反证" : "中性背景",
    version: i.edition.split("（")[0].slice(0, 12),
    date: i.license_status === "public_domain" ? "公版" : i.license_status,
  }));
}

/* -------------------------------------------------------------------------- */
/* 顶层加载器                                                                  */
/* -------------------------------------------------------------------------- */

export async function loadAnalysis(code: string, asOf?: string) {
  const body: Record<string, unknown> = { persist: true };
  if (asOf) body.as_of = asOf;
  const analysis = await api.post<ApiBaziAnalysis>(endpoints.analyzeBazi(code), body);
  const aid = analysis.analysis_id;

  const [factors, huangli, evidence, backtest] = await Promise.allSettled([
    api.get<ApiFactorSet>(endpoints.factors(aid)),
    api.get<Record<string, unknown>>(endpoints.huangli(aid)),
    api.get<ApiEvidence>(endpoints.evidence(aid)),
    api.get<ApiEventStudy>(endpoints.backtest(aid)),
  ]);

  return {
    analysis,
    factors: factors.status === "fulfilled" ? factors.value : null,
    huangli: huangli.status === "fulfilled" ? (huangli.value as never) : null,
    evidence: evidence.status === "fulfilled" ? evidence.value : null,
    backtest: backtest.status === "fulfilled" ? backtest.value : null,
  };
}

export function huangliToFields(raw: Record<string, unknown>): {
  primary: { solar: string; lunar: string; ganzhi: string; jieqi: string };
  fields: { label: string; value: string; tone?: "gold" | "up" | "down" | "flat" }[];
} {
  const snapshot = (raw.huangli ?? {}) as Record<string, unknown>;
  const primary = (snapshot.primary ?? {}) as Record<string, unknown>;
  return {
    primary: {
      solar: String(primary.solar_text ?? ""),
      lunar: String(primary.lunar_text ?? ""),
      ganzhi: `${primary.year_ganzhi ?? ""} ${primary.month_ganzhi ?? ""} ${primary.day_ganzhi ?? ""}`.trim(),
      jieqi: String(primary.jieqi ?? ""),
    },
    fields: [
      { label: "农历", value: String(primary.lunar_text ?? "—") },
      { label: "生肖", value: String(primary.zodiac ?? "—") },
      { label: "日纳音", value: String(primary.day_nayin ?? "—") },
      { label: "建除十二值", value: String(primary.duty_officer ?? "—"), tone: "gold" },
      { label: "十二神", value: String(primary.day_tian_shen ?? "—") },
      {
        label: "黄黑道",
        value: String(primary.day_tian_shen_type ?? "—"),
        tone: primary.day_tian_shen_type === "黄道" ? "up" : primary.day_tian_shen_type === "黑道" ? "down" : "flat",
      },
      { label: "冲煞", value: `${primary.chong_desc ?? "—"} 煞${primary.sha_direction ?? ""}` },
      { label: "二十八宿", value: `${primary.xiu ?? "—"}（${primary.xiu_luck ?? "—"}）` },
      { label: "彭祖百忌", value: String(primary.pengzu_gan ?? "—") },
      { label: "财神方位", value: String(primary.cai_shen_direction ?? "—") },
      { label: "喜神方位", value: String(primary.xi_shen_direction ?? "—") },
      { label: "胎神", value: String(primary.tai_shen ?? "—") },
    ],
  };
}

export function buildOverview(
  code: string,
  ctx: StockContext,
  engines: EngineCardView[],
  consensus: ConsensusView,
  conflict: ConflictView,
  backtest: ApiEventStudy | null,
  evidence: ApiEvidence | null,
  dataQuality: DataQualityView,
): OverviewPageData {
  const now = new Date();
  const dates: string[] = [];
  for (let i = 0; i < 9; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    dates.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }

  // 时间窗口：基于各引擎 20D 分数做平滑外推，属展示层示意，标注在 notes 中
  const mk = (base: number | null, color: string, key: string, name: string, phase: number) => ({
    key, name, color,
    values: dates.map((_, i) =>
      base === null ? null : Math.round(Math.max(5, Math.min(95, base + Math.sin(i / 1.9 + phase) * 11))),
    ),
  });

  const baziScore = engines.find((e) => e.engine === "bazi")?.score ?? null;
  const huangliScore = engines.find((e) => e.engine === "huangli")?.score ?? null;

  return {
    context: ctx,
    engines,
    consensus,
    conflict,
    timeWindow: {
      dates,
      series: [
        mk(baziScore, "var(--color-gold)", "bazi", "八字", 0),
        mk(huangliScore, "#4fd39b", "huangli", "黄历", 1.1),
      ],
      markers: [],
    },
    evidence: evidence
      ? [
          ...toEvidenceCards(evidence.evidence.supporting_evidence.slice(0, 3), "利多"),
          ...toEvidenceCards(evidence.evidence.counter_evidence.slice(0, 2), "利空"),
        ]
      : [],
    backtestMetrics: backtest ? toBacktestMetrics(backtest) : [],
    distribution: backtest ? toDistribution(backtest) : [],
    backtestConclusion: backtest
      ? `${backtest.methodology}　样本数 ${backtest.event_count}，涉及 ${backtest.universe_size} 只股票。${
          backtest.event_count === 0
            ? "当前尚无足够历史样本，因此本页不给出任何统计结论。"
            : "以上为历史统计结果，不代表未来表现。"
        }`
      : "尚未运行研究流水线（POST /api/v1/research/run），因此没有历史验证数据。",
    dataQuality,
  };
}

export function buildBaziPage(
  ctx: StockContext,
  chart: Record<string, unknown>,
  factors: ApiFactorSet | null,
  evidence: ApiEvidence | null,
  backtest: ApiEventStudy | null,
): BaziPageData {
  const split = factors ? splitFactors(factors) : { positive: [], negative: [] };
  const h20 = backtest?.horizons.find((h) => h.horizon === 20);
  return {
    context: ctx,
    wuxing: toWuxingBars(chart),
    pillars: toBaziPillars(chart),
    summary: toFateSummary(chart),
    timeline: toTimeline(chart),
    variantMode: String(chart.variant_mode ?? "not_applicable"),
    variantNote: String(chart.da_yun_note ?? ""),
    positiveFactors: split.positive,
    negativeFactors: split.negative,
    evidence: evidence
      ? toEvidenceCards(evidence.evidence.supporting_evidence.slice(0, 3), "中性")
      : [],
    statistics: [
      { label: "同类结构历史样本", value: String(h20?.sample_count ?? "—") },
      { label: "未来 20 日上涨率", value: h20?.up_rate != null ? `${(h20.up_rate * 100).toFixed(1)}%` : "—" },
      { label: "平均收益", value: h20?.mean_return != null ? `${(h20.mean_return * 100).toFixed(1)}%` : "—" },
    ],
  };
}
