/** W5/W6 versioned research API contracts used by the research UI. */

export const DEFAULT_RESEARCH_DATASET_ID =
  process.env.NEXT_PUBLIC_SMP_RESEARCH_DATASET_ID?.trim() ||
  "w4-engineering-002561-20120223-asof-v2";

export interface ApiSystemVersions {
  config_version: string;
  market_data_cutoff_date: string | null;
  market_data_source: string | null;
  market_data_version: string;
}

export interface ApiHistoricalDatasetVersions {
  feature_version: string;
  pit_version: string;
  birth_profile_version: string;
  birth_profile_source_version: string;
  calendar_version: string;
  engine_versions: Record<string, unknown>;
  rule_versions: Record<string, unknown>;
  config_version: string;
  label_version: string;
  bar_version: string;
  factor_version: string;
  price_basis: "raw_times_factor";
}

export interface ApiHistoricalDatasetV2 {
  contract_version: "research-api-v2";
  dataset_id: string;
  dataset_digest: string;
  schema_version: string;
  status: "COMPLETE" | "PARTIAL";
  row_count: number;
  expected_shard_count: number;
  complete_shard_count: number;
  failed_shards: string[];
  missing_shards: string[];
  metadata: {
    research_eligible?: boolean;
    confirmatory_research_eligible?: boolean;
    scope?: {
      research_dates?: string[];
      stock_code?: string;
      exchange?: string;
      sample_kind?: string;
      research_time?: string;
      research_timezone?: string;
    };
    input_versions?: Record<string, unknown>;
    known_limitations?: string[];
    [key: string]: unknown;
  };
  available_versions: ApiHistoricalDatasetVersions[];
  research_eligible: boolean;
  confirmatory_research_eligible: boolean;
}

export interface ApiHistoricalEventStudyRequest {
  dataset_id: string;
  scope_mode: "stock" | "dates";
  stock_code: string | null;
  date_from: string;
  date_to: string;
  factor_ids: string[];
  activation: "any" | "nonzero" | "positive" | "negative";
  direction_filter: -1 | 0 | 1 | null;
  min_rule_score: number | null;
  horizon: 1 | 5 | 20;
  versions: ApiHistoricalDatasetVersions;
  limit: number;
  offset: number;
}

export interface ApiHistoricalStatistics {
  sample_count: number;
  missing_count: number;
  mean_return: number | null;
  median_return: number | null;
  win_rate: number | null;
}

export interface ApiHistoricalEvent {
  security_id: string;
  stock_code: string;
  research_date: string;
  factor_id: string;
  direction: number | null;
  rule_score: number | null;
  normalized_value: number | null;
  horizon: number;
  return_value: number | null;
  benchmark_return: number | null;
  excess_return: number | null;
  label_available: boolean;
  missing_reason: string | null;
}

export interface ApiHistoricalEventStudyV2 {
  contract_version: "research-api-v2";
  dataset_id: string;
  dataset_digest: string;
  scope_mode: "stock" | "dates";
  date_from: string;
  date_to: string;
  factor_ids: string[];
  activation: string;
  horizon: number;
  versions: ApiHistoricalDatasetVersions;
  research_status: string;
  research_status_reasons: string[];
  candidate_observation_count: number;
  matched_observation_count: number;
  matched_date_count: number;
  missing_observation_count: number;
  missing_by_reason: Record<string, number>;
  matched: ApiHistoricalStatistics;
  complement: ApiHistoricalStatistics;
  overall: ApiHistoricalStatistics;
  matched_date_equal_weighted: ApiHistoricalStatistics;
  returned_count: number;
  limit: number;
  offset: number;
  events: ApiHistoricalEvent[];
  warnings: string[];
}

export interface ApiFortuneAssumption {
  key: string;
  value: string;
  reason: string;
  impact: string;
}

export interface ApiFortuneBirthProfileV2 {
  symbol: string;
  exchange: string;
  listing_date: string | null;
  first_trade_datetime: string | null;
  first_trade_date: string | null;
  first_trade_resolution: string;
  birth_basis: string;
  birth_datetime: string | null;
  birth_datetime_status: string;
  timezone: string;
  birth_time_precision: string;
  source: { source: string; version?: string };
  source_version: string;
  confidence: number | null;
  birth_profile_version: string;
  rule_version: string;
  config_version: string;
  market_session_version: string;
  assumptions: ApiFortuneAssumption[];
  data_quality: { grade: string; score: number; notes: string[] } | null;
}

export interface ApiFortuneTimelinePointV2 {
  date: string;
  evaluation_datetime: string;
  trading_day: boolean | null;
  trading_calendar_source: string;
  annual_pillar: { stem: string; branch: string } | null;
  monthly_pillar: { stem: string; branch: string } | null;
  daily_pillar: { stem: string; branch: string } | null;
  availability: string;
}

export interface ApiFortuneTimelineV2 {
  stock_identity: { symbol: string; exchange: string; name: string; source_version: string };
  birth_context: ApiFortuneBirthProfileV2;
  start_date: string;
  end_date: string;
  timezone: string;
  points: ApiFortuneTimelinePointV2[];
  availability: string;
  rule_versions: Record<string, unknown>;
  provenance: Record<string, unknown>[];
  warnings: { code: string; message: string; severity?: string }[];
  assumptions: ApiFortuneAssumption[];
  rule_version: string;
}

export interface ApiFortuneTimelineV2Response {
  contract_version: "research-api-v2";
  resolved_versions: Record<string, string | null>;
  timeline: ApiFortuneTimelineV2;
}

export interface ApiExperimentReportV2Response {
  contract_version: "research-api-v2";
  experiment_id: string;
  report_digest: string;
  report: Record<string, unknown>;
}
