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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch (err) {
    throw new ApiError(
      0,
      "NETWORK_ERROR",
      "无法连接后端服务，请确认 apps/api 已启动（默认 http://127.0.0.1:8000）",
      String(err),
      true,
    );
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
  raw: async (path: string): Promise<string> => {
    const res = await fetch(API_BASE + path, { cache: "no-store" });
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
  },
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
  authority_weight: number;
  stance: string;
  source: string;
  edition: string;
  provenance: string;
  license_status: string;
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
  evidenceBundle: (id: string) => `/api/v1/analysis/${id}/evidence-bundle`,
  narrative: (id: string) => `/api/v1/analysis/${id}/narrative`,
  report: (id: string, format: "markdown" | "html" = "markdown") =>
    `/api/v1/analysis/${id}/report?format=${format}`,
  consensusResearch: () => `/api/v1/research/consensus`,
  consensusRun: (id: string) => `/api/v1/analysis/${id}/consensus`,
};
