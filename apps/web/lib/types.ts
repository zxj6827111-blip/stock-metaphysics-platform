/**
 * 前端领域类型（UI 消费用的视图模型）。
 *
 * 原则：
 *  - 前端**不重新计算任何术数**，只负责展示后端确定性数据（UI_RULES §12）。
 *  - 后端不可用字段一律以 `null` / `unavailable` 表达，禁止用 0 冒充。
 */

export type Direction = 1 | 0 | -1;

export type Availability = "ok" | "unavailable" | "partial" | "error";

export interface StockSummary {
  code: string;
  windCode: string;
  name: string;
  exchange: string;
  board: string;
  listingDate: string;
  industry?: string;
}

export interface BirthProfileView {
  basis: string;
  basisLabel: string;
  datetime: string;
  timezone: string;
  quality: string;
  qualityScore: number;
  sessionKey: string;
  derivation: string;
  variantMode: string;
  variantNote: string;
  assumptions: { key: string; value: string; reason: string; impact: string }[];
}

export interface StockContext {
  stock: StockSummary;
  birthProfile: BirthProfileView;
  asOf: string;
  horizon: string;
  quality: string;
}

export interface EngineCardView {
  engine: string;
  displayName: string;
  /** null 表示该引擎未启用 / 不可用 —— 绝不用 0 分代替 */
  score: number | null;
  direction: Direction;
  directionLabel: string;
  confidence: number | null;
  positiveCount: number;
  negativeCount: number;
  summary: string;
  available: boolean;
  unavailableReason?: string;
  detailHref: string;
  accent: "bazi" | "ziwei" | "huangli";
}

export interface ConsensusView {
  displayOnly: true;
  label: string;
  labelCn: string;
  agreement: string;
  historicalValidity: string;
  dataQuality: string;
  directions: { engine: string; displayName: string; direction: Direction }[];
  unavailableEngines: string[];
  note: string;
  meanScore: number | null;
}

export interface ConflictView {
  displayOnly: true;
  hasConflict: boolean;
  severity: "none" | "minor" | "major";
  headline: string;
  reasons: { engine: string; direction: string; text: string }[];
  note: string;
}

export interface LegendItem {
  key: string;
  name: string;
  color: string;
}

export interface TimeWindowSeries {
  dates: string[];
  series: { key: string; name: string; color: string; values: (number | null)[] }[];
  markers: { date: string; label: string; tone: "consensus" | "conflict" }[];
}

export interface EvidenceCardView {
  id: string;
  stance: "利多" | "利空" | "中性";
  title: string;
  detail: string;
  source: string;
  version: string;
  date: string;
}

export interface HuangliRow {
  label: string;
  value: string;
  tone?: "gold" | "up" | "down" | "flat";
}

export interface BacktestMetric {
  key: string;
  label: string;
  value: string;
  tone: "up" | "down" | "flat" | "gold";
  hint?: string;
}

export interface DistributionBin {
  label: string;
  value: number;
  tone: "up" | "down";
}

export interface DataQualityView {
  grade: string;
  score: number;
  title: string;
  subtitle: string;
  items: { label: string; value: string; state: "ok" | "warn" | "bad" }[];
  riskNote: string;
}

export interface BaziPillarView {
  position: string;
  positionCn: string;
  stem: string;
  branch: string;
  stemTenGod: string;
  hiddenStems: string;
  hiddenTenGods: string;
  nayin: string;
  diShi: string;
}

export interface WuxingBar {
  element: string;
  percent: number;
  color: string;
}

export interface FateSummaryRow {
  label: string;
  value: string;
  note: string;
  tone?: "gold" | "up" | "down" | "flat";
}

export interface TimelineItem {
  key: string;
  title: string;
  primary: string;
  secondary: string;
  note: string;
  tone?: "gold" | "up" | "down" | "flat";
}

export interface FactorRowView {
  factorId: string;
  name: string;
  direction: Direction;
  ruleScore: number;
  confidence: number;
  explanation: string;
  evidence: string[];
  category: string;
  engine: string;
  availability: Availability;
  rawValue?: string;
  normalized?: number | null;
}

export interface BaziPageData {
  context: StockContext;
  wuxing: WuxingBar[];
  pillars: BaziPillarView[];
  summary: FateSummaryRow[];
  timeline: TimelineItem[];
  variantMode: string;
  variantNote: string;
  positiveFactors: FactorRowView[];
  negativeFactors: FactorRowView[];
  evidence: EvidenceCardView[];
  statistics: { label: string; value: string }[];
}

export interface OverviewPageData {
  context: StockContext;
  engines: EngineCardView[];
  consensus: ConsensusView | null;
  conflict: ConflictView | null;
  timeWindow: TimeWindowSeries;
  evidence: EvidenceCardView[];
  backtestMetrics: BacktestMetric[];
  distribution: DistributionBin[];
  backtestConclusion: string;
  dataQuality: DataQualityView;
  /** Phase 1.1：研究状态机，NO_REAL_DATA 时必须显著横幅告警 */
  researchStatus?: string | null;
  researchStatusReasons?: string[];
}

export interface HomePageData {
  recent: {
    code: string;
    name: string;
    analyzedAt: string;
    price: string;
    changePct: string;
    trend: "up" | "down";
    engines: { key: string; label: string; direction: Direction }[];
    status: string;
    statusTone: "up" | "down" | "flat" | "conflict";
  }[];
  systemStatus: { key: string; label: string; state: "ok" | "off" | "warn"; note: string; latency: string }[];
  capabilities: { key: string; title: string; desc: string; tone: "up" | "info" | "gold" | "down" }[];
}
