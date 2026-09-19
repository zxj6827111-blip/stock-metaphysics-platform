/**
 * 紫微斗数排盘 —— iztro 的唯一入口。
 *
 * 设计纪律
 * --------
 * 1. **确定性**：同一输入必须产出完全相同的输出（无随机、无时区依赖、无当前时间）。
 * 2. **无性别默认**：iztro 的 `gender` 参数只影响**大限/小限的顺逆**，
 *    而股票没有真实性别。因此本服务不把性别当归一化参数，而是把自由度
 *    直接暴露为 `variantMode`：
 *      - `variant_forward` 强制顺行；
 *      - `variant_reverse` 强制逆行；
 *      - `not_applicable` 拒绝排盘（由 Python 侧提前拦截，这里也返回错误）。
 *    具体用哪个性别参数实现是**实现细节**，但必须写进 `genderParameter` 供审计。
 * 3. **不做业务判断**：只输出盘面，不输出任何分数、方向、吉凶结论。
 */

import { astro } from 'iztro';

import type {
  ZiweiChartResult,
  ZiweiDecadal,
  ZiweiHoroscope,
  ZiweiHoroscopeSection,
  ZiweiPalace,
  ZiweiRequest,
  ZiweiStar,
} from './types.js';

export const IZTRO_VERSION = '2.6.1';
export const ENGINE_VERSION = `iztro-${IZTRO_VERSION}+smx-1.0.0`;

/** 十天干阴阳：甲丙戊庚壬为阳。 */
const YANG_STEMS = new Set(['甲', '丙', '戊', '庚', '壬']);

/** 十二地支，index 0 = 寅（iztro `palaces` 的固定顺序）。 */
export const PALACE_BRANCHES = ['寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥', '子', '丑'];

type Gender = '男' | '女';

export class ZiweiError extends Error {}

function normalizeStars(stars: any[] | undefined): ZiweiStar[] {
  return (stars ?? []).map((s) => ({
    name: String(s?.name ?? ''),
    type: String(s?.type ?? ''),
    brightness: String(s?.brightness ?? ''),
    mutagen: String(s?.mutagen ?? ''),
    scope: String(s?.scope ?? 'origin'),
  }));
}

/**
 * 选择实现 variant 的性别参数。
 *
 * 传统规则：阳年男 / 阴年女 → 顺行；阴年男 / 阳年女 → 逆行。
 * 为了表达"强制顺行 / 强制逆行"这一自由度，必须在不知道性别的条件下
 * 反解出对应的性别参数——这正是 `genderParameter` 只作审计用途的原因。
 */
export function resolveGender(yearStem: string, variantMode: string): Gender {
  const isYang = YANG_STEMS.has(yearStem);
  if (variantMode === 'variant_forward') {
    return isYang ? '男' : '女';
  }
  if (variantMode === 'variant_reverse') {
    return isYang ? '女' : '男';
  }
  throw new ZiweiError(`不支持的 variant_mode: ${variantMode}`);
}

export function variantBasis(variantMode: string): string {
  if (variantMode === 'variant_forward') {
    return '顺行（阳年用男命规则、阴年用女命规则）。股票无真实性别，此为方向变体假设。';
  }
  if (variantMode === 'variant_reverse') {
    return '逆行（阳年用女命规则、阴年用男命规则）。股票无真实性别，此为方向变体假设。';
  }
  throw new ZiweiError(`不支持的 variant_mode: ${variantMode}`);
}

function section(scope: string, raw: any): ZiweiHoroscopeSection {
  if (!raw) {
    throw new ZiweiError(`运限层 ${scope} 缺失`);
  }
  return {
    scope,
    index: Number(raw.index ?? -1),
    heavenlyStem: String(raw.heavenlyStem ?? ''),
    earthlyBranch: String(raw.earthlyBranch ?? ''),
    name: String(raw.name ?? ''),
    mutagen: (raw.mutagen ?? []).map((m: unknown) => String(m)),
    palaceNames: (raw.palaceNames ?? []).map((n: unknown) => String(n)),
    // 注意：iztro 的 age（小限）层**不提供 stars 字段**（只给宫位/干支/四化）。
    // 这里如实输出空数组，不用任何推算去"补全"它 —— 缺失必须可被下游看见。
    stars: (raw.stars ?? []).map((s: any[]) => normalizeStars(s)),
    nominalAge: raw.nominalAge === undefined || raw.nominalAge === null
      ? null
      : Number(raw.nominalAge),
  };
}

export function buildZiweiChart(req: ZiweiRequest): ZiweiChartResult {
  const variantMode = req.variantMode ?? 'not_applicable';
  if (variantMode === 'not_applicable') {
    throw new ZiweiError(
      'variant_mode=not_applicable 时不进行紫微排盘：股票无真实性别，' +
        '本服务不提供任何默认性别假设。请显式传入 variant_forward 或 variant_reverse。',
    );
  }
  if (!/^\d{4}-\d{1,2}-\d{1,2}$/.test(req.solarDate)) {
    throw new ZiweiError(`solarDate 格式非法（应为 YYYY-MM-DD）: ${req.solarDate}`);
  }
  const timeIndex = Number(req.timeIndex);
  if (!Number.isInteger(timeIndex) || timeIndex < 0 || timeIndex > 12) {
    throw new ZiweiError(`timeIndex 必须为 0..12 的整数，收到 ${req.timeIndex}`);
  }

  // 先用临时性别取万年历信息（性别不影响四柱），再据此解析 variant。
  const probe = astro.bySolar(req.solarDate, timeIndex, '男', true, 'zh-CN');
  const chineseDate = String(probe.chineseDate);
  const yearStem = chineseDate.trim().split(/\s+/)[0]?.[0] ?? '';
  if (!yearStem) {
    throw new ZiweiError(`无法从四柱解析年干: ${chineseDate}`);
  }

  const gender = resolveGender(yearStem, variantMode);
  // 除大限/小限外盘面与性别无关；用解析出的性别重建一次，确保 decadal/ages 正确。
  const finalAstrolabe = astro.bySolar(req.solarDate, timeIndex, gender, true, 'zh-CN');

  // --- 十二宫 ---
  const palaces: ZiweiPalace[] = finalAstrolabe.palaces.map((p: any, i: number) => {
    let trine: number[] = [];
    try {
      const sp = finalAstrolabe.surroundedPalaces(p.name);
      trine = [sp.target.index, sp.opposite.index, sp.wealth.index, sp.career.index].map(Number);
    } catch {
      // 极少见的宫名解析失败：退化为固定索引算术（对宫+6、财帛+8、官禄+4）
      trine = [i, (i + 6) % 12, (i + 8) % 12, (i + 4) % 12];
    }
    return {
      index: i,
      name: String(p.name),
      heavenlyStem: String(p.heavenlyStem),
      earthlyBranch: String(p.earthlyBranch),
      isBodyPalace: Boolean(p.isBodyPalace),
      isOriginalPalace: Boolean(p.isOriginalPalace),
      majorStars: normalizeStars(p.majorStars),
      minorStars: normalizeStars(p.minorStars),
      adjectiveStars: normalizeStars(p.adjectiveStars),
      changsheng12: String(p.changsheng12 ?? ''),
      boshi12: String(p.boshi12 ?? ''),
      jiangqian12: String(p.jiangqian12 ?? ''),
      suiqian12: String(p.suiqian12 ?? ''),
      decadalRange: p.decadal?.range ? p.decadal.range.map(Number) : null,
      ages: (p.ages ?? []).map(Number),
      trineIndices: trine,
    };
  });

  if (palaces.length !== 12) {
    throw new ZiweiError(`十二宫数量异常: ${palaces.length}`);
  }

  // --- 生年四化 ---
  const natalMutagens: { mutagen: string; star: string; palaceIndex: number; palaceName: string }[] = [];
  for (const order of ['禄', '权', '科', '忌']) {
    for (const p of palaces) {
      const hit = [...p.majorStars, ...p.minorStars].find((s) => s.mutagen === order);
      if (hit) {
        natalMutagens.push({
          mutagen: order,
          star: hit.name,
          palaceIndex: p.index,
          palaceName: p.name,
        });
        break;
      }
    }
  }

  // --- 大限 ---
  const decadals: ZiweiDecadal[] = palaces.map((p: any) => ({
    palaceIndex: p.index,
    palaceName: p.name,
    range: p.decadalRange ?? [],
    heavenlyStem: p.heavenlyStem,
    earthlyBranch: p.earthlyBranch,
  }));

  // --- 运限（流年/流月/流日/流时 + 大限/小限） ---
  const asOf = req.asOfDate ?? req.solarDate;
  const asOfTimeIndex = req.asOfTimeIndex ?? timeIndex;
  const h = finalAstrolabe.horoscope(asOf, asOfTimeIndex);
  const horoscope: ZiweiHoroscope = {
    solarDate: asOf,
    timeIndex: asOfTimeIndex,
    decadal: section('decadal', h.decadal),
    age: section('age', h.age),
    yearly: section('yearly', h.yearly),
    monthly: section('monthly', h.monthly),
    daily: section('daily', h.daily),
    hourly: section('hourly', h.hourly),
  };

  return {
    engine: 'ziwei',
    engineVersion: ENGINE_VERSION,
    iztroVersion: IZTRO_VERSION,
    configVersion: 'cfg-ziwei-2026.09',
    variantMode,
    variantBasis: variantBasis(variantMode),
    genderParameter: gender,
    solarDate: req.solarDate,
    lunarDate: String(finalAstrolabe.lunarDate),
    chineseDate,
    timeIndex,
    timeName: String(finalAstrolabe.time),
    timeRange: String(finalAstrolabe.timeRange),
    soul: String(finalAstrolabe.soul),
    body: String(finalAstrolabe.body),
    fiveElementsClass: String(finalAstrolabe.fiveElementsClass),
    soulPalaceBranch: String(finalAstrolabe.earthlyBranchOfSoulPalace),
    sign: String(finalAstrolabe.sign),
    zodiac: String(finalAstrolabe.zodiac),
    soulPalaceIndex: palaces.findIndex((p) => p.name === '命宫'),
    bodyPalaceIndex: palaces.findIndex((p) => p.isBodyPalace),
    natalMutagens,
    palaces,
    decadals,
    horoscope,
  };
}
