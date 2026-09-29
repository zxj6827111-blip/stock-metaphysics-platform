/** W5/W6 versioned research API contracts used by the research UI. */

export const DEFAULT_RESEARCH_DATASET_ID =
  process.env.NEXT_PUBLIC_SMP_RESEARCH_DATASET_ID?.trim() ||
  "w4-certified-002561-20120223-20180514-v3-path-risk";

export const TEN_GOD_CATEGORIES = ["比肩", "劫财", "食神", "伤官", "偏财", "正财", "七杀", "正官", "偏印", "正印"] as const;

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
    status?: string;
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
  certification_status: "CERTIFIED_LIMITED_SCOPE" | "NOT_CERTIFIED" | "CERTIFICATE_MISMATCH" | "DATA_MISSING";
  certification_reason: string;
  certified_stock_code: string | null;
  certified_security_id: string | null;
  certified_date_from: string | null;
  certified_date_to: string | null;
  scope_certificate_id: string | null;
  scope_certificate_sha256: string | null;
}

export interface ApiHistoricalEventStudyRequest {
  dataset_id: string;
  scope_mode: "stock" | "dates";
  stock_code: string | null;
  date_from: string;
  date_to: string;
  target_date: string | null;
  factor_ids: string[];
  activation: "any" | "nonzero" | "positive" | "negative";
  direction_filter: -1 | 0 | 1 | null;
  min_rule_score: number | null;
  ten_god_category: string | null;
  ten_god_layer: "DAILY" | null;
  ten_god_position: "day" | null;
  relation_type: string | null;
  relation_source_context: "year" | "month" | "day" | "dayun" | null;
  relation_source_pillar: "year" | "month" | "day" | "dayun" | null;
  relation_target_context: "natal" | null;
  relation_target_pillar: "year" | "month" | "day" | null;
  relation_source_component: "stem" | "branch" | null;
  relation_target_component: "stem" | "branch" | null;
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
  mean_positive_return: number | null;
  mean_negative_return: number | null;
  payoff_ratio: number | null;
  max_return: number | null;
  max_loss: number | null;
  return_unit: "fraction";
  metric_summaries: Record<string, ApiHistoricalMetricSummary>;
}

export interface ApiHistoricalMetricSummary {
  sample_count: number;
  missing_count: number;
  mean: number | null;
  minimum: number | null;
  maximum: number | null;
  unit: "fraction";
  definition: string;
}

export interface ApiHistoricalEvent {
  security_id: string;
  stock_code: string;
  research_date: string;
  factor_id: string;
  direction: number | null;
  rule_score: number | null;
  normalized_value: number | null;
  ten_god_category: string | null;
  relation_evidence: Record<string, unknown> | null;
  horizon: number;
  return_value: number | null;
  benchmark_return: number | null;
  excess_return: number | null;
  max_favorable_move: number | null;
  max_adverse_move: number | null;
  max_drawdown: number | null;
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
  target_date: string | null;
  factor_ids: string[];
  activation: string;
  ten_god_category: string | null;
  ten_god_layer: "DAILY" | null;
  ten_god_position: "day" | null;
  relation_type: string | null;
  relation_source_context: string | null;
  relation_source_pillar: string | null;
  relation_target_context: string | null;
  relation_target_pillar: string | null;
  relation_source_component: string | null;
  relation_target_component: string | null;
  condition_logic: "AND";
  factor_selection_semantics: "per_factor_observation";
  certified_stock_code: string | null;
  certified_date_from: string | null;
  certified_date_to: string | null;
  horizon: number;
  versions: ApiHistoricalDatasetVersions;
  research_status: string;
  research_status_reasons: string[];
  candidate_observation_count: number;
  matched_observation_count: number;
  observation_unit: "security_date_factor";
  candidate_security_date_count: number;
  matched_security_date_count: number;
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
  monthly_ten_god?: { display_label: string } | null;
  daily_ten_god?: { display_label: string } | null;
  relation_events?: ApiFortuneRelationEvent[];
  availability: string;
}

export interface ApiFortuneRelationParticipant {
  context: string;
  pillar: string;
  component: string;
  value: string;
}

export interface ApiFortuneRelationEvent {
  relation_type: string;
  source: ApiFortuneRelationParticipant;
  target: ApiFortuneRelationParticipant;
  scope: string;
  explanation: string;
}

export interface ApiFortuneLuckCycleContext {
  polarity: string | null;
  direction: string | null;
  compatibility_gender: string | null;
  availability: string;
  direction_basis: string;
  polarity_source: { source: string; extra: Record<string, unknown> };
  polarity_source_version: string;
  market_session_version: string;
  polarity_observation_date: string | null;
  polarity_observed_at: string | null;
  assumptions: ApiFortuneAssumption[];
  unavailability_reason: string;
  rule_version: string;
  cycle_availability: string;
  cycle_periods: { cycle_index: number; ganzhi: { stem: string; branch: string }; start_year: number; end_year: number; start_age: number; end_age: number; start_at: string; end_at: string }[];
}

export interface ApiFortuneTenGodFilter {
  layer: string;
  ten_god: string;
  position?: string | null;
  hidden_stem?: string | null;
}

export interface ApiFortuneRelationFilter {
  relation_type: string;
  source_context: string;
  source_pillar: string;
  target_context: string;
  target_pillar: string;
  source_component?: string | null;
  target_component?: string | null;
}

export interface ApiFortuneTimelineV2 {
  stock_identity: { symbol: string; exchange: string; name: string; source_version: string };
  birth_context: ApiFortuneBirthProfileV2;
  stable_context?: { luck_cycle_context: ApiFortuneLuckCycleContext; natal_context: { day_master: string | null; availability: string } };
  start_date: string;
  end_date: string;
  date_mode: "ALL_CALENDAR_DAYS" | "TRADING_DAYS_ONLY";
  anchor_mode: string;
  timezone: string;
  ten_god_filters: ApiFortuneTenGodFilter[];
  relation_filters: ApiFortuneRelationFilter[];
  include_relation_events: boolean;
  include_month_segments: boolean;
  include_ten_god_index: boolean;
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

export interface ApiFortuneMonthCalendarRequest {
  stock_code: string;
  start_date: string;
  end_date: string;
  birth_basis: "listing_open" | "MARKET_FIRST_TRADE";
  birth_profile_version: string;
  evaluation_time: string;
  timezone: "Asia/Shanghai";
  market_session_version: string;
  config_version: string;
}

export interface ApiTenGodHiddenStem {
  stem: string;
  ten_god: string;
  rank: string;
}

export interface ApiTenGodMonthSegment {
  kind: string;
  ganzhi: { stem: string; branch: string; text?: string };
  boundary_jieqi: string;
  next_boundary_jieqi: string;
  stem: string;
  stem_wuxing: string;
  stem_ten_god: string;
  branch: string;
  branch_hidden_stems: ApiTenGodHiddenStem[];
  start_at: string;
  end_at: string;
  verdict: string;
  reason: string;
}

export interface ApiTenGodDay {
  date: string;
  ganzhi: { stem: string; branch: string; text?: string };
  stem: string;
  stem_ten_god: string;
  branch_hidden_stems: ApiTenGodHiddenStem[];
  verdict: string;
  is_trading_day: boolean | null;
  trading_calendar_source: string;
  reason: string;
}

export interface ApiTenGodCalendar {
  stock: {
    stock_code: string;
    name: string;
    exchange: string;
    birth_basis: string;
    birth_profile_version: string;
    birth_datetime: string | null;
    timezone: string;
    source: string;
    assumptions: string[];
  };
  versions: Record<string, string>;
  natal: {
    day_master: string;
    day_master_wuxing?: string;
    pillars: {
      position: string;
      ganzhi: { text?: string; stem: string; branch: string };
      stem: { ten_god: string; display_label?: string; is_day_master?: boolean };
      branch: string;
      hidden_stems: { stem: string; ten_god: string; rank: string }[];
    }[];
  };
  yong_shen: { available: boolean; yong_shen: string[]; xi_shen: string[]; ji_shen: string[] };
  months: ApiTenGodMonthSegment[];
  days: ApiTenGodDay[];
  natural_day_count: number;
  displayed_day_count: number;
  calendar_window_start: string | null;
  calendar_window_end: string | null;
  warnings: { code: string; message: string; severity: string }[];
}

export interface ApiFirstDayPolarityEvidence {
  status: "available" | "unavailable" | "conflict";
  first_day_yinyang: "阳" | "阴" | null;
  first_day_pct_chg: number | null;
  price_basis: string;
  observation_date: string | null;
  is_trading_day: boolean | null;
  trading_day_source: string;
  source: string;
  source_version: string;
  market_session_version: string;
  visible_at: string | null;
  reason: string;
}

export interface ApiFortuneMonthInterpretation {
  segment: ApiTenGodMonthSegment;
  wealth_star_locations: string[];
  related_events: ApiFortuneRelationEvent[];
  explanation: string;
}

export interface ApiFortuneMonthCalendarResponse {
  contract_version: "research-api-v2";
  request: ApiFortuneMonthCalendarRequest;
  stock_identity: { symbol: string; exchange: string; name: string; source_version: string };
  resolved_versions: Record<string, string | null>;
  birth_profile: ApiFortuneBirthProfileV2;
  first_day_polarity: ApiFirstDayPolarityEvidence;
  calendar: ApiTenGodCalendar | null;
  calendar_unavailability_reason: string;
  timeline: ApiFortuneTimelineV2 | null;
  timeline_unavailability_reason: string;
  month_interpretations: ApiFortuneMonthInterpretation[];
}

export interface ApiExperimentReportV2Response {
  contract_version: "research-api-v2";
  experiment_id: string;
  report_digest: string;
  report: Record<string, unknown>;
}
