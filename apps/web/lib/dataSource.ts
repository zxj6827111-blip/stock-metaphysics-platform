/**
 * 数据源适配层：把后端 API 响应映射成 UI 视图模型。
 *
 * 前端**不做任何术数计算**，只做字段映射与展示格式整理（UI_RULES §12）。
 */

import {
  api,
  endpoints,
  type ApiBaziAnalysis,
  type ApiBirthProfile,
  type ApiEvidenceItem,
  type ApiMultiAnalysis,
  type ApiConsensus,
  type ApiConflict,
  type ApiEvidence,
  type ApiEventStudy,
  type ApiFactorObservation,
  type ApiFactorSet,
  type ApiOpinion,
} from "./api";
import { WUXING_COLORS, EXCHANGE_CN, isFixtureActive } from "./fixture";
import { KNOWN_STOCK_NAMES } from "./stockCatalog";
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

/**
 * 出生模型（后端内部码）→ 中文表达。
 *
 * 为什么要集中映射：`buildContext` 与 `buildContextFromMulti` 两条路径都用它，
 * 之前只有前者做了映射，后者直接把 `listing_open` 这类内部码渲染进上下文栏
 * （UI 复核任务书 §2 明确要求内部码不进正文）。集中在一处才不会再次漏掉。
 */
const BIRTH_BASIS_LABEL: Record<string, string> = {
  listing_open: "上市首日正式开盘",
  ipo_date: "IPO 发行日",
  company_foundation: "公司成立日",
  first_trade: "首笔真实成交时刻",
  custom: "自定义基准",
};

/**
 * 研究窗口（horizon）→ 中文表达。
 *
 * 之前 `buildContext` / `buildContextFromMulti` 都把这里写死成「20 交易日」，
 * 于是用户在上下文栏选 60d、请求体带 `horizon=60d`，页面上却仍显示 20 交易日，
 * 导出的快照里也没有这个字段 —— 同一份分析在三个地方身份不一致。
 * 现在取后端回传的 `analysis.horizon`；后端没回传时如实显示「未指定」，
 * 不拿默认值冒充（AGENTS.md §2.4）。
 */
const HORIZON_LABEL: Record<string, string> = {
  "20d": "20 交易日",
  "60d": "60 交易日",
};

export function horizonLabel(horizon: string | null | undefined): string {
  if (!horizon) return "未指定";
  return HORIZON_LABEL[horizon] ?? horizon;
}

export function birthBasisLabel(basis: string | null | undefined): string {  if (!basis) return "—";
  return BIRTH_BASIS_LABEL[basis] ?? basis;
}

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
      name: s.name || KNOWN_STOCK_NAMES[s.stock_code]?.name || "—",
      exchange: EXCHANGE_CN[s.exchange] ?? s.exchange,
      board: s.board,
      listingDate: s.listing_date || KNOWN_STOCK_NAMES[s.stock_code]?.listingDate || "",
      industry: s.industry,
    },
    birthProfile: {
      basis: b.birth_basis,
      basisLabel: birthBasisLabel(b.birth_basis),
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
    // 单引擎响应不带 horizon 字段：如实显示「未指定」，不拿默认窗口冒充
    horizon: horizonLabel((analysis as { horizon?: string }).horizon),
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

export function toDistribution(es: ApiEventStudy, bins = 9, isFixture = false): DistributionBin[] {
  if (!isFixture) {
    // 正常模式下不采用正态近似伪造分箱，诚实返回空，交由 UI 展示真实空态
    return [];
  }
  const h20 = es.horizons.find((h) => h.horizon === 20);
  const mean = h20?.mean_return ?? null;
  if (mean === null || !h20?.sample_count) return [];
  // 演示/fixture 模式下按正态近似绘制分布示意，并在图注中明确标注为"示意分布"
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

/**
 * 数据质量视图 —— **每一项都必须能指回一个真实字段**。
 *
 * 这里曾经是硬编码的 `已验证 / 公版原文 / state:"ok"`：不管后端有没有回传
 * 出生档案推导证据、不管古籍检索是否成功，卡片上永远是四个绿勾。
 * 研究终端里"看起来已经核对过"的假勾等于虚报数据质量
 * （AGENTS.md §13「不得把降级/合成数据伪装成真实数据」、§16.4 synthetic 隔离）。
 * 现在：证明不了的一律 未提供 / 未验证，并用 warn 而不是绿色 ok。
 */

/** 后端 `DataQualityGrade` 的语义，见 `src/core/schemas/common.py`。 */
const GRADE_MEANING: Record<string, { value: string; state: "ok" | "warn" | "bad" }> = {
  A: { value: "来源确定", state: "ok" },
  B: { value: "含假设", state: "warn" },
  C: { value: "部分缺失", state: "warn" },
  D: { value: "严重缺失", state: "bad" },
  unavailable: { value: "不可用", state: "bad" },
};

/** 公版与"已核实授权"之外的一切许可状态，不得显示成来源完整。 */
const CLEAR_LICENSE: Set<string> = new Set(["public_domain", "verified"]);

export interface DataQualityInputs {
  /** 本次分析的数据质量等级（`birth_profile.data_quality.grade`）。 */
  grade?: string | null;
  /** 后端登记的质量说明。**逐条保留**，不得只显示第一条就丢掉其余风险。 */
  notes?: string[];
  /** `versions.engine_version`；没有就显示未提供，不拼一个 `v-` 冒充有版本。 */
  engineVersion?: string | null;
  /** 出生档案：推导证据（上市日 / 首个交易日）是否真的取到了。 */
  birthProfile?: ApiBirthProfile | null;
  /**
   * 古籍检索条目。
   * `null` / `undefined` = 证据接口这次没成功 ⇒「未验证」；
   * `[]` = 检索成功但零条命中 ⇒「无检索结果」。两者语义不同，不能合并。
   */
  evidenceItems?: ApiEvidenceItem[] | null;
}

/** 出生档案推导：等级 + 推导证据是否落地，两个条件都满足才说"来源确定"。 */
function birthDerivationView(bp: ApiBirthProfile | null | undefined): {
  value: string;
  state: "ok" | "warn" | "bad";
} {
  if (!bp) return { value: "未提供", state: "warn" };
  const proved = !!bp.evidence?.listing_date || !!bp.evidence?.first_trading_day;
  if (!proved) return { value: "未验证", state: "warn" };
  return GRADE_MEANING[bp.data_quality?.grade ?? ""] ?? { value: "未验证", state: "warn" };
}

/**
 * 古籍来源完整性：只统计检索结果里真实带回的 `license_status`。
 *
 * 许可状态之间不可互相指代（后端 `LicenseStatus` 四值）：
 * `public_domain` 是公版刊本原文，`verified` 是**已核实授权**——
 * 两者都允许展示，但把混合结果写成「公版原文」就是虚报版权状态。
 * `unknown` / `restricted` 一律计入未核实。
 */
function knowledgeLicenseView(items: ApiEvidenceItem[] | null | undefined): {
  value: string;
  state: "ok" | "warn" | "bad";
} {
  if (items === null || items === undefined) return { value: "未验证", state: "warn" };
  if (items.length === 0) return { value: "无检索结果", state: "warn" };
  const unclear = items.filter((i) => !CLEAR_LICENSE.has(i.license_status)).length;
  if (unclear) return { value: `含 ${unclear} 条未核实`, state: "warn" };
  const kinds = new Set(items.map((i) => i.license_status));
  if (kinds.size === 1) {
    return kinds.has("public_domain")
      ? { value: `公版原文 · ${items.length} 条`, state: "ok" }
      : { value: `已核实授权 · ${items.length} 条`, state: "ok" };
  }
  return { value: `公版/已核实授权 · ${items.length} 条`, state: "ok" };
}

export function toDataQualityView(input: DataQualityInputs): DataQualityView {
  const grade = input.grade?.trim() ? input.grade.trim() : null;
  const gradeInfo = grade ? GRADE_MEANING[grade] : undefined;
  const notes = (input.notes ?? []).filter((n) => n.trim() !== "");
  const engine = input.engineVersion?.trim()
    ? { value: input.engineVersion.trim(), state: "ok" as const }
    : { value: "未提供", state: "warn" as const };

  return {
    grade: grade ?? "—",
    score: grade === "A" ? 0.95 : grade === "B" ? 0.8 : grade === "C" ? 0.55 : 0.3,
    title: "数据质量",
    subtitle:
      grade === "A"
        ? "优秀"
        : grade === "B"
          ? "良好"
          : grade === "C"
            ? "一般"
            : grade === "D"
              ? "较差"
              : "未评级",
    items: [
      {
        label: "行情/资料完整性",
        value: grade ? `${grade}（${gradeInfo?.value ?? "未评级"}）` : "未提供",
        state: gradeInfo?.state ?? "warn",
      },
      { label: "出生档案推导", ...birthDerivationView(input.birthProfile) },
      { label: "术数引擎版本", ...engine },
      { label: "古籍来源完整性", ...knowledgeLicenseView(input.evidenceItems) },
    ],
    // 首条作为主风险前置展示，其余由卡片里的「其它 N 条」展开层逐条列出
    riskNote:
      notes[0] ??
      "本分析基于历史数据与传统文化模型，不构成投资建议；市场有风险，决策需谨慎。",
    riskNotes: notes,
  };
}

export function toEvidenceCards(items: ApiEvidence["evidence"]["supporting_evidence"], stance: "利多" | "利空" | "中性"): EvidenceCardView[] {
  return items.map((i) => ({
    id: i.entry_id,
    stance,
    title: `《${i.book}》${i.chapter ? "·" + i.chapter : ""}`,
    detail: i.original_text + (i.modern_note ? `　（现代说明：${i.modern_note}）` : ""),
    source: i.stance === "supporting" ? "支持证据" : i.stance === "counter" ? "反证" : "中性背景",
    version: (i.edition ?? "").split("（")[0].slice(0, 12) || "公版",
    date: i.license_status === "public_domain" ? "公版" : (i.license_status ?? "公版"),
  }));
}

/**
 * 取证据摘要（首屏只展示 limit 条，其余展开）。
 *
 * **按立场轮询取样**，而不是直接切前 N 条：证据列表通常是
 * 「先全部支持证据、再全部反证」，直接切片会让首屏只剩利多 ——
 * 等于把反证从第一屏删掉，违反研究纪律（支持与反证必须并列）。
 */
export function pickEvidenceSummary(
  items: EvidenceCardView[],
  limit: number,
): EvidenceCardView[] {
  if (items.length <= limit) return items;
  const buckets = new Map<string, EvidenceCardView[]>();
  for (const it of items) {
    const bucket = buckets.get(it.stance);
    if (bucket) bucket.push(it);
    else buckets.set(it.stance, [it]);
  }
  const out: EvidenceCardView[] = [];
  for (let round = 0; out.length < limit; round++) {
    let progressed = false;
    for (const bucket of buckets.values()) {
      const item = bucket[round];
      if (!item) continue;
      out.push(item);
      progressed = true;
      if (out.length >= limit) break;
    }
    if (!progressed) break;
  }
  return out;
}

/* -------------------------------------------------------------------------- */
/* 顶层加载器                                                                  */
/* -------------------------------------------------------------------------- */

const baziAnalysisCache = new Map<string, {
  analysis: ApiBaziAnalysis;
  factors: ApiFactorSet | null;
  huangli: Record<string, unknown> | null;
  evidence: ApiEvidence | null;
  backtest: ApiEventStudy | null;
}>();

export function invalidateBaziAnalysisCache(code?: string): void {
  if (code) {
    for (const k of baziAnalysisCache.keys()) {
      if (k.startsWith(code)) baziAnalysisCache.delete(k);
    }
  } else {
    baziAnalysisCache.clear();
  }
}

export async function loadAnalysis(code: string, asOf?: string) {
  if (isFixtureActive()) {
    if (code !== "600519") {
      throw new Error(
        `演示模式（UI 复刻）仅支持 600519（贵州茅台）。标的 ${code} 在演示模式下不可用；为保证数据隔离，系统已统一阻断对真实后端的排盘分析与持久化请求，请移除 URL 中的 fixture 参数以进入真实分析模式。`,
      );
    }
  }
  const cacheKey = `${code}|${asOf ?? ""}`;
  const hit = baziAnalysisCache.get(cacheKey);
  if (hit) return hit;

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

  const result = {
    analysis,
    factors: factors.status === "fulfilled" ? factors.value : null,
    huangli: huangli.status === "fulfilled" ? (huangli.value as never) : null,
    evidence: evidence.status === "fulfilled" ? evidence.value : null,
    backtest: backtest.status === "fulfilled" ? backtest.value : null,
  };
  baziAnalysisCache.set(cacheKey, result);
  return result;
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
  consensus: ConsensusView | null,
  conflict: ConflictView | null,
  backtest: ApiEventStudy | null,
  evidence: ApiEvidence | null,
  dataQuality: DataQualityView,
  isFixture = false,
): OverviewPageData {
  const now = new Date();
  const dates: string[] = [];
  for (let i = 0; i < 9; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() + i, 1);
    dates.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`);
  }

  // 时间窗口：基于各引擎 20D 分数做平滑外推，属演示层示意。
  // 只在显式 fixture 模式下生成 —— 正常模式渲染正弦外推曲线，
  // 等于向用户展示编造的未来走势（AGENTS.md 铁律 7 / UI 规范 12）。
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
      series: isFixture
        ? [
            mk(baziScore ?? 78, "var(--color-gold)", "bazi", "八字", 0),
            mk(huangliScore ?? 73, "#4fd39b", "huangli", "黄历", 1.1),
            mk(engines.find((e) => e.engine === "ziwei")?.score ?? 76, "#b07cd6", "ziwei", "紫微斗数", 0.6),
            mk(consensus?.meanScore ?? 75, "var(--color-up)", "consensus", "共识指数", 0.3),
          ]
        : [],
      markers: isFixture
        ? [
            { date: dates[2] ?? "2027-06", label: "高共识区", tone: "consensus" },
            { date: dates[6] ?? "2027-10", label: "高冲突区", tone: "conflict" },
          ]
        : [],
    },
    evidence: evidence
      ? [
          ...toEvidenceCards(evidence.evidence.supporting_evidence.slice(0, 3), "利多"),
          ...toEvidenceCards(evidence.evidence.counter_evidence.slice(0, 2), "利空"),
        ]
      : [],
    backtestMetrics: backtest ? toBacktestMetrics(backtest) : [],
    distribution: backtest ? toDistribution(backtest, 9, isFixture) : [],
    backtestConclusion: backtest
      ? `${backtest.methodology}　样本数 ${backtest.event_count}，涉及 ${backtest.universe_size} 只股票。${
          backtest.event_count === 0
            ? "当前尚无足够历史样本，因此本页不给出任何统计结论。"
            : "以上为历史统计结果，不代表未来表现。"
        }`
      : "尚未运行研究流水线（POST /api/v1/research/run），因此没有历史验证数据。",
    dataQuality,
    researchStatus: backtest?.research_status ?? null,
    researchStatusReasons: backtest?.research_status_reasons ?? [],
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

export function buildBaziPageFromMulti(
  multi: ApiMultiAnalysis,
  evidence: ApiEvidence | null = null,
  backtest: ApiEventStudy | null = null,
): BaziPageData {
  const ctx = buildContextFromMulti(multi);
  const chart = (multi.bazi_chart ?? {}) as Record<string, unknown>;
  return buildBaziPage(ctx, chart, multi.factors, evidence, backtest);
}


/* -------------------------------------------------------------------------- */
/* Phase 2：多模型分析                                                        */
/* -------------------------------------------------------------------------- */

/**
 * 由 `/analysis/multi` 的响应构造上下文栏数据。
 *
 * 与 `buildContext` 的差别：multi 响应同时含八字与紫微，
 * 但上下文栏只需要"股票 + 出生档案 + as_of"这三块。
 */
export function buildContextFromMulti(analysis: ApiMultiAnalysis): StockContext {
  const b = analysis.birth_profile;
  const s = analysis.stock;
  return {
    stock: {
      code: s.stock_code,
      windCode: s.wind_code,
      name: s.name || KNOWN_STOCK_NAMES[s.stock_code]?.name || "—",
      exchange: EXCHANGE_CN[s.exchange] ?? s.exchange,
      board: s.board,
      listingDate: s.listing_date || KNOWN_STOCK_NAMES[s.stock_code]?.listingDate || "",
      industry: s.industry,
    },
    birthProfile: {
      basis: b.birth_basis,
      basisLabel: birthBasisLabel(b.birth_basis),
      datetime: b.birth_datetime.replace("T", " ").slice(0, 19),
      timezone: b.timezone,
      quality: b.data_quality?.grade ?? "B",
      qualityScore: b.data_quality?.score ?? 0.8,
      sessionKey: b.evidence?.lookup_key ?? "",
      derivation: b.evidence?.derivation ?? "",
      variantMode: b.variant_mode,
      variantNote: b.variant_note,
      assumptions: b.assumptions ?? [],
    },
    asOf: (analysis.as_of ?? "").replace("T", " "),
    horizon: horizonLabel(analysis.horizon),
    quality: b.data_quality?.grade ?? "B",
  };
}

/** 引擎 key → 中文名（面向人的文本一律用中文名）。 */
export const ENGINE_CN: Record<string, string> = {
  bazi: "八字",
  ziwei: "紫微斗数",
  huangli: "黄历",
  calendar: "历法",
  liuyao: "六爻",
  qimen: "奇门遁甲",
};

/**
 * 依据返回区间与分析基准日判断该窗口是「当前周/月」还是「下一周/月」。
 *
 * 为什么不能写死"下一周"：基准日为 2024-11-15 时，2024-11-11~15 这一周
 * **已经包含基准日**，把它叫"下一周"会让研究者误判窗口起点
 * （见 docs/UI_REAUDIT_2026-09-21.md §2）。
 */
export function windowPositionCn(
  start: string | undefined,
  end: string | undefined,
  asOf: string,
  unit: "周" | "月",
): string {
  if (!start || !end) return `待定${unit}度窗口`;
  const a = asOf.slice(0, 10);
  if (a && start.slice(0, 10) <= a && a <= end.slice(0, 10)) {
    return `当前${unit}（含分析基准日）`;
  }
  if (a && start.slice(0, 10) > a) return `下一${unit}（基准日之后）`;
  return `${unit}度窗口`;
}

export function engineCn(key: string): string {
  return ENGINE_CN[key] ?? key;
}

/** 运限假设变体 → 中文表达（`forward` 这类内部码不直接进正文）。 */
const VARIANT_MODE_LABEL: Record<string, string> = {
  not_applicable: "不适用（股票无性别）",
  forward: "顺行（假设规则）",
  reverse: "逆行（假设规则）",
  both: "顺逆并列（假设规则）",
};

export function variantModeLabel(mode: string | null | undefined): string {
  if (!mode) return "未标注";
  return VARIANT_MODE_LABEL[mode] ?? mode;
}

/** 冲突级别 → 中文表达；`none` 不再是正文里的裸英文。 */
const CONFLICT_LEVEL_LABEL: Record<string, string> = {
  none: "无冲突",
  minor: "轻微分歧",
  moderate: "中度分歧",
  major: "明显分歧",
  severe: "严重分歧",
};

export function conflictLevelLabel(level: string | null | undefined, hasConflict: boolean): string {
  if (!hasConflict) return "无冲突";
  if (!level) return "存在分歧";
  return CONFLICT_LEVEL_LABEL[level] ?? level;
}

/** 把 0–1 的比例渲染成百分数；**null 必须显示为"—"而不是 0%**。 */
export function pct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function num(v: number | null | undefined, digits = 4): string {
  if (v === null || v === undefined) return "—";
  return v.toFixed(digits);
}

/** 控制结果 → 中文标签 + 语义色（红涨绿跌遵循 ADR-0007）。 */
export const CONTROL_RESULT_LABEL: Record<string, { label: string; tone: string }> = {
  outperform: { label: "优于对照", tone: "up" },
  underperform: { label: "弱于对照", tone: "down" },
  tie: { label: "无差异", tone: "flat" },
  invalid: { label: "对照失效", tone: "down" },
  not_run: { label: "未运行", tone: "flat" },
};

/**
 * 由后端 `opinions` 直接构造三张引擎卡。
 *
 * **前端不重算分数**：score / direction / confidence 全部来自后端 opinion
 * （由 `AnalysisService.build_opinion` 产出）。Phase 1 曾在综合页对黄历因子
 * 做前端聚合，Phase 2 已移除 —— 分数必须只有一个来源。
 */
export function toEngineCardsFromOpinions(
  analysis: ApiMultiAnalysis,
  /** 分析上下文后缀（fixture + birthBasis + horizon + asOf），见 `lib/analysisContext.ts`。 */
  contextSuffix = "",
): EngineCardView[] {
  const order: { key: "bazi" | "ziwei" | "huangli"; display: string; route: string }[] = [
    { key: "bazi", display: "八字模型", route: "bazi" },
    { key: "ziwei", display: "紫微斗数", route: "ziwei" },
    { key: "huangli", display: "黄历模型", route: "huangli" },
  ];
  return order.map(({ key, display, route }) => {
    const op = analysis.opinions?.[key];
    const ok = !!op && op.availability === "ok" && op.score !== null;
    const positives = (op?.top_positive_reasons ?? []).map((r) => r.text);
    const negatives = (op?.top_negative_reasons ?? []).map((r) => r.text);
    return {
      engine: key,
      displayName: display,
      available: ok,
      direction: (ok ? op!.direction : 0) as Direction,
      directionLabel: ok ? (DIRECTION_LABEL[op!.direction] ?? "中性") : "不可用",
      score: ok ? op!.score : null,
      confidence: ok ? op!.confidence : null,
      positiveCount: positives.length,
      negativeCount: negatives.length,
      summary: ok
        ? positives[0] ?? negatives[0] ?? "该引擎未给出明细理由"
        : op?.note ?? "该引擎本次不可用（score = null，不计入共识分母）",
      unavailableReason: ok ? "" : (op?.note ?? "本次分析未产出该引擎结果"),
      detailHref: `/stock/${analysis.stock.stock_code}/${route}${contextSuffix}`,
      accent: key,
    } satisfies EngineCardView;
  });
}
