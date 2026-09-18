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

export const FIXTURE_QUERY_VALUE = "ui-reference";

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
