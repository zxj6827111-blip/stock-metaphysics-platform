"""因子计算引擎 —— 把原始盘面确定性地转换为结构化因子。

输入：``BaziChart``（八字原局 + 时间流）+ ``HuangliSnapshot``（黄历）
输出：``FactorSet``

**计算纪律**

* 只读取 ``as_of`` 及之前的信息；未来数据一律不得进入因子。
* 所有方向 / 分数都是「传统规则强度」，不是收益预测。
* 计算不出来的因子返回 ``availability=unavailable`` 并带 warning，禁止猜数。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from src.core.config import settings
from src.core.constants import (
    BRANCH_CLASH_OF,
    BRANCH_HARMONY_OF,
    BRANCH_HARM_OF,
    DAY_TIAN_SHEN_LUCK,
    STEM_WUXING,
    WU_XING_ORDER,
    WUXING_GENERATED_BY,
    WUXING_GENERATES,
    WUXING_OVERCOME_BY,
    WUXING_OVERCOMES,
    twelve_stage,
)
from src.core.schemas.bazi import BaziChart, TemporalPillar, YongShenAnalysis
from src.core.schemas.calendar import HuangliDay, HuangliSnapshot
from src.core.schemas.common import Direction, EngineId
from src.core.schemas.factor import FactorCategory, FactorObservation, FactorSet
from src.factors.registry.definitions import DEFINITION_INDEX, FACTOR_DISCLAIMER

# 建除十二值的传统吉凶倾向（通书口径；仅作分类特征）
DUTY_OFFICER_TENDENCY: dict[str, int] = {
    "建": 0, "除": 1, "满": 0, "平": -1, "定": 1, "执": 1,
    "破": -1, "危": 1, "成": 1, "收": 0, "开": 1, "闭": -1,
}

# 十二长生 → 方向倾向
STAGE_TENDENCY: dict[str, int] = {
    "长生": 1, "沐浴": 0, "冠带": 1, "临官": 1, "帝旺": 1, "衰": -1,
    "病": -1, "死": -1, "墓": 0, "绝": -1, "胎": 0, "养": 0,
}

WUXING_CODE: dict[str, int] = {"木": 1, "火": 2, "土": 3, "金": 4, "水": 5}
PATTERN_CODE: dict[str, int] = {
    "财格": 1, "官格": 2, "印格": 3, "食伤格": 4, "比劫格": 5,
}
TEN_GOD_CODE: dict[str, int] = {
    "比肩": 0, "劫财": 1, "食神": 2, "伤官": 3, "偏财": 4,
    "正财": 5, "七杀": 6, "正官": 7, "偏印": 8, "正印": 9,
}

# 五行生克链（避免在业务逻辑里重复推导）
WUXING_CHAIN: dict[str, dict[str, str]] = {
    wx: {
        "self": wx,
        "resource": WUXING_GENERATED_BY[wx],
        "output": WUXING_GENERATES[wx],
        "wealth": WUXING_OVERCOMES[wx],
        "officer": WUXING_OVERCOME_BY[wx],
    }
    for wx in WU_XING_ORDER
}


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


def classify_wuxing(wx: str, yong: YongShenAnalysis) -> tuple[str, float, Direction]:
    """把五行分类为 用神/喜神/忌神/仇神/闲神，并给出 (归一化值, 方向)。

    归一化取值：用神 +1.0 / 喜神 +0.6 / 闲神 0.0 / 忌神 −1.0 / 仇神 −0.8。
    **这是传统规则的强弱映射，不是收益预期。**
    """
    if wx in yong.yong_shen:
        return "用神", 1.0, Direction.POSITIVE
    if wx in yong.xi_shen:
        return "喜神", 0.6, Direction.POSITIVE
    if wx in yong.ji_shen:
        return "忌神", -1.0, Direction.NEGATIVE
    if wx in yong.chou_shen:
        return "仇神", -0.8, Direction.NEGATIVE
    return "闲神", 0.0, Direction.NEUTRAL


def _obs(
    factor_id: str,
    stock_code: str,
    as_of: datetime,
    *,
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
    definition = DEFINITION_INDEX[factor_id]
    return FactorObservation(
        factor_id=factor_id,
        stock_code=stock_code,
        as_of=as_of,
        trade_date=trade_date,
        engine=definition.engine,
        category=definition.category,
        name=definition.name,
        raw_value=raw_value,  # type: ignore[arg-type]
        normalized_value=None if normalized is None else round(float(normalized), 6),
        direction=direction,
        rule_score=round(float(rule_score), 3),
        confidence=round(float(confidence), 4),
        availability=availability,
        rule_version=definition.rule_version,
        engine_version=settings.bazi_engine_version,
        config_version=settings.config_version,
        evidence=evidence or [],
        explanation=explanation,
        warnings=warnings or [],
    )


def _unavailable(factor_id: str, stock_code: str, as_of: datetime, reason: str) -> FactorObservation:
    return _obs(
        factor_id, stock_code, as_of,
        raw_value=None, normalized=None, direction=Direction.NEUTRAL,
        rule_score=0.0, confidence=0.0,
        explanation=f"该因子当前不可计算：{reason}（按契约返回 unavailable，不猜测数值）",
        availability="unavailable", warnings=[reason],
    )


def _strength_to_normalized(level: str) -> tuple[float, Direction]:
    mapping = {
        "身强": (1.0, Direction.POSITIVE),
        "偏强": (0.5, Direction.POSITIVE),
        "中和": (0.0, Direction.NEUTRAL),
        "偏弱": (-0.5, Direction.NEGATIVE),
        "身弱": (-1.0, Direction.NEGATIVE),
    }
    return mapping.get(level, (0.0, Direction.NEUTRAL))


# ---------------------------------------------------------------------------
# B_NATAL_*
# ---------------------------------------------------------------------------


def compute_natal_factors(chart: BaziChart, as_of: datetime) -> list[FactorObservation]:
    code = chart.stock_code or ""
    yong = chart.yong_shen
    out: list[FactorObservation] = []
    chain = WUXING_CHAIN[chart.day_master_wuxing]

    # 001 日主强弱
    norm, direction = _strength_to_normalized(chart.day_master_analysis.strength_level)
    out.append(_obs(
        "B_NATAL_001", code, as_of,
        raw_value=chart.day_master_analysis.strength_level,
        normalized=norm, direction=direction,
        rule_score=abs(norm) * 10,
        confidence=chart.day_master_analysis.confidence,
        explanation=(
            f"日主{chart.day_master}（{chart.day_master_wuxing}），"
            f"得令={chart.day_master_analysis.de_ling}、得地={chart.day_master_analysis.de_di}、"
            f"得势={chart.day_master_analysis.de_shi}，帮扶占比 {chart.day_master_analysis.balance_ratio}，"
            f"判定为「{chart.day_master_analysis.strength_level}」。"
        ),
        evidence=[f"月令 {chart.day_master_analysis.month_season}"],
    ))

    counts = chart.ten_god_counts

    def _count_factor(fid: str, gods: tuple[str, ...], label: str, note: str) -> None:
        n = sum(counts.get(g, 0) for g in gods)
        raw = "、".join(f"{g}×{counts.get(g, 0)}" for g in gods if counts.get(g, 0)) or "无"
        out.append(_obs(
            fid, code, as_of, raw_value=n,
            normalized=min(n / 4.0, 1.0),
            direction=Direction.NEUTRAL,   # 数量本身不预设方向
            rule_score=min(n / 4.0, 1.0) * 10,
            confidence=0.9,
            explanation=f"{label}共 {n} 个（含藏干）：{raw}。{note}",
            evidence=[f"十神统计：{raw}"],
        ))

    _count_factor("B_NATAL_002", ("正财", "偏财"), "财星", "数量多寡本身不代表股价方向，需历史检验。")
    _count_factor("B_NATAL_005", ("食神", "伤官"), "食伤", "传统视食伤为生财之源，仅为结构变量。")
    _count_factor("B_NATAL_006", ("正官", "七杀"), "官杀", "传统视官杀为约束与规制。")
    _count_factor("B_NATAL_007", ("正印", "偏印"), "印星", "传统视印星为资源与庇护。")
    _count_factor("B_NATAL_008", ("比肩", "劫财"), "比劫", "传统视比劫为竞争与分夺。")

    # 003 财星透干
    wealth_visible = [g for g in chart.visible_ten_gods if g in ("正财", "偏财")]
    out.append(_obs(
        "B_NATAL_003", code, as_of,
        raw_value=bool(wealth_visible),
        normalized=1.0 if wealth_visible else 0.0,
        direction=Direction.NEUTRAL,
        rule_score=10.0 if wealth_visible else 0.0,
        confidence=0.9,
        explanation=(
            f"财星{'透干：' + '、'.join(wealth_visible) if wealth_visible else '未透干'}。"
            "传统认为透干者显，但显不等于股价上涨。"
        ),
    ))

    # 004 财星得令
    wealth_in_month = chain["wealth"] == chart.month_pillar.ganzhi.branch_wuxing
    out.append(_obs(
        "B_NATAL_004", code, as_of,
        raw_value=wealth_in_month,
        normalized=1.0 if wealth_in_month else 0.0,
        direction=Direction.NEUTRAL,
        rule_score=10.0 if wealth_in_month else 0.0,
        confidence=0.85,
        explanation=(
            f"月支 {chart.month_pillar.ganzhi.branch}（{chart.month_pillar.ganzhi.branch_wuxing}）"
            f"{'即' if wealth_in_month else '不是'}日主所克之财星五行（{chain['wealth']}）。"
        ),
    ))

    # 009 格局类型
    if chart.pattern.availability == "ok" and chart.pattern.primary:
        cat_code = PATTERN_CODE.get(chart.pattern.category, 0)
        out.append(_obs(
            "B_NATAL_009", code, as_of,
            raw_value=chart.pattern.primary,
            normalized=cat_code / 5.0,
            direction=Direction.NEUTRAL,
            rule_score=chart.pattern.confidence * 10,
            confidence=chart.pattern.confidence,
            explanation=(
                f"格局「{chart.pattern.primary}」（{chart.pattern.category}），"
                f"取法：{chart.pattern.method}，置信度 {chart.pattern.confidence}。"
                "格局不同流派存在分歧，仅作分类特征。"
            ),
            evidence=[c.basis for c in chart.pattern.candidates[:3]],
        ))
    else:
        out.append(_unavailable("B_NATAL_009", code, as_of, "格局判定不可用"))

    # 010 用神五行
    if yong.yong_shen:
        wx = yong.yong_shen[0]
        out.append(_obs(
            "B_NATAL_010", code, as_of, raw_value=wx,
            normalized=WUXING_CODE.get(wx, 0) / 5.0,
            direction=Direction.NEUTRAL,
            rule_score=yong.confidence * 10,
            confidence=yong.confidence,
            explanation=f"扶抑法取用神五行「{wx}」。方法：{yong.method}；置信度 {yong.confidence}。",
            evidence=yong.rationale[:2],
        ))
    else:
        out.append(_unavailable("B_NATAL_010", code, as_of, "用神未能确定"))

    # 011 五行缺失
    n_missing = len(chart.wuxing.missing)
    out.append(_obs(
        "B_NATAL_011", code, as_of, raw_value=n_missing,
        normalized=min(n_missing / 3.0, 1.0),
        direction=Direction.NEUTRAL,
        rule_score=min(n_missing / 3.0, 1.0) * 10,
        confidence=0.95,
        explanation=(
            f"四柱未出现的五行：{'、'.join(chart.wuxing.missing) if chart.wuxing.missing else '无'}。"
            "传统认为五行偏枯需补，但不构成价格判断。"
        ),
    ))

    # 012 五行偏枯度
    pcts = list(chart.wuxing.percentages.values())
    spread = (max(pcts) - min(pcts)) if pcts else 0.0
    out.append(_obs(
        "B_NATAL_012", code, as_of, raw_value=round(spread, 2),
        normalized=min(spread / 60.0, 1.0),
        direction=Direction.NEUTRAL,
        rule_score=min(spread / 60.0, 1.0) * 10,
        confidence=0.9,
        explanation=f"五行百分比极差 {round(spread, 2)} 个百分点（最高 {chart.wuxing.dominant}，最低 {chart.wuxing.weakest}）。",
    ))

    # 013 原局合冲强度
    harmony_types = {"六合", "三合", "三会", "半合", "天干五合"}
    clash_types = {"六冲", "相刑", "相害", "天干相冲"}
    n_h = sum(1 for r in chart.relations if r.relation_type in harmony_types)
    n_c = sum(1 for r in chart.relations if r.relation_type in clash_types)
    net = n_h - n_c
    out.append(_obs(
        "B_NATAL_013", code, as_of,
        raw_value={"harmony": n_h, "clash": n_c, "net": net},
        normalized=_tanh(net / 3.0),
        direction=Direction.POSITIVE if net > 0 else (Direction.NEGATIVE if net < 0 else Direction.NEUTRAL),
        rule_score=min(abs(net) / 3.0, 1.0) * 10,
        confidence=0.85,
        explanation=(
            f"原局合类结构 {n_h} 个、冲类结构 {n_c} 个，净值 {net}。"
            "传统认为合主稳定、冲主变动；本项目只作结构变量。"
        ),
        evidence=[f"{r.relation_type}：{'/'.join(r.positions)}" for r in chart.relations[:5]],
    ))

    # 014 / 015 财星 / 食伤 力量占比
    wealth_pct = chart.wuxing.percentages.get(chain["wealth"], 0.0)
    out.append(_obs(
        "B_NATAL_014", code, as_of, raw_value=wealth_pct,
        normalized=wealth_pct / 100.0,
        direction=Direction.NEUTRAL,
        rule_score=min(wealth_pct / 40.0, 1.0) * 10,
        confidence=0.85,
        explanation=f"财星五行「{chain['wealth']}」在五行力量估算中占 {wealth_pct}%。",
    ))
    output_pct = chart.wuxing.percentages.get(chain["output"], 0.0)
    out.append(_obs(
        "B_NATAL_015", code, as_of, raw_value=output_pct,
        normalized=output_pct / 100.0,
        direction=Direction.NEUTRAL,
        rule_score=min(output_pct / 40.0, 1.0) * 10,
        confidence=0.85,
        explanation=f"食伤五行「{chain['output']}」在五行力量估算中占 {output_pct}%。",
    ))

    # 016 身财对比
    wealth_score = chart.wuxing.scores.get(chain["wealth"], 0.0)
    support = chart.day_master_analysis.support_score
    ratio = (support / wealth_score) if wealth_score > 1e-9 else float("inf")
    norm16 = _tanh(_safe_log(ratio))
    out.append(_obs(
        "B_NATAL_016", code, as_of,
        raw_value=round(ratio, 4) if ratio != float("inf") else "inf",
        normalized=norm16,
        direction=Direction.POSITIVE if norm16 > 0.05 else (Direction.NEGATIVE if norm16 < -0.05 else Direction.NEUTRAL),
        rule_score=min(abs(norm16), 1.0) * 10,
        confidence=0.7,
        explanation=(
            f"帮扶力量 {round(support, 3)} 与财星力量 {round(wealth_score, 3)} 的比值 "
            f"{'∞（原局无财）' if ratio == float('inf') else round(ratio, 3)}。"
            "仅描述『身』与『财』的相对强弱，不代表价格方向。"
        ),
    ))

    # 017 调候适宜度
    tiaohou_score, tiaohou_expl = _tiaohou_score(chart, yong)
    out.append(_obs(
        "B_NATAL_017", code, as_of, raw_value=tiaohou_score,
        normalized=tiaohou_score / 3.0,
        direction=Direction.POSITIVE if tiaohou_score >= 2 else (Direction.NEGATIVE if tiaohou_score == 0 else Direction.NEUTRAL),
        rule_score=tiaohou_score / 3.0 * 10,
        confidence=0.6,
        explanation=tiaohou_expl,
    ))

    # 018 日主阴阳
    out.append(_obs(
        "B_NATAL_018", code, as_of,
        raw_value="阳干" if chart.day_master_analysis.day_master_yang else "阴干",
        normalized=1.0 if chart.day_master_analysis.day_master_yang else -1.0,
        direction=Direction.NEUTRAL,
        rule_score=5.0,
        confidence=1.0,
        explanation=f"日主{chart.day_master}属{'阳' if chart.day_master_analysis.day_master_yang else '阴'}干，仅作分类特征。",
    ))

    return out


_TIAOHOU_REQUIRED: dict[str, str] = {
    "亥": "火", "子": "火", "丑": "火",
    "巳": "水", "午": "水", "未": "水",
    "辰": "木", "戌": "木",
}


def _tiaohou_score(chart: BaziChart, yong: YongShenAnalysis) -> tuple[int, str]:
    """0-3 分：调候需求是否被满足。"""
    month_branch = chart.month_pillar.ganzhi.branch
    required = _TIAOHOU_REQUIRED.get(month_branch)
    if required is None:
        return 2, "月令寒暖适中（申酉寅卯月），调候需求较低，记中位分 2。"

    favor = set(yong.yong_shen) | set(yong.xi_shen)
    present_in_chart = required in chart.wuxing.percentages and chart.wuxing.percentages[required] > 5

    if required in favor and present_in_chart:
        return 3, f"月令 {month_branch} 需「{required}」调候，且「{required}」已在喜用神中并被原局承载。"
    if required in favor:
        return 2, f"月令 {month_branch} 需「{required}」调候，喜用神已含「{required}」但原局承载偏弱。"
    if present_in_chart:
        return 1, f"月令 {month_branch} 需「{required}」调候，原局有「{required}」但未列为喜用神。"
    return 0, f"月令 {month_branch} 需「{required}」调候，原局与喜用神均未覆盖。"


# ---------------------------------------------------------------------------
# B_YEAR_* / B_MONTH_* / B_DAY_*
# ---------------------------------------------------------------------------


def _temporal_factors(
    chart: BaziChart,
    tp: TemporalPillar,
    prefix: str,
    out: list[FactorObservation],
    as_of: datetime,
) -> None:
    code = chart.stock_code or ""
    yong = chart.yong_shen

    st_label, st_norm, st_dir = classify_wuxing(tp.ganzhi.stem_wuxing, yong)
    br_label, br_norm, br_dir = classify_wuxing(tp.ganzhi.branch_wuxing, yong)

    gods = {tp.stem_ten_god, *tp.branch_ten_gods}
    is_wealth = bool(gods & {"正财", "偏财"})
    is_output = bool(gods & {"食神", "伤官"})
    is_officer = bool(gods & {"正官", "七杀"})

    if prefix == "B_YEAR":
        out.append(_obs("B_YEAR_001", code, as_of, raw_value=st_label, normalized=st_norm,
                        direction=st_dir, rule_score=abs(st_norm) * 10, confidence=0.75,
                        explanation=f"流年天干 {tp.ganzhi.stem}（{tp.ganzhi.stem_wuxing}）为「{st_label}」。"))
        out.append(_obs("B_YEAR_002", code, as_of, raw_value=br_label, normalized=br_norm,
                        direction=br_dir, rule_score=abs(br_norm) * 10, confidence=0.75,
                        explanation=f"流年地支 {tp.ganzhi.branch}（{tp.ganzhi.branch_wuxing}）为「{br_label}」。"))
        out.append(_obs("B_YEAR_003", code, as_of, raw_value=is_wealth,
                        normalized=1.0 if is_wealth else 0.0, direction=Direction.NEUTRAL,
                        rule_score=10.0 if is_wealth else 0.0, confidence=0.8,
                        explanation=(
                            f"流年 {tp.ganzhi.text} 所引动十神：{'、'.join(sorted(gods))}；"
                            f"{'含财星。' if is_wealth else '不含财星。'}"
                            "注意：财星被引动 ≠ 股票上涨。"
                        )))
        out.append(_obs("B_YEAR_004", code, as_of, raw_value=is_output,
                        normalized=1.0 if is_output else 0.0, direction=Direction.NEUTRAL,
                        rule_score=10.0 if is_output else 0.0, confidence=0.8,
                        explanation=f"流年{'引动' if is_output else '未引动'}食伤。"))
        _rel_factors(out, tp, code, as_of, "B_YEAR_005", "B_YEAR_006", "B_YEAR_007", "B_YEAR_008", "流年")
        stage = tp.di_shi
        out.append(_obs("B_YEAR_009", code, as_of, raw_value=stage,
                        normalized=_stage_norm(stage), direction=_stage_dir(stage),
                        rule_score=abs(_stage_norm(stage)) * 10, confidence=0.65,
                        explanation=f"日主在流年地支 {tp.ganzhi.branch} 处于「{stage}」。"))
        out.append(_obs("B_YEAR_010", code, as_of, raw_value=tp.triple_harmonies,
                        normalized=1.0 if tp.triple_harmonies else 0.0,
                        direction=Direction.NEUTRAL,
                        rule_score=10.0 if tp.triple_harmonies else 0.0, confidence=0.7,
                        explanation=(
                            f"流年{'形成' + '、'.join(tp.triple_harmonies) if tp.triple_harmonies else '未形成三合局'}。"
                            "注意：三合 ≠ 股票上涨。"
                        )))

    elif prefix == "B_MONTH":
        out.append(_obs("B_MONTH_001", code, as_of, raw_value=st_label, normalized=st_norm,
                        direction=st_dir, rule_score=abs(st_norm) * 10, confidence=0.72,
                        explanation=f"流月天干 {tp.ganzhi.stem}（{tp.ganzhi.stem_wuxing}）为「{st_label}」。"))
        out.append(_obs("B_MONTH_002", code, as_of, raw_value=br_label, normalized=br_norm,
                        direction=br_dir, rule_score=abs(br_norm) * 10, confidence=0.72,
                        explanation=f"流月地支 {tp.ganzhi.branch}（{tp.ganzhi.branch_wuxing}）为「{br_label}」。"))

        wealth_triggered = is_wealth or st_label in ("用神", "喜神") or br_label in ("用神", "喜神")
        out.append(_obs("B_MONTH_003", code, as_of, raw_value=wealth_triggered,
                        normalized=1.0 if wealth_triggered else 0.0,
                        direction=Direction.NEUTRAL,
                        rule_score=10.0 if wealth_triggered else 0.0, confidence=0.65,
                        explanation=(
                            f"流月 {tp.ganzhi.text}：十神 {'、'.join(sorted(gods))}；"
                            f"天干{st_label}、地支{br_label}。"
                            f"{'财星/喜用被引动。' if wealth_triggered else '未引动财星。'}"
                            "传统称之为『财星引动』，但不构成上涨结论。"
                        )))

        has_wealth_in_natal = sum(chart.ten_god_counts.get(g, 0) for g in ("正财", "偏财")) > 0
        sd_sc = is_output and has_wealth_in_natal
        out.append(_obs("B_MONTH_004", code, as_of, raw_value=sd_sc,
                        normalized=1.0 if sd_sc else 0.0, direction=Direction.NEUTRAL,
                        rule_score=10.0 if sd_sc else 0.0, confidence=0.6,
                        explanation=(
                            f"{'流月引动食伤且原局有财星 → 命中传统「食伤生财」结构。' if sd_sc else '未同时满足食伤引动与原局有财。'}"
                            "**该结构不代表股价一定上涨**，必须经历史统计检验。"
                        )))
        out.append(_obs("B_MONTH_005", code, as_of, raw_value=is_officer,
                        normalized=1.0 if is_officer else 0.0, direction=Direction.NEUTRAL,
                        rule_score=10.0 if is_officer else 0.0, confidence=0.7,
                        explanation=f"流月{'引动' if is_officer else '未引动'}官杀。"))

        _rel_factors(out, tp, code, as_of, "B_MONTH_006", "B_MONTH_007", "B_MONTH_008",
                     "B_MONTH_009", "流月", extra_harm_id="B_MONTH_010")
        out.append(_obs("B_MONTH_011", code, as_of, raw_value=tp.stem_ten_god,
                        normalized=TEN_GOD_CODE.get(tp.stem_ten_god, 0) / 9.0,
                        direction=Direction.NEUTRAL, rule_score=5.0, confidence=0.9,
                        explanation=f"流月天干 {tp.ganzhi.stem} 相对日主为「{tp.stem_ten_god}」。"))
        stage = tp.di_shi
        out.append(_obs("B_MONTH_012", code, as_of, raw_value=stage,
                        normalized=_stage_norm(stage), direction=_stage_dir(stage),
                        rule_score=abs(_stage_norm(stage)) * 10, confidence=0.62,
                        explanation=f"日主在流月地支 {tp.ganzhi.branch} 处于「{stage}」。"))

    elif prefix == "B_DAY":
        out.append(_obs("B_DAY_001", code, as_of, raw_value=st_label, normalized=st_norm,
                        direction=st_dir, rule_score=abs(st_norm) * 10, confidence=0.7,
                        explanation=f"流日天干 {tp.ganzhi.stem}（{tp.ganzhi.stem_wuxing}）为「{st_label}」。"))
        out.append(_obs("B_DAY_002", code, as_of, raw_value=len(tp.clashes_with_natal),
                        normalized=min(len(tp.clashes_with_natal) / 2.0, 1.0),
                        direction=Direction.NEGATIVE if tp.clashes_with_natal else Direction.NEUTRAL,
                        rule_score=min(len(tp.clashes_with_natal) / 2.0, 1.0) * 10, confidence=0.68,
                        explanation=f"流日 {tp.ganzhi.text} 冲原局位置：{'、'.join(tp.clashes_with_natal) or '无'}。"))
        out.append(_obs("B_DAY_003", code, as_of, raw_value=len(tp.harmonies_with_natal),
                        normalized=min(len(tp.harmonies_with_natal) / 2.0, 1.0),
                        direction=Direction.POSITIVE if tp.harmonies_with_natal else Direction.NEUTRAL,
                        rule_score=min(len(tp.harmonies_with_natal) / 2.0, 1.0) * 10, confidence=0.68,
                        explanation=f"流日 {tp.ganzhi.text} 与原局六合位置：{'、'.join(tp.harmonies_with_natal) or '无'}。"))
        out.append(_obs("B_DAY_004", code, as_of, raw_value=br_label, normalized=br_norm,
                        direction=br_dir, rule_score=abs(br_norm) * 10, confidence=0.7,
                        explanation=f"流日地支 {tp.ganzhi.branch}（{tp.ganzhi.branch_wuxing}）为「{br_label}」。"))
        out.append(_obs("B_DAY_005", code, as_of, raw_value=tp.stem_ten_god,
                        normalized=TEN_GOD_CODE.get(tp.stem_ten_god, 0) / 9.0,
                        direction=Direction.NEUTRAL, rule_score=5.0, confidence=0.9,
                        explanation=f"流日天干 {tp.ganzhi.stem} 相对日主为「{tp.stem_ten_god}」。"))
        stage = tp.di_shi
        out.append(_obs("B_DAY_006", code, as_of, raw_value=stage,
                        normalized=_stage_norm(stage), direction=_stage_dir(stage),
                        rule_score=abs(_stage_norm(stage)) * 10, confidence=0.6,
                        explanation=f"日主在流日地支 {tp.ganzhi.branch} 处于「{stage}」。"))
        out.append(_obs("B_DAY_007", code, as_of, raw_value=len(tp.punishments_with_natal),
                        normalized=min(len(tp.punishments_with_natal) / 2.0, 1.0),
                        direction=Direction.NEGATIVE if tp.punishments_with_natal else Direction.NEUTRAL,
                        rule_score=min(len(tp.punishments_with_natal) / 2.0, 1.0) * 10, confidence=0.62,
                        explanation=f"流日 {tp.ganzhi.text} 与原局相刑位置：{'、'.join(tp.punishments_with_natal) or '无'}。"))
        out.append(_obs("B_DAY_008", code, as_of, raw_value=len(tp.harms_with_natal),
                        normalized=min(len(tp.harms_with_natal) / 2.0, 1.0),
                        direction=Direction.NEGATIVE if tp.harms_with_natal else Direction.NEUTRAL,
                        rule_score=min(len(tp.harms_with_natal) / 2.0, 1.0) * 10, confidence=0.6,
                        explanation=f"流日 {tp.ganzhi.text} 与原局相害位置：{'、'.join(tp.harms_with_natal) or '无'}。"))


def _rel_factors(
    out: list[FactorObservation],
    tp: TemporalPillar,
    code: str,
    as_of: datetime,
    triple_id: str,
    harmony_id: str,
    clash_id: str,
    punish_id: str,
    scope: str,
    extra_harm_id: str | None = None,
) -> None:
    """统一生成 三合 / 六合 / 冲 / 刑 ( / 害 ) 四个关系因子。"""
    out.append(_obs(triple_id, code, as_of, raw_value=tp.triple_harmonies,
                    normalized=1.0 if tp.triple_harmonies else 0.0,
                    direction=Direction.NEUTRAL,
                    rule_score=10.0 if tp.triple_harmonies else 0.0, confidence=0.7,
                    explanation=(
                        f"{scope}{'形成' + '、'.join(tp.triple_harmonies) if tp.triple_harmonies else '未形成三合局'}。"
                        "注意：三合 ≠ 股票上涨。"
                    )))
    out.append(_obs(harmony_id, code, as_of, raw_value=len(tp.harmonies_with_natal),
                    normalized=min(len(tp.harmonies_with_natal) / 2.0, 1.0),
                    direction=Direction.POSITIVE if tp.harmonies_with_natal else Direction.NEUTRAL,
                    rule_score=min(len(tp.harmonies_with_natal) / 2.0, 1.0) * 10, confidence=0.7,
                    explanation=f"{scope}六合原局位置：{'、'.join(tp.harmonies_with_natal) or '无'}。"))
    out.append(_obs(clash_id, code, as_of, raw_value=len(tp.clashes_with_natal),
                    normalized=min(len(tp.clashes_with_natal) / 2.0, 1.0),
                    direction=Direction.NEGATIVE if tp.clashes_with_natal else Direction.NEUTRAL,
                    rule_score=min(len(tp.clashes_with_natal) / 2.0, 1.0) * 10, confidence=0.7,
                    explanation=f"{scope}冲原局位置：{'、'.join(tp.clashes_with_natal) or '无'}。"))
    out.append(_obs(punish_id, code, as_of, raw_value=len(tp.punishments_with_natal),
                    normalized=min(len(tp.punishments_with_natal) / 2.0, 1.0),
                    direction=Direction.NEGATIVE if tp.punishments_with_natal else Direction.NEUTRAL,
                    rule_score=min(len(tp.punishments_with_natal) / 2.0, 1.0) * 10, confidence=0.65,
                    explanation=f"{scope}刑原局位置：{'、'.join(tp.punishments_with_natal) or '无'}。"))
    if extra_harm_id:
        out.append(_obs(extra_harm_id, code, as_of, raw_value=len(tp.harms_with_natal),
                        normalized=min(len(tp.harms_with_natal) / 2.0, 1.0),
                        direction=Direction.NEGATIVE if tp.harms_with_natal else Direction.NEUTRAL,
                        rule_score=min(len(tp.harms_with_natal) / 2.0, 1.0) * 10, confidence=0.65,
                        explanation=f"{scope}害原局位置：{'、'.join(tp.harms_with_natal) or '无'}。"))


def _stage_norm(stage: str) -> float:
    return STAGE_TENDENCY.get(stage, 0) * 1.0


def _stage_dir(stage: str) -> Direction:
    t = STAGE_TENDENCY.get(stage, 0)
    return Direction.POSITIVE if t > 0 else (Direction.NEGATIVE if t < 0 else Direction.NEUTRAL)


def compute_bazi_factors(chart: BaziChart, as_of: datetime) -> list[FactorObservation]:
    """全部 B_* 因子。"""
    out: list[FactorObservation] = []
    out.extend(compute_natal_factors(chart, as_of))
    if chart.current_year_pillar:
        _temporal_factors(chart, chart.current_year_pillar, "B_YEAR", out, as_of)
    if chart.current_month_pillar:
        _temporal_factors(chart, chart.current_month_pillar, "B_MONTH", out, as_of)
    if chart.current_day_pillar:
        _temporal_factors(chart, chart.current_day_pillar, "B_DAY", out, as_of)
    return out


# ---------------------------------------------------------------------------
# H_DAY_* 黄历 × 原局
# ---------------------------------------------------------------------------


def compute_huangli_factors(
    chart: BaziChart,
    huangli: HuangliSnapshot,
    as_of: datetime,
) -> list[FactorObservation]:
    """全部 H_DAY_*（日）+ H_MONTH_*（月）因子。"""
    code = chart.stock_code or ""
    yong = chart.yong_shen
    day: HuangliDay = huangli.primary
    out: list[FactorObservation] = []

    day_stem_wx = STEM_WUXING.get(day.day_ganzhi[:1], "")
    day_branch_wx = STEM_WUXING.get("甲") if False else _branch_wuxing(day.day_ganzhi[1:2])
    st_label, st_norm, st_dir = classify_wuxing(day_stem_wx, yong)
    br_label, br_norm, br_dir = classify_wuxing(day_branch_wx, yong)

    out.append(_obs("H_DAY_001", code, as_of, raw_value=st_label, normalized=st_norm,
                    direction=st_dir, rule_score=abs(st_norm) * 10, confidence=0.7,
                    explanation=f"当日日干 {day.day_ganzhi[:1]}（{day_stem_wx}）为「{st_label}」。"))
    out.append(_obs("H_DAY_002", code, as_of, raw_value=br_label, normalized=br_norm,
                    direction=br_dir, rule_score=abs(br_norm) * 10, confidence=0.7,
                    explanation=f"当日日支 {day.day_ganzhi[1:2]}（{day_branch_wx}）为「{br_label}」。"))

    natal_day_branch = chart.day_pillar.ganzhi.branch
    day_branch = day.day_ganzhi[1:2]

    is_clash = BRANCH_CLASH_OF.get(natal_day_branch) == day_branch
    out.append(_obs("H_DAY_003", code, as_of, raw_value=is_clash,
                    normalized=-1.0 if is_clash else 0.0,
                    direction=Direction.NEGATIVE if is_clash else Direction.NEUTRAL,
                    rule_score=10.0 if is_clash else 0.0, confidence=0.72,
                    explanation=(
                        f"当日日支 {day_branch} {'冲' if is_clash else '不冲'}股票日支 {natal_day_branch}。"
                    )))
    is_harmony = BRANCH_HARMONY_OF.get(natal_day_branch) == day_branch
    out.append(_obs("H_DAY_004", code, as_of, raw_value=is_harmony,
                    normalized=1.0 if is_harmony else 0.0,
                    direction=Direction.POSITIVE if is_harmony else Direction.NEUTRAL,
                    rule_score=10.0 if is_harmony else 0.0, confidence=0.72,
                    explanation=(
                        f"当日日支 {day_branch} {'与原局日支' + natal_day_branch + '六合' if is_harmony else '与原局日支无六合'}。"
                    )))

    natal_branches = {
        "year": chart.year_pillar.ganzhi.branch,
        "month": chart.month_pillar.ganzhi.branch,
        "day": chart.day_pillar.ganzhi.branch,
        "hour": chart.hour_pillar.ganzhi.branch,
    }
    n_harmony = sum(1 for b in natal_branches.values() if BRANCH_HARMONY_OF.get(b) == day_branch)
    n_clash = sum(1 for b in natal_branches.values() if BRANCH_CLASH_OF.get(b) == day_branch)
    net = n_harmony - n_clash
    out.append(_obs("H_DAY_005", code, as_of,
                    raw_value={"harmony": n_harmony, "clash": n_clash, "net": net},
                    normalized=_tanh(net / 3.0),
                    direction=Direction.POSITIVE if net > 0 else (Direction.NEGATIVE if net < 0 else Direction.NEUTRAL),
                    rule_score=min(abs(net) / 3.0, 1.0) * 10, confidence=0.68,
                    explanation=f"当日与原局：合 {n_harmony} 处、冲 {n_clash} 处，净值 {net}。"))

    duty = day.duty_officer
    duty_t = DUTY_OFFICER_TENDENCY.get(duty, 0)
    out.append(_obs("H_DAY_006", code, as_of, raw_value=duty,
                    normalized=duty_t * 1.0,
                    direction=Direction.POSITIVE if duty_t > 0 else (Direction.NEGATIVE if duty_t < 0 else Direction.NEUTRAL),
                    rule_score=abs(duty_t) * 7.0, confidence=0.5,
                    explanation=(
                        f"建除十二值为「{duty}」，按通书吉凶倾向记为 {duty_t}。"
                        "该倾向来自传统黄历分类，与股票收益无实证关系。"
                    )))

    tian_shen_type = day.day_tian_shen_type or DAY_TIAN_SHEN_LUCK.get(day.day_tian_shen, "")
    ts_norm = 1.0 if tian_shen_type == "黄道" else (-1.0 if tian_shen_type == "黑道" else 0.0)
    out.append(_obs("H_DAY_007", code, as_of, raw_value=tian_shen_type,
                    normalized=ts_norm,
                    direction=Direction.POSITIVE if ts_norm > 0 else (Direction.NEGATIVE if ts_norm < 0 else Direction.NEUTRAL),
                    rule_score=abs(ts_norm) * 8.0, confidence=0.55,
                    explanation=f"当日十二神「{day.day_tian_shen}」属「{tian_shen_type}」。"))
    out.append(_obs("H_DAY_008", code, as_of, raw_value=day.day_tian_shen,
                    normalized=ts_norm, direction=Direction.NEUTRAL,
                    rule_score=abs(ts_norm) * 8.0, confidence=0.55,
                    explanation=f"当日十二神为「{day.day_tian_shen}」，保留原始类别供研究。"))

    n_punish = sum(1 for b in natal_branches.values() if _is_punishment(b, day_branch))
    n_harm = sum(1 for b in natal_branches.values() if BRANCH_HARM_OF.get(b) == day_branch)
    total = n_harmony + n_clash + n_punish + n_harm
    out.append(_obs("H_DAY_009", code, as_of, raw_value=total,
                    normalized=min(total / 4.0, 1.0), direction=Direction.NEUTRAL,
                    rule_score=min(total / 4.0, 1.0) * 10, confidence=0.7,
                    explanation=f"当日与原局四支的刑冲合害互动共 {total} 次（合{n_harmony}/冲{n_clash}/刑{n_punish}/害{n_harm}）。"))

    nayin_wx = _nayin_wuxing(day.day_nayin)
    ny_label, ny_norm, ny_dir = classify_wuxing(nayin_wx, yong) if nayin_wx else ("未知", 0.0, Direction.NEUTRAL)
    out.append(_obs("H_DAY_010", code, as_of, raw_value=day.day_nayin or "未知",
                    normalized=ny_norm, direction=ny_dir,
                    rule_score=abs(ny_norm) * 8.0,
                    confidence=0.55 if nayin_wx else 0.0,
                    explanation=(
                        f"当日纳音「{day.day_nayin}」属五行「{nayin_wx or '未知'}」，判定为「{ny_label}」。"
                    )))

    xiu_norm = 1.0 if day.xiu_luck == "吉" else (-1.0 if day.xiu_luck == "凶" else 0.0)
    out.append(_obs("H_DAY_011", code, as_of, raw_value=day.xiu_luck or "未知",
                    normalized=xiu_norm,
                    direction=Direction.POSITIVE if xiu_norm > 0 else (Direction.NEGATIVE if xiu_norm < 0 else Direction.NEUTRAL),
                    rule_score=abs(xiu_norm) * 6.0, confidence=0.5,
                    explanation=f"当日二十八宿为「{day.xiu}」，吉凶属性「{day.xiu_luck or '未知'}」。"))

    is_punish_day = _is_punishment(natal_day_branch, day_branch)
    out.append(_obs("H_DAY_012", code, as_of, raw_value=is_punish_day,
                    normalized=-1.0 if is_punish_day else 0.0,
                    direction=Direction.NEGATIVE if is_punish_day else Direction.NEUTRAL,
                    rule_score=10.0 if is_punish_day else 0.0, confidence=0.62,
                    explanation=f"当日日支 {day_branch} {'与' if is_punish_day else '不与'}股票日支 {natal_day_branch} 相刑。"))

    # --- H_MONTH_* 月度聚合（扫描当月自然日，不读取任何未来行情） ---
    out.extend(_month_aggregates(chart, huangli, as_of))
    return out


def _month_aggregates(
    chart: BaziChart, huangli: HuangliSnapshot, as_of: datetime
) -> list[FactorObservation]:
    code = chart.stock_code or ""
    days = huangli.days[1:] if len(huangli.days) > 1 else []
    if not days:
        return [
            _unavailable(fid, code, as_of, "未提供月度扫描窗口（days<=1）")
            for fid in ("H_MONTH_001", "H_MONTH_002", "H_MONTH_003", "H_MONTH_004", "H_MONTH_005")
        ]

    yong = chart.yong_shen
    n = len(days)
    natal_day_branch = chart.day_pillar.ganzhi.branch
    favor = set(yong.yong_shen) | set(yong.xi_shen)

    n_huangdao = sum(1 for d in days if (d.day_tian_shen_type or DAY_TIAN_SHEN_LUCK.get(d.day_tian_shen)) == "黄道")
    n_ji = sum(1 for d in days if d.day_tian_shen_luck == "吉")
    n_harmony = sum(1 for d in days if BRANCH_HARMONY_OF.get(natal_day_branch) == d.day_ganzhi[1:2])
    n_clash = sum(1 for d in days if BRANCH_CLASH_OF.get(natal_day_branch) == d.day_ganzhi[1:2])
    n_favor = sum(
        1 for d in days
        if (STEM_WUXING.get(d.day_ganzhi[:1]) in favor) or (_branch_wuxing(d.day_ganzhi[1:2]) in favor)
    )

    macro = huangli.primary.date.strftime("%Y-%m")

    def _ratio_factor(fid: str, count: int, label: str) -> FactorObservation:
        ratio = count / n
        return _obs(fid, code, as_of,
                    raw_value={"count": count, "days": n, "ratio": round(ratio, 4), "month": macro},
                    normalized=_clamp((ratio - 0.5) * 2, -1.0, 1.0),
                    direction=Direction.POSITIVE if ratio > 0.5 else (Direction.NEGATIVE if ratio < 0.5 else Direction.NEUTRAL),
                    rule_score=abs(ratio - 0.5) * 2 * 10,
                    confidence=0.55,
                    explanation=(
                        f"{macro} 共 {n} 天，{label} {count} 天（占比 {round(ratio * 100, 1)}%）。"
                        "统计窗口为自然日，不包含任何未来行情数据。"
                    ))

    return [
        _ratio_factor("H_MONTH_001", n_huangdao, "黄道日"),
        _ratio_factor("H_MONTH_002", n_ji, "吉神日"),
        _obs("H_MONTH_003", code, as_of,
             raw_value={"days": n_harmony, "month": macro},
             normalized=min(n_harmony / 4.0, 1.0),
             direction=Direction.POSITIVE if n_harmony else Direction.NEUTRAL,
             rule_score=min(n_harmony / 4.0, 1.0) * 10, confidence=0.6,
             explanation=f"{macro} 内当日支与原局日支 {natal_day_branch} 六合共 {n_harmony} 天。"),
        _obs("H_MONTH_004", code, as_of,
             raw_value={"days": n_clash, "month": macro},
             normalized=min(n_clash / 4.0, 1.0),
             direction=Direction.NEGATIVE if n_clash else Direction.NEUTRAL,
             rule_score=min(n_clash / 4.0, 1.0) * 10, confidence=0.6,
             explanation=f"{macro} 内当日支与原局日支 {natal_day_branch} 六冲共 {n_clash} 天。"),
        _obs("H_MONTH_005", code, as_of,
             raw_value={"days": n_favor, "days_in_month": n, "month": macro},
             normalized=_clamp((n_favor / n - 0.5) * 2, -1.0, 1.0),
             direction=Direction.POSITIVE if n_favor / n > 0.5 else Direction.NEUTRAL,
             rule_score=abs(n_favor / n - 0.5) * 2 * 10, confidence=0.55,
             explanation=(
                 f"{macro} 内当日干支五行属喜用神的有 {n_favor}/{n} 天"
                 f"（喜用五行：{'、'.join(sorted(favor)) or '未定'}）。"
             )),
    ]


# ---------------------------------------------------------------------------
# 顶层入口
# ---------------------------------------------------------------------------


def compute_factor_set(
    chart: BaziChart,
    huangli: HuangliSnapshot | None,
    as_of: datetime,
    *,
    stock_code: str | None = None,
) -> FactorSet:
    """计算某只股票在某 as_of 的全部因子。

    严格只使用 ``as_of`` 时刻已经确定的盘面信息（原局 + 当时的流年/流月/流日
    + 当月黄历扫描），**不读取任何行情数据**。
    """
    code = stock_code or chart.stock_code or ""
    observations = compute_bazi_factors(chart, as_of)
    if huangli is not None:
        observations.extend(compute_huangli_factors(chart, huangli, as_of))

    return FactorSet(
        stock_code=code,
        as_of=as_of,
        engine_version=settings.bazi_engine_version,
        rule_version=settings.factor_rule_version,
        config_version=settings.config_version,
        observations=observations,
    )


def factor_ids() -> list[str]:
    return sorted(DEFINITION_INDEX)


def factor_disclaimer() -> str:
    return FACTOR_DISCLAIMER


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------


def _branch_wuxing(branch: str) -> str:
    from src.core.constants import BRANCH_WUXING

    return BRANCH_WUXING.get(branch, "")


def _nayin_wuxing(nayin: str) -> str:
    """纳音名（如『大海水』）→ 五行。"""
    if not nayin:
        return ""
    tail = nayin[-1]
    return tail if tail in WU_XING_ORDER else ""


def _is_punishment(a: str, b: str) -> bool:
    from src.engines.bazi.rules import _punishment_hit  # noqa: PLC2701

    return _punishment_hit(a, b) is not None


def _tanh(x: float) -> float:
    import math

    return round(math.tanh(max(-20.0, min(20.0, x))), 6)


def _safe_log(x: float) -> float:
    import math

    if x <= 0:
        return -3.0
    return math.log(x)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def month_scan_window(as_of: datetime, days: int = 31) -> list[date]:
    """返回从 as_of 当日开始的连续自然日（用于黄历月度聚合）。"""
    start = as_of.date()
    return [start + timedelta(days=i) for i in range(days)]
