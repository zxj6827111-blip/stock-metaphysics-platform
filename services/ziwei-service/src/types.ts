/**
 * Ziwei 服务输出契约。
 *
 * 这些结构是「本项目自有」的领域模型（ADR-0001：第三方对象不得越出 Adapter）。
 * Python 侧 `src/core/schemas/ziwei.py` 必须与这里逐字段对应；
 * 由 `tests/engines/test_ziwei_engine.py` 的契约测试锁定。
 */

/** 星曜（主星 / 辅星 / 杂曜共用）。 */
export interface ZiweiStar {
  name: string;
  /** major | soft | tough | lucun | tianma | flower | helper | adjective | lucun ... */
  type: string;
  /** 庙 / 旺 / 得 / 利 / 平 / 不 / 陷，无庙旺概念时为空串 */
  brightness: string;
  /** 生年四化：禄 / 权 / 科 / 忌，无则为空串 */
  mutagen: string;
  /** 来源盘：origin | decadal | yearly | monthly | daily | hourly */
  scope: string;
}

/** 十二宫之一。 */
export interface ZiweiPalace {
  /** 0..11，固定为地支顺序（0 = 寅，1 = 卯 … 11 = 丑） */
  index: number;
  name: string;
  heavenlyStem: string;
  earthlyBranch: string;
  isBodyPalace: boolean;
  isOriginalPalace: boolean;
  majorStars: ZiweiStar[];
  minorStars: ZiweiStar[];
  adjectiveStars: ZiweiStar[];
  changsheng12: string;
  boshi12: string;
  jiangqian12: string;
  suiqian12: string;
  /** 大限年龄区间 [起, 止]，缺失为 null */
  decadalRange: number[] | null;
  /** 小限年龄列表（12 个） */
  ages: number[];
  /**
   * 三方四正（本宫 / 对宫 / 财帛位 / 官禄位）的宫位 index。
   * 由 iztro `surroundedPalaces` 提供，顺序固定 [target, opposite, wealth, career]。
   */
  trineIndices: number[];
}

/** 大限（运限）一项。 */
export interface ZiweiDecadal {
  /** 对应宫位 index */
  palaceIndex: number;
  palaceName: string;
  range: number[];
  heavenlyStem: string;
  earthlyBranch: string;
}

/** 流年 / 流月 / 流日 / 流时 / 大限 / 小限 的一层运限快照。 */
export interface ZiweiHoroscopeSection {
  /** decadal | age | yearly | monthly | daily | hourly */
  scope: string;
  /** 该层运限落在原盘的宫位 index */
  index: number;
  heavenlyStem: string;
  earthlyBranch: string;
  /** 该层命宫名（如 "命宫" / "夫妻"） */
  name: string;
  /**
   * 小限虚岁。iztro 只在 `age`（小限）层提供；其他层为 null。
   */
  nominalAge: number | null;
  /**
   * 四化星名，顺序固定 [禄, 权, 科, 忌]。
   * 这是运限四化，与生年四化必须分开保存。
   */
  mutagen: string[];
  /**
   * 12 个元素，与 `palaces` 同序：
   * `palaceNames[i]` = 原盘第 i 宫在该层运限中扮演的宫名；
   * `stars[i]` = 落在原盘第 i 宫的该层运限星曜。
   */
  palaceNames: string[];
  stars: ZiweiStar[][];
}

export interface ZiweiHoroscope {
  solarDate: string;
  timeIndex: number;
  decadal: ZiweiHoroscopeSection;
  age: ZiweiHoroscopeSection;
  yearly: ZiweiHoroscopeSection;
  monthly: ZiweiHoroscopeSection;
  daily: ZiweiHoroscopeSection;
  hourly: ZiweiHoroscopeSection;
}

/** 一次排盘的完整原始结果（落 `chart_artifact.raw_chart`）。 */
export interface ZiweiChartResult {
  engine: string;
  engineVersion: string;
  iztroVersion: string;
  configVersion: string;

  /** not_applicable | variant_forward | variant_reverse */
  variantMode: string;
  /** variant 语义说明（写入 assumptions，必须可读） */
  variantBasis: string;
  /** 为实现该 variant 实际传入的性别参数（审计用） */
  genderParameter: string;

  solarDate: string;
  lunarDate: string;
  chineseDate: string;
  timeIndex: number;
  timeName: string;
  timeRange: string;

  soul: string;
  body: string;
  fiveElementsClass: string;
  soulPalaceBranch: string;
  sign: string;
  zodiac: string;

  soulPalaceIndex: number;
  bodyPalaceIndex: number;

  /** 生年四化：[{mutagen, star, palaceIndex, palaceName}]，顺序 禄权科忌 */
  natalMutagens: { mutagen: string; star: string; palaceIndex: number; palaceName: string }[];

  palaces: ZiweiPalace[];
  decadals: ZiweiDecadal[];
  horoscope: ZiweiHoroscope;
}

export interface ZiweiRequest {
  /** ISO 日期，如 2001-08-27 */
  solarDate: string;
  /** 0..12（0 = 早子时，12 = 晚子时） */
  timeIndex: number;
  /** not_applicable | variant_forward | variant_reverse */
  variantMode?: string;
  /** 流年/流月/流日 的目标时刻（默认取 solarDate） */
  asOfDate?: string;
  asOfTimeIndex?: number;
}

export interface ZiweiBatchResponse {
  results: ZiweiChartResult[];
  errors: { index: number; message: string }[];
}
