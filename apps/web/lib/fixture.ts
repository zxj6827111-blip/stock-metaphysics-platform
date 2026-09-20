/**
 * UI Reference Fixture —— 用于复刻 doc/ui-reference/*.png 的固定演示数据。
 *
 * ⚠️ 边界（务必遵守）
 *  - 本模块**只**服务于 `?fixture=ui-reference` 视觉复刻模式；
 *  - 生产 runtime（默认）必须读取真实 API，见 `lib/api.ts`；
 *  - 这里的紫微斗数数据是**纯展示 Mock**，不写入任何分析数据库，
 *    也不代表系统实现了紫微引擎（Phase 1 明确不实现）。
 */

import type {
  BaziPageData,
  HomePageData,
  OverviewPageData,
  FactorRowView,
} from "./types";
import type {
  ApiMultiAnalysis,
  ApiZiweiChart,
  ApiEventStudy,
  ApiConflict,
  ApiConsensus,
  ApiEvidence,
  ApiTimelineMonths,
  ApiTimelineWeeks,
  ApiOpinion,
} from "./api";
import rawAnalyze from "./fixtures/analyze.json";
import rawZiweiForward from "./fixtures/ziwei-forward.json";
import rawZiweiReverse from "./fixtures/ziwei-reverse.json";

export const FIXTURE_QUERY_VALUE = "ui-reference";

export function isFixtureActive(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return new URLSearchParams(window.location.search).get("fixture") === FIXTURE_QUERY_VALUE;
  } catch {
    return false;
  }
}

export const WUXING_COLORS: Record<string, string> = {
  木: "var(--color-wood)",
  火: "var(--color-fire)",
  土: "var(--color-earth)",
  金: "var(--color-metal)",
  水: "var(--color-water)",
};

/* -------------------------------------------------------------------------- */
/* 首页 01_home.png                                                            */
/* -------------------------------------------------------------------------- */

export const homeFixture: HomePageData = {
  recent: [
    {
      code: "600519",
      name: "贵州茅台",
      analyzedAt: "2024-11-15 14:32",
      price: "1682.30",
      changePct: "+1.24%",
      trend: "up",
      engines: [
        { key: "bazi", label: "八字", direction: 1 },
        { key: "ziwei", label: "紫微", direction: 1 },
        { key: "huangli", label: "黄历", direction: 1 },
        { key: "backtest", label: "回测", direction: 1 },
      ],
      status: "正向共振",
      statusTone: "up",
    },
    {
      code: "000001",
      name: "平安银行",
      analyzedAt: "2024-11-14 16:20",
      price: "10.24",
      changePct: "-0.39%",
      trend: "down",
      engines: [
        { key: "bazi", label: "八字", direction: 1 },
        { key: "ziwei", label: "紫微", direction: -1 },
        { key: "huangli", label: "黄历", direction: 0 },
        { key: "backtest", label: "回测", direction: 1 },
      ],
      status: "模型分歧",
      statusTone: "conflict",
    },
    {
      code: "300750",
      name: "宁德时代",
      analyzedAt: "2024-11-13 10:18",
      price: "181.90",
      changePct: "+0.11%",
      trend: "up",
      engines: [
        { key: "bazi", label: "八字", direction: 0 },
        { key: "ziwei", label: "紫微", direction: 0 },
        { key: "huangli", label: "黄历", direction: 1 },
        { key: "backtest", label: "回测", direction: 0 },
      ],
      status: "中性观察",
      statusTone: "flat",
    },
  ],
  systemStatus: [
    { key: "bazi", label: "八字引擎", state: "ok", note: "运行正常", latency: "12ms" },
    { key: "ziwei", label: "紫微引擎", state: "ok", note: "运行正常", latency: "18ms" },
    { key: "huangli", label: "黄历引擎", state: "ok", note: "运行正常", latency: "16ms" },
    { key: "market", label: "行情数据", state: "ok", note: "运行正常", latency: "23ms" },
    { key: "knowledge", label: "古籍索引", state: "ok", note: "运行正常", latency: "28ms" },
  ],
  capabilities: [
    {
      key: "multi",
      title: "多模型研判",
      desc: "八字、紫微、黄历、量化",
      tone: "up",
    },
    {
      key: "window",
      title: "月/周时间窗口",
      desc: "识别关键时间节点",
      tone: "info",
    },
    {
      key: "classics",
      title: "古籍证据检索",
      desc: "连通经典古籍",
      tone: "gold",
    },
    {
      key: "backtest",
      title: "历史回测验证",
      desc: "基于历史数据检验",
      tone: "down",
    },
  ],
};

/** 首页能力卡的副标题（参考图为两行） */
export const homeCapabilitySub: Record<string, string> = {
  multi: "多维度综合分析",
  window: "把握周期与节奏",
  classics: "寻找历史中的相似性",
  backtest: "评估策略有效性",
};

/* -------------------------------------------------------------------------- */
/* 综合研判 02_integrated_analysis.png                                         */
/* -------------------------------------------------------------------------- */

const timeWindowDates = [
  "2027-04", "2027-05", "2027-06", "2027-07", "2027-08",
  "2027-09", "2027-10", "2027-11", "2027-12",
];

export const overviewFixture: OverviewPageData = {
  context: {
    stock: {
      code: "600519",
      windCode: "600519.SH",
      name: "贵州茅台",
      exchange: "上海证券交易所",
      board: "主板",
      listingDate: "2001-08-27",
      industry: "白酒",
    },
    birthProfile: {
      basis: "listing_open",
      basisLabel: "上市首日正式开盘",
      datetime: "2001-08-27 09:30 +08:00",
      timezone: "Asia/Shanghai",
      quality: "A",
      qualityScore: 0.95,
      sessionKey: "SSE/DEFAULT",
      derivation: "listing_open = 上市首个正式交易日(2001-08-27) + SSE 正式开盘(09:30) + Asia/Shanghai",
      variantMode: "not_applicable",
      variantNote: "股票不存在真实性别，运限顺逆不参与正式因子。",
      assumptions: [],
    },
    asOf: "2027-04-01 09:00",
    horizon: "20 交易日",
    quality: "A",
  },
  engines: [
    {
      engine: "bazi",
      displayName: "八字",
      score: 84,
      direction: 1,
      directionLabel: "偏强",
      confidence: 0.88,
      positiveCount: 6,
      negativeCount: 1,
      summary: "命理格局 · 五行生克",
      available: true,
      detailHref: "bazi",
      accent: "bazi",
    },
    {
      engine: "ziwei",
      displayName: "紫微斗数",
      score: 79,
      direction: 1,
      directionLabel: "偏强",
      confidence: 0.82,
      positiveCount: 5,
      negativeCount: 2,
      summary: "十四主星 · 宫位四化",
      available: true,
      detailHref: "ziwei",
      accent: "ziwei",
    },
    {
      engine: "huangli",
      displayName: "黄历",
      score: 73,
      direction: 1,
      directionLabel: "温和偏强",
      confidence: 0.76,
      positiveCount: 4,
      negativeCount: 2,
      summary: "天时因素 · 宜忌冲煞",
      available: true,
      detailHref: "huangli",
      accent: "huangli",
    },
  ],
  consensus: {
    displayOnly: true,
    label: "POSITIVE_CONSENSUS",
    labelCn: "正向共振",
    agreement: "高",
    historicalValidity: "中等",
    dataQuality: "A",
    directions: [
      { engine: "bazi", displayName: "八字", direction: 1 },
      { engine: "ziwei", displayName: "紫微斗数", direction: 1 },
      { engine: "huangli", displayName: "黄历", direction: 1 },
    ],
    unavailableEngines: [],
    note: "三才同顺 · 趋势可期",
    meanScore: 78.7,
  },
  conflict: {
    displayOnly: true,
    hasConflict: false,
    severity: "none",
    headline: "当前无显著冲突",
    reasons: [],
    note: "各模型结论趋于一致，未发现需要重点关注的分类。",
  },
  timeWindow: {
    dates: timeWindowDates,
    series: [
      {
        key: "bazi", name: "八字", color: "var(--color-gold)",
        values: [46, 61, 77, 83, 71, 58, 52, 63, 74],
      },
      {
        key: "ziwei", name: "紫微斗数", color: "#b07cd6",
        values: [42, 55, 68, 74, 62, 66, 72, 68, 60],
      },
      {
        key: "huangli", name: "黄历", color: "#4fd39b",
        values: [55, 58, 66, 70, 68, 60, 57, 62, 69],
      },
      {
        key: "consensus", name: "共识指数", color: "var(--color-up)",
        values: [48, 58, 72, 76, 67, 61, 60, 64, 68],
      },
    ],
    markers: [
      { date: "2027-06", label: "高共识区", tone: "consensus" },
      { date: "2027-10", label: "高冲突区", tone: "conflict" },
    ],
  },
  evidence: [
    {
      id: "EV-1",
      stance: "利多",
      title: "流年与命局三合",
      detail: "2027年丁未年与命局形成亥卯未三合，木火相生，利于品牌扩张与业绩增长。",
      source: "来源：八字",
      version: "v1.5",
      date: "2024-11-14",
    },
    {
      id: "EV-2",
      stance: "利多",
      title: "命宫化禄，财帛宫见吉曜",
      detail: "紫微命盘中命宫化禄，财帛宫见天厨、左辅，主财源稳固、贵人相助。",
      source: "来源：紫微斗数",
      version: "v1.4",
      date: "2024-11-14",
    },
    {
      id: "EV-3",
      stance: "中性",
      title: "黄历多吉日，利交易",
      detail: "未来20个交易日中，15日为黄道吉日，收账日，整体时机偏吉。",
      source: "来源：黄历",
      version: "v1.2",
      date: "2024-11-14",
    },
    {
      id: "EV-4",
      stance: "利空",
      title: "水旺克火，短期波动",
      detail: "流月壬子水旺，或对短期情绪面形成压制，需关注市场情绪与外部波动性。",
      source: "来源：八字",
      version: "v1.3",
      date: "2024-11-14",
    },
    {
      id: "EV-5",
      stance: "中性",
      title: "行业宫受冲，注意估值",
      detail: "紫微行业宫受对冲冲击，提示估值层面存在一定压力，建议控制仓位节奏。",
      source: "来源：紫微斗数",
      version: "v1.2",
      date: "2024-11-14",
    },
  ],
  backtestMetrics: [
    { key: "sample", label: "样本数", value: "312", tone: "flat", hint: "同类术数结构的历史出现次数" },
    { key: "uprate", label: "上涨率", value: "68.9%", tone: "up" },
    { key: "mean", label: "平均收益", value: "+12.6%", tone: "up" },
    { key: "excess", label: "超额收益", value: "+8.4%", tone: "up" },
    { key: "dd", label: "最大回撤", value: "-18.7%", tone: "down" },
  ],
  distribution: [
    { label: "-30%", value: 3, tone: "down" },
    { label: "-20%", value: 6, tone: "down" },
    { label: "-10%", value: 11, tone: "down" },
    { label: "0%", value: 26, tone: "up" },
    { label: "+10%", value: 31, tone: "up" },
    { label: "+20%", value: 19, tone: "up" },
    { label: "+30%", value: 7, tone: "up" },
  ],
  backtestConclusion:
    "在相似信号下，历史表现整体偏正向，胜率较高，具备一定的超额收益能力。但仍需关注极端行情下的回撤风险。",
  dataQuality: {
    grade: "A",
    score: 0.92,
    title: "数据质量",
    subtitle: "优秀",
    items: [
      { label: "数据完整性", value: "100%", state: "ok" },
      { label: "数据一致性", value: "通过", state: "ok" },
      { label: "未发现数据异常", value: "正常", state: "ok" },
      { label: "模型适用性", value: "良好", state: "ok" },
    ],
    riskNote:
      "本分析基于历史数据与传统文化模型，不构成投资建议；市场有风险，决策需谨慎。",
  },
};

/* -------------------------------------------------------------------------- */
/* 八字详情 03_bazi_detail.png                                                 */
/* -------------------------------------------------------------------------- */

function factor(
  factorId: string,
  name: string,
  direction: 1 | -1,
  ruleScore: number,
  explanation: string,
): FactorRowView {
  return {
    factorId,
    name,
    direction,
    ruleScore,
    confidence: 0.72,
    explanation,
    evidence: [],
    category: direction === 1 ? "month" : "natal",
    engine: factorId.startsWith("H_") ? "huangli" : "bazi",
    availability: "ok",
    rawValue: "",
    normalized: direction,
  };
}

export const baziFixture: BaziPageData = {
  context: overviewFixture.context,
  wuxing: [
    { element: "木", percent: 22, color: WUXING_COLORS["木"] },
    { element: "火", percent: 28, color: WUXING_COLORS["火"] },
    { element: "土", percent: 18, color: WUXING_COLORS["土"] },
    { element: "金", percent: 20, color: WUXING_COLORS["金"] },
    { element: "水", percent: 12, color: WUXING_COLORS["水"] },
  ],
  pillars: [
    {
      position: "year", positionCn: "年柱", stem: "辛", branch: "巳",
      stemTenGod: "伤官", hiddenStems: "丙 庚 戊", hiddenTenGods: "偏财 食神 比肩",
      nayin: "白蜡金", diShi: "绝",
    },
    {
      position: "month", positionCn: "月柱", stem: "丙", branch: "申",
      stemTenGod: "食神", hiddenStems: "庚 壬 戊", hiddenTenGods: "食神 偏财 比肩",
      nayin: "山下火", diShi: "长生",
    },
    {
      position: "day", positionCn: "日柱", stem: "戊", branch: "寅",
      stemTenGod: "日主", hiddenStems: "甲 丙 戊", hiddenTenGods: "正官 偏财 比肩",
      nayin: "城头土", diShi: "长生",
    },
    {
      position: "hour", positionCn: "时柱", stem: "丁", branch: "巳",
      stemTenGod: "伤官", hiddenStems: "丙 庚 戊", hiddenTenGods: "偏财 食神 比肩",
      nayin: "沙中土", diShi: "绝",
    },
  ],
  summary: [
    { label: "日主", value: "戊土", note: "厚重稳健，包容万物", tone: "gold" },
    { label: "旺衰", value: "偏旺", note: "得月令相生，根气较足", tone: "up" },
    { label: "格局", value: "食神生财格", note: "食神泄秀，财气通门户", tone: "gold" },
    { label: "喜神", value: "水", note: "调候润燥，流通全局", tone: "flat" },
    { label: "用神", value: "金", note: "泄土生财，助力流通", tone: "flat" },
    { label: "忌神", value: "火", note: "火土过旺，易致燥烈", tone: "down" },
  ],
  timeline: [
    {
      key: "dayun", title: "大运", primary: "2020 - 2030", secondary: "庚子 运",
      note: "金水 · 利于流通", tone: "gold",
    },
    {
      key: "year", title: "当前流年", primary: "2024 甲辰", secondary: "木土",
      note: "驿动中机有机", tone: "up",
    },
    {
      key: "month", title: "当前流月", primary: "2024-11 乙亥", secondary: "水水",
      note: "水旺润局，关注变化", tone: "flat",
    },
    {
      key: "day", title: "当前流日", primary: "2024-11-15 辛巳", secondary: "金火",
      note: "情绪波动，宜谨慎", tone: "down",
    },
  ],
  variantMode: "not_applicable",
  variantNote:
    "注：股票无天然性别，以下运限推演基于假设规则，请结合多模型综合判断。",
  positiveFactors: [
    factor("B_MONTH_003", "月令申金，泄土生财", 1, 8.2, "利于资金流动与估值修复。"),
    factor("B_YEAR_001", "流年甲辰，木土相生", 1, 7.6, "有利于行业景气与基本面改善。"),
    factor("B_STRUCT_002", "食神生财格，产品力强", 1, 7.1, "现金流稳定，未合长期配置。"),
    factor("B_FIVE_001", "五行流通，金水相济", 1, 6.4, "利于市场情绪回暖。"),
    factor("B_CYCLE_004", "当前大运金水", 1, 6.0, "外部环境与流动性相对友好。"),
  ],
  negativeFactors: [
    factor("B_FIRE_001", "火土过旺", -1, -8.5, "易致估值过热与情绪波动。"),
    factor("B_DAY_002", "当前流日辛巳", -1, -7.2, "金火相战，短期波动风险加大。"),
    factor("B_SEASON_003", "巳火重现", -1, -6.5, "市场情绪易躁，注意高位回调风险。"),
    factor("B_MACRO_001", "宏观流动性仍有不确定性", -1, -6.1, "可能压制估值扩张。"),
    factor("B_IND_002", "行业政策与消费环境变化", -1, -5.8, "存在外部扰动因素。"),
  ],
  evidence: [
    {
      id: "CT-1", stance: "中性", title: "《渊海子平》", detail: "「食神生财，财源自丰，乃富贵之格。」",
      source: "格局类", version: "卷三", date: "公版",
    },
    {
      id: "CT-2", stance: "中性", title: "《三命通会》", detail: "「土旺得金，泄秀生财，富厚可期。」",
      source: "五行类", version: "卷二", date: "公版",
    },
    {
      id: "CT-3", stance: "中性", title: "《滴天髓》", detail: "「土厚宜疏，得水而行，万物借生。」",
      source: "调候类", version: "卷四", date: "公版",
    },
  ],
  statistics: [
    { label: "同类结构历史样本", value: "312" },
    { label: "未来 20 日上涨率", value: "68.9%" },
    { label: "平均收益", value: "+12.6%" },
  ],
};

/** 上证/深证指数的展示用映射（参考图里的交易所中文名） */
export const EXCHANGE_CN: Record<string, string> = {
  SSE: "上海证券交易所",
  SZSE: "深圳证券交易所",
  BSE: "北京证券交易所",
  UNKNOWN: "未知交易所",
};

/* -------------------------------------------------------------------------- */
/* 十页显式 Fixture 数据集（离线 UI 验收用，不入库）                              */
/* -------------------------------------------------------------------------- */

export const ziweiForwardFixture = rawZiweiForward as unknown as ApiZiweiChart;
export const ziweiReverseFixture = rawZiweiReverse as unknown as ApiZiweiChart;

export const multiAnalysisFixture: ApiMultiAnalysis = {
  ...(rawAnalyze as unknown as ApiMultiAnalysis),
  ziwei_charts: {
    forward: ziweiForwardFixture,
    reverse: ziweiReverseFixture,
  },
  opinions: {
    bazi: {
      engine: "bazi",
      engine_version: "smx-bazi-native-1.0.0",
      availability: "ok",
      direction: 1,
      score: 81.2,
      confidence: 0.85,
      top_positive_reasons: [{ text: "日主偏旺，食神生财", factor_ids: ["B_MONTH_003"] }],
      top_negative_reasons: [{ text: "火土过旺，注意估值波动", factor_ids: ["B_FIRE_001"] }],
      factor_ids: ["B_MONTH_003", "B_YEAR_001"],
      note: "食神生财格，格局清纯，金水流通有情",
    },
    ziwei: {
      engine: "ziwei",
      engine_version: "smx-ziwei-native-1.0.0",
      availability: "ok",
      direction: 1,
      score: 74.0,
      confidence: 0.78,
      top_positive_reasons: [{ text: "命宫天府，三方四正吉星拱照", factor_ids: ["Z_PALACE_001"] }],
      top_negative_reasons: [{ text: "擎羊落陷，注意暗耗", factor_ids: ["Z_SHA_002"] }],
      factor_ids: ["Z_PALACE_001"],
      note: "本命财帛禄存，田宅武曲化禄，主基业稳固",
    },
    huangli: {
      engine: "huangli",
      engine_version: "huangli-engine-1.0.0",
      availability: "ok",
      direction: 1,
      score: 73.0,
      confidence: 0.76,
      top_positive_reasons: [{ text: "成日明堂黄道吉星", factor_ids: ["H_DAY_001"] }],
      top_negative_reasons: [{ text: "日支相刑，天干相冲", factor_ids: ["H_CHONG_001"] }],
      factor_ids: ["H_DAY_001"],
      note: "天时吉星相生，日课建除成日有利开拓",
    },
  },
  consensus: {
    display_only: true,
    label: "POSITIVE_CONSENSUS",
    label_cn: "正向共振",
    agreement: "高",
    historical_validity: "中等",
    data_quality: "A",
    directions: { bazi: 1, ziwei: 1, huangli: 1 },
    unavailable_engines: [],
    note: "三才同顺 · 趋势可期",
    mean_score: 76.1,
    available_engine_count: 3,
    agreement_score: 0.88,
  } as unknown as ApiConsensus,
  conflict: {
    display_only: true,
    has_conflict: false,
    severity: "none",
    conflict_level: "none",
    conflicting_engines: [],
    directions: { bazi: 1, ziwei: 1, huangli: 1 },
    reasons: [],
    note: "各模型结论趋于一致，未发现需要重点关注的分类。",
  } as unknown as ApiConflict,
};

export const huangliFixture = {
  chart_id: "HL-600519-20241115",
  engine_version: "huangli-engine-1.0.0",
  config_version: "cfg-2026.09",
  as_of: "2024-11-15T14:32:00",
  huangli:
    (rawAnalyze as unknown as { huangli?: Record<string, unknown> }).huangli ??
    (rawAnalyze as unknown as { raw_huangli?: Record<string, unknown> }).raw_huangli ??
    {},
};

export const backtestFixture: ApiEventStudy = {
  experiment_id: "EXP-20241115-01",
  factor_ids: ["COMBO_BAZI_ZIWEI_HUANGLI"],
  event_count: 312,
  universe_size: 500,
  research_status: "VALIDATED",
  research_status_reasons: ["通过随机置换负对照检验", "样本容量达到统计阈值"],
  horizons: [
    {
      horizon: 1,
      sample_count: 312,
      up_rate: 0.542,
      excess_up_rate: 0.038,
      mean_return: 0.008,
      median_return: 0.005,
      std_return: 0.021,
      mean_excess_return: 0.004,
      max_drawdown: -0.032,
      note: "超短期脉冲，受大盘日内噪音主导",
    },
    {
      horizon: 5,
      sample_count: 312,
      up_rate: 0.598,
      excess_up_rate: 0.071,
      mean_return: 0.032,
      median_return: 0.026,
      std_return: 0.048,
      mean_excess_return: 0.021,
      max_drawdown: -0.058,
      note: "周度效应初显，胜率具备初步统计显著性",
    },
    {
      horizon: 10,
      sample_count: 312,
      up_rate: 0.635,
      excess_up_rate: 0.095,
      mean_return: 0.068,
      median_return: 0.052,
      std_return: 0.076,
      mean_excess_return: 0.045,
      max_drawdown: -0.092,
      note: "半月度窗口，多模型共振胜率进一步提升",
    },
    {
      horizon: 20,
      sample_count: 312,
      up_rate: 0.689,
      excess_up_rate: 0.124,
      mean_return: 0.126,
      median_return: 0.098,
      std_return: 0.112,
      mean_excess_return: 0.084,
      max_drawdown: -0.142,
      note: "主研究窗口：历史同类共振结构平均跑赢基准 8.4%",
    },
    {
      horizon: 60,
      sample_count: 280,
      up_rate: 0.612,
      excess_up_rate: 0.088,
      mean_return: 0.158,
      median_return: 0.114,
      std_return: 0.185,
      mean_excess_return: 0.062,
      max_drawdown: -0.228,
      note: "季度窗口，易受行业周期与宏观Beta稀释",
    },
  ],
  methodology: "事件研究法：以多模型共振信号为触发锚点，计算持有期超额收益与最大回撤",
  warnings: [],
  data_source: {
    is_real: true,
    benchmark_degraded: false,
    label_rows: 312,
  },
};

export const conflictsFixture: ApiConflict = {
  display_only: true,
  has_conflict: false,
  severity: "none",
  conflict_level: "none",
  conflicting_engines: [],
  directions: { bazi: 1, ziwei: 1, huangli: 1 },
  reasons: [],
  note: "当前八字、紫微、黄历三引擎结论一致为正向，未检出跨模型冲突与假设分歧。",
  notes: [
    "方向一致性：八字(+1)、紫微(+1)、黄历(+1)均指向温和偏强",
    "时间尺度共振：月柱与当前流年均处于生旺阶段",
    "假设敏感度：顺行与逆行变体在核心三方四正上无致命冲突",
  ],
};

export const evidenceFixture: ApiEvidence = {
  analysis_id: "AN-20241115143200-600519-987e89",
  driver_factors: [
    { factor_id: "B_STRUCT_002", name: "食神生财格", normalized_value: 1, direction: 1 },
    { factor_id: "B_MONTH_003", name: "月令申金泄秀", normalized_value: 1, direction: 1 },
    { factor_id: "Z_PALACE_001", name: "命宫天府庙旺", normalized_value: 1, direction: 1 },
  ],
  evidence: {
    query: {
      query: "食神生财 月令申金 命宫天府",
      factor_ids: ["B_STRUCT_002", "B_MONTH_003", "Z_PALACE_001"],
      topics: ["格局", "用神", "星曜"],
    },
    supporting_evidence: [
      {
        entry_id: "EV-SUP-01",
        book: "渊海子平",
        chapter: "卷三·论食神",
        school: "子平法",
        topic: ["食神", "财帛"],
        original_text: "食神生旺，胜过财官。食神生财，财源自丰，乃富贵之格也。",
        modern_note: "日主得食神泄秀而转生财星，喻主营业务具备自主造血与现金流扩张能力。",
        score: 8.8,
        authority_weight: 1.0,
        stance: "support",
        source: "公版",
        edition: "明代崇祯本",
        provenance: "国家图书馆藏本",
        license_status: "公版",
      },
      {
        entry_id: "EV-SUP-02",
        book: "三命通会",
        chapter: "卷五·论十干坐支",
        school: "子平法",
        topic: ["五行", "流通"],
        original_text: "土旺得金，泄秀生财，富厚可期；金逢水润，流通无滞。",
        modern_note: "五行相生有情，资产结构扎实且周转顺畅。",
        score: 8.2,
        authority_weight: 1.0,
        stance: "support",
        source: "公版",
        edition: "清文渊阁四库全书本",
        provenance: "文渊阁本",
        license_status: "公版",
      },
      {
        entry_id: "EV-SUP-03",
        book: "紫微斗数全书",
        chapter: "卷一·诸星问答",
        school: "中州派",
        topic: ["天府", "命宫"],
        original_text: "天府南斗令星，主延寿解厄，在命宫主厚重沉着，财帛丰盈。",
        modern_note: "天府为财库之官，防守力强，在实体企业命盘中往往象征厚实的资产壁垒。",
        score: 8.5,
        authority_weight: 1.0,
        stance: "support",
        source: "公版",
        edition: "清同治刻本",
        provenance: "公版古籍",
        license_status: "公版",
      },
    ],
    counter_evidence: [
      {
        entry_id: "EV-CNT-01",
        book: "滴天髓",
        chapter: "通变篇·论衰旺",
        school: "子平法",
        topic: ["衰旺", "过旺"],
        original_text: "太旺者衰其势，火土燥烈无水以济，物极必反，反生破耗。",
        modern_note: "若火土过盛而缺乏持续水源润泽，可能面临估值过热或资金面边际收紧的隐忧。",
        score: 8.0,
        authority_weight: 1.0,
        stance: "counter",
        source: "公版",
        edition: "清道光陈素庵辑本",
        provenance: "清刻本",
        license_status: "公版",
      },
    ],
    neutral_evidence: [
      {
        entry_id: "EV-NEU-01",
        book: "神峰通考",
        chapter: "卷二·评断篇",
        school: "命理古籍",
        topic: ["运限", "变迁"],
        original_text: "运逢吉宿尚须防微杜渐，时逢凶煞亦有绝处逢生，吉凶相倚，非一成不变。",
        modern_note: "历史规律受宏观环境制约，术数结构推断需结合实际基本面动态跟踪。",
        score: 7.5,
        authority_weight: 1.0,
        stance: "neutral",
        source: "公版",
        edition: "明万历刊本",
        provenance: "公版藏书",
        license_status: "公版",
      },
    ],
    total_candidates: 3,
    retrieval_method: "公版古籍确定性倒排索引检索（规则与因子严格对齐）",
    knowledge_version: "v2026.09.1",
    note: "本检索依据清代及以前公版原文，遵循同时输出支持与反证原则，不作单向偏袒。",
  },
  disclaimer: "古籍条文只说明传统术数文献论述，不构成对证券资产未来收益率或涨跌的任何预测或保证。",
};

export const timelineMonthsFixture: ApiTimelineMonths = {
  analysis_id: "AN-20241115143200-600519-987e89",
  stock_code: "600519",
  as_of: "2024-11-15",
  variant_mode: "forward",
  aggregation_version: "v1.2.0",
  months: [
    {
      month: "2024-11",
      month_index: 1,
      start_date: "2024-11-01",
      end_date: "2024-11-30",
      bazi: { direction: 1, score: 78 } as unknown as ApiOpinion,
      ziwei: { direction: 1, score: 72 } as unknown as ApiOpinion,
      huangli: { direction: 1, score: 74 } as unknown as ApiOpinion,
      consensus: { label: "POSITIVE", label_cn: "正向共振", agreement: "高" } as unknown as ApiConsensus,
      conflict: { has_conflict: false } as unknown as ApiConflict,
      research_status: "VALIDATED",
      trading_days: 21,
      sample_dates: ["2024-11-01", "2024-11-15"],
      warnings: [],
    },
    {
      month: "2024-12",
      month_index: 2,
      start_date: "2024-12-01",
      end_date: "2024-12-31",
      bazi: { direction: 1, score: 76 } as unknown as ApiOpinion,
      ziwei: { direction: 0, score: 62 } as unknown as ApiOpinion,
      huangli: { direction: 1, score: 70 } as unknown as ApiOpinion,
      consensus: { label: "MODERATE", label_cn: "温和偏强", agreement: "中" } as unknown as ApiConsensus,
      conflict: { has_conflict: false } as unknown as ApiConflict,
      research_status: "VALIDATED",
      trading_days: 22,
      sample_dates: ["2024-12-02", "2024-12-16"],
      warnings: [],
    },
    {
      month: "2025-01",
      month_index: 3,
      start_date: "2025-01-01",
      end_date: "2025-01-31",
      bazi: { direction: 0, score: 58 } as unknown as ApiOpinion,
      ziwei: { direction: 1, score: 75 } as unknown as ApiOpinion,
      huangli: { direction: 0, score: 56 } as unknown as ApiOpinion,
      consensus: { label: "MIXED", label_cn: "中性观察", agreement: "中" } as unknown as ApiConsensus,
      conflict: { has_conflict: true } as unknown as ApiConflict,
      research_status: "VALIDATED",
      trading_days: 18,
      sample_dates: ["2025-01-02", "2025-01-15"],
      warnings: [],
    },
    {
      month: "2025-02",
      month_index: 4,
      start_date: "2025-02-01",
      end_date: "2025-02-28",
      bazi: { direction: 1, score: 82 } as unknown as ApiOpinion,
      ziwei: { direction: 1, score: 80 } as unknown as ApiOpinion,
      huangli: { direction: 1, score: 76 } as unknown as ApiOpinion,
      consensus: { label: "STRONG", label_cn: "强烈共振", agreement: "高" } as unknown as ApiConsensus,
      conflict: { has_conflict: false } as unknown as ApiConflict,
      research_status: "VALIDATED",
      trading_days: 15,
      sample_dates: ["2025-02-03", "2025-02-17"],
      warnings: [],
    },
  ],
  research_status: "VALIDATED",
  research_status_reasons: [],
  methodology: "交易日月度窗口：按交易日提取逐日流日因子并使用加权法聚合",
  warnings: [],
};

export const timelineWeeksFixture: ApiTimelineWeeks = {
  analysis_id: "AN-20241115143200-600519-987e89",
  stock_code: "600519",
  as_of: "2024-11-15",
  variant_mode: "forward",
  aggregation_version: "v1.2.0",
  weeks: [
    {
      week_index: 1,
      week_start: "2024-11-11",
      week_end: "2024-11-15",
      trading_days: 5,
      daily_results: [],
      aggregation_method: "交易日时间加权聚合（传统术数无原生流周）",
      aggregation_version: "v1.2.0",
      mean: 73.6,
      median: 73.0,
      min: 71.0,
      max: 77.0,
      positive_day_ratio: 0.8,
      weighted_mean: 74.2,
      consensus: { label: "POSITIVE", label_cn: "正向共振", agreement: "高" } as unknown as ApiConsensus,
      research_status: "VALIDATED",
      warnings: [],
    },
    {
      week_index: 2,
      week_start: "2024-11-18",
      week_end: "2024-11-22",
      trading_days: 5,
      daily_results: [],
      aggregation_method: "交易日时间加权聚合（传统术数无原生流周）",
      aggregation_version: "v1.2.0",
      mean: 71.3,
      median: 75.0,
      min: 60.0,
      max: 79.0,
      positive_day_ratio: 0.67,
      weighted_mean: 72.0,
      consensus: { label: "POSITIVE", label_cn: "偏多共振", agreement: "中" } as unknown as ApiConsensus,
      research_status: "VALIDATED",
      warnings: [],
    },
    {
      week_index: 3,
      week_start: "2024-11-25",
      week_end: "2024-11-29",
      trading_days: 5,
      daily_results: [],
      aggregation_method: "交易日时间加权聚合（传统术数无原生流周）",
      aggregation_version: "v1.2.0",
      mean: 65.0,
      median: 68.0,
      min: 55.0,
      max: 72.0,
      positive_day_ratio: 0.5,
      weighted_mean: 66.0,
      consensus: { label: "MODERATE", label_cn: "中性偏温和", agreement: "中" } as unknown as ApiConsensus,
      research_status: "VALIDATED",
      warnings: [],
    },
  ],
  research_status: "VALIDATED",
  research_status_reasons: [],
  methodology: "交易日周度窗口：周度为交易日聚合结果，非独立运限",
  warnings: [],
};

export const factorsDictionaryFixture = {
  total: 4,
  total_all: 114,
  by_category: {
    natal: 1,
    month: 1,
    day: 1,
    palace: 1,
  },
  disclaimer: "因子规则分仅表达传统文化模型结构强度，不代表预期收益率或上涨概率。",
  rule_version: "v2026.09.1",
  items: [
    {
      factor_id: "B_STRUCT_002",
      name: "食神生财格",
      engine: "bazi",
      category: "natal",
      definition: "日主有气，月令食神透出或得禄，并生助正偏财星之格局。",
      computation: "判定月令本气或透干十神为食神，且天干见财星无枭印克夺。",
      raw_unit: "布尔/分值",
      normalized_hint: "[-1, 1]",
      default_direction: 1,
      rule_score_meaning: "表示原局现金流与创利结构清纯度，不代表预期收益率。",
      rule_version: "1.0.0",
      requires: ["chart.pattern", "chart.ten_gods"],
      tags: ["格局", "财星", "食神"],
    },
    {
      factor_id: "B_MONTH_003",
      name: "月令申金生财",
      engine: "bazi",
      category: "month",
      definition: "月令为申金，为壬水之长生、戊土之食神泄秀之所。",
      computation: "月支为申，日主五行对应生助关系。",
      raw_unit: "分值",
      normalized_hint: "[-1, 1]",
      default_direction: 1,
      rule_score_meaning: "反映月令天时支持度，不代表短期股价上涨概率。",
      rule_version: "1.0.0",
      requires: ["chart.month_pillar"],
      tags: ["月令", "五行"],
    },
    {
      factor_id: "H_DAY_001",
      name: "建除明堂吉神",
      engine: "huangli",
      category: "day",
      definition: "流日建除十二值临成日，十二天神临明堂黄道吉星。",
      computation: "当日值日为成，天神为明堂黄道。",
      raw_unit: "类别",
      normalized_hint: "[-1, 1]",
      default_direction: 1,
      rule_score_meaning: "传统通书择日吉位强度，不构成证券交易买入建议。",
      rule_version: "1.0.0",
      requires: ["huangli.primary"],
      tags: ["黄历", "建除", "黄道"],
    },
    {
      factor_id: "Z_PALACE_001",
      name: "命宫天府庙旺",
      engine: "ziwei",
      category: "palace",
      definition: "命宫主星天府坐守，处于庙旺状态，三方四正吉星拱照。",
      computation: "命宫主星为天府，brightness为庙旺。",
      raw_unit: "星曜亮度",
      normalized_hint: "[-1, 1]",
      default_direction: 1,
      rule_score_meaning: "表示命盘防守稳固度与基业扎实度，不代表超额收益率。",
      rule_version: "1.0.0",
      requires: ["ziwei.palaces"],
      tags: ["紫微", "命宫", "天府"],
    },
  ],
};
