"""术数日历（只读描述工具）：给定日期/时辰 ↔ 个股原局的契合关系。

三个视图
--------
    1. intraday  —— 同一只票：当天（或指定日）**各时辰**与原局的关系
    2. forecast  —— 同一只票：**未来若干天**逐日与原局的关系
    3. screen    —— 给定**日期（可带时辰）**：全市场按契合度排序（最合 / 最冲）

"契合度"是什么，不是什么
------------------------
**是**：把原局喜用忌与外部干支的刑冲合害做一次确定性归纳，用于**浏览排序**。
**不是**：不是预测，也不是因子。它没有 `factor_id`、不进 `FactorSet`、
不参与任何评分或共识，**未经回测**（项目铁律：未经回测不得解释成利好）。

口径（写死在本文件，便于核对）::

    喜忌：用神 +3 / 喜神 +2 / 闲神 0 / 忌神 −3      （对天干、地支各计一次）
    关系：六合 +2 / 三合 +2 / 天干五合 +2
          相冲 −3 / 天干相冲 −2 / 相刑 −2 / 相害 −2  （每命中一处计一次）

复用而非另造
------------
* 原局四柱 / 日主 / 喜用忌：``BaziEngine.build_chart``
* 外部干支（任意时刻，含时柱）：``CalendarEngine.snapshot``
* 刑冲合害：``rules.relations_with_external``（与流年/流月/流日同源）
* 十神与喜忌标注：引擎自己的 ``_build_temporal`` / ``_annotate_temporal``
  （调用私有方法是**刻意**的：要的是引擎的规范口径；一旦重构会立刻
  AttributeError 报错，而不是静默算错）

用法::

    python scripts/astrology_calendar.py cache --limit 500        # 建原局缓存
    python scripts/astrology_calendar.py intraday 600519
    python scripts/astrology_calendar.py forecast 600519 --days 30
    python scripts/astrology_calendar.py screen --date 2026-09-20 --hour 10
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import pickle
import sys
import time
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from src.core.stock.trading_calendar import get_trading_calendar_provider  # noqa: E402
from src.core.stock.variant_basis import (  # noqa: E402
    FIRST_DAY_YINYANG_DISCLAIMER,
    FIRST_DAY_YINYANG_TO_GENDER,
    FIRST_DAY_YINYANG_TO_VARIANT,
)
from src.db.base import get_session_factory  # noqa: E402
from src.db.models import StockMasterRow, UniverseMembershipRow  # noqa: E402
from src.engines.bazi import rules  # noqa: E402
from src.engines.bazi.bazi_engine import POSITIONS, BaziEngine  # noqa: E402
from src.engines.calendar.calendar_engine import CalendarEngine  # noqa: E402

CACHE_PATH = ROOT / "data" / "phase4_cache" / "astrology_natal_cache.pkl"
CACHE_VERSION = 2
#: 原局缓存必须与出生档案版本绑定：档案一改（例如上市日修正），旧缓存立刻作废，
#: 绝不允许继续用"上个月那套出生时刻"算出来的盘。
BIRTH_PROFILE_PREFIX = "v2-phase4b"
UNIVERSE_VERSION = "v4-full"
DEFAULT_MODEL = "listing_open_v1"

# 喜忌权重（与 _annotate_temporal 的输出域一致：用神/喜神/忌神/闲神）
YONG_WEIGHT = {"用神": 3, "喜神": 2, "闲神": 0, "忌神": -3}
# 关系权重：合类 +2；冲类为负（地支冲 −3 重于天干冲 −2）；刑害 −2。
# 每个 REL_LABEL 取值都必须在此表中有条目 —— 缺条目会被 get(..., 0) 静默漏计，
# tests/test_astrology_calendar.py 有断言守着这一点。
REL_WEIGHT = {
    "六合": 2, "三合": 2, "天干五合": 2,
    "相冲": -3, "天干相冲": -2, "相刑": -2, "相害": -2,
}
REL_LABEL = {
    "clashes": "相冲", "harmonies": "六合", "triple_harmonies": "三合",
    "punishments": "相刑", "harms": "相害",
    "stem_harmonies": "天干五合", "stem_clashes": "天干相冲",
}
# A 股交易时段（用于标注时柱与盘中重叠多少分钟）
SESSIONS = ((dtime(9, 30), dtime(11, 30)), (dtime(13, 0), dtime(15, 0)))

DISCLAIMER = (
    "契合度是原局喜用忌与刑冲合害的确定性归纳，仅用于浏览排序；"
    "未经回测，不代表涨跌、不构成任何交易依据。"
)

BAZI = BaziEngine()
CALENDAR = CalendarEngine()

#: 运限变体枚举（从引擎签名取，避免重复定义）
VariantMode = inspect.signature(BAZI.build_chart).parameters["variant_mode"].default.__class__

#: 首日阴阳 → 性别假设的映射。**这是假设，不是事实**：
#: 股票没有真实性别（AGENTS.md §5），这里只是把用户的「阳→男 / 阴→女」
#: 规则显式化，用于起运；大运顺逆再由「性别 + 年干阴阳」自动决定。
#:
#: 口径定义在 ``src/core/stock/variant_basis.py``（单一真源，ADR-0014）：
#: CLI 与 API 必须共用同一套映射 —— 2026-09「界面显示不出大运」正是
#: CLI 与界面各有一套口径造成的。
YINYANG_TO_GENDER = {
    yinyang: (variant, FIRST_DAY_YINYANG_TO_GENDER[yinyang])
    for yinyang, variant in FIRST_DAY_YINYANG_TO_VARIANT.items()
}
DAYUN_DISCLAIMER = FIRST_DAY_YINYANG_DISCLAIMER

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"


# ---------------------------------------------------------------------------
# 原局摘要（缓存的内容）
# ---------------------------------------------------------------------------

def natal_summary(birth: datetime) -> dict:
    chart = BAZI.build_chart(birth_datetime=birth, as_of=birth)
    return {
        "stems": {p: getattr(chart, f"{p}_pillar").ganzhi.stem for p in POSITIONS},
        "branches": {p: getattr(chart, f"{p}_pillar").ganzhi.branch for p in POSITIONS},
        "day_master": chart.day_master,
        "yong_shen": chart.yong_shen,          # YongShenAnalysis（pickle 保真）
        "engine_version": chart.engine_version,
        "four_pillars": " ".join(getattr(chart, f"{p}_pillar").ganzhi.text for p in POSITIONS),
        "pattern": chart.pattern.primary,
    }


def load_cache() -> dict:
    if not CACHE_PATH.is_file():
        return {}
    with CACHE_PATH.open("rb") as handle:
        payload = pickle.load(handle)
    if payload.get("cache_version") != CACHE_VERSION:
        print(f"缓存版本不符（{payload.get('cache_version')}≠{CACHE_VERSION}），忽略旧缓存")
        return {}
    if payload.get("birth_profile_prefix") != BIRTH_PROFILE_PREFIX:
        print(f"出生档案版本已变（缓存={payload.get('birth_profile_prefix')} "
              f"≠ 当前={BIRTH_PROFILE_PREFIX}），忽略旧缓存")
        return {}
    return payload["entries"]


def save_cache(entries: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("wb") as handle:
        pickle.dump(
            {
                "cache_version": CACHE_VERSION,
                "birth_profile_prefix": BIRTH_PROFILE_PREFIX,
                "entries": entries,
                "saved_at": datetime.now(),
            },
            handle, protocol=pickle.HIGHEST_PROTOCOL,
        )


def load_profiles(codes: list[str]) -> dict:
    """复用面板采集器的出生档加载（同一实现）。"""
    spec = importlib.util.spec_from_file_location(
        "phase3d_collect_panel", ROOT / "scripts" / "phase3d_collect_panel.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module.load_profiles(codes)


def trading_status(target: date, exchange: str) -> tuple[bool | None, str]:
    """交易日判定 + 来源。

    实测日历覆盖范围外的日期（例如未来日）本身返回"未知"。这里**显式降级**
    为周末规则并标注来源——绝不静默顶替；节假日仍然无法识别。
    """
    query = get_trading_calendar_provider().for_exchange(exchange).is_trading_day(target)
    if query.value is not None:
        return bool(query.value), query.source
    return target.weekday() < 5, "weekend_rule_fallback(降级)"


def trading_day_note(target: date, exchange: str) -> str:
    value, source = trading_status(target, exchange)
    if value:
        return f"{target} 是交易日（{source}）"
    return (f"⚠ {target} **不是交易日**（{source}）——术数关系照算，但没有交易含义"
            if "fallback" not in source else
            f"⚠ {target} **不是交易日**（{source}：实测日历覆盖 "
            f"{get_trading_calendar_provider().for_exchange(exchange).coverage[1]}，"
            f"假日无法识别）——术数关系照算，但没有交易含义")


def stock_exchange(code: str) -> str:
    session = get_session_factory()
    with session() as db:
        row = db.execute(
            UniverseMembershipRow.__table__.select()
            .with_only_columns(UniverseMembershipRow.exchange)
            .where(
                UniverseMembershipRow.universe_version == UNIVERSE_VERSION,
                UniverseMembershipRow.stock_code == code,
            )
        ).first()
    return (row[0] if row and row[0] else "SSE").upper()


def universe_codes(limit: int = 0) -> list[str]:
    session = get_session_factory()
    with session() as db:
        rows = db.execute(
            UniverseMembershipRow.__table__.select()
            .with_only_columns(UniverseMembershipRow.stock_code)
            .where(UniverseMembershipRow.universe_version == UNIVERSE_VERSION)
            .order_by(UniverseMembershipRow.stock_code)
        ).all()
    codes = [row[0] for row in rows]
    return codes[:limit] if limit else codes


# ---------------------------------------------------------------------------
# 契合度
# ---------------------------------------------------------------------------

def evaluate(summary: dict, when: datetime, level: str) -> dict:
    """外部干支（level=year/month/day/hour）与原局的关系 + 契合度。"""
    snap = CALENDAR.snapshot(when)
    ganzhi = getattr(snap, f"{level}_ganzhi")
    pillar = BAZI._build_temporal(
        level, ganzhi, summary["day_master"], summary["stems"], summary["branches"],
        (when.date(), when.date()),
    )
    BAZI._annotate_temporal(pillar, summary["yong_shen"])
    interact = rules.relations_with_external(
        summary["branches"], ganzhi.branch, ganzhi.stem, natal_stems=summary["stems"],
    )

    score = YONG_WEIGHT.get(pillar.stem_is, 0) + YONG_WEIGHT.get(pillar.branch_is, 0)
    hits: list[str] = []
    for key, label in REL_LABEL.items():
        for position in interact.get(key) or []:
            score += REL_WEIGHT.get(label, 0)
            hits.append(f"{label}·{position}" if isinstance(position, str) else f"{label}")
    return {
        "level": level,
        "ganzhi": ganzhi.text,
        "stem": ganzhi.stem, "branch": ganzhi.branch,
        "stem_ten_god": pillar.stem_ten_god,
        "branch_ten_gods": list(pillar.branch_ten_gods),
        "stem_is": pillar.stem_is, "branch_is": pillar.branch_is,
        "relations": hits,
        "di_shi": pillar.di_shi,
        "score": score,
        "note": pillar.note,
    }


def session_overlap_minutes(hour: int) -> int:
    """该时辰（起始整点 hour）与 A 股交易时段重叠的分钟数。"""
    start = dtime(hour % 24, 0)
    end = dtime((hour + 2) % 24, 0)
    total = 0
    for open_, close in SESSIONS:
        lo = max(start, open_)
        hi = min(end if end > start else dtime(23, 59), close)
        if hi > lo:
            total += (hi.hour * 60 + hi.minute) - (lo.hour * 60 + lo.minute)
    return total


def fmt(result: dict, minutes: int | None = None) -> str:
    relations = "、".join(result["relations"]) or "—"
    suffix = f"  盘中{minutes}分钟" if minutes is not None else ""
    return (
        f"{result['ganzhi']}  天干{result['stem']}={result['stem_ten_god']}({result['stem_is']})"
        f"  地支{result['branch']}={('/'.join(result['branch_ten_gods'])) or '—'}({result['branch_is']})"
        f"  关系:{relations}  契合度{result['score']:+d}{suffix}"
    )


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------

def cmd_cache(args: argparse.Namespace) -> int:
    entries = load_cache()
    codes = universe_codes(args.limit)
    profiles = load_profiles(codes)
    missing = [(c, m) for c in codes for m in (args.models or (DEFAULT_MODEL,))
               if (c, m) not in entries and (c, m) in profiles]
    print(f"universe={len(codes)} 只；待计算原局 {len(missing)} 个；已有缓存 {len(entries)} 个")
    started = time.time()
    for order, (code, model) in enumerate(missing, 1):
        entries[(code, model)] = natal_summary(profiles[(code, model)])
        if order % 200 == 0 or order == len(missing):
            save_cache(entries)
            print(f"  {order}/{len(missing)}  elapsed={time.time() - started:.0f}s", flush=True)
    save_cache(entries)
    print(f"缓存完成：{len(entries)} 条 → {CACHE_PATH}")
    return 0


def cmd_intraday(args: argparse.Namespace) -> int:
    target = date.fromisoformat(args.date) if args.date else date.today()
    profiles = load_profiles([args.code])
    key = (args.code, args.model)
    if key not in profiles:
        print(f"缺少出生档：{key}（可用出生档见 /birth-profile）")
        return 1
    summary = natal_summary(profiles[key])
    print(f"{args.code}  出生档 {args.model} = {profiles[key]}")
    print(f"原局：{summary['four_pillars']}  日主 {summary['day_master']}  格局 {summary['pattern']}")
    print(f"日期：{target}（{CALENDAR.snapshot(datetime.combine(target, dtime(10, 0))).day_ganzhi.text}日）")
    print(f"      {trading_day_note(target, stock_exchange(args.code))}")
    print(f"口径：{DISCLAIMER}")
    print()
    print("— 十二时辰 —" if args.all_hours else "— 交易时段相关时辰 —")
    for start in (range(0, 24, 2) if args.all_hours else (9, 11, 13)):
        when = datetime.combine(target, dtime(start, 0))
        result = evaluate(summary, when, "hour")
        minutes = None if args.all_hours else session_overlap_minutes(start)
        if minutes == 0:
            continue
        print(f"  {start:02d}:00–{(start + 2) % 24:02d}:00  " + fmt(result, minutes))
    return 0


def covering_dayun(items: list, year: int) -> str:
    """返回该年份所处的大运干支（起运前返回空串）。"""
    for item in items:
        start, end = item.get("start_year"), item.get("end_year")
        if start and end and start <= year <= end:
            return str(item.get("ganzhi") or "")
    return ""


def cmd_forecast(args: argparse.Namespace) -> int:
    start = date.fromisoformat(args.date) if args.date else date.today()
    profiles = load_profiles([args.code])
    key = (args.code, args.model)
    if key not in profiles:
        print(f"缺少出生档：{key}")
        return 1
    summary = natal_summary(profiles[key])
    exchange = stock_exchange(args.code)
    print(f"{args.code}  出生档 {args.model} = {profiles[key]}")
    print(f"原局：{summary['four_pillars']}  日主 {summary['day_master']}  格局 {summary['pattern']}")
    print(f"口径：{DISCLAIMER}")
    print()

    dayun_items: list = []
    if args.dayun:
        info = first_day_info(args.code)
        if info["yinyang"]:
            plan = dayun_plan(
                profiles[key], info["yinyang"], datetime.combine(start, dtime(12, 0)),
            )
            dayun_items = plan["items"]
            print(f"首日涨跌幅 {info['pct']:+.2%} → 标识「{info['yinyang']}」"
                  f" → 假设 {plan['gender']}（{plan['variant'].name}），大运{plan['direction']}")
            print(f"口径：{DAYUN_DISCLAIMER}")
            print()
        else:
            print("（缺首日阴阳数据，本次不显示大运）\n")

    header = f"{'日期':<12}{'日柱':<8}{'关系与契合度'}"
    print(header + ("  大运" if dayun_items else ""))
    skipped = 0
    shown = 0
    offset = 0
    degraded = False
    previous_dayun: str | None = None
    while shown < args.days and offset < args.days * 3:
        day = start + timedelta(days=offset)
        offset += 1
        is_trading, source = trading_status(day, exchange)
        degraded = degraded or "fallback" in source
        if not args.all_days and not is_trading:
            skipped += 1
            continue
        result = evaluate(summary, datetime.combine(day, dtime(12, 0)), "day")
        mark = "★" if result["score"] >= 4 else ("✗" if result["score"] <= -4 else " ")
        flag = "  [实测非交易日]" if (args.all_days and not is_trading) else ""
        extra = ""
        if dayun_items:
            current = covering_dayun(dayun_items, day.year)
            if current != previous_dayun:
                extra = f"   大运→ {current or '(起运前)'}"
                previous_dayun = current
        print(f"{day.isoformat():<12}{result['ganzhi']:<8}{mark} " + fmt(result) + flag + extra)
        shown += 1
    if skipped:
        print(f"\n（已跳过 {skipped} 个非交易日；用 --all-days 可显示全部）")
    if degraded:
        print("⚠ 该区间超出实测交易日历覆盖 → 按**周末规则降级**过滤，节假日无法识别")
    return 0


def cmd_screen(args: argparse.Namespace) -> int:
    target = date.fromisoformat(args.date) if args.date else date.today()
    hour = args.hour
    level = "hour" if hour is not None else "day"
    when = datetime.combine(target, dtime(hour, 0)) if hour is not None else datetime.combine(target, dtime(12, 0))
    entries = load_cache()
    candidates = [(code, model) for (code, model) in entries if model == args.model]
    if not candidates:
        print(f"缓存为空或不含出生档 {args.model}；先跑 cache 子命令")
        return 1
    rows = []
    for code, model in candidates:
        result = evaluate(entries[(code, model)], when, level)
        rows.append((result["score"], code, result))
    rows.sort(key=lambda item: (-item[0], item[1]))
    snap = CALENDAR.snapshot(when)
    print(f"日期 {target} {f'{hour:02d}:00' if hour is not None else '(日级)'}  "
          f"年{snap.year_ganzhi.text} 月{snap.month_ganzhi.text} 日{snap.day_ganzhi.text}"
          f" 时{snap.hour_ganzhi.text}  层级={level}  出生档={args.model}")
    print(f"候选 {len(rows)} 只（缓存）"
          f"{f'  盘中重叠 {session_overlap_minutes(hour)} 分钟' if hour is not None else ''}")
    print(f"      {trading_day_note(target, 'SSE')}")
    print(f"口径：{DISCLAIMER}")
    print()

    def show(title: str, subset: list) -> None:
        print(f"— {title} —")
        for score, code, result in subset:
            relations = "、".join(result["relations"]) or "—"
            print(f"  {score:+3d}  {code}  {result['ganzhi']}  "
                  f"{result['stem_is']}/{result['branch_is']}  {relations}")
        print()

    show(f"最合前 {args.top}", rows[: args.top])
    if args.bottom:
        show(f"最冲前 {args.bottom}", list(reversed(rows[-args.bottom:])))

    # 分布：让"今天大部分票都差不多"这件事看得见
    buckets: dict[str, int] = {}
    for score, _code, _result in rows:
        label = f"{score:+d}"
        buckets[label] = buckets.get(label, 0) + 1
    ordered = sorted(buckets.items(), key=lambda item: -int(item[0]))
    print("契合度分布：" + "  ".join(f"{k}×{v}" for k, v in ordered))
    return 0


# ---------------------------------------------------------------------------
# 运限（大运）—— 由「首日阴阳 → 性别假设」驱动的显式推演
# ---------------------------------------------------------------------------

def first_day_info(code: str) -> dict:
    """读上市首日涨跌幅与阴阳（``stock_master.first_day_*``）。"""
    session = get_session_factory()
    with session() as db:
        row = db.execute(
            select(StockMasterRow.first_day_pct_chg, StockMasterRow.first_day_yinyang)
            .where(StockMasterRow.stock_code == code)
        ).first()
    if row is None:
        return {"pct": None, "yinyang": None}
    return {"pct": row[0], "yinyang": row[1]}


def ganzhi_index(text: str) -> int | None:
    """干支在六十甲子中的序号（0=甲子）；用于自检大运顺/逆。"""
    if len(text) != 2 or text[0] not in STEMS or text[1] not in BRANCHES:
        return None
    stem_i, branch_i = STEMS.index(text[0]), BRANCHES.index(text[1])
    for index in range(60):
        if index % 10 == stem_i and index % 12 == branch_i:
            return index
    return None


def dayun_plan(birth: datetime, yinyang: str, as_of: datetime) -> dict:
    """按「阴阳→性别假设」起运，并从干支序列自检顺/逆行。"""
    variant, gender = YINYANG_TO_GENDER[yinyang]
    chart = BAZI.build_chart(birth_datetime=birth, as_of=as_of, variant_mode=variant)
    items = list(chart.da_yun or [])
    indices = [ganzhi_index(str(item.get("ganzhi", ""))) for item in items]
    valid = [index for index in indices if index is not None]
    direction = "—"
    if len(valid) >= 2:
        step = (valid[1] - valid[0]) % 60
        direction = {1: "顺行", 59: "逆行"}.get(step, f"异常(步长{step})")
    return {
        "variant": variant,
        "gender": gender,
        "items": items,
        "direction": direction,
        "note": chart.da_yun_note,
        "year_stem": chart.year_pillar.ganzhi.stem,
        "year_stem_wuxing": chart.year_pillar.ganzhi.stem_wuxing,
    }


def cmd_dayun(args: argparse.Namespace) -> int:
    target = date.fromisoformat(args.date) if args.date else date.today()
    profiles = load_profiles([args.code])
    key = (args.code, args.model)
    if key not in profiles:
        print(f"缺少出生档：{key}")
        return 1
    birth = profiles[key]
    info = first_day_info(args.code)

    print(f"{args.code}  出生档 {args.model} = {birth}")
    if info["pct"] is None or not info["yinyang"]:
        print("缺上市首日数据（stock_master.first_day_*），无法起运")
        return 1
    print(f"上市首日：涨跌幅 {info['pct']:+.2%} → 标识「{info['yinyang']}」")
    print(f"口径：{DAYUN_DISCLAIMER}")
    print()

    plan = dayun_plan(birth, info["yinyang"], datetime.combine(target, dtime(12, 0)))
    yang_year = plan["year_stem"] in STEMS[::2]
    print(f"假设：{info['yinyang']} → {plan['gender']}"
          f"（variant_mode={plan['variant'].name}）")
    print(f"年干 {plan['year_stem']}（{'阳' if yang_year else '阴'}干，{plan['year_stem_wuxing']}）"
          f" → 依「阳男阴女顺行 / 阴男阳女逆行」应"
          f"{'顺行' if (info['yinyang'] == '阳') == yang_year else '逆行'}")
    print(f"引擎实际给出：{plan['direction']}  ← 顺逆自检")
    print(f"引擎说明：{plan['note']}")
    print()
    print(f"{'起':<6}{'止':<6}{'干支':<8}{'起运岁':<7}区间")
    for item in plan["items"]:
        start, end = item.get("start_year"), item.get("end_year")
        mark = "  ← 当前" if start and end and start <= target.year <= end else ""
        print(f"{start:<6}{end:<6}{item.get('ganzhi', ''):<8}"
              f"{item.get('start_age', ''):<7}[{start}, {end}]{mark}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="术数日历（只读描述工具）")
    sub = parser.add_subparsers(dest="command", required=True)

    cache = sub.add_parser("cache", help="构建原局摘要缓存")
    cache.add_argument("--limit", type=int, default=0)
    cache.add_argument("--models", nargs="*", default=None)
    cache.set_defaults(func=cmd_cache)

    intraday = sub.add_parser("intraday", help="单票当日各时辰")
    intraday.add_argument("code")
    intraday.add_argument("--date", default="")
    intraday.add_argument("--model", default=DEFAULT_MODEL)
    intraday.add_argument("--all-hours", action="store_true")
    intraday.set_defaults(func=cmd_intraday)

    forecast = sub.add_parser("forecast", help="单票未来逐日")
    forecast.add_argument("code")
    forecast.add_argument("--date", default="")
    forecast.add_argument("--days", type=int, default=30)
    forecast.add_argument("--model", default=DEFAULT_MODEL)
    forecast.add_argument("--all-days", action="store_true", help="包含非交易日")
    forecast.add_argument(
        "--dayun", action="store_true",
        help="显示所处大运（按「首日阴阳→性别」显式假设起运）",
    )
    forecast.set_defaults(func=cmd_forecast)

    screen = sub.add_parser("screen", help="给定日期/时辰反查全市场")
    screen.add_argument("--date", default="")
    screen.add_argument("--hour", type=int, default=None)
    screen.add_argument("--model", default=DEFAULT_MODEL)
    screen.add_argument("--top", type=int, default=15)
    screen.add_argument("--bottom", type=int, default=15)
    screen.set_defaults(func=cmd_screen)

    dayun = sub.add_parser(
        "dayun", help="单票大运（由「首日阴阳→性别」显式假设起运）",
    )
    dayun.add_argument("code")
    dayun.add_argument("--date", default="")
    dayun.add_argument("--model", default=DEFAULT_MODEL)
    dayun.set_defaults(func=cmd_dayun)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
