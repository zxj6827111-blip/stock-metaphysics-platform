#!/usr/bin/env node
/**
 * 紫微第二实现源（REFERENCE ONLY）—— 中州派排盘 CLI。
 *
 * 定位（GOAL §3G-2，硬约束）
 * -------------------------
 * 本服务**只能**用于"验证 iztro 排盘实现差异"的交叉核对：
 *   * 不得进入 ConsensusEngine；
 *   * 不得与 iztro 一起构成"双重确认"；
 *   * 不得被业务层直接依赖（业务层只依赖 MetaphysicsEngine 接口）。
 *
 * 第三方库
 * --------
 * ``fortel-ziweidoushu`` v1.3.4（MIT，作者 airicyu，2022 年起维护）——
 * 中州派体系，自带日历实现，唯一运行时依赖是 ``util``。
 * **不依赖 iztro**，因此是一个真正独立于生产引擎的实现源。
 *
 * 用法::
 *
 *     echo '{"cases":[{...}]}' | node reference_chart.js
 *
 * 输入（stdin JSON）::
 *
 *     {"cases": [{"case_id": "c1", "solar": {"year":1952,"month":4,"day":9},
 *                 "time_branch": "寅時", "gender": "F", "config_type": "SKY"}]}
 *
 * 输出（stdout JSON）：逐案例的**归一化**盘面（字段名与比较器对齐）。
 */

import { createInterface } from 'node:readline'
import {
  ConfigType,
  DayTimeGround,
  DestinyBoard,
  DestinyConfigBuilder,
  Gender,
} from 'fortel-ziweidoushu'

const REFERENCE_LIBRARY = 'fortel-ziweidoushu'
const REFERENCE_VERSION = '1.3.4'
const SCHOOL = '中州派'

function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = []
    const rl = createInterface({ input: process.stdin })
    rl.on('line', (line) => chunks.push(line))
    rl.on('close', () => resolve(chunks.join('\n')))
    rl.on('error', reject)
  })
}

/** 时辰归一：优先接受 ``hour``（0..23），库自身区分 早子時/夜子時；
 *  ``time_branch`` 仅在需要显式指定时才用（例如闰月边界案例）。 */
function resolveTimeGroundByHour(hour) {
  const value = DayTimeGround.getByHour(Number(hour))
  if (value === undefined || value === null) {
    throw new Error(`无法解析小时：${hour}`)
  }
  return value
}

/** 时辰名归一：接受 "寅時"/"寅时"/"寅" 三种写法。 */
function resolveTimeGround(raw) {
  const text = String(raw ?? '').trim()
  const candidates = [text]
  if (text.endsWith('时')) candidates.push(text.slice(0, -1) + '時')
  if (text.endsWith('時')) candidates.push(text.slice(0, -1) + '时')
  if (!text.endsWith('时') && !text.endsWith('時')) {
    candidates.push(`${text}時`, `${text}时`)
  }
  for (const candidate of candidates) {
    // getByName 在找不到时**抛异常**而不是返回 undefined，因此必须逐个 try
    try {
      const value = DayTimeGround.getByName(candidate)
      if (value !== undefined && value !== null) return value
    } catch {
      // 继续尝试下一种写法
    }
  }
  throw new Error(`无法解析时辰：${raw}`)
}

function resolveConfigType(raw) {
  const text = String(raw ?? 'SKY').toUpperCase()
  if (text === 'GROUND' || text === 'HUMAN' || text === 'SKY') return ConfigType[text]
  throw new Error(`无法解析 config_type：${raw}`)
}

function resolveGender(raw) {
  const text = String(raw ?? 'F').toUpperCase()
  if (text !== 'M' && text !== 'F') throw new Error(`无法解析 gender：${raw}`)
  return Gender[text]
}

/** 星曜/宫位对象 → 字符串。
 *
 * 注意：``toJSON()`` 之后星曜与宫位仍是**对象**（它们各自的 toJSON 才返回名字），
 * 因此比较器要用的名字必须显式从 ``getDisplayName()`` / ``toString()`` 取。
 */
function nameOf(value) {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string') return value
  if (typeof value.getDisplayName === 'function') return String(value.getDisplayName())
  return String(value)
}

/** 把盘面归一化成比较器需要的形状（保持传统字形，比较器负责简繁归一）。 */
function normalise(board) {
  const json = board.toJSON()
  const cells = (json.cells ?? []).map((cell, index) => {
    // toJSON() 之后 cells 仍是 Cell 实例（元素才各自 toJSON），
    // 且 杂曜 只在 Cell.toJSON() 里以 miscStars 暴露（等价于 allMiniStars）。
    const plain = typeof cell.toJSON === 'function' ? cell.toJSON() : cell
    return {
      index,
      sky: nameOf(plain.sky),
      ground: nameOf(plain.ground),
      temples: (plain.temples ?? []).map(nameOf),
      majorStars: (plain.majorStars ?? []).map(nameOf),
      minorStars: (plain.minorStars ?? []).map(nameOf),
      miniStars: (plain.miniStars ?? []).map(nameOf),
      miscStars: (plain.miscStars ?? []).map(nameOf),
      ageStart: plain.ageStart,
      ageEnd: plain.ageEnd,
      lifeStage: nameOf(plain.lifeStage),
    }
  })
  const templeOf = (name) => {
    const hit = cells.find((cell) => cell.temples.includes(name))
    return hit ? { index: hit.index, ground: hit.ground, sky: hit.sky } : null
  }
  const config = json.config ?? {}
  const lunarConfig = {
    year: config.year,
    month: config.month,
    day: config.day,
    isLeapMonth: config.isLeapMonth,
    yearSky: nameOf(config.yearSky),
    yearGround: nameOf(config.yearGround),
    monthSky: nameOf(config.monthSky),
    monthGround: nameOf(config.monthGround),
    daySky: nameOf(config.daySky),
    dayGround: nameOf(config.dayGround),
    bornTimeGround: nameOf(config.bornTimeGround),
    configType: nameOf(config.configType),
    gender: nameOf(config.gender),
  }
  return {
    element: json.element,
    destinyMaster: json.destinyMaster,
    bodyMaster: json.bodyMaster,
    startControl: json.startControl,
    bornStarDerivativeMap: json.bornStarDerivativeMap,
    lunarConfig,
    cells,
    soulPalace: templeOf('命宮') ?? templeOf('命宫'),
    bodyPalace: templeOf('身宮') ?? templeOf('身宫'),
  }
}

async function main() {
  const raw = await readStdin()
  let payload
  try {
    payload = JSON.parse(raw)
  } catch (error) {
    process.stdout.write(JSON.stringify({ error: `stdin 不是合法 JSON：${error.message}` }))
    return 1
  }
  const cases = payload?.cases ?? []
  const results = []
  for (const item of cases) {
    const caseId = item.case_id ?? ''
    try {
      const solar = item.solar ?? {}
      const config = DestinyConfigBuilder.withSolar({
        year: Number(solar.year),
        month: Number(solar.month),
        day: Number(solar.day),
        bornTimeGround: item.hour === undefined || item.hour === null
          ? resolveTimeGround(item.time_branch)
          : resolveTimeGroundByHour(item.hour),
        configType: resolveConfigType(item.config_type),
        gender: resolveGender(item.gender),
      })
      const board = new DestinyBoard(config)
      results.push({
        case_id: caseId,
        ok: true,
        reference_library: REFERENCE_LIBRARY,
        reference_version: REFERENCE_VERSION,
        school: SCHOOL,
        chart: normalise(board),
        input_echo: {
          solar: {
            year: Number(solar.year), month: Number(solar.month), day: Number(solar.day),
          },
          hour: item.hour ?? null,
          time_branch: item.time_branch ?? '',
          resolved_time_ground: nameOf(
            (item.hour === undefined || item.hour === null
              ? resolveTimeGround(item.time_branch)
              : resolveTimeGroundByHour(item.hour)).displayName,
          ),
          gender: String(item.gender ?? 'F').toUpperCase(),
          config_type: String(item.config_type ?? 'SKY').toUpperCase(),
        },
      })
    } catch (error) {
      results.push({ case_id: caseId, ok: false, error: String(error?.message ?? error) })
    }
  }
  process.stdout.write(JSON.stringify({
    reference_library: REFERENCE_LIBRARY,
    reference_version: REFERENCE_VERSION,
    school: SCHOOL,
    case_count: cases.length,
    results,
  }))
  return 0
}

main().then(
  (code) => process.exit(code),
  (error) => {
    process.stdout.write(JSON.stringify({ error: String(error?.message ?? error) }))
    process.exit(1)
  },
)
