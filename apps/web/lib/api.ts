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
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
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
}

export interface ApiConflict {
  display_only: boolean;
  has_conflict: boolean;
  severity: string;
  conflicting_engines: string[];
  directions: Record<string, number>;
  reasons: string[];
  note: string;
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
};
