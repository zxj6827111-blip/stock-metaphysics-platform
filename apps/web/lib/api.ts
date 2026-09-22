/**
 * 后端 API 客户端。
 *
 * 生产 runtime 一律走这里读取真实数据；`?fixture=ui-reference` 时才
 * 切换到 `lib/fixture.ts` 的固定演示数据（见 lib/dataSource.ts）。
 *
 * 后端契约要点：
 *  - 不可用字段返回 null / "unavailable"，**不会**用 0 冒充；
 *  - 紫微在 Phase 1 返回 availability=unavailable；
 *  - 所有错误返回 { error: { code, message, detail, retryable } }。
 */

const API_BASE = process.env.NEXT_PUBLIC_SMP_API_BASE ?? "/api/backend";

export class ApiError extends Error {
  code: string;
  detail: string;
  retryable: boolean;
  status: number;

  constructor(status: number, code: string, message: string, detail = "", retryable = false) {
    super(message);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.retryable = retryable;
  }
}

/**
 * 请求超时（毫秒）。
 *
 * 为什么必须有：`fetch` **没有内置超时**。后端进程卡住（未崩溃、但不再响应）时，
 * 请求会一直挂起，页面就永远停在 Loading —— 用户看到的是"一直在算"，
 * 而不是"失败了、可以重试"。这类"永远转圈"属于比报错更差的失败模式：
 * 它把故障伪装成了进行中的工作。
 *
 * 取值：时间窗口逐日批量求值是最慢的只读路径（实测秒级，冷启动更久），
 * 30 秒足够；再慢就应当以错误暴露出来，而不是继续无提示地等。
 */
const REQUEST_TIMEOUT_MS = 30_000;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  let res: Response;
  // 允许调用方传入自己的 signal（与超时信号合并）
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
  if (init?.signal) {
    if (init.signal.aborted) controller.abort();
    else init.signal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  try {
    res = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (err) {
    const timedOut = controller.signal.aborted && !init?.signal?.aborted;
    throw new ApiError(
      0,
      timedOut ? "NETWORK_TIMEOUT" : "NETWORK_ERROR",
      timedOut
        ? `请求超时（${REQUEST_TIMEOUT_MS / 1000} 秒）：后端未在时限内返回。本次分析未被写入，可直接重试。`
        : "无法连接后端服务，请确认 apps/api 已启动（默认 http://127.0.0.1:8000）",
      String(err),
      true,
    );
  } finally {
    clearTimeout(timer);
  }

  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }

  if (!res.ok) {
    const errObj = (body as { error?: { code?: string; message?: string; detail?: string; retryable?: boolean } } | null)?.error;
    throw new ApiError(
      res.status,
      errObj?.code ?? `HTTP_${res.status}`,
      errObj?.message ?? `请求失败 (${res.status})`,
      errObj?.detail ?? "",
      errObj?.retryable ?? res.status >= 500,
    );
  }
  return body as T;
}

/**
 * 纯文本请求（导出报告等 Markdown / HTML 响应）。
 *
 * 与 `request()` 共用同一套超时与错误语义：导出报告要在后端拼装
 * EvidenceBundle（含古籍检索与历史统计），同样可能卡住 ——
 * 没有超时会表现为"点了导出，永远停在导出中"。
 */
async function requestText(path: string): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(API_BASE + path, {
      cache: "no-store",
      signal: controller.signal,
    });
    if (!res.ok) {
      throw new ApiError(
        res.status,
        `HTTP_${res.status}`,
        `导出失败 (${res.status})`,
        await res.text().catch(() => ""),
        res.status >= 500,
      );
    }
    return res.text();
  } catch (err) {
    if (err instanceof ApiError) throw err;
    const timedOut = controller.signal.aborted;
    throw new ApiError(
      0,
      timedOut ? "NETWORK_TIMEOUT" : "NETWORK_ERROR",
      timedOut
        ? `导出超时（${REQUEST_TIMEOUT_MS / 1000} 秒）：后端未在时限内返回，可直接重试。`
        : "无法连接后端服务，导出失败。",
      String(err),
      true,
    );
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  /**
   * POST JSON。
   *
   * ⚠️ **不要在这里再传 `content-type`**：`request()` 已经默认设置了它。
   * 传两次会让 fetch 合并成 `"application/json, application/json"`，
   * 而 FastAPI 会因此把请求体当成无法解析的字节流，返回 422
   * `model_attributes_type`（这个坑在 Phase 2F 的 E2E 里真实踩到过）。
   */
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: JSON.stringify(body ?? {}),
    }),
  /** 导出报告等纯文本响应（Markdown / HTML）。 */
  raw: (path: string): Promise<string> => requestText(path),
};

/** 后端原始响应类型（只声明 UI 用得到的字段）。 */
export interface ApiStockSearchResponse {
  items: {
    stock_code: string;
    wind_code: string;
    name: string;
    exchange: string;
    board: string;
    listing_date: string;
  }[];
  total: number;
  query: string;
  source: string;
  is_degraded: boolean;
  warnings: { code: string; message: string; severity: string }[];
}

export interface ApiStockDetail {
  stock: {
    stock_code: string;
    wind_code: string;
    name: string;
    exchange: string;
    board: string;
    industry: string;
    listing_date: string | null;
    data_quality: { grade: string; score: number; notes: string[] };
  };
  birth_profile: ApiBirthProfile | null;
  session_key: string;
  warnings: { code: string; message: string; severity: string }[];
}

export interface ApiBirthProfile {
  stock_code: string;
  exchange: string;
  birth_basis: string;
  birth_datetime: string;
  timezone: string;
  birth_profile_version: string;
  evidence: {
    listing_date: string | null;
    first_trading_day: string | null;
    session_name: string;
    session_open_time: string;
    timezone: string;
    derivation: string;
    lookup_key: string;
  };
  assumptions: { key: string; value: string; reason: string; impact: string }[];
  data_quality: { grade: string; score: number; notes: string[] };
  variant_mode: string;
  variant_note: string;
}

export interface ApiEnginesResponse {
  phase: string;
  engines: {
    engine_id: string;
    display_name: string;
    available: boolean;
    engine_version: string;
    config_version: string;
    third_party: string;
    third_party_commit: string;
    notes: string;
    unavailable_reason?: string;
  }[];
  market_provider: string;
  facts: Record<string, string | number>;
}

export interface ApiConsensus {
  display_only: boolean;
  label: string;
  label_cn: string;
  participating_engines: string[];
  unavailable_engines: string[];
  directions: Record<string, number>;
  mean_score: number | null;
  agreement: string;
  historical_validity: string;
  data_quality: string;
  note: string;

  // --- Phase 2 正式 ConsensusEngine（可选，向后兼容） ---
  consensus_class?: string;
  agreement_score?: number;
  available_engine_count?: number;
  positive_engine_count?: number;
  negative_engine_count?: number;
  neutral_engine_count?: number;
  engine_opinions?: Record<string, Record<string, unknown>>;
  research_status?: string;
  historical_consensus_stats?: Record<string, unknown>;
  interpretation?: string;
  notes?: string[];
}

export interface ApiConflict {
  display_only: boolean;
  has_conflict: boolean;
  severity: string;
  conflicting_engines: string[];
  directions: Record<string, number>;
  /** 与后端 ConflictSnapshot 对齐：参与分歧的因子 ID（此前 TS 类型漏声明）。 */
  conflicting_factor_ids?: string[];
  reasons: string[];
  note: string;

  // --- Phase 2 正式 ConflictDetector（可选，向后兼容） ---
  conflict_level?: string;
  major_conflicts?: Record<string, unknown>[];
  factor_conflicts?: Record<string, unknown>[];
  time_horizon_conflicts?: Record<string, unknown>[];
  assumption_conflicts?: Record<string, unknown>[];
  historical_conflict_stats?: Record<string, unknown>;
  notes?: string[];
}

export interface ApiOpinion {
  engine: string;
  engine_version: string;
  availability: string;
  direction: number;
  score: number | null;
  confidence: number;
  top_positive_reasons: { text: string; factor_ids: string[] }[];
  top_negative_reasons: { text: string; factor_ids: string[] }[];
  factor_ids: string[];
  note: string;

  // --- Phase 2（可选，向后兼容） ---
  research_status?: string;
  historical_validity?: Record<string, unknown>;
  data_quality?: Record<string, unknown>;
  assumptions?: string[];
  warnings?: { code: string; message: string; severity: string }[];
}

export interface ApiFactorObservation {
  factor_id: string;
  name: string;
  engine: string;
  category: string;
  raw_value: unknown;
  normalized_value: number | null;
  direction: number;
  rule_score: number;
  confidence: number;
  availability: string;
  rule_version: string;
  engine_version: string;
  evidence: string[];
  explanation: string;
  warnings: string[];
}

export interface ApiFactorSet {
  stock_code: string;
  as_of: string;
  observations: ApiFactorObservation[];
}

export interface ApiEventStudy {
  experiment_id: string;
  factor_ids: string[];
  event_count: number;
  universe_size: number;
  horizons: {
    horizon: number;
    sample_count: number;
    up_rate: number | null;
    excess_up_rate: number | null;
    mean_return: number | null;
    median_return: number | null;
    std_return: number | null;
    mean_excess_return: number | null;
    max_drawdown: number | null;
    note: string;
  }[];
  methodology: string;
  warnings: { code: string; message: string; severity: string }[];
  /**
   * Phase 1.1：研究状态机。
   * NO_REAL_DATA=合成/降级行情（历史统计仅供联调，不构成研究证据）。
   * 不可用/未知时可能缺省。
   */
  research_status?: string | null;
  research_status_reasons?: string[];
  data_source?: {
    is_real?: boolean;
    degraded_codes?: string[];
    label_rows?: number;
    benchmark_degraded?: boolean;
  } | null;
}

export interface ApiExperimentSummary {
  experiment_id: string;
  kind: string;
  name: string;
  factor_ids: string[];
  universe: string[];
  created_at: string;
  status: string;
}

export interface ApiExperimentResultRow {
  /** 持有期（交易日）。库里该列是动态类型，后端原样透出，可能为 number。 */
  horizon: string | number;
  sample_count: number;
  up_rate: number | null;
  mean_return: number | null;
  median_return: number | null;
  mean_excess_return: number | null;
  max_drawdown: number | null;
  excess_up_rate: number | null;
  /** 后端 extra_json：对照组判决（verdict）、Jaccard 重合度、备注等原始字段。 */
  extra: Record<string, unknown>;
}

export interface ApiExperimentListResponse {
  total: number;
  filtered_count: number;
  returned_count: number;
  query: { limit: number; offset: number; kind: string | null; status: string | null; sort: string };
  items: ApiExperimentSummary[];
}

export interface ApiRelationStudyHorizon {
  horizon: number;
  sample_count: number;
  activation_rate: number | null;
  mean_return: number | null;
  median_return: number | null;
  mean_excess_return: number | null;
  up_rate: number | null;
  max_drawdown: number | null;
  p_value: number | null;
  q_value: number | null;
  control_mean_return: number | null;
  control_up_rate: number | null;
}

export interface ApiRelationStudySplit {
  name: string;
  date_from: string | null;
  date_to: string | null;
  event_count: number;
  observation_count: number;
  sample_count: number;
  activation_rate: number | null;
  horizons: ApiRelationStudyHorizon[];
  research_status: string;
  research_status_reasons: string[];
  negative_controls: Record<string, { verdict?: string; jaccard_with_real?: number | null }>;
}

export interface ApiRelationStudy {
  experiment_id: string;
  relation_type: string;
  factor_id: string;
  direction: number;
  universe: string;
  universe_size: number;
  date_from: string | null;
  date_to: string | null;
  horizons: number[];
  splits: ApiRelationStudySplit[];
  data_source: Record<string, unknown>;
  methodology: string;
  warnings: string[];
  created_at: string;
}

export interface ApiExperimentDetail {
  experiment: {
    experiment_id: string;
    kind: string;
    name: string;
    factor_ids: string[];
    universe: string[];
    horizons: number[];
    methodology: string;
    seed: string;
    created_at: string;
    status?: string;
    date_from?: string | null;
    date_to?: string | null;
    benchmark_code?: string | null;
    params?: Record<string, unknown>;
  };
  results_by_variant: Record<string, ApiExperimentResultRow[]>;
}

export interface ApiEvidence {
  analysis_id: string;
  driver_factors: { factor_id: string; name: string; normalized_value: number | null; direction: number }[];
  evidence: {
    query: { query: string; factor_ids: string[]; topics: string[] };
    supporting_evidence: ApiEvidenceItem[];
    counter_evidence: ApiEvidenceItem[];
    neutral_evidence: ApiEvidenceItem[];
    total_candidates: number;
    retrieval_method: string;
    knowledge_version: string;
    note: string;
  };
  disclaimer: string;
}

export interface ApiEvidenceItem {
  entry_id: string;
  book: string;
  chapter: string;
  school: string;
  topic: string[];
  original_text: string;
  modern_note: string;
  score: number;
  authority_weight: number | null;
  stance: string;
  source: string;
  edition: string;
  provenance: string;
  license_status: string;
  /** 命中本次检索主题的条目内主题（后端原样返回，不由前端推断）。 */
  matched_query_terms?: string[];
}

export interface ApiBaziAnalysis {
  analysis_id: string;
  stock: ApiStockDetail["stock"];
  birth_profile: ApiBirthProfile;
  chart: Record<string, unknown>;
  factors: ApiFactorSet;
  opinion: ApiOpinion;
  versions: Record<string, string>;
  warnings: { code: string; message: string; severity: string }[];
}

export interface ApiZiweiStar {
  name: string;
  type: string;
  brightness: string;
  mutagen: string;
  scope: string;
}

export interface ApiZiweiPalace {
  index: number;
  name: string;
  heavenly_stem: string;
  earthly_branch: string;
  is_body_palace: boolean;
  major_stars: ApiZiweiStar[];
  minor_stars: ApiZiweiStar[];
  adjective_stars: ApiZiweiStar[];
  changsheng12: string;
  trine_indices: number[];
}

export interface ApiZiweiChart {
  variant_mode: string;
  variant_basis: string;
  gender_parameter: string;
  solar_date: string;
  lunar_date: string;
  chinese_date: string;
  time_name: string;
  time_range: string;
  soul: string;
  body: string;
  five_elements_class: string;
  soul_palace_branch: string;
  soul_palace_index: number;
  body_palace_index: number;
  natal_mutagens: { mutagen: string; star: string; palace_index: number; palace_name: string }[];
  palaces: ApiZiweiPalace[];
  horoscope: Record<string, {
    scope: string; index: number; heavenly_stem: string; earthly_branch: string;
    name: string; mutagen: string[]; palace_names: string[]; nominal_age?: number | null;
  } | null> | null;
  assumptions: { key: string; value: string; reason: string; impact: string }[];
  warnings: { code: string; message: string; severity: string }[];
}

export interface ApiZiweiChartsResponse {
  analysis_id: string;
  variants: string[];
  charts: Record<string, {
    chart_id: string;
    engine_version: string;
    input: Record<string, unknown>;
    chart: ApiZiweiChart;
    warnings: { code: string; message: string; severity: string }[];
  }>;
  note: string;
}

export interface ApiOpinionsResponse {
  analysis_id: string;
  opinions: Record<string, ApiOpinion>;
  available_engines: string[];
  unavailable_engines: string[];
  disclaimer: string;
}

export interface ApiTimeWindowDay {
  trade_date: string;
  is_trading_day: boolean;
  bazi_direction: number;
  ziwei_direction: number;
  huangli_direction: number;
  combined_direction: number;
  bazi_score: number | null;
  ziwei_score: number | null;
  huangli_score: number | null;
}

export interface ApiWeekWindow {
  week_index: number;
  week_start: string;
  week_end: string;
  trading_days: number;
  daily_results: ApiTimeWindowDay[];
  aggregation_method: string;
  aggregation_version: string;
  mean: number | null;
  median: number | null;
  min: number | null;
  max: number | null;
  positive_day_ratio: number | null;
  weighted_mean: number | null;
  consensus: ApiConsensus | null;
  research_status: string;
  warnings: { code: string; message: string; severity: string }[];
}

export interface ApiMonthWindow {
  month: string;
  month_index: number;
  start_date: string | null;
  end_date: string | null;
  bazi: ApiOpinion | null;
  ziwei: ApiOpinion | null;
  huangli: ApiOpinion | null;
  consensus: ApiConsensus | null;
  conflict: ApiConflict | null;
  research_status: string;
  trading_days: number;
  sample_dates: string[];
  warnings: { code: string; message: string; severity: string }[];
}

export interface ApiTimelineMonths {
  analysis_id: string;
  stock_code: string;
  as_of: string;
  variant_mode: string;
  aggregation_version: string;
  months: ApiMonthWindow[];
  research_status: string;
  research_status_reasons: string[];
  methodology: string;
  warnings: { code: string; message: string; severity: string }[];
}

export interface ApiTimelineWeeks {
  analysis_id: string;
  stock_code: string;
  as_of: string;
  variant_mode: string;
  aggregation_version: string;
  weeks: ApiWeekWindow[];
  research_status: string;
  research_status_reasons: string[];
  methodology: string;
  warnings: { code: string; message: string; severity: string }[];
}

/** 逐日窗口（as_of 之后连续交易日的三模型流日结果）。 */
export interface ApiTimelineDays {
  analysis_id: string;
  stock_code: string;
  as_of: string;
  variant_mode: string;
  daily_version: string;
  requested_days: number;
  returned_days: number;
  available_engines: string[];
  days: ApiTimeWindowDay[];
  research_status: string;
  research_status_reasons: string[];
  methodology: string;
  warnings: { code: string; message: string; severity: string }[];
  cache?: ApiCacheInfo;
  /** 交易日历三层覆盖（实测成交 / 官方已公布）。 */
  calendar_coverage?: ApiCalendarLayers | null;
}

export interface ApiCacheInfo {
  key: string;
  hit: boolean;
}

/** 版本化的日课分类口径说明（后端随每次响应下发）。 */
export interface ApiHuangliClassRule {
  rule_id: string;
  basis_field: string;
  basis_source: string;
  categories: { code: string; label_cn: string }[];
  third_category_supported: boolean;
  difference_note_cn: string;
  not_a_recommendation_cn: string;
}

/** 未来交易日黄历的单张日期卡。 */
export interface ApiHuangliDayCard {
  date: string;
  weekday_cn: string;
  /** 该日期的交易日判定来源：实测成交事实 / 交易所已公布安排。 */
  calendar_source?: string;
  lunar_text: string;
  year_ganzhi: string;
  month_ganzhi: string;
  day_ganzhi: string;
  jieqi: string;
  zodiac: string;
  duty_officer: string;
  day_tian_shen: string;
  day_tian_shen_type: string;
  day_tian_shen_luck: string;
  xiu: string;
  xiu_luck: string;
  day_nayin: string;
  chong_desc: string;
  sha_direction: string;
  pengzu_gan: string;
  pengzu_zhi: string;
  cai_shen_direction: string;
  xi_shen_direction: string;
  fu_shen_direction: string;
  day_yi: string[];
  day_ji: string[];
  class_code: string | null;
  class_label_cn: string | null;
  class_available: boolean;
  class_basis_cn: string;
  is_trading_day: boolean;
  offset_trading_days: number;
}

export interface ApiCalendarLayer {
  loaded: boolean;
  error?: string | null;
  start: string | null;
  end: string | null;
  days?: number;
  source?: string;
  generated_at?: string | null;
  verified?: boolean | null;
  sources?: { layer: string; url: string; note: string }[] | null;
  boundary_cn?: string | null;
}

/** 交易日历的三层覆盖（`GET /api/v1/system/trading-calendar` 与 outlook 响应共用）。 */
export interface ApiCalendarLayers {
  exchange: string;
  observed: ApiCalendarLayer;
  published: ApiCalendarLayer;
}

export interface ApiHuangliOutlook {
  analysis_id: string;
  stock_code: string;
  outlook_version: string;
  class_rule_version: string;
  engine_version: string;
  exchange: string;
  as_of: string;
  anchor_date: string;
  anchor_is_trading_day: boolean | null;
  mode: string;
  requested_days: number | null;
  requested_months: number | null;
  returned_days: number;
  rule_cn: string;
  coverage: {
    status: "complete" | "partial" | "unavailable" | string;
    explanation_cn: string;
    calendar_loaded: boolean;
    calendar_source: string;
    /** 实测成交日历覆盖（观测事实，只能到过去）。保持原有语义不变。 */
    calendar_coverage: { start: string; end: string } | null;
    /** 官方公布日历覆盖（交易所已公告的未来安排）。 */
    published_calendar_loaded?: boolean;
    published_coverage?: { start: string; end: string } | null;
    /** 两层合并后的可用范围。 */
    effective_coverage?: { start: string; end: string } | null;
    /** 三层覆盖详情（实测 / 公布 / 官方公布边界）。 */
    calendar_layers?: ApiCalendarLayers;
    /** 日期卡判定来源分布：observed_index_days / published_exchange_calendar。 */
    day_sources?: Record<string, number>;
    unknown_days: number;
    first_unknown_date: string | null;
  };
  class_rule: ApiHuangliClassRule;
  month_groups: { month: string; dates: string[] }[];
  days: ApiHuangliDayCard[];
  warnings: { code: string; message: string; severity: string }[];
  methodology_cn: string;
  cache?: ApiCacheInfo;
}

export interface ApiHuangliPerformanceGroup {
  class_code: string | null;
  class_label_cn: string;
  n: number;
  mean: number | null;
  median: number | null;
  up_share: number | null;
  mean_excess: number | null;
  n_excess: number;
  stats_available: boolean;
  independent_n: number;
}

export interface ApiHuangliPerformance {
  analysis_id: string;
  stock_code: string;
  performance_version: string;
  class_rule_version: string;
  engine_version: string;
  as_of: string;
  window: {
    id: string;
    years: number | null;
    requested_start: string;
    requested_end: string;
    effective_start: string | null;
    effective_end: string | null;
  };
  horizon: number;
  class_rule: ApiHuangliClassRule;
  labels: {
    label_version: string;
    horizon_supported: number[];
    return_basis_cn: string;
    bar_source: string | null;
    bar_adjust: string | null;
    adj_factor_snapshot: string | null;
    benchmark_code: string;
    benchmark_available: boolean;
    benchmark_note_cn: string;
    data_cutoff: string | null;
    label_cutoff: string | null;
    n_dropped_incomplete_label: number;
    degraded: boolean;
  };
  sample_rule_cn: string;
  groups: ApiHuangliPerformanceGroup[];
  series: {
    dates: string[];
    by_class: Record<string, (number | null)[]>;
    counts_by_class: Record<string, number[]>;
    metric_cn: string;
  };
  overlap: {
    horizon: number;
    overlap_ratio: number;
    total_samples?: number;
    independent_samples?: number;
    independent_note_cn: string;
  };
  key_findings: { level: string; text_cn: string }[];
  limitations_cn: string[];
  warnings: { code: string; message: string; severity: string }[];
  unavailable_reason: string;
  cache?: ApiCacheInfo;
}

export interface ApiNarrative {
  analysis_id: string;
  mode: "template" | "llm";
  llm_requested: boolean;
  fallback_reason: string;
  passed_guard: boolean;
  guard_summary: string;
  guard_violations: { kind: string; detail: string; severity: string }[];
  sections: Record<string, string>;
  text: string;
  research_status: string;
  disclaimer: string;
}

export interface ApiConsensusCombo {
  combo_id: string;
  description: string;
  engines: string[];
  logic: string;
  sample_count: number;
  event_count: number;
  event_rate: number;
  up_rate: number | null;
  mean_return: number | null;
  median_return: number | null;
  excess_return: number | null;
  control_kind: string;
  control_event_count: number;
  control_up_rate: number | null;
  control_mean_return: number | null;
  jaccard_with_real: number | null;
  control_result: string;
  t_stat: number | null;
  p_value: number | null;
  test_method: string;
  horizon: number;
  research_status: string;
  research_status_reasons: string[];
}

export interface ApiConsensusResearch {
  experiment_id: string;
  universe_size: number;
  sample_dates: number;
  horizon: number;
  data_source: Record<string, unknown>;
  combos: ApiConsensusCombo[];
  multiple_testing: {
    experiment_count: number;
    parameter_count: number;
    selection_method: string;
    warning_level: string;
    bonferroni_alpha: number | null;
    message: string;
  };
  overall_research_status: string;
  overall_reasons: string[];
  conclusion: string;
  methodology: string;
  warnings: { code: string; message: string; severity: string }[];
}

export interface ApiMultiAnalysis {
  analysis_id: string;
  stock: ApiStockDetail["stock"];
  birth_profile: ApiBirthProfile;
  as_of: string;
  variant_mode: string;
  /** 研究窗口标签（如 ``20d``）。**只被记录，不参与因子计算**，见后端 schema 说明。 */
  horizon?: string;
  bazi_chart: Record<string, unknown> | null;
  ziwei_charts: Record<string, ApiZiweiChart>;
  huangli: Record<string, unknown> | null;
  factors: ApiFactorSet;
  opinions: Record<string, ApiOpinion>;
  consensus: ApiConsensus | null;
  conflict: ApiConflict | null;
  versions: Record<string, string>;
  warnings: { code: string; message: string; severity: string }[];
  created_at: string;
}

export interface ApiRelationEvent {
  relation_type: string;
  source_scope: string;
  source_pillar: string;
  target_pillar: string;
  source_stem: string;
  source_branch: string;
  target_stem: string;
  target_branch: string;
  element: string;
  ten_god: string;
  strength: number | null;
  notes: string;
  rule_version: string;
}

export interface ApiRelationCell {
  source_pillar: string;
  target_pillar: string;
  source_ganzhi: string;
  target_ganzhi: string;
  events: ApiRelationEvent[];
  relation_types: string[];
  unavailable: string[];
}

export interface ApiRelationMatrixRow {
  source_pillar: string;
  source_ganzhi: string;
  cells: ApiRelationCell[];
}

export interface ApiRelationMatrix {
  rows: ApiRelationMatrixRow[];
  columns: string[];
  schema_version: string;
  relation_rule_version: string;
}

export interface ApiDateRelationFingerprint {
  date: string;
  year: string;
  month: string;
  day: string;
  hour: string | null;
  stem_targets: Record<string, string[]>;
  branch_targets: Record<string, string[]>;
  candidates: Record<string, string[]>;
  supported_relations: string[];
  unavailable_relations: string[];
  calendar_engine_version: string;
  fingerprint_version: string;
  relation_rule_version: string;
}

export interface ApiRelationMetrics {
  s_raw: number | null;
  v_raw: number | null;
  u_raw: number | null;
  s_percentile: number | null;
  v_percentile: number | null;
  u_percentile: number | null;
  group: string;
}

export interface ApiRelationStockResult {
  stock_code: string;
  name: string;
  exchange: string;
  natal: Record<string, string>;
  day_master: string;
  yong_shen: string[];
  xi_shen: string[];
  ji_shen: string[];
  relation_types: string[];
  hit_explanations: string[];
  stem_relations: string[];
  branch_relations: string[];
  compound_relations: string[];
  ten_gods: string[];
  yong_shen_relations: string[];
  metrics: ApiRelationMetrics;
  research_status: string;
  matrix: ApiRelationMatrix | null;
  availability: string;
  unavailable: string[];
}

export interface ApiDateScanResponse {
  scan_id: string;
  target_date: string;
  fingerprint: ApiDateRelationFingerprint;
  versions: {
    calendar_engine_version: string;
    bazi_engine_version: string;
    relation_rule_version: string;
    fingerprint_version: string;
    birth_basis: string;
    birth_profile_version: string;
    universe_version: string;
    universe_digest: string;
  };
  stock_total: number;
  valid_scan_count: number;
  returned_count: number;
  filtered_count: number;
  offset: number;
  limit: number;
  group_counts: Record<string, number>;
  relation_type_counts: Record<string, number>;
  query: {
    date: string;
    hour: number | null;
    universe: string;
    birth_basis: string;
    birth_profile_version: string;
    relation_rule_version: string;
    relation_type: string | null;
    sort: string;
    offset: number;
    limit: number;
  };
  rows: ApiRelationStockResult[];
  warnings: { code: string; message: string; severity: string }[];
  cache: { key: string; hit: boolean };
  disclaimer: string;
}

export interface ApiDateScanDetail {
  scan_id: string;
  target_date: string;
  row: ApiRelationStockResult;
}

export const endpoints = {
  search: (q: string) => `/api/v1/stocks/search?q=${encodeURIComponent(q)}`,
  stock: (code: string) => `/api/v1/stocks/${code}`,
  birthProfile: (code: string) => `/api/v1/stocks/${code}/birth-profile`,
  analyzeBazi: (code: string) => `/api/v1/stocks/${code}/analysis/bazi`,
  factors: (id: string) => `/api/v1/analysis/${id}/factors`,
  huangli: (id: string) => `/api/v1/analysis/${id}/huangli`,
  chartBazi: (id: string) => `/api/v1/analysis/${id}/charts/bazi`,
  consensus: (id: string) => `/api/v1/analysis/${id}/consensus`,
  conflicts: (id: string) => `/api/v1/analysis/${id}/conflicts`,
  evidence: (id: string) => `/api/v1/analysis/${id}/evidence`,
  researchExperiments: (limit = 30, opts: { offset?: number; kind?: string; status?: string; sort?: string } = {}) => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(opts.offset ?? 0) });
    if (opts.kind) params.set("kind", opts.kind);
    if (opts.status) params.set("status", opts.status);
    if (opts.sort) params.set("sort", opts.sort);
    return `/api/v1/research/experiments?${params.toString()}`;
  },
  relationStudy: () => "/api/v1/research/relation-study",
  researchExperiment: (id: string) => `/api/v1/research/experiments/${encodeURIComponent(id)}`,
  dateRelations: (date: string, hour?: number | null) => {
    const suffix = hour === undefined || hour === null ? "" : `?hour=${hour}`;
    return `/api/v1/research/date-relations/${encodeURIComponent(date)}${suffix}`;
  },
  dateScan: () => "/api/v1/research/date-scan",
  dateScanDetail: (scanId: string, code: string, opts: { date: string; universe?: string; birthProfileVersion?: string; birthBasis?: string; relationRuleVersion?: string; hour?: number | null }) => {
    const params = new URLSearchParams({
      target_date: opts.date,
      universe: opts.universe ?? "v4-full",
      birth_basis: opts.birthBasis ?? "listing_open",
      birth_profile_version: opts.birthProfileVersion ?? "v2-phase4b-listing_open",
      relation_rule_version: opts.relationRuleVersion ?? "bazi-relation-v2",
    });
    if (opts.hour !== undefined && opts.hour !== null) params.set("hour", String(opts.hour));
    return `/api/v1/research/date-scan/${encodeURIComponent(scanId)}/stocks/${encodeURIComponent(code)}?${params.toString()}`;
  },
  backtest: (id: string) => `/api/v1/analysis/${id}/backtest`,
  guide: (id: string) => `/api/v1/analysis/${id}/guide`,
  engineStatus: () => `/api/v1/system/engines`,
  dataQuality: () => `/api/v1/system/data-quality`,
  factorDictionary: () => `/api/v1/factor-dictionary`,
  knowledgeStats: () => `/api/v1/knowledge/stats`,
  health: () => `/api/v1/system/health`,

  // --- Phase 2 ---
  analyzeZiwei: (code: string) => `/api/v1/stocks/${code}/analysis/ziwei`,
  analyzeMulti: (code: string) => `/api/v1/stocks/${code}/analysis/multi`,
  chartZiwei: (id: string) => `/api/v1/analysis/${id}/charts/ziwei`,
  opinions: (id: string) => `/api/v1/analysis/${id}/opinions`,
  timelineMonths: (id: string, months = 12) =>
    `/api/v1/analysis/${id}/timeline/months?months=${months}`,
  timelineWeeks: (id: string, weeks = 12) =>
    `/api/v1/analysis/${id}/timeline/weeks?weeks=${weeks}`,
  timelineDays: (id: string, days = 20) =>
    `/api/v1/analysis/${id}/timeline/days?days=${days}`,
  huangliOutlook: (id: string, mode: string, value: number) =>
    `/api/v1/analysis/${id}/huangli/outlook?mode=${mode}&${
      mode === "months" ? "months" : "days"
    }=${value}`,
  huangliPerformance: (
    id: string,
    opts: { window: string; horizon: number; start?: string; end?: string },
  ) => {
    const params = new URLSearchParams({
      window: opts.window,
      horizon: String(opts.horizon),
    });
    if (opts.start) params.set("start", opts.start);
    if (opts.end) params.set("end", opts.end);
    return `/api/v1/analysis/${id}/huangli/performance?${params.toString()}`;
  },
  evidenceBundle: (id: string) => `/api/v1/analysis/${id}/evidence-bundle`,
  narrative: (id: string) => `/api/v1/analysis/${id}/narrative`,
  report: (id: string, format: "markdown" | "html" = "markdown") =>
    `/api/v1/analysis/${id}/report?format=${format}`,
  consensusResearch: () => `/api/v1/research/consensus`,
  consensusRun: (id: string) => `/api/v1/analysis/${id}/consensus`,
};
