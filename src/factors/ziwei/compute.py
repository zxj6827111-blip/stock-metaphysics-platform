"""紫微因子计算（Phase 2B）—— 把 ``ZiweiChart`` 确定性地转换为 ``FactorObservation``。

纪律
----
* 只读盘面；不读任何行情数据（因此天然不涉及未来数据泄漏）；
* 缺口一律 ``_unavailable(...)``，**不得猜数、不得填 0**；
* 方向只表达传统规则认为的方向，不是收益预测；
* 小限层没有流曜（iztro 事实，见 calculation-differences-phase2-ziwei.md D1），
  相关计算只能使用原局星曜 —— 这一限制在因子定义中已声明。
"""

from __future__ import annotations

from datetime import date, datetime

from src.core.config import settings
from src.core.schemas.common import Direction
from src.core.schemas.factor import FactorObservation
from src.core.schemas.ziwei import ZiweiChart, ZiweiHoroscopeSection, ZiweiPalace
from src.engines.ziwei import constants as zc
from src.factors.ziwei.definitions import (
    KEY_PALACES,
    SECONDARY_PALACES,
    ZIWEI_DEFINITION_INDEX,
)

# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _variant_key(value: object) -> str:
    """枚举/字符串统一取字符串值。

    项目里大量使用 ``class X(str, Enum)``（JSON 友好），但 ``str(X.A)``
    在 Python 3.11+ 会返回 ``"X.A"`` 而不是 ``"a"`` —— 这个坑在
    HANDOFF_PHASE1 §12.1#8 已经踩过一次。这里统一走 ``.value``。
    """
    inner = getattr(value, "value", None)
    return str(inner) if inner is not None else str(value)


def _tanh(x: float) -> float:
    import math

    return round(math.tanh(max(-20.0, min(20.0, x))), 6)


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _count_category(palace: ZiweiPalace, categories: set[str]) -> int:
    return sum(1 for s in palace.all_stars() if zc.star_category(s.name) in categories)


def _brightness_sum(palace: ZiweiPalace) -> float:
    return round(sum(zc.brightness_score(s.brightness) for s in palace.major_stars), 6)


def _malefic_count(palace: ZiweiPalace) -> int:
    return sum(1 for s in palace.all_stars() if s.name in zc.MALEFIC_STARS)


def _lucky_count(palace: ZiweiPalace) -> int:
    return (
        sum(1 for s in palace.all_stars() if s.name in zc.LUCKY_STARS)
        + sum(1 for s in palace.all_stars() if s.name in zc.WEALTH_MOVE_STARS)
    )


def _palace_tier(palace_name: str) -> int:
    """研究映射位阶：2=命财官迁、1=福德/田宅、0=其他。"""
    if palace_name in KEY_PALACES:
        return 2
    if palace_name in SECONDARY_PALACES:
        return 1
    return 0


def _tier_normalized(tier: int) -> float:
    return {2: 1.0, 1: 0.5, 0: 0.0}.get(tier, 0.0)


def _index_normalized(index: int) -> float:
    """宫位 index(0..11) → [-1, 1] 的**纯结构编码**（不含吉凶语义）。"""
    if index < 0:
        return 0.0
    return round((index - 5.5) / 5.5, 6)


def _horoscope_palace(chart: ZiweiChart, section: ZiweiHoroscopeSection | None) -> ZiweiPalace | None:
    """运限层命宫对应的**原盘宫位**。"""
    if section is None or section.index < 0:
        return None
    return chart.palace_at(section.index)


def _palaces_in_section(section: ZiweiHoroscopeSection | None, index: int) -> list:
    """某宫在该运限层的流曜列表（小限层为空，见 D1）。"""
    if section is None or not section.stars:
        return []
    if 0 <= index < len(section.stars):
        return list(section.stars[index])
    return []


def _flow_malefic_count(section: ZiweiHoroscopeSection | None, index: int) -> int:
    return sum(1 for s in _palaces_in_section(section, index) if s.name in zc.MALEFIC_STARS)


def _star_palace_index(chart: ZiweiChart, star_name: str) -> int:
    """星曜在原盘的落宫 index；找不到返回 -1。

    只在**原局**星曜（scope == "origin"）里找 —— 流曜不能用来定位原盘宫位。
    """
    if not star_name:
        return -1
    for p in chart.palaces:
        for s in p.all_stars():
            if s.name == star_name and s.scope == "origin":
                return p.index
    return -1


def _mutagen_palace(chart: ZiweiChart, mutagen: str) -> str:
    for m in chart.natal_mutagens:
        if m.mutagen == mutagen:
            return m.palace_name
    return ""


# ---------------------------------------------------------------------------
# observation 构造
# ---------------------------------------------------------------------------


def ziwei_rule_version(variant: str) -> str:
    """紫微观测的 rule_version。

    因为 ``Z_DECADE_*`` / ``Z_AGE_*`` 随 variant 变化，同一个
    ``(stock_code, as_of, factor_id)`` 在两个 variant 下是不同的观测，
    必须能各自落库（``factor_observation`` 的唯一键含 ``rule_version``）。

    后缀是**符号**而不是语义：``fwd`` = 顺行，``rev`` = 逆行。
    """
    suffix = {"forward": "fwd", "reverse": "rev"}.get(variant, "na")
    return f"{settings.ziwei_factor_rule_version}.{suffix}"


def _zobs(
    factor_id: str,
    stock_code: str,
    as_of: datetime,
    *,
    variant: str,
    raw_value: object,
    normalized: float | None,
    direction: Direction,
    rule_score: float,
    confidence: float,
    explanation: str,
    evidence: list[str] | None = None,
    availability: str = "ok",
    warnings: list[str] | None = None,
    trade_date: date | None = None,
) -> FactorObservation:
    definition = ZIWEI_DEFINITION_INDEX[factor_id]
    return FactorObservation(
        factor_id=factor_id,
        stock_code=stock_code,
        as_of=as_of,
        trade_date=trade_date,
        engine=definition.engine,
        category=definition.category,
        name=definition.name,
        raw_value=raw_value,  # type: ignore[arg-type]
        # `+ 0.0` 把 -0.0 归一成 0.0：负零会在 JSON / 前端比较里制造假差异，
        # 而它没有任何语义（-min(0/2,1) 这类表达式很容易产出 -0.0）。
        normalized_value=None if normalized is None else round(float(_clamp(normalized)), 6) + 0.0,
        direction=direction,
        rule_score=round(float(rule_score), 3),
        confidence=round(float(confidence), 4),
        availability=availability,
        rule_version=ziwei_rule_version(variant),
        engine_version=settings.ziwei_engine_version,
        config_version=settings.config_version,
        evidence=evidence or [],
        explanation=explanation,
        warnings=warnings or [],
    )


def _unavailable(
    factor_id: str, stock_code: str, as_of: datetime, *, variant: str, reason: str,
) -> FactorObservation:
    return _zobs(
        factor_id, stock_code, as_of, variant=variant,
        raw_value=None, normalized=None, direction=Direction.NEUTRAL,
        rule_score=0.0, confidence=0.0,
        explanation=f"该因子当前不可计算：{reason}（按契约返回 unavailable，不猜测数值）",
        availability="unavailable", warnings=[reason],
    )


# ---------------------------------------------------------------------------
# 分组计算
# ---------------------------------------------------------------------------


def _structure_problem(chart: ZiweiChart) -> str:
    """盘面结构校验；返回空串表示结构合法。

    坐标契约（见 `docs/ziwei-engine.md` §5）：
      * 恰好 12 个宫；
      * ``palaces[i].index == i``（index 0 = 寅）。
    违反任一条，整组因子都不可信。
    """
    if len(chart.palaces) != 12:
        return f"盘面结构非法：十二宫数量为 {len(chart.palaces)}（应为 12），拒绝计算任何紫微因子"
    for i, p in enumerate(chart.palaces):
        if p.index != i:
            return (f"盘面结构非法：第 {i} 个宫位的 index={p.index}，"
                    "与位置不一致（坐标系契约被破坏），拒绝计算任何紫微因子")
    return ""


def _palace_factor_block(
    chart: ZiweiChart, code: str, as_of: datetime, variant: str,
    *, palace_name: str, ids: dict[str, str], prefix_cn: str,
) -> list[FactorObservation]:
    """命宫 / 财帛 / 官禄 / 迁移 四个『单宫』因子组的公共实现。"""
    # ``ids`` 里除了 factor_id 还有 ``mutagen_wanted`` 这类**参数**，
    # 因此不能用 ids.values() 直接当 factor_id 列表。
    factor_ids = [v for k, v in ids.items() if k != "mutagen_wanted" and isinstance(v, str)]

    palace = chart.palace_by_name(palace_name)
    if palace is None:
        return [
            _unavailable(fid, code, as_of, variant=variant, reason=f"盘面缺少{palace_name}宫")
            for fid in factor_ids
        ]

    bsum = _brightness_sum(palace)
    mal = _malefic_count(palace)
    lucky = _lucky_count(palace)
    stars_txt = "、".join(s.name for s in palace.major_stars) or "空宫"
    out: list[FactorObservation] = []

    out.append(_zobs(
        ids["brightness"], code, as_of, variant=variant, raw_value=bsum,
        normalized=_tanh(bsum / 1.5), direction=Direction.POSITIVE,
        rule_score=min(abs(_tanh(bsum / 1.5)) * 10, 10.0), confidence=0.6,
        explanation=f"{prefix_cn}（{palace.earthly_branch}宫）主星 {stars_txt}，庙旺和 {bsum}。",
        evidence=[f"{palace_name}: {s.name}{s.brightness or '（无庙旺标记）'}" for s in palace.major_stars],
    ))
    if "count" in ids:
        n = len(palace.major_stars)
        out.append(_zobs(
            ids["count"], code, as_of, variant=variant, raw_value=n,
            normalized=min(n / 2, 1.0), direction=Direction.NEUTRAL,
            rule_score=min(n / 2, 1.0) * 5, confidence=0.7,
            explanation=f"{prefix_cn}主星 {n} 颗（0 表示空宫，传统需借对宫安星）。",
            evidence=[f"{palace_name}主星: {stars_txt}"],
        ))
    if "malefic" in ids:
        out.append(_zobs(
            ids["malefic"], code, as_of, variant=variant, raw_value=mal,
            normalized=-min(mal / 2, 1.0), direction=Direction.NEGATIVE,
            rule_score=min(mal / 2, 1.0) * 8, confidence=0.55,
            explanation=f"{prefix_cn}煞曜 {mal} 颗（传统视为阻力；本项为研究变量）。",
            evidence=[f"{palace_name}煞曜: "
                      f"{'、'.join(s.name for s in palace.all_stars() if s.name in zc.MALEFIC_STARS) or '无'}"],
        ))
    if "lucky" in ids:
        out.append(_zobs(
            ids["lucky"], code, as_of, variant=variant, raw_value=lucky,
            normalized=min(lucky / 3, 1.0), direction=Direction.POSITIVE,
            rule_score=min(lucky / 3, 1.0) * 8, confidence=0.55,
            explanation=f"{prefix_cn}吉曜（六吉+禄马）{lucky} 颗。",
            evidence=[f"{palace_name}吉曜: "
                      f"{'、'.join(s.name for s in palace.all_stars() if s.name in (zc.LUCKY_STARS | zc.WEALTH_MOVE_STARS)) or '无'}"],
        ))
    if "diff" in ids:
        diff = lucky - mal
        out.append(_zobs(
            ids["diff"], code, as_of, variant=variant, raw_value=diff,
            normalized=_tanh(diff / 2), direction=Direction.POSITIVE,
            rule_score=abs(_tanh(diff / 2)) * 8, confidence=0.5,
            explanation=f"{prefix_cn}吉煞差 = {lucky} - {mal} = {diff}。",
        ))
    if "mutagen" in ids:
        wanted = ids["mutagen_wanted"]
        hit = [m for m in chart.natal_mutagens if m.mutagen in wanted and m.palace_name == palace_name]
        val = bool(hit)
        out.append(_zobs(
            ids["mutagen"], code, as_of, variant=variant,
            raw_value="、".join(sorted(wanted)) if val else "",
            normalized=1.0 if val else 0.0, direction=Direction.POSITIVE,
            rule_score=8.0 if val else 0.0, confidence=0.6,
            explanation=(
                f"生年{'/'.join(sorted(wanted))}落在{prefix_cn}"
                + (f"（{hit[0].star}）" if hit else "：未命中")
                + "。"
            ),
            evidence=["生年四化: " + "、".join(f"{m.mutagen}{m.star}→{m.palace_name}"
                                               for m in chart.natal_mutagens)],
        ))
    return out


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def compute_ziwei_factors(
    chart: ZiweiChart,
    as_of: datetime,
    *,
    stock_code: str = "",
    variant: str = "forward",
    trade_date: date | None = None,
) -> list[FactorObservation]:
    """把一张紫微盘转换为一组 ``FactorObservation``。

    Args:
        variant: ``forward`` / ``reverse`` —— 决定 ``rule_version`` 后缀
            （见 ``ziwei_rule_version``）。每次调用只处理**一个** variant：
            两个 variant 必须分别调用、分别落库，**不得平均**。

    Raises:
        ValueError: ``variant`` 与 ``chart.variant_mode`` 不一致。
            这是**必需的防错**：紫微盘面里已经固定了方向，如果调用方传错 variant，
            产出的因子会被打上错误的 rule_version 落库，
            之后完全无法分辨"哪一份是顺行结果"。
    """
    chart_variant = _variant_key(chart.variant_mode)
    variant = _variant_key(variant)
    if chart_variant != variant:
        raise ValueError(
            f"variant 与盘面不一致：入参 variant={variant!r}，"
            f"但盘面 variant_mode={chart_variant!r}。"
            "紫微因子必须用与盘面相同的 variant 计算（ADR-0010）。"
        )

    code = stock_code or chart.stock_code

    # 盘面结构校验：紫微的全部计算都建立在"index 即坐标"这一前提上。
    # 一旦宫数不对或 index 与位置错位，任何局部结果都不可信 ——
    # 此时**整组因子返回 unavailable**，而不是算出一半看似正常的数字。
    problem = _structure_problem(chart)
    if problem:
        return [
            _unavailable(fid, code, as_of, variant=variant, reason=problem)
            for fid in sorted(ZIWEI_DEFINITION_INDEX)
        ]

    out: list[FactorObservation] = []

    # --- Z_LIFE_* 命宫 ---
    out += _palace_factor_block(
        chart, code, as_of, variant, palace_name="命宫", prefix_cn="命宫",
        ids={"brightness": "Z_LIFE_001", "count": "Z_LIFE_002", "lucky": "Z_LIFE_003",
             "malefic": "Z_LIFE_004", "diff": "Z_LIFE_005"},
    )
    soul = chart.palace_at(chart.soul_palace_index)
    same = chart.body_palace_index == chart.soul_palace_index
    out.append(_zobs(
        "Z_LIFE_006", code, as_of, variant=variant, raw_value=same,
        normalized=0.5 if same else 0.0, direction=Direction.NEUTRAL,
        rule_score=5.0 if same else 0.0, confidence=0.7,
        explanation=f"身宫{'与' if same else '不与'}命宫同宫。",
        evidence=[f"命宫#{chart.soul_palace_index}、身宫#{chart.body_palace_index}"],
    ))
    ju = zc.FIVE_ELEMENTS_CLASS.get(chart.five_elements_class)
    if ju is None:
        out.append(_unavailable("Z_LIFE_007", code, as_of, variant=variant,
                                reason=f"未知五行局 {chart.five_elements_class!r}"))
    else:
        num, wx = ju
        norm = (num - 4) / 2.0  # 2..6 → [-1, 1]
        out.append(_zobs(
            "Z_LIFE_007", code, as_of, variant=variant, raw_value=chart.five_elements_class,
            normalized=norm, direction=Direction.NEUTRAL,
            rule_score=abs(norm) * 5, confidence=0.9,
            explanation=f"五行局为 {chart.five_elements_class}（局数 {num}，"
                        f"决定起运岁数 {num} 岁）。结构性编码，不含吉凶。",
            evidence=[f"命宫地支 {chart.soul_palace_branch}"],
        ))
    _ = soul

    # --- Z_FIN_* / Z_CAREER_* / Z_MOVE_* ---
    out += _palace_factor_block(
        chart, code, as_of, variant, palace_name="财帛", prefix_cn="财帛宫",
        ids={"brightness": "Z_FIN_001", "count": "Z_FIN_002", "malefic": "Z_FIN_003",
             "mutagen": "Z_FIN_004", "mutagen_wanted": {"禄", "权"}},
    )
    out += _palace_factor_block(
        chart, code, as_of, variant, palace_name="官禄", prefix_cn="官禄宫",
        ids={"brightness": "Z_CAREER_001", "count": "Z_CAREER_002", "malefic": "Z_CAREER_003",
             "mutagen": "Z_CAREER_004", "mutagen_wanted": {"权", "科"}},
    )
    out += _palace_factor_block(
        chart, code, as_of, variant, palace_name="迁移", prefix_cn="迁移宫",
        ids={"brightness": "Z_MOVE_001", "malefic": "Z_MOVE_002",
             "mutagen": "Z_MOVE_003", "mutagen_wanted": {"禄", "科"}},
    )

    # --- Z_MUTAGEN_* 生年四化 ---
    for fid, mut, sign in (
        ("Z_MUTAGEN_001", "禄", 1), ("Z_MUTAGEN_002", "权", 1),
        ("Z_MUTAGEN_003", "科", 1), ("Z_MUTAGEN_004", "忌", -1),
    ):
        pname = _mutagen_palace(chart, mut)
        if not pname:
            out.append(_unavailable(fid, code, as_of, variant=variant,
                                    reason=f"生年化{mut}未解析到落宫"))
            continue
        tier = _palace_tier(pname)
        norm = _tier_normalized(tier) * (1 if sign > 0 else -1)
        idx = chart.mutagen_palace_index(mut)
        star = next((m.star for m in chart.natal_mutagens if m.mutagen == mut), "")
        out.append(_zobs(
            fid, code, as_of, variant=variant,
            raw_value={"palace": pname, "tier": tier, "star": star},
            normalized=norm,
            direction=Direction.POSITIVE if sign > 0 else Direction.NEGATIVE,
            rule_score=abs(norm) * 10, confidence=0.6,
            explanation=(
                f"生年化{mut}（{star}）落 {pname}（位阶 {tier}："
                f"{'核心宫' if tier == 2 else '次核心宫' if tier == 1 else '其他宫'}）。"
                "位阶体系属本研究项目的映射假设。"
            ),
            evidence=[f"化{mut}落宫 index={idx}"],
        ))

    key_hits = [
        m for m in chart.natal_mutagens if m.mutagen in ("禄", "权", "科") and m.palace_name in KEY_PALACES
    ]
    out.append(_zobs(
        "Z_MUTAGEN_005", code, as_of, variant=variant, raw_value=len(key_hits),
        normalized=min(len(key_hits) / 2, 1.0), direction=Direction.POSITIVE,
        rule_score=min(len(key_hits) / 2, 1.0) * 10, confidence=0.6,
        explanation=f"化禄/权/科 中落在『命-财-官-迁』的有 {len(key_hits)} 个"
                    f"（{'、'.join(m.mutagen + m.star for m in key_hits) or '无'}）。",
    ))
    ji = _mutagen_palace(chart, "忌")
    ji_hit = ji in KEY_PALACES
    out.append(_zobs(
        "Z_MUTAGEN_006", code, as_of, variant=variant, raw_value=ji or None,
        normalized=-1.0 if ji_hit else 0.0, direction=Direction.NEGATIVE,
        rule_score=8.0 if ji_hit else 0.0, confidence=0.6,
        explanation=f"生年化忌落 {ji or '未知'}"
                    + ("（命中关键宫）" if ji_hit else "（未落关键宫）") + "。",
    ))

    # --- Z_TRINE_* 三方四正 ---
    trine = chart.trine_of(chart.soul_palace_index)
    if len(trine) != 4:
        for fid in ("Z_TRINE_001", "Z_TRINE_002", "Z_TRINE_003", "Z_TRINE_004", "Z_TRINE_005"):
            out.append(_unavailable(fid, code, as_of, variant=variant,
                                    reason=f"三方四正解析不完整（{len(trine)}/4）"))
    else:
        tb = round(sum(_brightness_sum(p) for p in trine), 6)
        tl = sum(_lucky_count(p) for p in trine)
        tm = sum(_malefic_count(p) for p in trine)
        names = "、".join(p.name for p in trine)
        out.append(_zobs(
            "Z_TRINE_001", code, as_of, variant=variant, raw_value=tb,
            normalized=_tanh(tb / 4), direction=Direction.POSITIVE,
            rule_score=abs(_tanh(tb / 4)) * 10, confidence=0.55,
            explanation=f"命宫三方四正（{names}）主星庙旺和 {tb}。",
            evidence=[f"{p.name}: {[s.name for s in p.major_stars]}" for p in trine],
        ))
        out.append(_zobs(
            "Z_TRINE_002", code, as_of, variant=variant, raw_value=tl,
            normalized=min(tl / 6, 1.0), direction=Direction.POSITIVE,
            rule_score=min(tl / 6, 1.0) * 10, confidence=0.5,
            explanation=f"三方四正吉曜共 {tl} 颗。",
        ))
        out.append(_zobs(
            "Z_TRINE_003", code, as_of, variant=variant, raw_value=tm,
            normalized=-min(tm / 4, 1.0), direction=Direction.NEGATIVE,
            rule_score=min(tm / 4, 1.0) * 10, confidence=0.5,
            explanation=f"三方四正煞曜共 {tm} 颗。",
        ))
        out.append(_zobs(
            "Z_TRINE_004", code, as_of, variant=variant, raw_value=tl - tm,
            normalized=_tanh((tl - tm) / 3), direction=Direction.POSITIVE,
            rule_score=abs(_tanh((tl - tm) / 3)) * 10, confidence=0.5,
            explanation=f"三方四正吉煞差 = {tl} - {tm} = {tl - tm}。",
        ))
        three = [chart.palace_by_name(n) for n in ("财帛", "官禄", "迁移")]
        total = sum(len(p.major_stars) for p in three if p is not None)
        out.append(_zobs(
            "Z_TRINE_005", code, as_of, variant=variant, raw_value=total,
            normalized=min(total / 5, 1.0), direction=Direction.NEUTRAL,
            rule_score=min(total / 5, 1.0) * 5, confidence=0.7,
            explanation=f"财帛/官禄/迁移三宫主星合计 {total} 颗（不含命宫）。结构性变量。",
        ))

    # --- Z_YEAR_* 流年 ---
    out += _horoscope_block(chart, code, as_of, variant, "yearly", {
        "index": "Z_YEAR_001", "brightness": "Z_YEAR_002", "malefic": "Z_YEAR_003",
        "lu": "Z_YEAR_004", "ji": "Z_YEAR_005",
    }, label="流年")
    y = chart.horoscope.yearly if chart.horoscope else None
    if y is None:
        out.append(_unavailable("Z_YEAR_006", code, as_of, variant=variant, reason="缺少流年运限层"))
    else:
        same_soul = y.index == chart.soul_palace_index
        out.append(_zobs(
            "Z_YEAR_006", code, as_of, variant=variant, raw_value=same_soul,
            normalized=0.5 if same_soul else 0.0, direction=Direction.NEUTRAL,
            rule_score=5.0 if same_soul else 0.0, confidence=0.6,
            explanation=("流年命宫与原盘命宫同位（太岁重叠，原局结构被直接引动）"
                         if same_soul else "流年命宫与原盘命宫不同位。"),
            evidence=[f"流年命宫 index={y.index}，原盘命宫 index={chart.soul_palace_index}"],
        ))

    # --- Z_MONTH_* 流月 ---
    out += _horoscope_block(chart, code, as_of, variant, "monthly", {
        "index": "Z_MONTH_001", "brightness": "Z_MONTH_002", "malefic": "Z_MONTH_003",
        "lu": "Z_MONTH_004", "ji": "Z_MONTH_005",
    }, label="流月")

    # --- Z_DAY_* 流日 ---
    out += _horoscope_block(chart, code, as_of, variant, "daily", {
        "index": "Z_DAY_001", "brightness": "Z_DAY_002", "malefic": "Z_DAY_003",
        "lu": "Z_DAY_004", "ji": "Z_DAY_005",
    }, label="流日")

    # --- Z_DECADE_* / Z_AGE_* （随 variant 变化） ---
    for sid, bid, mid, label in (
        ("decadal", "Z_DECADE_001", "Z_DECADE_002", "大限"),
        ("age", "Z_AGE_001", "Z_AGE_002", "小限"),
    ):
        section = getattr(chart.horoscope, sid) if chart.horoscope else None
        palace = _horoscope_palace(chart, section)
        if palace is None:
            out.append(_unavailable(bid, code, as_of, variant=variant, reason=f"缺少{label}层"))
            out.append(_unavailable(mid, code, as_of, variant=variant, reason=f"缺少{label}层"))
            continue
        bsum = _brightness_sum(palace)
        mal = _malefic_count(palace) + _flow_malefic_count(section, palace.index)
        out.append(_zobs(
            bid, code, as_of, variant=variant,
            raw_value={"palace": palace.name, "index": palace.index, "brightness_sum": bsum},
            normalized=_tanh(bsum / 1.5), direction=Direction.POSITIVE,
            rule_score=abs(_tanh(bsum / 1.5)) * 10, confidence=0.5,
            explanation=(
                f"当前{label}落 {palace.name}宫（{palace.earthly_branch}），"
                f"主星 {'、'.join(s.name for s in palace.major_stars) or '空宫'}，庙旺和 {bsum}。"
                f"该因子**随 variant（顺行/逆行）变化**。"
            ),
            evidence=[f"variant={variant}", f"{label}宫 index={palace.index}"],
        ))
        out.append(_zobs(
            mid, code, as_of, variant=variant, raw_value=mal,
            normalized=-min(mal / 2, 1.0), direction=Direction.NEGATIVE,
            rule_score=min(mal / 2, 1.0) * 8, confidence=0.5,
            explanation=(f"当前{label}宫煞曜 {mal} 颗（含原局与运限流曜；"
                         f"小限层无流曜，见计算差异 D1）。该因子随 variant 变化。"),
            evidence=[f"variant={variant}"],
        ))

    # 按 factor_id 排序，保证输出确定性
    out.sort(key=lambda o: o.factor_id)
    return out


def _horoscope_block(
    chart: ZiweiChart, code: str, as_of: datetime, variant: str,
    scope: str, ids: dict[str, str], *, label: str,
) -> list[FactorObservation]:
    """流年 / 流月 / 流日 共用的运限因子块。"""
    section = getattr(chart.horoscope, scope) if chart.horoscope else None
    if section is None:
        return [
            _unavailable(fid, code, as_of, variant=variant, reason=f"缺少{label}运限层")
            for fid in ids.values()
        ]
    palace = chart.palace_at(section.index)
    if palace is None:
        return [
            _unavailable(fid, code, as_of, variant=variant,
                         reason=f"{label}命宫 index={section.index} 越界")
            for fid in ids.values()
        ]

    bsum = _brightness_sum(palace)
    mal = _malefic_count(palace) + _flow_malefic_count(section, palace.index)
    lu_star = section.mutagen[0] if len(section.mutagen) > 0 else ""
    ji_star = section.mutagen[3] if len(section.mutagen) > 3 else ""
    lu_idx = _star_palace_index(chart, lu_star)
    ji_idx = _star_palace_index(chart, ji_star)

    return [
        _zobs(
            ids["index"], code, as_of, variant=variant,
            raw_value={"index": section.index, "palace": palace.name,
                       "ganzhi": section.heavenly_stem + section.earthly_branch},
            normalized=_index_normalized(section.index), direction=Direction.NEUTRAL,
            rule_score=abs(_index_normalized(section.index)) * 5, confidence=0.8,
            explanation=(
                f"{label}命宫落原盘 {palace.name}宫（index={section.index}），"
                f"{label}干支 {section.heavenly_stem}{section.earthly_branch}。"
                "宫位编码仅作结构标记，不含吉凶。"
            ),
            evidence=[f"{label}十二宫名: {'/'.join(section.palace_names)}"],
        ),
        _zobs(
            ids["brightness"], code, as_of, variant=variant, raw_value=bsum,
            normalized=_tanh(bsum / 1.5), direction=Direction.POSITIVE,
            rule_score=abs(_tanh(bsum / 1.5)) * 10, confidence=0.5,
            explanation=(f"{label}命宫（{palace.name}）主星 "
                         f"{'、'.join(s.name for s in palace.major_stars) or '空宫'}，庙旺和 {bsum}。"),
            evidence=[f"{label}命宫 index={section.index}"],
        ),
        _zobs(
            ids["malefic"], code, as_of, variant=variant, raw_value=mal,
            normalized=-min(mal / 3, 1.0), direction=Direction.NEGATIVE,
            rule_score=min(mal / 3, 1.0) * 8, confidence=0.5,
            explanation=f"{label}命宫原局煞曜 + {label}流煞合计 {mal} 颗。",
            evidence=[f"{label}流曜: "
                      f"{'、'.join(s.name for s in _palaces_in_section(section, palace.index)) or '（该层无流曜）'}"],
        ),
        _zobs(
            ids["lu"], code, as_of, variant=variant, raw_value=lu_star or None,
            normalized=_index_normalized(lu_idx), direction=Direction.NEUTRAL,
            rule_score=abs(_index_normalized(lu_idx)) * 5, confidence=0.6,
            explanation=(f"{label}化禄为 {lu_star or '未知'}"
                         + (f"，原盘落 {chart.palace_at(lu_idx).name}宫。" if lu_idx >= 0 else "，原盘落宫未解析。")
                         + " 宫位编码仅作结构标记。"),
            evidence=[f"{label}四化(禄权科忌): {'/'.join(section.mutagen)}"],
        ),
        _zobs(
            ids["ji"], code, as_of, variant=variant, raw_value=ji_star or None,
            normalized=_index_normalized(ji_idx), direction=Direction.NEUTRAL,
            rule_score=abs(_index_normalized(ji_idx)) * 5, confidence=0.6,
            explanation=(f"{label}化忌为 {ji_star or '未知'}"
                         + (f"，原盘落 {chart.palace_at(ji_idx).name}宫。" if ji_idx >= 0 else "，原盘落宫未解析。")
                         + " 宫位编码仅作结构标记。"),
            evidence=[f"{label}四化(禄权科忌): {'/'.join(section.mutagen)}"],
        ),
    ]


__all__ = ["compute_ziwei_factors", "ziwei_rule_version"]
