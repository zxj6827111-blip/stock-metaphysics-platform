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
  ApiHuangliOutlook,
  ApiHuangliPerformance,
  ApiTimelineDays,
  ApiTimelineMonths,
  ApiTimelineWeeks,
  ApiOpinion,
  ApiExperimentSummary,
  ApiExperimentDetail,
} from "./api";
import rawAnalyze from "./fixtures/analyze.json";
import rawZiweiForward from "./fixtures/ziwei-forward.json";
import rawZiweiReverse from "./fixtures/ziwei-reverse.json";
import rawHuangliOutlookToday from "./fixtures/huangli-outlook-today.json";
import rawHuangliOutlook20d from "./fixtures/huangli-outlook-20d.json";
import rawHuangliOutlook3m from "./fixtures/huangli-outlook-3m.json";
import rawHuangliPerformance1y1d from "./fixtures/huangli-performance-1y-1d.json";
import rawTimelineDays20 from "./fixtures/timeline-days-20.json";
import rawTimelineMonths12 from "./fixtures/timeline-months-12.json";
import rawTimelineWeeks12 from "./fixtures/timeline-weeks-12.json";

export const FIXTURE_QUERY_VALUE = "ui-reference";

/* -------------------------------------------------------------------------- */
/* 黄历 / 时间窗口演示样本                                                      */
/* -------------------------------------------------------------------------- */
/* 数值来自**真实确定性计算**（黄历引擎 + 实测交易日历 + 真实 hfq 行情），          */
/* 冻结成本地 JSON；`?fixture=ui-reference` 时页面直接读它，                       */
/* 从而保证演示模式全程**零真实后端请求**。                                        */
/* 边界：这些是固定样本，不是实时结果，也不能当作研究结论的验收证据。               */

export const huangliOutlookTodayFixture = rawHuangliOutlookToday as unknown as ApiHuangliOutlook;
export const huangliOutlook20dFixture = rawHuangliOutlook20d as unknown as ApiHuangliOutlook;
export const huangliOutlook3mFixture = rawHuangliOutlook3m as unknown as ApiHuangliOutlook;
export const huangliPerformanceFixture = rawHuangliPerformance1y1d as unknown as ApiHuangliPerformance;
export const timelineDaysFixture = rawTimelineDays20 as unknown as ApiTimelineDays;

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
  // 详情链接是**冻结那一刻拼好的**，所以自带当时的上下文（20d 窗口）。
  // 渲染时由 `withAnalysisContext` 用 URL 上此刻的上下文覆盖 ——
  // 这正是"链接携带过期上下文"这一类缺陷的样本，反例见
  // e2e/ui-parity-r1.spec.ts 的浏览器级点击落地测试。
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
      detailHref: "/stock/600519/bazi?fixture=ui-reference&horizon=20d",
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
      detailHref: "/stock/600519/ziwei?fixture=ui-reference&horizon=20d",
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
      detailHref: "/stock/600519/huangli?fixture=ui-reference&horizon=20d",
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
    // 演示样本没有真实行情与真实检索可核对，副标题必须说清这是冻结样本，
    // 不能写成"优秀"这种像核对结论的词。
    subtitle: "演示样本冻结值",
    items: [
      // 与真实模式同结构（dataSource.toDataQualityView 的四项），
      // 但演示模式下**没有依据的项一律标未提供 / 未验证**：
      // 出生档案没冻进样本，古籍检索在演示模式下被故意阻断。
      { label: "行情/资料完整性", value: "A（演示样本）", state: "warn" },
      { label: "出生档案推导", value: "未提供", state: "warn" },
      { label: "术数引擎版本", value: "smx-bazi-native-1.0.0", state: "ok" },
      { label: "古籍来源完整性", value: "未验证", state: "warn" },
    ],
    riskNote:
      "演示模式（UI 复刻）不加载真实行情与古籍检索，以上四项不构成数据质量核对结论。",
    riskNotes: [
      "演示模式（UI 复刻）不加载真实行情与古籍检索，以上四项不构成数据质量核对结论。",
      "移除 URL 中的 fixture 参数后，本卡改由本次分析的出生档案、版本戳与检索结果实算。",
    ],
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
  as_of: "2024-11-15 14:32:00",
  // 这份样本是在默认研究窗口下冻结的；后端会原样回传该字段，
  // 上下文栏与导出快照都读它，不再写死成「20 交易日」。
  horizon: "20d",
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

/** 研究实验演示样本（列表 + 详情）。
 *
 * 来自 scripts/capture_ui_fixtures.py 对 `backtest_experiment` / `backtest_result`
 * 中**已入库的真实实验**的冻结读取（含四类负对照判决与 Jaccard 重合度）。
 * 页面打开只读这份样本，不触发任何研究计算。
 */
export const experimentFixture: { list: ApiExperimentSummary[]; details: Record<string, ApiExperimentDetail> } = {
  "list": [
    {
      "experiment_id": "EXP-20260918173500-6f0889",
      "kind": "event_study",
      "name": "事件研究 B_MONTH_003,B_DAY_001,H_DAY_003",
      "factor_ids": [
        "B_MONTH_003",
        "B_DAY_001",
        "H_DAY_003"
      ],
      "universe": [
        "600519",
        "000001",
        "300750",
        "688981",
        "600036",
        "000858",
        "601318",
        "002594",
        "600000",
        "601899",
        "300059",
        "600030",
        "601012",
        "000333",
        "600276",
        "601888",
        "002415",
        "600887",
        "601166",
        "000651"
      ],
      "created_at": "2026-09-18 17:35:19.975521",
      "status": "INVALID_CONTROL"
    },
    {
      "experiment_id": "EXP-20260918162712-ddade1",
      "kind": "event_study",
      "name": "事件研究 B_MONTH_001,B_MONTH_002,H_DAY_001",
      "factor_ids": [
        "B_MONTH_001",
        "B_MONTH_002",
        "H_DAY_001"
      ],
      "universe": [
        "600519",
        "000001",
        "300750",
        "600036",
        "000858"
      ],
      "created_at": "2026-09-18 16:27:17.800302",
      "status": "completed"
    }
  ],
  "details": {
    "EXP-20260918162712-ddade1": {
      "experiment": {
        "experiment_id": "EXP-20260918162712-ddade1",
        "kind": "event_study",
        "name": "事件研究 B_MONTH_001,B_MONTH_002,H_DAY_001",
        "factor_ids": [
          "B_MONTH_001",
          "B_MONTH_002",
          "H_DAY_001"
        ],
        "universe": [
          "600519",
          "000001",
          "300750",
          "600036",
          "000858"
        ],
        "horizons": [
          5,
          10,
          20,
          60
        ],
        "methodology": "variant=real；事件 = 因子命中（logic=any, activation=nonzero）；持有期收益按事件日收盘至第 N 个交易日收盘计算；超额收益相对基准指数；样本要求事件日之后有完整的 N 个交易日数据，否则该样本被剔除（不用 0 填充）。",
        "seed": "20260918",
        "created_at": "2026-09-18 16:27:17.800302",
        "status": "completed",
        "date_from": "2021-01-01",
        "date_to": "2024-06-30",
        "benchmark_code": "000300",
        "params": {
          "sample_step_months": 3,
          "run_negative_controls": true
        }
      },
      "results_by_variant": {
        "random_birth_date": [
          {
            "horizon": "5",
            "sample_count": 70,
            "up_rate": 0.5,
            "mean_return": 0.002674,
            "median_return": 0.000631,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          },
          {
            "horizon": "10",
            "sample_count": 70,
            "up_rate": 0.6,
            "mean_return": 0.010676,
            "median_return": 0.009596,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          },
          {
            "horizon": "20",
            "sample_count": 70,
            "up_rate": 0.571429,
            "mean_return": 0.019104,
            "median_return": 0.026998,
            "mean_excess_return": -0.009325,
            "max_drawdown": -0.192174,
            "excess_up_rate": 0.428571,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          },
          {
            "horizon": "60",
            "sample_count": 70,
            "up_rate": 0.542857,
            "mean_return": 0.046304,
            "median_return": 0.022628,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          }
        ],
        "random_factor": [
          {
            "horizon": "5",
            "sample_count": 70,
            "up_rate": 0.5,
            "mean_return": 0.002674,
            "median_return": 0.000631,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          },
          {
            "horizon": "10",
            "sample_count": 70,
            "up_rate": 0.6,
            "mean_return": 0.010676,
            "median_return": 0.009596,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          },
          {
            "horizon": "20",
            "sample_count": 70,
            "up_rate": 0.571429,
            "mean_return": 0.019104,
            "median_return": 0.026998,
            "mean_excess_return": -0.009325,
            "max_drawdown": -0.192174,
            "excess_up_rate": 0.428571,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          },
          {
            "horizon": "60",
            "sample_count": 70,
            "up_rate": 0.542857,
            "mean_return": 0.046304,
            "median_return": 0.022628,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          }
        ],
        "real": [
          {
            "horizon": "5",
            "sample_count": 67,
            "up_rate": 0.507463,
            "mean_return": 0.002329,
            "median_return": 0.001782,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "note": "样本数 67；超额收益/最大回撤/最大上涨仅在 20D 列给出（避免指标口径错配）"
            }
          },
          {
            "horizon": "10",
            "sample_count": 67,
            "up_rate": 0.58209,
            "mean_return": 0.010251,
            "median_return": 0.007027,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "note": "样本数 67；超额收益/最大回撤/最大上涨仅在 20D 列给出（避免指标口径错配）"
            }
          },
          {
            "horizon": "20",
            "sample_count": 67,
            "up_rate": 0.58209,
            "mean_return": 0.019284,
            "median_return": 0.028815,
            "mean_excess_return": -0.010908,
            "max_drawdown": -0.192174,
            "excess_up_rate": 0.432836,
            "extra": {
              "note": "样本数 67"
            }
          },
          {
            "horizon": "60",
            "sample_count": 67,
            "up_rate": 0.537313,
            "mean_return": 0.04816,
            "median_return": 0.033227,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "note": "样本数 67；超额收益/最大回撤/最大上涨仅在 20D 列给出（避免指标口径错配）"
            }
          }
        ],
        "shift_minus_7d": [
          {
            "horizon": "5",
            "sample_count": 70,
            "up_rate": 0.5,
            "mean_return": 0.002674,
            "median_return": 0.000631,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          },
          {
            "horizon": "10",
            "sample_count": 70,
            "up_rate": 0.6,
            "mean_return": 0.010676,
            "median_return": 0.009596,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          },
          {
            "horizon": "20",
            "sample_count": 70,
            "up_rate": 0.571429,
            "mean_return": 0.019104,
            "median_return": 0.026998,
            "mean_excess_return": -0.009325,
            "max_drawdown": -0.192174,
            "excess_up_rate": 0.428571,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          },
          {
            "horizon": "60",
            "sample_count": 70,
            "up_rate": 0.542857,
            "mean_return": 0.046304,
            "median_return": 0.022628,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0180%，上涨率差 1.07%）。说明在当前样本上，术数因子相较随机未体现增量信息。"
            }
          }
        ],
        "shift_plus_7d": [
          {
            "horizon": "5",
            "sample_count": 66,
            "up_rate": 0.5,
            "mean_return": 0.00158,
            "median_return": 0.000631,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "outperform",
              "note": "真实因子 20 日平均收益高于对照 0.2035%，上涨率高出 3.66%。注意：这仍可能来自市场环境差异与多重检验，需样本外验证。"
            }
          },
          {
            "horizon": "10",
            "sample_count": 66,
            "up_rate": 0.590909,
            "mean_return": 0.007925,
            "median_return": 0.007947,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "outperform",
              "note": "真实因子 20 日平均收益高于对照 0.2035%，上涨率高出 3.66%。注意：这仍可能来自市场环境差异与多重检验，需样本外验证。"
            }
          },
          {
            "horizon": "20",
            "sample_count": 66,
            "up_rate": 0.545455,
            "mean_return": 0.017249,
            "median_return": 0.021968,
            "mean_excess_return": -0.011068,
            "max_drawdown": -0.192174,
            "excess_up_rate": 0.424242,
            "extra": {
              "verdict": "outperform",
              "note": "真实因子 20 日平均收益高于对照 0.2035%，上涨率高出 3.66%。注意：这仍可能来自市场环境差异与多重检验，需样本外验证。"
            }
          },
          {
            "horizon": "60",
            "sample_count": 66,
            "up_rate": 0.530303,
            "mean_return": 0.048454,
            "median_return": 0.0214,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "outperform",
              "note": "真实因子 20 日平均收益高于对照 0.2035%，上涨率高出 3.66%。注意：这仍可能来自市场环境差异与多重检验，需样本外验证。"
            }
          }
        ]
      }
    },
    "EXP-20260918173500-6f0889": {
      "experiment": {
        "experiment_id": "EXP-20260918173500-6f0889",
        "kind": "event_study",
        "name": "事件研究 B_MONTH_003,B_DAY_001,H_DAY_003",
        "factor_ids": [
          "B_MONTH_003",
          "B_DAY_001",
          "H_DAY_003"
        ],
        "universe": [
          "600519",
          "000001",
          "300750",
          "688981",
          "600036",
          "000858",
          "601318",
          "002594",
          "600000",
          "601899",
          "300059",
          "600030",
          "601012",
          "000333",
          "600276",
          "601888",
          "002415",
          "600887",
          "601166",
          "000651"
        ],
        "horizons": [
          5,
          10,
          20,
          60
        ],
        "methodology": "variant=real；事件 = 因子命中（logic=any, activation=nonzero）；持有期收益按事件日收盘至第 N 个交易日收盘计算；超额收益相对基准指数（按相同日历区间对齐，处理停牌）；样本要求事件日之后有完整的 N 个交易日数据，否则该样本被剔除（不用 0 填充）。",
        "seed": "20260918",
        "created_at": "2026-09-18 17:35:19.975521",
        "status": "INVALID_CONTROL",
        "date_from": "2021-01-01",
        "date_to": "2026-09-01",
        "benchmark_code": "000300",
        "params": {
          "sample_step_months": 3,
          "run_negative_controls": true
        }
      },
      "results_by_variant": {
        "random_birth_date": [
          {
            "horizon": "5",
            "sample_count": 445,
            "up_rate": 0.388764,
            "mean_return": -0.008371,
            "median_return": -0.00804,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0477%，上涨率差 -0.10%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.941304,
              "overlap_with_real": 433,
              "event_count": 445
            }
          },
          {
            "horizon": "10",
            "sample_count": 445,
            "up_rate": 0.460674,
            "mean_return": -0.003474,
            "median_return": -0.004735,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0477%，上涨率差 -0.10%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.941304,
              "overlap_with_real": 433,
              "event_count": 445
            }
          },
          {
            "horizon": "20",
            "sample_count": 445,
            "up_rate": 0.478652,
            "mean_return": -0.001927,
            "median_return": -0.006045,
            "mean_excess_return": 0.011118,
            "max_drawdown": -0.319344,
            "excess_up_rate": 0.534831,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0477%，上涨率差 -0.10%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.941304,
              "overlap_with_real": 433,
              "event_count": 445
            }
          },
          {
            "horizon": "60",
            "sample_count": 425,
            "up_rate": 0.418824,
            "mean_return": -0.01184,
            "median_return": -0.024968,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0477%，上涨率差 -0.10%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.941304,
              "overlap_with_real": 433,
              "event_count": 445
            }
          }
        ],
        "random_factor": [
          {
            "horizon": "5",
            "sample_count": 460,
            "up_rate": 0.384783,
            "mean_return": -0.008416,
            "median_return": -0.008118,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0923%，上涨率差 -0.06%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.973913,
              "overlap_with_real": 448,
              "event_count": 460
            }
          },
          {
            "horizon": "10",
            "sample_count": 460,
            "up_rate": 0.454348,
            "mean_return": -0.004005,
            "median_return": -0.005576,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0923%，上涨率差 -0.06%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.973913,
              "overlap_with_real": 448,
              "event_count": 460
            }
          },
          {
            "horizon": "20",
            "sample_count": 460,
            "up_rate": 0.478261,
            "mean_return": -0.002373,
            "median_return": -0.005996,
            "mean_excess_return": 0.010771,
            "max_drawdown": -0.319344,
            "excess_up_rate": 0.536957,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0923%，上涨率差 -0.06%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.973913,
              "overlap_with_real": 448,
              "event_count": 460
            }
          },
          {
            "horizon": "60",
            "sample_count": 440,
            "up_rate": 0.422727,
            "mean_return": -0.011753,
            "median_return": -0.022255,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.0923%，上涨率差 -0.06%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.973913,
              "overlap_with_real": 448,
              "event_count": 460
            }
          }
        ],
        "real": [
          {
            "horizon": "5",
            "sample_count": 448,
            "up_rate": 0.383929,
            "mean_return": -0.008161,
            "median_return": -0.007959,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "note": "样本数 448；超额收益/最大回撤/最大上涨仅在 20D 列给出（避免指标口径错配）",
              "research_status": "INVALID_CONTROL"
            }
          },
          {
            "horizon": "10",
            "sample_count": 448,
            "up_rate": 0.455357,
            "mean_return": -0.003453,
            "median_return": -0.005385,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "note": "样本数 448；超额收益/最大回撤/最大上涨仅在 20D 列给出（避免指标口径错配）",
              "research_status": "INVALID_CONTROL"
            }
          },
          {
            "horizon": "20",
            "sample_count": 448,
            "up_rate": 0.477679,
            "mean_return": -0.00145,
            "median_return": -0.005996,
            "mean_excess_return": 0.011455,
            "max_drawdown": -0.319344,
            "excess_up_rate": 0.540179,
            "extra": {
              "note": "样本数 448",
              "research_status": "INVALID_CONTROL"
            }
          },
          {
            "horizon": "60",
            "sample_count": 430,
            "up_rate": 0.427907,
            "mean_return": -0.009451,
            "median_return": -0.020644,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "note": "样本数 430；超额收益/最大回撤/最大上涨仅在 20D 列给出（避免指标口径错配）",
              "research_status": "INVALID_CONTROL"
            }
          }
        ],
        "shift_minus_7d": [
          {
            "horizon": "5",
            "sample_count": 443,
            "up_rate": 0.383747,
            "mean_return": -0.008849,
            "median_return": -0.008291,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.1533%，上涨率差 -0.31%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.936957,
              "overlap_with_real": 431,
              "event_count": 443
            }
          },
          {
            "horizon": "10",
            "sample_count": 443,
            "up_rate": 0.453725,
            "mean_return": -0.004621,
            "median_return": -0.005438,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.1533%，上涨率差 -0.31%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.936957,
              "overlap_with_real": 431,
              "event_count": 443
            }
          },
          {
            "horizon": "20",
            "sample_count": 443,
            "up_rate": 0.480813,
            "mean_return": -0.002983,
            "median_return": -0.005947,
            "mean_excess_return": 0.010674,
            "max_drawdown": -0.319344,
            "excess_up_rate": 0.541761,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.1533%，上涨率差 -0.31%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.936957,
              "overlap_with_real": 431,
              "event_count": 443
            }
          },
          {
            "horizon": "60",
            "sample_count": 424,
            "up_rate": 0.419811,
            "mean_return": -0.013534,
            "median_return": -0.024207,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 0.1533%，上涨率差 -0.31%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.936957,
              "overlap_with_real": 431,
              "event_count": 443
            }
          }
        ],
        "shift_plus_7d": [
          {
            "horizon": "5",
            "sample_count": 437,
            "up_rate": 0.386728,
            "mean_return": -0.008036,
            "median_return": -0.008196,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 -0.0221%，上涨率差 -0.52%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.923913,
              "overlap_with_real": 425,
              "event_count": 437
            }
          },
          {
            "horizon": "10",
            "sample_count": 437,
            "up_rate": 0.462243,
            "mean_return": -0.00307,
            "median_return": -0.004393,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 -0.0221%，上涨率差 -0.52%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.923913,
              "overlap_with_real": 425,
              "event_count": 437
            }
          },
          {
            "horizon": "20",
            "sample_count": 437,
            "up_rate": 0.482838,
            "mean_return": -0.001229,
            "median_return": -0.00502,
            "mean_excess_return": 0.011119,
            "max_drawdown": -0.319344,
            "excess_up_rate": 0.540046,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 -0.0221%，上涨率差 -0.52%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.923913,
              "overlap_with_real": 425,
              "event_count": 437
            }
          },
          {
            "horizon": "60",
            "sample_count": 419,
            "up_rate": 0.424821,
            "mean_return": -0.009961,
            "median_return": -0.021208,
            "mean_excess_return": null,
            "max_drawdown": null,
            "excess_up_rate": null,
            "extra": {
              "verdict": "tie",
              "note": "真实因子与对照无显著差异（平均收益差 -0.0221%，上涨率差 -0.52%）。说明在当前样本上，术数因子相较随机未体现增量信息。",
              "research_status": "INVALID_CONTROL",
              "jaccard_with_real": 0.923913,
              "overlap_with_real": 425,
              "event_count": 437
            }
          }
        ]
      }
    }
  }
};
/** 逐标的 EventStudy 演示样本。
 *
 * **刻意为空**：演示数据没有跑过事件研究流水线，因此 `horizons` 为空数组、
 * 状态为 NOT_RUN。早期版本这里填了一组看起来很漂亮的收益与"显著性"结论，
 * 那是伪造研究结论 —— 现在改为真实空态，页面显示"无样本"并说明原因。
 */
export const backtestFixture: ApiEventStudy = {
  "experiment_id": "",
  "factor_ids": [],
  "event_count": 0,
  "universe_size": 0,
  "research_status": "NOT_RUN",
  "research_status_reasons": [
    "演示数据：该标的未运行事件研究流水线（无标签样本），历史有效性判定不可用；本页不下任何\"已通过验证\"的结论。"
  ],
  "horizons": [],
  "methodology": "",
  "warnings": [],
  "data_source": null
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

/** 古籍证据演示样本。
 *
 * **不是手写样例**：由 scripts/capture_ui_fixtures.py 用真实 KnowledgeProvider
 * 对真实因子组合检索本地公版语料后**冻结**；entry_id / 书名 / 版本 / provenance
 * 与真实模式同源、逐条可核对。语料自身声明未逐字校勘，该限制在页面如实展示。
 */
/** 模型分歧的三种场景（无冲突 / 有冲突 / 模型不可用）。
 *
 * 由 scripts/capture_ui_fixtures.py 用**真实 ConflictDetector / ConsensusEngine**
 * 在固定输入上产出；不是手写的 has_conflict 布尔值。
 * 页面用 `?scenario=` 选择（仅演示模式生效），便于逐场景截图验收。
 */
export const conflictScenariosFixture: Record<string, { opinions: Record<string, Record<string, unknown>>; consensus: ApiConsensus; conflict: ApiConflict }> = {
  "no_conflict": {
    "opinions": {
      "bazi": {
        "engine": "bazi",
        "engine_version": "bazi-1.0.0",
        "availability": "ok",
        "direction": 1,
        "score": 68.0,
        "confidence": 0.72,
        "top_positive_reasons": [
          {
            "text": "bazi 的主要支持依据（演示固定输入）",
            "factor_ids": []
          }
        ],
        "top_negative_reasons": [],
        "factor_ids": [],
        "note": "",
        "assumptions": []
      },
      "ziwei": {
        "engine": "ziwei",
        "engine_version": "ziwei-1.0.0",
        "availability": "ok",
        "direction": 1,
        "score": 61.5,
        "confidence": 0.63,
        "top_positive_reasons": [
          {
            "text": "ziwei 的主要支持依据（演示固定输入）",
            "factor_ids": []
          }
        ],
        "top_negative_reasons": [],
        "factor_ids": [],
        "note": "",
        "assumptions": []
      },
      "huangli": {
        "engine": "huangli",
        "engine_version": "huangli-1.0.0",
        "availability": "ok",
        "direction": 1,
        "score": 57.2,
        "confidence": 0.55,
        "top_positive_reasons": [
          {
            "text": "huangli 的主要支持依据（演示固定输入）",
            "factor_ids": []
          }
        ],
        "top_negative_reasons": [],
        "factor_ids": [],
        "note": "",
        "assumptions": []
      }
    },
    "consensus": {
      "display_only": false,
      "label": "POSITIVE_CONSENSUS",
      "label_cn": "正向共振",
      "participating_engines": [
        "bazi",
        "ziwei",
        "huangli"
      ],
      "unavailable_engines": [],
      "directions": {
        "bazi": 1,
        "ziwei": 1,
        "huangli": 1
      },
      "mean_score": 62.23,
      "agreement": "高（方向完全一致）",
      "historical_validity": "ResearchStatus=NOT_RUN；共识与历史有效性是两件事，必须分开阅读。",
      "data_quality": "B",
      "note": "agreement_score 是**方向一致度**（与多数方向相同的引擎占比），不是各引擎分数的平均，也不表示上涨概率。",
      "consensus_class": "POSITIVE_CONSENSUS",
      "agreement_score": 1.0,
      "available_engine_count": 3,
      "positive_engine_count": 3,
      "negative_engine_count": 0,
      "neutral_engine_count": 0,
      "engine_opinions": {
        "bazi": {
          "engine": "bazi",
          "availability": "ok",
          "direction": 1,
          "direction_label": "偏强",
          "score": 68.0,
          "confidence": 0.72,
          "engine_version": "bazi-1.0.0",
          "factor_ids": [],
          "positive_reasons": [
            "bazi 的主要支持依据（演示固定输入）"
          ],
          "negative_reasons": [],
          "research_status": "NOT_RUN",
          "historical_validity": {},
          "data_quality": {},
          "assumptions": [],
          "note": ""
        },
        "ziwei": {
          "engine": "ziwei",
          "availability": "ok",
          "direction": 1,
          "direction_label": "偏强",
          "score": 61.5,
          "confidence": 0.63,
          "engine_version": "ziwei-1.0.0",
          "factor_ids": [],
          "positive_reasons": [
            "ziwei 的主要支持依据（演示固定输入）"
          ],
          "negative_reasons": [],
          "research_status": "NOT_RUN",
          "historical_validity": {},
          "data_quality": {},
          "assumptions": [],
          "note": ""
        },
        "huangli": {
          "engine": "huangli",
          "availability": "ok",
          "direction": 1,
          "direction_label": "偏强",
          "score": 57.2,
          "confidence": 0.55,
          "engine_version": "huangli-1.0.0",
          "factor_ids": [],
          "positive_reasons": [
            "huangli 的主要支持依据（演示固定输入）"
          ],
          "negative_reasons": [],
          "research_status": "NOT_RUN",
          "historical_validity": {},
          "data_quality": {},
          "assumptions": [],
          "note": ""
        }
      },
      "research_status": "NOT_RUN",
      "historical_consensus_stats": {},
      "interpretation": "术数模型之间的一致性：正向共振（可用 3 个引擎：八字 偏强、黄历 偏强、紫微斗数 偏强）。 **历史统计未运行**：上述一致性只是模型之间的方向比较，没有经过任何历史数据检验。",
      "notes": [
        "agreement_score 是**方向一致度**（与多数方向相同的引擎占比），不是各引擎分数的平均，也不表示上涨概率。"
      ]
    },
    "conflict": {
      "display_only": false,
      "has_conflict": false,
      "severity": "none",
      "conflicting_engines": [],
      "directions": {
        "bazi": 1,
        "ziwei": 1,
        "huangli": 1
      },
      "reasons": [
        "当前无显著冲突：各可用模型方向一致或均为中性。"
      ],
      "conflicting_factor_ids": [],
      "note": "分歧是**信息**而不是噪声：本系统如实并列展示各模型方向与依据，禁止用平均分掩盖冲突（AGENTS.md §2.4）。；historical_conflict_stats 未运行时视为 `NOT_RUN`，即『历史类似冲突的后续表现』尚未被统计过。",
      "conflict_level": "none",
      "major_conflicts": [],
      "factor_conflicts": [],
      "time_horizon_conflicts": [],
      "assumption_conflicts": [],
      "historical_conflict_stats": {
        "status": "NOT_RUN"
      },
      "notes": [
        "分歧是**信息**而不是噪声：本系统如实并列展示各模型方向与依据，禁止用平均分掩盖冲突（AGENTS.md §2.4）。",
        "historical_conflict_stats 未运行时视为 `NOT_RUN`，即『历史类似冲突的后续表现』尚未被统计过。"
      ]
    }
  },
  "conflict": {
    "opinions": {
      "bazi": {
        "engine": "bazi",
        "engine_version": "bazi-1.0.0",
        "availability": "ok",
        "direction": 1,
        "score": 71.0,
        "confidence": 0.74,
        "top_positive_reasons": [
          {
            "text": "bazi 的主要支持依据（演示固定输入）",
            "factor_ids": []
          }
        ],
        "top_negative_reasons": [],
        "factor_ids": [],
        "note": "",
        "assumptions": []
      },
      "ziwei": {
        "engine": "ziwei",
        "engine_version": "ziwei-1.0.0",
        "availability": "ok",
        "direction": 0,
        "score": 52.0,
        "confidence": 0.48,
        "top_positive_reasons": [
          {
            "text": "ziwei 的主要支持依据（演示固定输入）",
            "factor_ids": []
          }
        ],
        "top_negative_reasons": [
          {
            "text": "ziwei 的主要反对依据（演示固定输入）",
            "factor_ids": []
          }
        ],
        "factor_ids": [],
        "note": "",
        "assumptions": []
      },
      "huangli": {
        "engine": "huangli",
        "engine_version": "huangli-1.0.0",
        "availability": "ok",
        "direction": -1,
        "score": 41.5,
        "confidence": 0.58,
        "top_positive_reasons": [],
        "top_negative_reasons": [
          {
            "text": "huangli 的主要反对依据（演示固定输入）",
            "factor_ids": []
          }
        ],
        "factor_ids": [],
        "note": "",
        "assumptions": []
      }
    },
    "consensus": {
      "display_only": false,
      "label": "MIXED",
      "label_cn": "模型分歧",
      "participating_engines": [
        "bazi",
        "ziwei",
        "huangli"
      ],
      "unavailable_engines": [],
      "directions": {
        "bazi": 1,
        "ziwei": 0,
        "huangli": -1
      },
      "mean_score": 54.83,
      "agreement": "低（存在反向引擎）",
      "historical_validity": "ResearchStatus=NOT_RUN；共识与历史有效性是两件事，必须分开阅读。",
      "data_quality": "B",
      "note": "agreement_score 是**方向一致度**（与多数方向相同的引擎占比），不是各引擎分数的平均，也不表示上涨概率。",
      "consensus_class": "MIXED",
      "agreement_score": 0.3333,
      "available_engine_count": 3,
      "positive_engine_count": 1,
      "negative_engine_count": 1,
      "neutral_engine_count": 1,
      "engine_opinions": {
        "bazi": {
          "engine": "bazi",
          "availability": "ok",
          "direction": 1,
          "direction_label": "偏强",
          "score": 71.0,
          "confidence": 0.74,
          "engine_version": "bazi-1.0.0",
          "factor_ids": [],
          "positive_reasons": [
            "bazi 的主要支持依据（演示固定输入）"
          ],
          "negative_reasons": [],
          "research_status": "NOT_RUN",
          "historical_validity": {},
          "data_quality": {},
          "assumptions": [],
          "note": ""
        },
        "ziwei": {
          "engine": "ziwei",
          "availability": "ok",
          "direction": 0,
          "direction_label": "中性",
          "score": 52.0,
          "confidence": 0.48,
          "engine_version": "ziwei-1.0.0",
          "factor_ids": [],
          "positive_reasons": [
            "ziwei 的主要支持依据（演示固定输入）"
          ],
          "negative_reasons": [
            "ziwei 的主要反对依据（演示固定输入）"
          ],
          "research_status": "NOT_RUN",
          "historical_validity": {},
          "data_quality": {},
          "assumptions": [],
          "note": ""
        },
        "huangli": {
          "engine": "huangli",
          "availability": "ok",
          "direction": -1,
          "direction_label": "偏弱",
          "score": 41.5,
          "confidence": 0.58,
          "engine_version": "huangli-1.0.0",
          "factor_ids": [],
          "positive_reasons": [],
          "negative_reasons": [
            "huangli 的主要反对依据（演示固定输入）"
          ],
          "research_status": "NOT_RUN",
          "historical_validity": {},
          "data_quality": {},
          "assumptions": [],
          "note": ""
        }
      },
      "research_status": "NOT_RUN",
      "historical_consensus_stats": {},
      "interpretation": "术数模型之间的一致性：模型分歧（可用 3 个引擎：八字 偏强、黄历 偏弱、紫微斗数 中性）。 **历史统计未运行**：上述一致性只是模型之间的方向比较，没有经过任何历史数据检验。 **方向存在冲突，本系统不做平均**：各模型方向已如实并列展示，冲突原因见 conflict 报告。",
      "notes": [
        "agreement_score 是**方向一致度**（与多数方向相同的引擎占比），不是各引擎分数的平均，也不表示上涨概率。"
      ]
    },
    "conflict": {
      "display_only": false,
      "has_conflict": true,
      "severity": "major",
      "conflicting_engines": [
        "bazi",
        "huangli"
      ],
      "directions": {
        "bazi": 1,
        "ziwei": 0,
        "huangli": -1
      },
      "reasons": [
        "方向对立：八字(偏强) vs 黄历(偏弱)。系统**不会**用平均值掩盖该分歧。"
      ],
      "conflicting_factor_ids": [],
      "note": "分歧是**信息**而不是噪声：本系统如实并列展示各模型方向与依据，禁止用平均分掩盖冲突（AGENTS.md §2.4）。；historical_conflict_stats 未运行时视为 `NOT_RUN`，即『历史类似冲突的后续表现』尚未被统计过。",
      "conflict_level": "major",
      "major_conflicts": [
        {
          "kind": "direction",
          "engine": "bazi",
          "direction": 1,
          "direction_label": "偏强",
          "score": 71.0,
          "confidence": 0.74,
          "reasons": [
            "bazi 的主要支持依据（演示固定输入）"
          ],
          "factor_ids": []
        },
        {
          "kind": "direction",
          "engine": "huangli",
          "direction": -1,
          "direction_label": "偏弱",
          "score": 41.5,
          "confidence": 0.58,
          "reasons": [
            "huangli 的主要反对依据（演示固定输入）"
          ],
          "factor_ids": []
        }
      ],
      "factor_conflicts": [],
      "time_horizon_conflicts": [],
      "assumption_conflicts": [],
      "historical_conflict_stats": {
        "status": "NOT_RUN"
      },
      "notes": [
        "分歧是**信息**而不是噪声：本系统如实并列展示各模型方向与依据，禁止用平均分掩盖冲突（AGENTS.md §2.4）。",
        "historical_conflict_stats 未运行时视为 `NOT_RUN`，即『历史类似冲突的后续表现』尚未被统计过。"
      ]
    }
  },
  "engine_unavailable": {
    "opinions": {
      "bazi": {
        "engine": "bazi",
        "engine_version": "bazi-1.0.0",
        "availability": "ok",
        "direction": 1,
        "score": 66.0,
        "confidence": 0.7,
        "top_positive_reasons": [
          {
            "text": "bazi 的主要支持依据（演示固定输入）",
            "factor_ids": []
          }
        ],
        "top_negative_reasons": [],
        "factor_ids": [],
        "note": "",
        "assumptions": []
      },
      "ziwei": {
        "engine": "ziwei",
        "engine_version": "ziwei-1.0.0",
        "availability": "unavailable",
        "direction": 0,
        "score": null,
        "confidence": 0.0,
        "top_positive_reasons": [],
        "top_negative_reasons": [],
        "factor_ids": [],
        "note": "紫微排盘服务不可用，本次未产出观点（不以 0 分参与共识）。",
        "assumptions": []
      },
      "huangli": {
        "engine": "huangli",
        "engine_version": "huangli-1.0.0",
        "availability": "ok",
        "direction": -1,
        "score": 44.0,
        "confidence": 0.6,
        "top_positive_reasons": [],
        "top_negative_reasons": [
          {
            "text": "huangli 的主要反对依据（演示固定输入）",
            "factor_ids": []
          }
        ],
        "factor_ids": [],
        "note": "",
        "assumptions": []
      }
    },
    "consensus": {
      "display_only": false,
      "label": "MIXED",
      "label_cn": "模型分歧",
      "participating_engines": [
        "bazi",
        "huangli"
      ],
      "unavailable_engines": [
        "ziwei"
      ],
      "directions": {
        "bazi": 1,
        "huangli": -1
      },
      "mean_score": 55.0,
      "agreement": "低（存在反向引擎）",
      "historical_validity": "ResearchStatus=NOT_RUN；共识与历史有效性是两件事，必须分开阅读。",
      "data_quality": "B",
      "note": "agreement_score 是**方向一致度**（与多数方向相同的引擎占比），不是各引擎分数的平均，也不表示上涨概率。；以下引擎本次不可用，未计入分母：ziwei。",
      "consensus_class": "MIXED",
      "agreement_score": 0.5,
      "available_engine_count": 2,
      "positive_engine_count": 1,
      "negative_engine_count": 1,
      "neutral_engine_count": 0,
      "engine_opinions": {
        "bazi": {
          "engine": "bazi",
          "availability": "ok",
          "direction": 1,
          "direction_label": "偏强",
          "score": 66.0,
          "confidence": 0.7,
          "engine_version": "bazi-1.0.0",
          "factor_ids": [],
          "positive_reasons": [
            "bazi 的主要支持依据（演示固定输入）"
          ],
          "negative_reasons": [],
          "research_status": "NOT_RUN",
          "historical_validity": {},
          "data_quality": {},
          "assumptions": [],
          "note": ""
        },
        "ziwei": {
          "engine": "ziwei",
          "availability": "unavailable",
          "direction": 0,
          "direction_label": "中性",
          "score": null,
          "confidence": 0.0,
          "engine_version": "ziwei-1.0.0",
          "factor_ids": [],
          "positive_reasons": [],
          "negative_reasons": [],
          "research_status": "NOT_RUN",
          "historical_validity": {},
          "data_quality": {},
          "assumptions": [],
          "note": "紫微排盘服务不可用，本次未产出观点（不以 0 分参与共识）。"
        },
        "huangli": {
          "engine": "huangli",
          "availability": "ok",
          "direction": -1,
          "direction_label": "偏弱",
          "score": 44.0,
          "confidence": 0.6,
          "engine_version": "huangli-1.0.0",
          "factor_ids": [],
          "positive_reasons": [],
          "negative_reasons": [
            "huangli 的主要反对依据（演示固定输入）"
          ],
          "research_status": "NOT_RUN",
          "historical_validity": {},
          "data_quality": {},
          "assumptions": [],
          "note": ""
        }
      },
      "research_status": "NOT_RUN",
      "historical_consensus_stats": {},
      "interpretation": "术数模型之间的一致性：模型分歧（可用 2 个引擎：八字 偏强、黄历 偏弱）。 未计入：ziwei。 **历史统计未运行**：上述一致性只是模型之间的方向比较，没有经过任何历史数据检验。 **方向存在冲突，本系统不做平均**：各模型方向已如实并列展示，冲突原因见 conflict 报告。",
      "notes": [
        "agreement_score 是**方向一致度**（与多数方向相同的引擎占比），不是各引擎分数的平均，也不表示上涨概率。",
        "以下引擎本次不可用，未计入分母：ziwei。"
      ]
    },
    "conflict": {
      "display_only": false,
      "has_conflict": true,
      "severity": "major",
      "conflicting_engines": [
        "bazi",
        "huangli"
      ],
      "directions": {
        "bazi": 1,
        "huangli": -1
      },
      "reasons": [
        "方向对立：八字(偏强) vs 黄历(偏弱)。系统**不会**用平均值掩盖该分歧。"
      ],
      "conflicting_factor_ids": [],
      "note": "分歧是**信息**而不是噪声：本系统如实并列展示各模型方向与依据，禁止用平均分掩盖冲突（AGENTS.md §2.4）。；historical_conflict_stats 未运行时视为 `NOT_RUN`，即『历史类似冲突的后续表现』尚未被统计过。",
      "conflict_level": "major",
      "major_conflicts": [
        {
          "kind": "direction",
          "engine": "bazi",
          "direction": 1,
          "direction_label": "偏强",
          "score": 66.0,
          "confidence": 0.7,
          "reasons": [
            "bazi 的主要支持依据（演示固定输入）"
          ],
          "factor_ids": []
        },
        {
          "kind": "direction",
          "engine": "huangli",
          "direction": -1,
          "direction_label": "偏弱",
          "score": 44.0,
          "confidence": 0.6,
          "reasons": [
            "huangli 的主要反对依据（演示固定输入）"
          ],
          "factor_ids": []
        }
      ],
      "factor_conflicts": [],
      "time_horizon_conflicts": [],
      "assumption_conflicts": [],
      "historical_conflict_stats": {
        "status": "NOT_RUN"
      },
      "notes": [
        "分歧是**信息**而不是噪声：本系统如实并列展示各模型方向与依据，禁止用平均分掩盖冲突（AGENTS.md §2.4）。",
        "historical_conflict_stats 未运行时视为 `NOT_RUN`，即『历史类似冲突的后续表现』尚未被统计过。"
      ]
    }
  }
};
/** 古籍证据演示样本。
 *
 * **不是手写样例**：由 scripts/capture_ui_fixtures.py 用真实 KnowledgeProvider
 * 对真实因子组合检索本地公版语料后**冻结**；entry_id / 书名 / 版本 / provenance
 * 与真实模式同源、逐条可核对。语料自身声明未逐字校勘，该限制在页面如实展示。
 */
export const evidenceFixture: ApiEvidence = {
  "analysis_id": "AN-20241115143200-600519-987e89",
  "driver_factors": [
    {
      "factor_id": "B_NATAL_001",
      "name": "日主强弱",
      "normalized_value": null,
      "direction": 1
    },
    {
      "factor_id": "B_NATAL_002",
      "name": "财星数量",
      "normalized_value": null,
      "direction": 1
    },
    {
      "factor_id": "B_NATAL_009",
      "name": "格局类型",
      "normalized_value": null,
      "direction": 1
    }
  ],
  "evidence": {
    "query": {
      "query": "日主强弱 财星数量 格局类型",
      "factor_ids": [
        "B_NATAL_001",
        "B_NATAL_002",
        "B_NATAL_009"
      ],
      "topics": [
        "旺衰",
        "财星",
        "格局"
      ]
    },
    "supporting_evidence": [
      {
        "entry_id": "DTS-0006",
        "book": "滴天髓",
        "chapter": "衰旺",
        "school": "子平",
        "topic": [
          "得令",
          "月令",
          "旺衰"
        ],
        "original_text": "月令乃提纲之府，譬之宅也，人元为用事之神，宅之定向也。",
        "modern_note": "月令是全局的提纲，藏干是实际用事之神。本系统 B_NATAL_004 与格局判定都以月令为第一依据。",
        "score": 8.7845,
        "authority_weight": 1.4,
        "stance": "supporting",
        "source": "公版古籍《滴天髓》（公版通行本（清代刊本系统））",
        "edition": "公版通行本（清代刊本系统）",
        "provenance": "明清以来广泛流传的命理经典，原文属公有领域。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "格局"
        ]
      },
      {
        "entry_id": "ZPZQ-0001",
        "book": "子平真诠",
        "chapter": "论用神",
        "school": "子平",
        "topic": [
          "月令",
          "用神",
          "格局"
        ],
        "original_text": "八字用神，专求月令。",
        "modern_note": "子平真诠的核心主张：用神从月令求取。本系统 B_NATAL_004 / B_NATAL_009 严格以此为第一依据。",
        "score": 7.8689,
        "authority_weight": 1.5,
        "stance": "supporting",
        "source": "公版古籍《子平真诠》（公版通行本）",
        "edition": "公版通行本",
        "provenance": "清代论格局最精之作，专主月令取用。",
        "license_status": "public_domain",
        "matched_query_terms": []
      },
      {
        "entry_id": "DTS-0004",
        "book": "滴天髓",
        "chapter": "衰旺",
        "school": "子平",
        "topic": [
          "旺衰",
          "用神",
          "扶抑"
        ],
        "original_text": "能知衰旺之真机，其于三命之奥，思过半矣。",
        "modern_note": "判断日主旺衰是命理分析的核心难点，也是本系统 B_NATAL_001 因子的经典依据。",
        "score": 7.8557,
        "authority_weight": 1.4,
        "stance": "supporting",
        "source": "公版古籍《滴天髓》（公版通行本（清代刊本系统））",
        "edition": "公版通行本（清代刊本系统）",
        "provenance": "明清以来广泛流传的命理经典，原文属公有领域。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "日主",
          "旺衰"
        ]
      },
      {
        "entry_id": "DTS-0005",
        "book": "滴天髓",
        "chapter": "衰旺",
        "school": "子平",
        "topic": [
          "旺衰",
          "扶抑",
          "用神"
        ],
        "original_text": "旺则宜泄宜伤，衰则喜帮喜助，子平之理也。",
        "modern_note": "身旺宜用食伤泄、官杀克；身衰宜用印绶生、比劫帮。这正是本系统扶抑法的实现依据。",
        "score": 7.7539,
        "authority_weight": 1.4,
        "stance": "supporting",
        "source": "公版古籍《滴天髓》（公版通行本（清代刊本系统））",
        "edition": "公版通行本（清代刊本系统）",
        "provenance": "明清以来广泛流传的命理经典，原文属公有领域。",
        "license_status": "public_domain",
        "matched_query_terms": []
      },
      {
        "entry_id": "DTS-0007",
        "book": "滴天髓",
        "chapter": "何知章",
        "school": "子平",
        "topic": [
          "财星",
          "富"
        ],
        "original_text": "何知其人富，财气通门户。",
        "modern_note": "传统以『财气通门户』论富，即财星得地、有源有护。**注意：这是命理概念，不是股票价格与收益的预测规则。**",
        "score": 7.4767,
        "authority_weight": 1.4,
        "stance": "supporting",
        "source": "公版古籍《滴天髓》（公版通行本（清代刊本系统））",
        "edition": "公版通行本（清代刊本系统）",
        "provenance": "明清以来广泛流传的命理经典，原文属公有领域。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "财星"
        ]
      },
      {
        "entry_id": "YHZP-0001",
        "book": "渊海子平",
        "chapter": "论财",
        "school": "子平",
        "topic": [
          "财星"
        ],
        "original_text": "财为养命之源，不可无也。",
        "modern_note": "传统认为财星是养命之源。这只是命理表述，不能直接翻译成『股价会涨』。",
        "score": 7.0084,
        "authority_weight": 1.3,
        "stance": "supporting",
        "source": "公版古籍《渊海子平》（公版通行本）",
        "edition": "公版通行本",
        "provenance": "子平术集成性典籍，十神、格局、神煞诸论多出于此系统。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "财星"
        ]
      }
    ],
    "counter_evidence": [
      {
        "entry_id": "DTS-0010",
        "book": "滴天髓",
        "chapter": "财论",
        "school": "子平",
        "topic": [
          "财星",
          "比劫",
          "反证"
        ],
        "original_text": "财旺身强，白手成家；财旺身弱，多为他人作嫁。",
        "modern_note": "**反证条目**：财星的作用依赖日主强弱这一前提条件。脱离旺衰单看财星数量没有意义。",
        "score": 14.6418,
        "authority_weight": 1.4,
        "stance": "counter",
        "source": "公版古籍《滴天髓》（公版通行本（清代刊本系统））",
        "edition": "公版通行本（清代刊本系统）",
        "provenance": "明清以来广泛流传的命理经典，原文属公有领域。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "日主",
          "强弱",
          "财星",
          "数量",
          "旺衰"
        ]
      },
      {
        "entry_id": "DTS-0009",
        "book": "滴天髓",
        "chapter": "财论",
        "school": "子平",
        "topic": [
          "财星",
          "身财",
          "反证"
        ],
        "original_text": "财多身弱，正谓富屋贫人。",
        "modern_note": "**反证条目**：财星并非越多越好。日主衰弱而财星过旺，传统反而认为『富屋贫人』。这直接反驳『财星多 = 股价上涨』的简单映射。",
        "score": 9.5275,
        "authority_weight": 1.4,
        "stance": "counter",
        "source": "公版古籍《滴天髓》（公版通行本（清代刊本系统））",
        "edition": "公版通行本（清代刊本系统）",
        "provenance": "明清以来广泛流传的命理经典，原文属公有领域。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "日主",
          "财星"
        ]
      },
      {
        "entry_id": "YHZP-0002",
        "book": "渊海子平",
        "chapter": "论财",
        "school": "子平",
        "topic": [
          "财星",
          "反证",
          "身弱"
        ],
        "original_text": "财多身弱，反为不美。",
        "modern_note": "**反证条目**：财多而身弱，传统视为不美。再次说明单一『财星数量』指标的方向并不确定。",
        "score": 8.5671,
        "authority_weight": 1.3,
        "stance": "counter",
        "source": "公版古籍《渊海子平》（公版通行本）",
        "edition": "公版通行本",
        "provenance": "子平术集成性典籍，十神、格局、神煞诸论多出于此系统。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "财星",
          "数量"
        ]
      },
      {
        "entry_id": "MLYY-0002",
        "book": "命理约言",
        "chapter": "论格局",
        "school": "子平",
        "topic": [
          "格局",
          "反证"
        ],
        "original_text": "格局之名，古人所立，不必拘泥。",
        "modern_note": "**反证条目**：对格局名称本身持保留态度，提示格局分类的边界具有主观性。本系统据此对格局因子 B_NATAL_009 保持中性与较低置信度。",
        "score": 7.6342,
        "authority_weight": 1.3,
        "stance": "counter",
        "source": "公版古籍《命理约言》（公版通行本）",
        "edition": "公版通行本",
        "provenance": "清代命理著作，主张去神煞、专论五行生克。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "格局"
        ]
      },
      {
        "entry_id": "ZPZQ-0005",
        "book": "子平真诠",
        "chapter": "论财",
        "school": "子平",
        "topic": [
          "财星",
          "反证"
        ],
        "original_text": "财格之贵，在于身强而任财。",
        "modern_note": "**反证条目**：财格的成立前提是『身强能任财』。若身弱，财反而成为负担。这是本系统 B_NATAL_016（身财对比）的经典依据。",
        "score": 7.5998,
        "authority_weight": 1.5,
        "stance": "counter",
        "source": "公版古籍《子平真诠》（公版通行本）",
        "edition": "公版通行本",
        "provenance": "清代论格局最精之作，专主月令取用。",
        "license_status": "public_domain",
        "matched_query_terms": []
      },
      {
        "entry_id": "SFTK-0002",
        "book": "神峰通考",
        "chapter": "论财",
        "school": "子平",
        "topic": [
          "财星",
          "反证",
          "身弱"
        ],
        "original_text": "财多身弱，富屋贫人，虽有多财，反不能享。",
        "modern_note": "**反证条目**：与滴天髓同调，强调身弱不胜财。三条独立古籍都指向同一结论，因此『财星数量多 = 利好』在传统命理内部也并非共识。",
        "score": 7.5433,
        "authority_weight": 1.2,
        "stance": "counter",
        "source": "公版古籍《神峰通考》（公版通行本）",
        "edition": "公版通行本",
        "provenance": "明代命理著作，以『病药说』著名。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "财星",
          "数量"
        ]
      }
    ],
    "neutral_evidence": [
      {
        "entry_id": "ZPZQ-0002",
        "book": "子平真诠",
        "chapter": "论用神成败救应",
        "school": "子平",
        "topic": [
          "格局",
          "成败"
        ],
        "original_text": "格局有成败，成败有救应。",
        "modern_note": "格局有成有败，需要救应。说明单一格局标签不足以决定吉凶，本系统因此输出 confidence 与候选列表。",
        "score": 8.6974,
        "authority_weight": 1.5,
        "stance": "neutral",
        "source": "公版古籍《子平真诠》（公版通行本）",
        "edition": "公版通行本",
        "provenance": "清代论格局最精之作，专主月令取用。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "格局"
        ]
      },
      {
        "entry_id": "SMTY-0005",
        "book": "三命通会",
        "chapter": "论贵贱",
        "school": "子平",
        "topic": [
          "格局"
        ],
        "original_text": "格局既成，贵贱可辨。",
        "modern_note": "传统以格局论贵贱。本项目把格局编码为分类特征 B_NATAL_009，不做方向映射。",
        "score": 7.6088,
        "authority_weight": 1.3,
        "stance": "neutral",
        "source": "公版古籍《三命通会》（公版通行本（四库全书系统））",
        "edition": "公版通行本（四库全书系统）",
        "provenance": "明代命理集大成之作，体系完备。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "格局"
        ]
      },
      {
        "entry_id": "SMTY-0001",
        "book": "三命通会",
        "chapter": "论十干",
        "school": "子平",
        "topic": [
          "十神",
          "财星"
        ],
        "original_text": "夫财者，为我所克之物也。",
        "modern_note": "十神中『财』的定义就是日主所克之五行，是一套符号关系，与现实的金钱财富不是同一概念。这是本项目反复强调语境的直接依据。",
        "score": 6.6158,
        "authority_weight": 1.3,
        "stance": "neutral",
        "source": "公版古籍《三命通会》（公版通行本（四库全书系统））",
        "edition": "公版通行本（四库全书系统）",
        "provenance": "明代命理集大成之作，体系完备。",
        "license_status": "public_domain",
        "matched_query_terms": [
          "日主"
        ]
      },
      {
        "entry_id": "DTS-0003",
        "book": "滴天髓",
        "chapter": "人道",
        "school": "子平",
        "topic": [
          "中和",
          "用神"
        ],
        "original_text": "人道有损益，裁制品汇，人道得之，不可过也。",
        "modern_note": "强调『损有余、补不足』的中和思想，是扶抑取用神的理论基础。",
        "score": 4.2,
        "authority_weight": 1.4,
        "stance": "neutral",
        "source": "公版古籍《滴天髓》（公版通行本（清代刊本系统））",
        "edition": "公版通行本（清代刊本系统）",
        "provenance": "明清以来广泛流传的命理经典，原文属公有领域。",
        "license_status": "public_domain",
        "matched_query_terms": []
      }
    ],
    "total_candidates": 22,
    "retrieval_method": "bm25 + topic_match + authority_weight + domain_filter",
    "knowledge_version": "kb-1.1.0",
    "note": "本系统同时检索支持与相反观点，以避免『先有结论后找古籍』。古籍条文只说明传统术数的说法，不构成对股票收益的任何判断。"
  },
  "disclaimer": "古籍条文只说明传统术数的说法，不构成对股票收益的任何判断。条目文字由项目组从公版古籍录入，未逐字对照权威刊本校勘，正式引用前必须完成校勘。"
};
/* 月度 / 周度窗口样本：**直接由真实后端算出**并冻结成 JSON。
   为什么不再手写：手写版本用的是"分数"单位（mean=73.6），而真实后端
   `WeekWindow.mean` 是 `combined_direction`（-1/0/1）的均值，量纲完全不同 ——
   演示模式与真实模式给出两种数字，读者无法分辨哪个是真的。
   现在两份 fixture 与 `/timeline/{months,weeks}` 的响应逐字段同构。 */
export const timelineMonthsFixture = rawTimelineMonths12 as unknown as ApiTimelineMonths;
export const timelineWeeksFixture = rawTimelineWeeks12 as unknown as ApiTimelineWeeks;

/** 因子字典演示样本。
 *
 * 来自 scripts/capture_ui_fixtures.py 对**真实因子注册表**的整表冻结：
 * factor_id / definition / computation / requires / rule_version 与真实模式逐条一致。
 * 早期版本这里是手写的 4 个因子（表里并不存在），会在演示模式展示一个
 * 系统里没有的字典 —— 已废弃。
 */
export const factorsDictionaryFixture: { total: number; total_all: number; by_category: Record<string, number>; items: Record<string, unknown>[]; disclaimer: string; rule_version: string } = {
  "total": 114,
  "total_all": 114,
  "by_category": {
    "natal": 51,
    "year": 16,
    "month": 22,
    "day": 13,
    "cross": 12
  },
  "items": [
    {
      "factor_id": "B_NATAL_001",
      "name": "日主强弱",
      "engine": "bazi",
      "category": "natal",
      "definition": "日主在月令与全局中的旺衰等级。传统命理认为身强身弱决定取用方向，但股票不存在『命主』，此处仅作为原局结构特征。",
      "computation": "support/(support+drain) 比值映射：>=0.62 身强 / >=0.55 偏强 / >0.45 中和 / >0.38 偏弱 / 其余身弱",
      "raw_unit": "strength_level",
      "normalized_hint": "身强→+1，偏强→+0.5，中和→0，偏弱→-0.5，身弱→-1",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "day_master_analysis.strength_level"
      ],
      "tags": [
        "旺衰"
      ]
    },
    {
      "factor_id": "B_NATAL_002",
      "name": "财星数量",
      "engine": "bazi",
      "category": "natal",
      "definition": "四柱天干地支十神中『正财 + 偏财』的出现次数（含藏干）。传统命理视财星为财源象征；本项目仅视其为可检验的结构变量。",
      "computation": "count(ten_god ∈ {正财, 偏财})，统计 3 个天干 + 4 支全部藏干",
      "raw_unit": "count",
      "normalized_hint": "min(count/4, 1) 线性映射到 [0,1]",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "ten_god_counts"
      ],
      "tags": [
        "财星"
      ]
    },
    {
      "factor_id": "B_NATAL_003",
      "name": "财星透干",
      "engine": "bazi",
      "category": "natal",
      "definition": "财星是否透出天干（年/月/时干）。传统认为透干者显，不透者藏。",
      "computation": "any(stem_ten_god ∈ {正财,偏财} for year/month/hour)",
      "raw_unit": "bool",
      "normalized_hint": "True→+1，False→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "visible_ten_gods"
      ],
      "tags": [
        "财星",
        "透干"
      ]
    },
    {
      "factor_id": "B_NATAL_004",
      "name": "财星得令",
      "engine": "bazi",
      "category": "natal",
      "definition": "月令地支是否为财星（月支藏干含财星，或月支五行即日主所克者）。",
      "computation": "月支五行 == 日主所克五行",
      "raw_unit": "bool",
      "normalized_hint": "True→+1，False→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "month_pillar"
      ],
      "tags": [
        "财星",
        "月令"
      ]
    },
    {
      "factor_id": "B_NATAL_005",
      "name": "食伤结构",
      "engine": "bazi",
      "category": "natal",
      "definition": "食神 + 伤官的出现次数。传统认为食伤为『生财之源』。",
      "computation": "count(ten_god ∈ {食神, 伤官})",
      "raw_unit": "count",
      "normalized_hint": "min(count/4, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "ten_god_counts"
      ],
      "tags": [
        "食伤"
      ]
    },
    {
      "factor_id": "B_NATAL_006",
      "name": "官杀结构",
      "engine": "bazi",
      "category": "natal",
      "definition": "正官 + 七杀的出现次数。传统认为官杀主约束、规制。",
      "computation": "count(ten_god ∈ {正官, 七杀})",
      "raw_unit": "count",
      "normalized_hint": "min(count/4, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "ten_god_counts"
      ],
      "tags": [
        "官杀"
      ]
    },
    {
      "factor_id": "B_NATAL_007",
      "name": "印星结构",
      "engine": "bazi",
      "category": "natal",
      "definition": "正印 + 偏印的出现次数。传统认为印星主资源、庇护。",
      "computation": "count(ten_god ∈ {正印, 偏印})",
      "raw_unit": "count",
      "normalized_hint": "min(count/4, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "ten_god_counts"
      ],
      "tags": [
        "印星"
      ]
    },
    {
      "factor_id": "B_NATAL_008",
      "name": "比劫结构",
      "engine": "bazi",
      "category": "natal",
      "definition": "比肩 + 劫财的出现次数（不含日主本身）。传统认为比劫主竞争、分夺。",
      "computation": "count(ten_god ∈ {比肩, 劫财})",
      "raw_unit": "count",
      "normalized_hint": "min(count/4, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "ten_god_counts"
      ],
      "tags": [
        "比劫"
      ]
    },
    {
      "factor_id": "B_NATAL_009",
      "name": "格局类型",
      "engine": "bazi",
      "category": "natal",
      "definition": "月令取格所得的格局大类。仅作为分类特征，不对应收益方向。",
      "computation": "月令本气/透干取格（子平通行法）",
      "raw_unit": "pattern_category",
      "normalized_hint": "分类变量编码为整数（财格=1/官格=2/印格=3/食伤格=4/比劫格=5/其他=0）",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "pattern.category"
      ],
      "tags": [
        "格局"
      ]
    },
    {
      "factor_id": "B_NATAL_010",
      "name": "用神五行",
      "engine": "bazi",
      "category": "natal",
      "definition": "扶抑法所取用神五行。作为分类特征，不映射为收益方向。",
      "computation": "扶抑法（主）+ 调候法（辅）",
      "raw_unit": "wuxing",
      "normalized_hint": "五行编码 木=1/火=2/土=3/金=4/水=5",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "yong_shen.yong_shen"
      ],
      "tags": [
        "用神"
      ]
    },
    {
      "factor_id": "B_NATAL_011",
      "name": "五行缺失数",
      "engine": "bazi",
      "category": "natal",
      "definition": "四柱天干地支中完全未出现的五行个数。传统认为五行偏枯需补。",
      "computation": "count(wuxing not in stems+branches)",
      "raw_unit": "count",
      "normalized_hint": "min(count/3, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "wuxing.missing"
      ],
      "tags": [
        "五行"
      ]
    },
    {
      "factor_id": "B_NATAL_012",
      "name": "五行偏枯度",
      "engine": "bazi",
      "category": "natal",
      "definition": "五行百分比最大值与最小值之差，衡量原局五行分布的不均衡程度。",
      "computation": "max(percentages) - min(percentages)",
      "raw_unit": "percentage_point",
      "normalized_hint": "min(diff/60, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "wuxing.percentages"
      ],
      "tags": [
        "五行"
      ]
    },
    {
      "factor_id": "B_NATAL_013",
      "name": "原局合冲强度",
      "engine": "bazi",
      "category": "natal",
      "definition": "原局内部六合/三合/三会（合类）与六冲/相刑/相害（冲类）的数量差。传统认为合主稳定、冲主变动；本项目仅作为结构变量。",
      "computation": "count(合类) - count(冲类)",
      "raw_unit": "count",
      "normalized_hint": "tanh(diff/3)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "relations"
      ],
      "tags": [
        "刑冲合害"
      ]
    },
    {
      "factor_id": "B_NATAL_014",
      "name": "财星力量占比",
      "engine": "bazi",
      "category": "natal",
      "definition": "财星五行在五行力量估算中的百分比。",
      "computation": "wuxing.percentages[日主所克五行]",
      "raw_unit": "percent",
      "normalized_hint": "percentage/100",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "wuxing.percentages"
      ],
      "tags": [
        "财星"
      ]
    },
    {
      "factor_id": "B_NATAL_015",
      "name": "食伤力量占比",
      "engine": "bazi",
      "category": "natal",
      "definition": "食伤五行（日主所生）在五行力量估算中的百分比。",
      "computation": "wuxing.percentages[日主所生五行]",
      "raw_unit": "percent",
      "normalized_hint": "percentage/100",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "wuxing.percentages"
      ],
      "tags": [
        "食伤"
      ]
    },
    {
      "factor_id": "B_NATAL_016",
      "name": "身财对比",
      "engine": "bazi",
      "category": "natal",
      "definition": "帮扶力量与财星力量的比值关系，传统『身财两停』概念的量化近似。",
      "computation": "(比劫+印) / 财星力量",
      "raw_unit": "ratio",
      "normalized_hint": "tanh(log(ratio))，>0 表示身强于财",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "wuxing.scores"
      ],
      "tags": [
        "财星",
        "旺衰"
      ]
    },
    {
      "factor_id": "B_NATAL_017",
      "name": "调候适宜度",
      "engine": "bazi",
      "category": "natal",
      "definition": "按调候法判断原局寒暖燥湿是否需要调候，以及用神是否已含调候五行。",
      "computation": "月支季节 + 用神/喜神是否覆盖调候五行",
      "raw_unit": "0-3",
      "normalized_hint": "score/3",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "yong_shen.tiaohou_note"
      ],
      "tags": [
        "调候"
      ]
    },
    {
      "factor_id": "B_NATAL_018",
      "name": "日主阴阳",
      "engine": "bazi",
      "category": "natal",
      "definition": "日主天干阴阳属性（阳干/阴干）。仅作为分类特征。",
      "computation": "STEM_YANG[day_master]",
      "raw_unit": "bool",
      "normalized_hint": "阳→+1，阴→-1",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "day_master"
      ],
      "tags": [
        "日主"
      ]
    },
    {
      "factor_id": "B_YEAR_001",
      "name": "流年天干喜忌",
      "engine": "bazi",
      "category": "year",
      "definition": "流年天干五行相对日主喜用忌神的位置。",
      "computation": "classify(流年天干五行 ∈ {用神,喜神,忌神,仇神,闲神})",
      "raw_unit": "category",
      "normalized_hint": "用神→+1，喜神→+0.6，闲神→0，忌神/仇神→-1",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_year_pillar.stem_is"
      ],
      "tags": [
        "流年"
      ]
    },
    {
      "factor_id": "B_YEAR_002",
      "name": "流年地支喜忌",
      "engine": "bazi",
      "category": "year",
      "definition": "流年地支五行相对日主喜用忌神的位置。",
      "computation": "classify(流年地支五行)",
      "raw_unit": "category",
      "normalized_hint": "同 B_YEAR_001",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_year_pillar.branch_is"
      ],
      "tags": [
        "流年"
      ]
    },
    {
      "factor_id": "B_YEAR_003",
      "name": "流年财星",
      "engine": "bazi",
      "category": "year",
      "definition": "流年干支所引动的十神是否属财星。",
      "computation": "十神(流年天干/支藏干) ∈ {正财,偏财}",
      "raw_unit": "bool/count",
      "normalized_hint": "命中→+1，未命中→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_year_pillar.stem_ten_god"
      ],
      "tags": [
        "流年",
        "财星"
      ]
    },
    {
      "factor_id": "B_YEAR_004",
      "name": "流年食伤",
      "engine": "bazi",
      "category": "year",
      "definition": "流年是否引动食伤。",
      "computation": "十神(流年天干/支藏干) ∈ {食神,伤官}",
      "raw_unit": "bool/count",
      "normalized_hint": "命中→+1，未命中→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_year_pillar.branch_ten_gods"
      ],
      "tags": [
        "流年",
        "食伤"
      ]
    },
    {
      "factor_id": "B_YEAR_005",
      "name": "流年冲原局",
      "engine": "bazi",
      "category": "year",
      "definition": "流年地支是否冲原局四支。传统认为冲主变动。",
      "computation": "六冲关系匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_year_pillar.clashes_with_natal"
      ],
      "tags": [
        "流年",
        "冲"
      ]
    },
    {
      "factor_id": "B_YEAR_006",
      "name": "流年合原局",
      "engine": "bazi",
      "category": "year",
      "definition": "流年地支是否与原局四支六合。",
      "computation": "六合关系匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_year_pillar.harmonies_with_natal"
      ],
      "tags": [
        "流年",
        "合"
      ]
    },
    {
      "factor_id": "B_YEAR_007",
      "name": "流年刑原局",
      "engine": "bazi",
      "category": "year",
      "definition": "流年地支是否与原局相刑。",
      "computation": "相刑关系匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_year_pillar.punishments_with_natal"
      ],
      "tags": [
        "流年",
        "刑"
      ]
    },
    {
      "factor_id": "B_YEAR_008",
      "name": "流年害原局",
      "engine": "bazi",
      "category": "year",
      "definition": "流年地支是否与原局相害。",
      "computation": "相害关系匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_year_pillar.harms_with_natal"
      ],
      "tags": [
        "流年",
        "害"
      ]
    },
    {
      "factor_id": "B_YEAR_009",
      "name": "流年十二长生",
      "engine": "bazi",
      "category": "year",
      "definition": "日主在流年地支的十二长生阶段。",
      "computation": "twelve_stage(day_master, 流年支)",
      "raw_unit": "stage",
      "normalized_hint": "按长生序映射：长生/临官/帝旺→+1，衰病死墓绝→-1",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_year_pillar.di_shi"
      ],
      "tags": [
        "流年",
        "旺衰"
      ]
    },
    {
      "factor_id": "B_YEAR_010",
      "name": "流年三合",
      "engine": "bazi",
      "category": "year",
      "definition": "流年支与原局构成三合局。",
      "computation": "三合局匹配",
      "raw_unit": "bool",
      "normalized_hint": "命中→+1，未命中→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_year_pillar.triple_harmonies"
      ],
      "tags": [
        "流年",
        "三合"
      ]
    },
    {
      "factor_id": "B_MONTH_001",
      "name": "流月天干喜忌",
      "engine": "bazi",
      "category": "month",
      "definition": "流月天干五行相对日主喜用忌神的位置。",
      "computation": "classify(流月天干五行)",
      "raw_unit": "category",
      "normalized_hint": "用神→+1，喜神→+0.6，闲神→0，忌/仇→-1",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar.stem_is"
      ],
      "tags": [
        "流月"
      ]
    },
    {
      "factor_id": "B_MONTH_002",
      "name": "流月地支喜忌",
      "engine": "bazi",
      "category": "month",
      "definition": "流月地支五行相对日主喜用忌神的位置。",
      "computation": "classify(流月地支五行)",
      "raw_unit": "category",
      "normalized_hint": "同 B_MONTH_001",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar.branch_is"
      ],
      "tags": [
        "流月"
      ]
    },
    {
      "factor_id": "B_MONTH_003",
      "name": "流月财星引动",
      "engine": "bazi",
      "category": "month",
      "definition": "流月干支是否引动财星（十神属财或财星为喜用）。",
      "computation": "十神(流月) ∈ {正财,偏财} 或 流月五行 ∈ 喜用",
      "raw_unit": "bool",
      "normalized_hint": "命中→+1，未命中→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar"
      ],
      "tags": [
        "流月",
        "财星"
      ]
    },
    {
      "factor_id": "B_MONTH_004",
      "name": "流月食伤生财",
      "engine": "bazi",
      "category": "month",
      "definition": "流月引动食伤，且原局有财星。传统『食伤生财』结构的时点近似。注意：该结构**不代表**股价上涨。",
      "computation": "流月十神 ∈ {食神,伤官} 且 ten_god_counts 含财星",
      "raw_unit": "bool",
      "normalized_hint": "命中→+1，未命中→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar",
        "ten_god_counts"
      ],
      "tags": [
        "流月",
        "食伤",
        "财星"
      ]
    },
    {
      "factor_id": "B_MONTH_005",
      "name": "流月官杀变化",
      "engine": "bazi",
      "category": "month",
      "definition": "流月是否引动官杀。",
      "computation": "十神(流月) ∈ {正官,七杀}",
      "raw_unit": "bool",
      "normalized_hint": "命中→+1，未命中→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar"
      ],
      "tags": [
        "流月",
        "官杀"
      ]
    },
    {
      "factor_id": "B_MONTH_006",
      "name": "流月三合",
      "engine": "bazi",
      "category": "month",
      "definition": "流月支与原局构成三合局。",
      "computation": "三合局匹配",
      "raw_unit": "list",
      "normalized_hint": "命中→+1，未命中→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar.triple_harmonies"
      ],
      "tags": [
        "流月",
        "三合"
      ]
    },
    {
      "factor_id": "B_MONTH_007",
      "name": "流月六合",
      "engine": "bazi",
      "category": "month",
      "definition": "流月支与原局支六合的数量。",
      "computation": "六合匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar.harmonies_with_natal"
      ],
      "tags": [
        "流月",
        "合"
      ]
    },
    {
      "factor_id": "B_MONTH_008",
      "name": "流月冲原局",
      "engine": "bazi",
      "category": "month",
      "definition": "流月支冲原局支的数量。",
      "computation": "六冲匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar.clashes_with_natal"
      ],
      "tags": [
        "流月",
        "冲"
      ]
    },
    {
      "factor_id": "B_MONTH_009",
      "name": "流月刑原局",
      "engine": "bazi",
      "category": "month",
      "definition": "流月支与原局相刑的数量。",
      "computation": "相刑匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar.punishments_with_natal"
      ],
      "tags": [
        "流月",
        "刑"
      ]
    },
    {
      "factor_id": "B_MONTH_010",
      "name": "流月害原局",
      "engine": "bazi",
      "category": "month",
      "definition": "流月支与原局相害的数量。",
      "computation": "相害匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar.harms_with_natal"
      ],
      "tags": [
        "流月",
        "害"
      ]
    },
    {
      "factor_id": "B_MONTH_011",
      "name": "流月十神",
      "engine": "bazi",
      "category": "month",
      "definition": "流月天干相对日主的十神，作为分类特征。",
      "computation": "ten_god(day_master, 流月干)",
      "raw_unit": "category",
      "normalized_hint": "编码为 0-9 的类别整数",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar.stem_ten_god"
      ],
      "tags": [
        "流月",
        "十神"
      ]
    },
    {
      "factor_id": "B_MONTH_012",
      "name": "流月十二长生",
      "engine": "bazi",
      "category": "month",
      "definition": "日主在流月地支的十二长生阶段。",
      "computation": "twelve_stage(day_master, 流月支)",
      "raw_unit": "stage",
      "normalized_hint": "长生/临官/帝旺→+1，衰病死墓绝→-1",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_month_pillar.di_shi"
      ],
      "tags": [
        "流月",
        "旺衰"
      ]
    },
    {
      "factor_id": "B_DAY_001",
      "name": "流日天干喜忌",
      "engine": "bazi",
      "category": "day",
      "definition": "流日天干五行相对日主喜用忌神的位置。",
      "computation": "classify(流日天干五行)",
      "raw_unit": "category",
      "normalized_hint": "用神→+1，喜神→+0.6，闲神→0，忌/仇→-1",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_day_pillar.stem_is"
      ],
      "tags": [
        "流日"
      ]
    },
    {
      "factor_id": "B_DAY_002",
      "name": "流日冲原局",
      "engine": "bazi",
      "category": "day",
      "definition": "流日支冲原局支的数量。",
      "computation": "六冲匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_day_pillar.clashes_with_natal"
      ],
      "tags": [
        "流日",
        "冲"
      ]
    },
    {
      "factor_id": "B_DAY_003",
      "name": "流日合原局",
      "engine": "bazi",
      "category": "day",
      "definition": "流日支与原局六合的数量。",
      "computation": "六合匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_day_pillar.harmonies_with_natal"
      ],
      "tags": [
        "流日",
        "合"
      ]
    },
    {
      "factor_id": "B_DAY_004",
      "name": "流日地支喜忌",
      "engine": "bazi",
      "category": "day",
      "definition": "流日地支五行相对日主喜用忌神的位置。",
      "computation": "classify(流日地支五行)",
      "raw_unit": "category",
      "normalized_hint": "同 B_DAY_001",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_day_pillar.branch_is"
      ],
      "tags": [
        "流日"
      ]
    },
    {
      "factor_id": "B_DAY_005",
      "name": "流日十神",
      "engine": "bazi",
      "category": "day",
      "definition": "流日天干相对日主的十神，作为分类特征。",
      "computation": "ten_god(day_master, 流日干)",
      "raw_unit": "category",
      "normalized_hint": "编码 0-9",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_day_pillar.stem_ten_god"
      ],
      "tags": [
        "流日",
        "十神"
      ]
    },
    {
      "factor_id": "B_DAY_006",
      "name": "流日十二长生",
      "engine": "bazi",
      "category": "day",
      "definition": "日主在流日地支的十二长生阶段。",
      "computation": "twelve_stage(day_master, 流日支)",
      "raw_unit": "stage",
      "normalized_hint": "长生/临官/帝旺→+1，衰病死墓绝→-1",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_day_pillar.di_shi"
      ],
      "tags": [
        "流日",
        "旺衰"
      ]
    },
    {
      "factor_id": "B_DAY_007",
      "name": "流日刑原局",
      "engine": "bazi",
      "category": "day",
      "definition": "流日支与原局相刑的数量。",
      "computation": "相刑匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_day_pillar.punishments_with_natal"
      ],
      "tags": [
        "流日",
        "刑"
      ]
    },
    {
      "factor_id": "B_DAY_008",
      "name": "流日害原局",
      "engine": "bazi",
      "category": "day",
      "definition": "流日支与原局相害的数量。",
      "computation": "相害匹配数",
      "raw_unit": "count",
      "normalized_hint": "min(count/2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "current_day_pillar.harms_with_natal"
      ],
      "tags": [
        "流日",
        "害"
      ]
    },
    {
      "factor_id": "H_DAY_001",
      "name": "当日天干喜忌",
      "engine": "huangli",
      "category": "cross",
      "definition": "黄历当日天干五行相对股票日主喜用忌神的位置。",
      "computation": "classify(当日日干五行 vs 原局喜用忌)",
      "raw_unit": "category",
      "normalized_hint": "用神→+1，喜神→+0.6，闲神→0，忌/仇→-1",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.day_ganzhi",
        "chart.yong_shen"
      ],
      "tags": [
        "黄历",
        "交叉"
      ]
    },
    {
      "factor_id": "H_DAY_002",
      "name": "当日地支喜忌",
      "engine": "huangli",
      "category": "cross",
      "definition": "黄历当日地支五行相对股票日主喜用忌神的位置。",
      "computation": "classify(当日日支五行)",
      "raw_unit": "category",
      "normalized_hint": "同 H_DAY_001",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.day_ganzhi"
      ],
      "tags": [
        "黄历",
        "交叉"
      ]
    },
    {
      "factor_id": "H_DAY_003",
      "name": "当日冲股票日支",
      "engine": "huangli",
      "category": "cross",
      "definition": "当日地支是否冲股票八字的日支（坐下）。传统认为日支为『身位』。",
      "computation": "六冲(当日支, 原局日支)",
      "raw_unit": "bool",
      "normalized_hint": "命中→-1，未命中→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.day_ganzhi",
        "chart.day_pillar"
      ],
      "tags": [
        "黄历",
        "冲"
      ]
    },
    {
      "factor_id": "H_DAY_004",
      "name": "当日合股票日支",
      "engine": "huangli",
      "category": "cross",
      "definition": "当日地支是否与原局日支六合。",
      "computation": "六合(当日支, 原局日支)",
      "raw_unit": "bool",
      "normalized_hint": "命中→+1，未命中→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.day_ganzhi",
        "chart.day_pillar"
      ],
      "tags": [
        "黄历",
        "合"
      ]
    },
    {
      "factor_id": "H_DAY_005",
      "name": "当日与原局合冲净值",
      "engine": "huangli",
      "category": "cross",
      "definition": "当日地支与原局四支的互动净值：合类命中数 − 冲类命中数。",
      "computation": "count(合/六合/三合) − count(冲/刑/害)",
      "raw_unit": "count",
      "normalized_hint": "tanh(net/3)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.day_ganzhi",
        "chart"
      ],
      "tags": [
        "黄历",
        "交叉"
      ]
    },
    {
      "factor_id": "H_DAY_006",
      "name": "建除十二值",
      "engine": "huangli",
      "category": "cross",
      "definition": "当日建除十二值（建/除/满/平/定/执/破/危/成/收/开/闭）。传统通书对十二值有吉凶分类，本项目仅作分类特征。",
      "computation": "lunar-python getZhiXing()",
      "raw_unit": "category",
      "normalized_hint": "按传统吉凶分类：开/成/定/危/除→偏正，破/闭/平→偏负，其余 0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.duty_officer"
      ],
      "tags": [
        "黄历",
        "建除"
      ]
    },
    {
      "factor_id": "H_DAY_007",
      "name": "黄黑道",
      "engine": "huangli",
      "category": "cross",
      "definition": "当日为黄道日或黑道日（十二神所属）。",
      "computation": "lunar-python getDayTianShenType()",
      "raw_unit": "category",
      "normalized_hint": "黄道→+1，黑道→-1",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.day_tian_shen_type"
      ],
      "tags": [
        "黄历",
        "黄黑道"
      ]
    },
    {
      "factor_id": "H_DAY_008",
      "name": "十二神",
      "engine": "huangli",
      "category": "cross",
      "definition": "当日十二神（青龙/明堂/天刑/朱雀/…）。",
      "computation": "lunar-python getDayTianShen()",
      "raw_unit": "category",
      "normalized_hint": "走 H_DAY_007 的统一映射，本因子保留原始类别",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.day_tian_shen"
      ],
      "tags": [
        "黄历",
        "十二神"
      ]
    },
    {
      "factor_id": "H_DAY_009",
      "name": "当日与原局关系数",
      "engine": "huangli",
      "category": "cross",
      "definition": "当日地支与原局四支发生刑冲合害的总次数，衡量当日与原局的『互动强度』。",
      "computation": "count(全部关系命中)",
      "raw_unit": "count",
      "normalized_hint": "min(count/4, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.day_ganzhi",
        "chart"
      ],
      "tags": [
        "黄历",
        "交叉"
      ]
    },
    {
      "factor_id": "H_DAY_010",
      "name": "当日纳音五行",
      "engine": "huangli",
      "category": "cross",
      "definition": "当日日柱纳音所属五行相对日主喜用的位置。",
      "computation": "纳音五行 classify",
      "raw_unit": "wuxing",
      "normalized_hint": "喜用→+1，忌→-1，其他 0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.day_nayin"
      ],
      "tags": [
        "黄历",
        "纳音"
      ]
    },
    {
      "factor_id": "H_DAY_011",
      "name": "星宿吉凶",
      "engine": "huangli",
      "category": "cross",
      "definition": "当日二十八宿的吉凶属性。",
      "computation": "lunar-python getXiuLuck()",
      "raw_unit": "category",
      "normalized_hint": "吉→+1，凶→-1，其余 0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.xiu_luck"
      ],
      "tags": [
        "黄历",
        "星宿"
      ]
    },
    {
      "factor_id": "H_DAY_012",
      "name": "当日刑股票日支",
      "engine": "huangli",
      "category": "cross",
      "definition": "当日地支是否与原局日支相刑。",
      "computation": "相刑(当日支, 原局日支)",
      "raw_unit": "bool",
      "normalized_hint": "命中→-1，未命中→0",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.day_ganzhi",
        "chart.day_pillar"
      ],
      "tags": [
        "黄历",
        "刑"
      ]
    },
    {
      "factor_id": "H_MONTH_001",
      "name": "本月黄道日占比",
      "engine": "huangli",
      "category": "month",
      "definition": "未来一个自然月内黄道日占全部自然日的比例。",
      "computation": "count(day_tian_shen_type == 黄道) / days_in_month",
      "raw_unit": "ratio",
      "normalized_hint": "(ratio - 0.5) * 2",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.month_scan"
      ],
      "tags": [
        "黄历",
        "月度"
      ]
    },
    {
      "factor_id": "H_MONTH_002",
      "name": "本月吉神日占比",
      "engine": "huangli",
      "category": "month",
      "definition": "本月 day_tian_shen_luck == 吉 的自然日占比。",
      "computation": "count(luck == 吉) / days_in_month",
      "raw_unit": "ratio",
      "normalized_hint": "(ratio - 0.5) * 2",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.month_scan"
      ],
      "tags": [
        "黄历",
        "月度"
      ]
    },
    {
      "factor_id": "H_MONTH_003",
      "name": "本月合股票日支天数",
      "engine": "huangli",
      "category": "month",
      "definition": "本月内当日地支与原局日支六合的自然日数量。",
      "computation": "count(六合)",
      "raw_unit": "days",
      "normalized_hint": "min(days/4, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.month_scan",
        "chart.day_pillar"
      ],
      "tags": [
        "黄历",
        "月度",
        "合"
      ]
    },
    {
      "factor_id": "H_MONTH_004",
      "name": "本月冲股票日支天数",
      "engine": "huangli",
      "category": "month",
      "definition": "本月内当日地支与原局日支六冲的自然日数量。",
      "computation": "count(六冲)",
      "raw_unit": "days",
      "normalized_hint": "min(days/4, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.month_scan",
        "chart.day_pillar"
      ],
      "tags": [
        "黄历",
        "月度",
        "冲"
      ]
    },
    {
      "factor_id": "H_MONTH_005",
      "name": "本月喜神日占比",
      "engine": "huangli",
      "category": "month",
      "definition": "本月内当日日干或日支五行属于原局喜用神的自然日占比。",
      "computation": "count(day ganzhi wuxing ∈ 喜用) / days_in_month",
      "raw_unit": "ratio",
      "normalized_hint": "(ratio - 0.5) * 2",
      "default_direction": 0,
      "rule_score_meaning": "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "v1.1",
      "enabled": true,
      "requires": [
        "huangli.month_scan"
      ],
      "tags": [
        "黄历",
        "月度"
      ]
    },
    {
      "factor_id": "Z_LIFE_001",
      "name": "命宫主星庙旺和",
      "engine": "ziwei",
      "category": "natal",
      "definition": "命宫主星的庙旺等级之和。传统紫微以主星庙旺程度衡量该宫的力量强弱。股票研究中作为『主体结构强度』的代理变量（研究假设，非定论）。",
      "computation": "sum(BRIGHTNESS_SCORE[主星.brightness] for 主星 in 命宫)",
      "raw_unit": "score_sum",
      "normalized_hint": "tanh(sum / 1.5)，落在 [-1, 1]",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.命宫.major_stars"
      ],
      "tags": [
        "紫微",
        "命宫",
        "庙旺"
      ]
    },
    {
      "factor_id": "Z_LIFE_002",
      "name": "命宫主星数量",
      "engine": "ziwei",
      "category": "natal",
      "definition": "命宫主星个数。0 表示空宫（传统认为需借对宫安星），属于结构性变量，数量本身不对应收益方向。",
      "computation": "len(命宫.major_stars)",
      "raw_unit": "count",
      "normalized_hint": "min(count / 2, 1)（仅作强度，方向中性）",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.命宫.major_stars"
      ],
      "tags": [
        "紫微",
        "命宫"
      ]
    },
    {
      "factor_id": "Z_LIFE_003",
      "name": "命宫吉曜数量",
      "engine": "ziwei",
      "category": "natal",
      "definition": "命宫中六吉星（左辅/右弼/文昌/文曲/天魁/天钺）与禄马（禄存/天马）的数量。传统视为助力，本项目仅作为可检验的结构变量。",
      "computation": "count(star_category ∈ {lucky, wealth_move} in 命宫)",
      "raw_unit": "count",
      "normalized_hint": "min(count / 3, 1)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.命宫"
      ],
      "tags": [
        "紫微",
        "命宫",
        "吉曜"
      ]
    },
    {
      "factor_id": "Z_LIFE_004",
      "name": "命宫煞曜数量",
      "engine": "ziwei",
      "category": "natal",
      "definition": "命宫中六煞星（擎羊/陀罗/火星/铃星/地空/地劫）的数量。传统视为阻力。**这是传统规则的看法，不构成对股价的判断。**",
      "computation": "count(star_category == malefic in 命宫)",
      "raw_unit": "count",
      "normalized_hint": "-min(count / 2, 1)",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.命宫"
      ],
      "tags": [
        "紫微",
        "命宫",
        "煞曜"
      ]
    },
    {
      "factor_id": "Z_LIFE_005",
      "name": "命宫吉煞差",
      "engine": "ziwei",
      "category": "natal",
      "definition": "命宫吉曜数与煞曜数之差，传统『吉凶相抵』概念的量化近似。正值表示吉曜多于煞曜。这是传统规则的看法，不构成对股价的判断。",
      "computation": "(吉曜数 + 禄马数) - 煞曜数",
      "raw_unit": "count_diff",
      "normalized_hint": "tanh(diff / 2)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.命宫"
      ],
      "tags": [
        "紫微",
        "命宫"
      ]
    },
    {
      "factor_id": "Z_LIFE_006",
      "name": "身宫与命宫同宫",
      "engine": "ziwei",
      "category": "natal",
      "definition": "身宫是否与命宫落在同一宫位。传统认为命身同宫者结构集中、倾向性更强。作为结构性标记，方向中性。",
      "computation": "body_palace_index == soul_palace_index",
      "raw_unit": "bool",
      "normalized_hint": "True→+0.5、False→0（仅作结构标记）",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.body_palace_index"
      ],
      "tags": [
        "紫微",
        "命宫",
        "身宫"
      ]
    },
    {
      "factor_id": "Z_LIFE_007",
      "name": "五行局",
      "engine": "ziwei",
      "category": "natal",
      "definition": "命宫所属五行局（水二/木三/金四/土五/火六），决定起运岁数与紫微星安放起点。属于分类变量，不映射收益方向。",
      "computation": "iztro five_elements_class",
      "raw_unit": "class",
      "normalized_hint": "局数 2..6 线性映射到 [-1,1]；分类变量仅作结构编码",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.five_elements_class"
      ],
      "tags": [
        "紫微",
        "五行局"
      ]
    },
    {
      "factor_id": "Z_FIN_001",
      "name": "财帛宫主星庙旺和",
      "engine": "ziwei",
      "category": "natal",
      "definition": "财帛宫主星庙旺等级之和。**研究映射**：把财帛宫视为『资金/价格结构』的代理，该映射属本项目假设（ziwei_stock_mapping_v1），不是传统紫微对股票的规定。",
      "computation": "sum(BRIGHTNESS_SCORE[主星.brightness] for 主星 in 财帛宫)",
      "raw_unit": "score_sum",
      "normalized_hint": "tanh(sum / 1.5)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.财帛.major_stars"
      ],
      "tags": [
        "紫微",
        "财帛宫",
        "research_mapping"
      ]
    },
    {
      "factor_id": "Z_FIN_002",
      "name": "财帛宫主星数量",
      "engine": "ziwei",
      "category": "natal",
      "definition": "财帛宫主星个数（0 为空宫）。结构性变量，方向中性。",
      "computation": "len(财帛宫.major_stars)",
      "raw_unit": "count",
      "normalized_hint": "min(count / 2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.财帛"
      ],
      "tags": [
        "紫微",
        "财帛宫"
      ]
    },
    {
      "factor_id": "Z_FIN_003",
      "name": "财帛宫煞曜数量",
      "engine": "ziwei",
      "category": "natal",
      "definition": "财帛宫中六煞星（擎羊/陀罗/火星/铃星/地空/地劫）的数量。传统视为财位上的阻力；**这是传统规则的看法，不构成对股价的判断。**",
      "computation": "count(malefic in 财帛宫)",
      "raw_unit": "count",
      "normalized_hint": "-min(count / 2, 1)",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.财帛"
      ],
      "tags": [
        "紫微",
        "财帛宫",
        "煞曜"
      ]
    },
    {
      "factor_id": "Z_FIN_004",
      "name": "财帛宫化禄化权同宫",
      "engine": "ziwei",
      "category": "natal",
      "definition": "生年化禄或化权是否落在财帛宫。传统视为财位受化，偏吉。",
      "computation": "any(生年四化 in {禄, 权} 落于 财帛宫)",
      "raw_unit": "bool",
      "normalized_hint": "True→+1，False→0",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.natal_mutagens"
      ],
      "tags": [
        "紫微",
        "财帛宫",
        "四化"
      ]
    },
    {
      "factor_id": "Z_CAREER_001",
      "name": "官禄宫主星庙旺和",
      "engine": "ziwei",
      "category": "natal",
      "definition": "官禄宫主星庙旺等级之和。**研究映射**：官禄宫 → 公司经营/行业地位，属本项目假设。",
      "computation": "sum(BRIGHTNESS_SCORE[主星.brightness] for 主星 in 官禄宫)",
      "raw_unit": "score_sum",
      "normalized_hint": "tanh(sum / 1.5)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.官禄.major_stars"
      ],
      "tags": [
        "紫微",
        "官禄宫",
        "research_mapping"
      ]
    },
    {
      "factor_id": "Z_CAREER_002",
      "name": "官禄宫主星数量",
      "engine": "ziwei",
      "category": "natal",
      "definition": "官禄宫主星个数（0 为空宫）。结构性变量，方向中性。",
      "computation": "len(官禄宫.major_stars)",
      "raw_unit": "count",
      "normalized_hint": "min(count / 2, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.官禄"
      ],
      "tags": [
        "紫微",
        "官禄宫"
      ]
    },
    {
      "factor_id": "Z_CAREER_003",
      "name": "官禄宫煞曜数量",
      "engine": "ziwei",
      "category": "natal",
      "definition": "官禄宫中六煞星的数量。**研究映射**：官禄宫 → 公司经营，故该因子被用作『经营阻力』的代理变量，属本项目假设。**不是传统定论。**",
      "computation": "count(malefic in 官禄宫)",
      "raw_unit": "count",
      "normalized_hint": "-min(count / 2, 1)",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.官禄"
      ],
      "tags": [
        "紫微",
        "官禄宫",
        "煞曜"
      ]
    },
    {
      "factor_id": "Z_CAREER_004",
      "name": "官禄宫化权化科同宫",
      "engine": "ziwei",
      "category": "natal",
      "definition": "生年化权或化科是否落在官禄宫。传统视为权位/名位受化。",
      "computation": "any(生年四化 in {权, 科} 落于 官禄宫)",
      "raw_unit": "bool",
      "normalized_hint": "True→+1，False→0",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.natal_mutagens"
      ],
      "tags": [
        "紫微",
        "官禄宫",
        "四化"
      ]
    },
    {
      "factor_id": "Z_MOVE_001",
      "name": "迁移宫主星庙旺和",
      "engine": "ziwei",
      "category": "natal",
      "definition": "迁移宫主星庙旺等级之和。**研究映射**：迁移宫 → 外部市场/资金流入环境，属本项目假设。",
      "computation": "sum(BRIGHTNESS_SCORE[主星.brightness] for 主星 in 迁移宫)",
      "raw_unit": "score_sum",
      "normalized_hint": "tanh(sum / 1.5)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.迁移.major_stars"
      ],
      "tags": [
        "紫微",
        "迁移宫",
        "research_mapping"
      ]
    },
    {
      "factor_id": "Z_MOVE_002",
      "name": "迁移宫煞曜数量",
      "engine": "ziwei",
      "category": "natal",
      "definition": "迁移宫中六煞星的数量。**研究映射**：迁移宫 → 外部市场环境，故该因子被用作『外部阻力』的代理变量，属本项目假设。**不是传统定论。**",
      "computation": "count(malefic in 迁移宫)",
      "raw_unit": "count",
      "normalized_hint": "-min(count / 2, 1)",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace.迁移"
      ],
      "tags": [
        "紫微",
        "迁移宫",
        "煞曜"
      ]
    },
    {
      "factor_id": "Z_MOVE_003",
      "name": "迁移宫化禄化科同宫",
      "engine": "ziwei",
      "category": "natal",
      "definition": "生年化禄或化科是否落在迁移宫。**研究映射**：迁移宫 → 外部市场，故此处把化吉入迁移解释为外部环境受化，属本项目假设。",
      "computation": "any(生年四化 in {禄, 科} 落于 迁移宫)",
      "raw_unit": "bool",
      "normalized_hint": "True→+1，False→0",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.natal_mutagens"
      ],
      "tags": [
        "紫微",
        "迁移宫",
        "四化"
      ]
    },
    {
      "factor_id": "Z_MUTAGEN_001",
      "name": "生年化禄落宫位阶",
      "engine": "ziwei",
      "category": "natal",
      "definition": "生年化禄所落宫位在『命-财-官-迁』关键宫集中的位阶。传统认为化禄入命财官迁为吉位。位阶 2=核心位（命财官迁），1=次核心位（福德/田宅），0=其他位，-1=缺失。",
      "computation": "根据 natal_mutagens[禄].palace_name 映射位阶",
      "raw_unit": "tier",
      "normalized_hint": "tier 2→+1，1→+0.5，0→0，-1→不可用",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.natal_mutagens"
      ],
      "tags": [
        "紫微",
        "四化",
        "禄"
      ]
    },
    {
      "factor_id": "Z_MUTAGEN_002",
      "name": "生年化权落宫位阶",
      "engine": "ziwei",
      "category": "natal",
      "definition": "生年化权所落宫位的位阶（同 Z_MUTAGEN_001 的位阶定义）。",
      "computation": "根据 natal_mutagens[权].palace_name 映射位阶",
      "raw_unit": "tier",
      "normalized_hint": "tier 2→+1，1→+0.5，0→0，-1→不可用",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.natal_mutagens"
      ],
      "tags": [
        "紫微",
        "四化",
        "权"
      ]
    },
    {
      "factor_id": "Z_MUTAGEN_003",
      "name": "生年化科落宫位阶",
      "engine": "ziwei",
      "category": "natal",
      "definition": "生年化科所落宫位的位阶（同 Z_MUTAGEN_001 的位阶定义）。",
      "computation": "根据 natal_mutagens[科].palace_name 映射位阶",
      "raw_unit": "tier",
      "normalized_hint": "tier 2→+1，1→+0.5，0→0，-1→不可用",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.natal_mutagens"
      ],
      "tags": [
        "紫微",
        "四化",
        "科"
      ]
    },
    {
      "factor_id": "Z_MUTAGEN_004",
      "name": "生年化忌落宫位阶",
      "engine": "ziwei",
      "category": "natal",
      "definition": "生年化忌所落宫位的位阶。化忌入命财官迁传统视为该位受冲。",
      "computation": "根据 natal_mutagens[忌].palace_name 映射位阶",
      "raw_unit": "tier",
      "normalized_hint": "tier 2→-1，1→-0.5，0→0，-1→不可用",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.natal_mutagens"
      ],
      "tags": [
        "紫微",
        "四化",
        "忌"
      ]
    },
    {
      "factor_id": "Z_MUTAGEN_005",
      "name": "化吉入关键宫计数",
      "engine": "ziwei",
      "category": "natal",
      "definition": "生年化禄/化权/化科三者中，落在『命-财-官-迁』关键宫的数量。",
      "computation": "count(禄权科 落宫 ∈ {命宫, 财帛, 官禄, 迁移})",
      "raw_unit": "count",
      "normalized_hint": "min(count / 2, 1)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.natal_mutagens"
      ],
      "tags": [
        "紫微",
        "四化"
      ]
    },
    {
      "factor_id": "Z_MUTAGEN_006",
      "name": "化忌入关键宫",
      "engine": "ziwei",
      "category": "natal",
      "definition": "生年化忌是否落在『命-财-官-迁』任一关键宫。",
      "computation": "natal_mutagens[忌].palace_name ∈ {命宫, 财帛, 官禄, 迁移}",
      "raw_unit": "bool",
      "normalized_hint": "True→-1，False→0",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.natal_mutagens"
      ],
      "tags": [
        "紫微",
        "四化",
        "忌"
      ]
    },
    {
      "factor_id": "Z_TRINE_001",
      "name": "命宫三方四正主星庙旺和",
      "engine": "ziwei",
      "category": "natal",
      "definition": "命宫三方四正（命/迁/财/官）四宫主星庙旺等级之和。传统以三方四正的整体格局判断结构强弱。",
      "computation": "sum(BRIGHTNESS_SCORE[主星.brightness] over 四宫)",
      "raw_unit": "score_sum",
      "normalized_hint": "tanh(sum / 4)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.trine.命宫"
      ],
      "tags": [
        "紫微",
        "三方四正"
      ]
    },
    {
      "factor_id": "Z_TRINE_002",
      "name": "命宫三方四正吉曜数",
      "engine": "ziwei",
      "category": "natal",
      "definition": "命宫三方四正四宫中吉曜（六吉星 + 禄存 + 天马）的总数。传统认为吉曜汇集则格局得力，本项目仅作为可检验的结构变量。",
      "computation": "count(吉曜 over 四宫)",
      "raw_unit": "count",
      "normalized_hint": "min(count / 6, 1)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.trine.命宫"
      ],
      "tags": [
        "紫微",
        "三方四正",
        "吉曜"
      ]
    },
    {
      "factor_id": "Z_TRINE_003",
      "name": "命宫三方四正煞曜数",
      "engine": "ziwei",
      "category": "natal",
      "definition": "命宫三方四正四宫中六煞星（六煞全集）的总数。传统以三方四正的整体格局判断结构强弱，本因子是该判断的一个分量。",
      "computation": "count(煞曜 over 四宫)",
      "raw_unit": "count",
      "normalized_hint": "-min(count / 4, 1)",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.trine.命宫"
      ],
      "tags": [
        "紫微",
        "三方四正",
        "煞曜"
      ]
    },
    {
      "factor_id": "Z_TRINE_004",
      "name": "命宫三方四正吉煞差",
      "engine": "ziwei",
      "category": "natal",
      "definition": "三方四正的吉曜总数与煞曜总数之差，传统『吉凶相抵』概念的量化近似。正值表示吉曜多于煞曜。这是传统规则的看法，不构成对股价的判断。",
      "computation": "吉曜数 - 煞曜数",
      "raw_unit": "count_diff",
      "normalized_hint": "tanh(diff / 3)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.trine.命宫"
      ],
      "tags": [
        "紫微",
        "三方四正"
      ]
    },
    {
      "factor_id": "Z_TRINE_005",
      "name": "三宫主星总数",
      "engine": "ziwei",
      "category": "natal",
      "definition": "财帛 / 官禄 / 迁移 三宫的主星总数（不含命宫）。结构性变量，方向中性。",
      "computation": "sum(len(主星) for 宫 ∈ {财帛, 官禄, 迁移})",
      "raw_unit": "count",
      "normalized_hint": "min(count / 5, 1)",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.palace"
      ],
      "tags": [
        "紫微",
        "三方四正"
      ]
    },
    {
      "factor_id": "Z_YEAR_001",
      "name": "流年命宫原盘位阶",
      "engine": "ziwei",
      "category": "year",
      "definition": "该年流年命宫落在原盘的哪一宫（宫位 index）。属于分类/结构变量，方向中性。",
      "computation": "horoscope.yearly.index",
      "raw_unit": "palace_index",
      "normalized_hint": "index 映射到 [-1,1]；仅作结构编码，不含吉凶",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.yearly.index"
      ],
      "tags": [
        "紫微",
        "流年"
      ]
    },
    {
      "factor_id": "Z_YEAR_002",
      "name": "流年命宫主星庙旺和",
      "engine": "ziwei",
      "category": "year",
      "definition": "流年命宫（原盘对应宫位）的主星庙旺等级之和。",
      "computation": "sum(BRIGHTNESS_SCORE[主星.brightness] at palace horoscope.yearly.index)",
      "raw_unit": "score_sum",
      "normalized_hint": "tanh(sum / 1.5)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.yearly.index"
      ],
      "tags": [
        "紫微",
        "流年"
      ]
    },
    {
      "factor_id": "Z_YEAR_003",
      "name": "流年命宫煞曜数量",
      "engine": "ziwei",
      "category": "year",
      "definition": "流年命宫所在宫位的原局煞曜与流年煞曜（流羊/流陀等）总数。",
      "computation": "count(malefic in 原局宫) + count(流年煞曜)",
      "raw_unit": "count",
      "normalized_hint": "-min(count / 3, 1)",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.yearly"
      ],
      "tags": [
        "紫微",
        "流年",
        "煞曜"
      ]
    },
    {
      "factor_id": "Z_YEAR_004",
      "name": "流年化禄落原盘宫",
      "engine": "ziwei",
      "category": "year",
      "definition": "该年流年四化中化禄所落星曜的原盘宫位 index。结构变量，方向中性（吉凶判断留给 Z_YEAR_006 等带方向的因子）。",
      "computation": "horoscope.yearly.mutagen[0] → 找到该星在原盘的宫位",
      "raw_unit": "palace_index",
      "normalized_hint": "index 映射到 [-1,1]；仅作结构编码",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.yearly.mutagen"
      ],
      "tags": [
        "紫微",
        "流年",
        "四化"
      ]
    },
    {
      "factor_id": "Z_YEAR_005",
      "name": "流年化忌落原盘宫",
      "engine": "ziwei",
      "category": "year",
      "definition": "该年流年四化中化忌所落星曜的原盘宫位 index。结构变量，方向中性。",
      "computation": "horoscope.yearly.mutagen[3] → 找到该星在原盘的宫位",
      "raw_unit": "palace_index",
      "normalized_hint": "index 映射到 [-1,1]；仅作结构编码",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.yearly.mutagen"
      ],
      "tags": [
        "紫微",
        "流年",
        "四化"
      ]
    },
    {
      "factor_id": "Z_YEAR_006",
      "name": "流年命宫与原盘命宫同位",
      "engine": "ziwei",
      "category": "year",
      "definition": "流年命宫是否与原盘命宫落在同一宫（太岁重叠）。传统视为该年原局结构被直接引动。",
      "computation": "horoscope.yearly.index == soul_palace_index",
      "raw_unit": "bool",
      "normalized_hint": "True→+0.5（结构集中），False→0",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.yearly.index"
      ],
      "tags": [
        "紫微",
        "流年"
      ]
    },
    {
      "factor_id": "Z_MONTH_001",
      "name": "流月命宫原盘位阶",
      "engine": "ziwei",
      "category": "month",
      "definition": "该月流月命宫落在原盘的哪一宫。结构变量，方向中性。",
      "computation": "horoscope.monthly.index",
      "raw_unit": "palace_index",
      "normalized_hint": "index 映射到 [-1,1]；仅作结构编码",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.monthly.index"
      ],
      "tags": [
        "紫微",
        "流月"
      ]
    },
    {
      "factor_id": "Z_MONTH_002",
      "name": "流月命宫主星庙旺和",
      "engine": "ziwei",
      "category": "month",
      "definition": "流月命宫（原盘对应宫位）的主星庙旺等级之和。",
      "computation": "sum(BRIGHTNESS_SCORE over 流月命宫主星)",
      "raw_unit": "score_sum",
      "normalized_hint": "tanh(sum / 1.5)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.monthly.index"
      ],
      "tags": [
        "紫微",
        "流月"
      ]
    },
    {
      "factor_id": "Z_MONTH_003",
      "name": "流月命宫煞曜数量",
      "engine": "ziwei",
      "category": "month",
      "definition": "流月命宫所在宫位的原局煞曜与流月煞曜总数。",
      "computation": "count(煞曜)",
      "raw_unit": "count",
      "normalized_hint": "-min(count / 3, 1)",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.monthly"
      ],
      "tags": [
        "紫微",
        "流月",
        "煞曜"
      ]
    },
    {
      "factor_id": "Z_MONTH_004",
      "name": "流月化禄落原盘宫",
      "engine": "ziwei",
      "category": "month",
      "definition": "流月四化中化禄所落星曜的原盘宫位 index。结构变量，方向中性。",
      "computation": "horoscope.monthly.mutagen[0] → 星曜原盘落宫",
      "raw_unit": "palace_index",
      "normalized_hint": "index 映射到 [-1,1]",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.monthly.mutagen"
      ],
      "tags": [
        "紫微",
        "流月",
        "四化"
      ]
    },
    {
      "factor_id": "Z_MONTH_005",
      "name": "流月化忌落原盘宫",
      "engine": "ziwei",
      "category": "month",
      "definition": "流月四化中化忌所落星曜的原盘宫位 index。结构变量，方向中性。",
      "computation": "horoscope.monthly.mutagen[3] → 星曜原盘落宫",
      "raw_unit": "palace_index",
      "normalized_hint": "index 映射到 [-1,1]",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.monthly.mutagen"
      ],
      "tags": [
        "紫微",
        "流月",
        "四化"
      ]
    },
    {
      "factor_id": "Z_DAY_001",
      "name": "流日命宫原盘位阶",
      "engine": "ziwei",
      "category": "day",
      "definition": "该日流日命宫落在原盘的哪一宫。结构变量，方向中性。本因子是周度聚合（交易日流日 → 周）的基础输入。",
      "computation": "horoscope.daily.index",
      "raw_unit": "palace_index",
      "normalized_hint": "index 映射到 [-1,1]；仅作结构编码",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.daily.index"
      ],
      "tags": [
        "紫微",
        "流日",
        "周度"
      ]
    },
    {
      "factor_id": "Z_DAY_002",
      "name": "流日命宫主星庙旺和",
      "engine": "ziwei",
      "category": "day",
      "definition": "流日命宫（原盘对应宫位）的主星庙旺等级之和。",
      "computation": "sum(BRIGHTNESS_SCORE over 流日命宫主星)",
      "raw_unit": "score_sum",
      "normalized_hint": "tanh(sum / 1.5)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.daily.index"
      ],
      "tags": [
        "紫微",
        "流日"
      ]
    },
    {
      "factor_id": "Z_DAY_003",
      "name": "流日命宫煞曜数量",
      "engine": "ziwei",
      "category": "day",
      "definition": "流日命宫所在宫位的原局煞曜与流日煞曜总数。",
      "computation": "count(煞曜)",
      "raw_unit": "count",
      "normalized_hint": "-min(count / 3, 1)",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.daily"
      ],
      "tags": [
        "紫微",
        "流日",
        "煞曜"
      ]
    },
    {
      "factor_id": "Z_DAY_004",
      "name": "流日化禄落原盘宫",
      "engine": "ziwei",
      "category": "day",
      "definition": "流日四化中化禄所落星曜的原盘宫位 index。结构变量，方向中性。",
      "computation": "horoscope.daily.mutagen[0] → 星曜原盘落宫",
      "raw_unit": "palace_index",
      "normalized_hint": "index 映射到 [-1,1]",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.daily.mutagen"
      ],
      "tags": [
        "紫微",
        "流日",
        "四化"
      ]
    },
    {
      "factor_id": "Z_DAY_005",
      "name": "流日化忌落原盘宫",
      "engine": "ziwei",
      "category": "day",
      "definition": "流日四化中化忌所落星曜的原盘宫位 index。结构变量，方向中性。",
      "computation": "horoscope.daily.mutagen[3] → 星曜原盘落宫",
      "raw_unit": "palace_index",
      "normalized_hint": "index 映射到 [-1,1]",
      "default_direction": 0,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.daily.mutagen"
      ],
      "tags": [
        "紫微",
        "流日",
        "四化"
      ]
    },
    {
      "factor_id": "Z_DECADE_001",
      "name": "当前大限宫主星庙旺和",
      "engine": "ziwei",
      "category": "natal",
      "definition": "as_of 所处大限所在宫位的主星庙旺等级之和。**该因子随 variant（顺行/逆行）变化**，是两个 variant 对比的核心变量。",
      "computation": "sum(BRIGHTNESS_SCORE over 大限宫主星)",
      "raw_unit": "score_sum",
      "normalized_hint": "tanh(sum / 1.5)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.decadal.index"
      ],
      "tags": [
        "紫微",
        "大限",
        "variant敏感"
      ]
    },
    {
      "factor_id": "Z_DECADE_002",
      "name": "当前大限宫煞曜数量",
      "engine": "ziwei",
      "category": "natal",
      "definition": "as_of 所处大限所在宫位的煞曜数量。**随 variant 变化。**",
      "computation": "count(煞曜 in 大限宫)",
      "raw_unit": "count",
      "normalized_hint": "-min(count / 2, 1)",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.decadal.index"
      ],
      "tags": [
        "紫微",
        "大限",
        "variant敏感"
      ]
    },
    {
      "factor_id": "Z_AGE_001",
      "name": "当前小限宫主星庙旺和",
      "engine": "ziwei",
      "category": "natal",
      "definition": "as_of 所处小限所在宫位的主星庙旺等级之和。**随 variant 变化。**",
      "computation": "sum(BRIGHTNESS_SCORE over 小限宫主星)",
      "raw_unit": "score_sum",
      "normalized_hint": "tanh(sum / 1.5)",
      "default_direction": 1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.age.index"
      ],
      "tags": [
        "紫微",
        "小限",
        "variant敏感"
      ]
    },
    {
      "factor_id": "Z_AGE_002",
      "name": "当前小限宫煞曜数量",
      "engine": "ziwei",
      "category": "natal",
      "definition": "as_of 所处小限所在宫位的煞曜数量。**随 variant 变化。**注意：小限层在 iztro 中不提供流曜，因此本因子只使用原局煞曜。",
      "computation": "count(原局煞曜 in 小限宫)",
      "raw_unit": "count",
      "normalized_hint": "-min(count / 2, 1)",
      "default_direction": -1,
      "rule_score_meaning": "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。",
      "rule_version": "zv1",
      "enabled": true,
      "requires": [
        "ziwei.horoscope.age.index"
      ],
      "tags": [
        "紫微",
        "小限",
        "variant敏感"
      ]
    }
  ],
  "disclaimer": "因子 direction / rule_score 表达的是**传统规则认为的方向与强度**，不是预期收益率，也不是上涨概率。财星 ≠ 股票上涨；三合 ≠ 股票上涨。",
  "rule_version": "v1.1"
};
