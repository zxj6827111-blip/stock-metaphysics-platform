"""八字规则计算内核（纯函数，无第三方依赖，易于单测）。

本模块实现传统子平法的**确定性**计算规则：

    五行力量估算 → 日主旺衰 → 格局取法 → 喜用忌神 → 刑冲合害

**重要声明（必须在任何输出中体现）**

1. 这里全部是**传统命理规则**的工程化实现，不是现代金融科学结论。
2. 不同流派（子平 / 盲派 / 新派）对格局与用神判定存在差异，
   本模块采用**通行子平扶抑法**，并显式输出 ``rationale`` 与 ``confidence``。
3. 任何结果都只是"研究变量"，必须经历史数据检验（见 ``src/research``）。
4. 力量估算中的权重是**工程近似**，不是传统定论；
   因此所有依赖它的因子都带 ``rule_version``，升级后可重新回测。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.constants import (
    BRANCH_CLASH_OF,
    BRANCH_HARMONY_OF,
    BRANCH_HARM_OF,
    BRANCH_HIDDEN_STEMS,
    BRANCH_PUNISHMENTS,
    BRANCH_TRIPLE_HARMONY,
    BRANCH_TRIPLE_MEETING,
    BRANCH_WUXING,
    STEM_CLASH,
    STEM_FIVE_HARMONY,
    STEM_WUXING,
    TEN_GOD_GROUP,
    WU_XING_ORDER,
    WUXING_GENERATED_BY,
    WUXING_GENERATES,
    WUXING_OVERCOME_BY,
    WUXING_OVERCOMES,
    hidden_stem_weight,
    ten_god,
    twelve_stage,
)

# ---------------------------------------------------------------------------
# 权重配置（工程近似，可版本化调整）
# ---------------------------------------------------------------------------

#: 天干（含日主）在力量估算中的权重
STEM_WEIGHT = 1.0
#: 月支（月令司权）的加权倍数
MONTH_BRANCH_MULTIPLIER = 1.5
#: 日支（坐下）的加权倍数
DAY_BRANCH_MULTIPLIER = 1.2

#: 地支在"得地/有根"判断中的位置权重
BRANCH_ROOT_WEIGHT: dict[str, float] = {
    "day": 1.0,     # 日支坐下最重
    "month": 0.9,   # 月令
    "hour": 0.7,
    "year": 0.5,
}

#: 五行在四季的旺衰状态（旺 / 相 / 休 / 囚 / 死）
#: 依据月支所属季节（寅卯=春木旺 …），通行五行旺衰表
SEASON_STATE: dict[str, dict[str, str]] = {
    "木": {"木": "旺", "火": "相", "水": "休", "金": "囚", "土": "死"},   # 寅卯月
    "火": {"火": "旺", "土": "相", "木": "休", "水": "囚", "金": "死"},   # 巳午月
    "金": {"金": "旺", "水": "相", "土": "休", "火": "囚", "木": "死"},   # 申酉月
    "水": {"水": "旺", "木": "相", "金": "休", "土": "囚", "火": "死"},   # 亥子月
    "土": {"土": "旺", "金": "相", "火": "休", "木": "囚", "水": "死"},   # 辰戌丑未月
}

#: 月支 → 季节五行
BRANCH_SEASON: dict[str, str] = {
    "寅": "木", "卯": "木",
    "巳": "火", "午": "火",
    "申": "金", "酉": "金",
    "亥": "水", "子": "水",
    "辰": "土", "戌": "土", "丑": "土", "未": "土",
}

SEASON_CN: dict[str, str] = {"木": "春", "火": "夏", "金": "秋", "水": "冬", "土": "四季"}


# ---------------------------------------------------------------------------
# 五行力量
# ---------------------------------------------------------------------------


@dataclass
class WuxingScore:
    """五行力量估算结果。"""

    scores: dict[str, float] = field(default_factory=dict)
    percentages: dict[str, float] = field(default_factory=dict)
    dominant: str = ""
    weakest: str = ""
    missing: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)


def compute_wuxing_scores(
    stems: dict[str, str],
    branches: dict[str, str],
) -> WuxingScore:
    """估算五行力量。

    Args:
        stems: 位置 → 天干，如 ``{"year": "辛", "month": "丙", "day": "戊", "hour": "丁"}``
        branches: 位置 → 地支
    """
    raw: dict[str, float] = dict.fromkeys(WU_XING_ORDER, 0.0)
    rationale: list[str] = []

    for pos, stem in stems.items():
        wx = STEM_WUXING.get(stem)
        if wx:
            weight = STEM_WEIGHT * (0.8 if pos == "day" else 1.0)
            raw[wx] += weight

    for pos, branch in branches.items():
        multiplier = 1.0
        if pos == "month":
            multiplier = MONTH_BRANCH_MULTIPLIER
        elif pos == "day":
            multiplier = DAY_BRANCH_MULTIPLIER

        hidden = BRANCH_HIDDEN_STEMS.get(branch, ())
        total = len(hidden)
        for idx, hs in enumerate(hidden):
            hwx = STEM_WUXING.get(hs)
            if hwx:
                base = hidden_stem_weight(idx, total)
                # 单一藏干（子/卯/酉）本气按 1.0 计
                raw[hwx] += base * multiplier

    total_score = sum(raw.values()) or 1.0
    percentages = {k: round(v / total_score * 100, 2) for k, v in raw.items()}

    present = {STEM_WUXING[s] for s in stems.values()} | {BRANCH_WUXING[b] for b in branches.values()}
    missing = [wx for wx in WU_XING_ORDER if wx not in present]

    dominant = max(raw, key=lambda k: raw[k])
    weakest = min(raw, key=lambda k: raw[k])

    rationale.append(
        "天干权重 1.0（日干 0.8）；地支按藏干本气/中气/余气赋权，"
        f"月支 ×{MONTH_BRANCH_MULTIPLIER}、日支 ×{DAY_BRANCH_MULTIPLIER}"
    )
    rationale.append(f"五行力量最高：{dominant}（{percentages[dominant]}%）；最低：{weakest}（{percentages[weakest]}%）")
    if missing:
        rationale.append(f"四柱未出现的五行：{'、'.join(missing)}")

    return WuxingScore(
        scores={k: round(v, 4) for k, v in raw.items()},
        percentages=percentages,
        dominant=dominant,
        weakest=weakest,
        missing=missing,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# 日主旺衰（得令 / 得地 / 得势）
# ---------------------------------------------------------------------------


@dataclass
class StrengthResult:
    day_master: str
    day_master_wuxing: str
    month_branch: str
    season: str
    season_state: str
    de_ling: bool
    de_di: bool
    de_shi: bool
    support_score: float
    drain_score: float
    balance_ratio: float
    strength_level: str
    confidence: float
    rationale: list[str] = field(default_factory=list)
    roots: list[str] = field(default_factory=list)


def _season_state(month_branch: str, wuxing: str) -> str:
    season = BRANCH_SEASON.get(month_branch, "土")
    return SEASON_STATE.get(season, {}).get(wuxing, "平")


def compute_strength(
    stems: dict[str, str],
    branches: dict[str, str],
    wuxing: WuxingScore,
) -> StrengthResult:
    """判定日主旺衰。

    三个维度：
      * 得令：日主五行在月令处于「旺」（当令）
      * 得地：日主五行在四支藏干中有根（按位置加权计分）
      * 得势：比劫 + 印星的总力量是否超过耗泄方
    """
    day_master = stems["day"]
    dm_wx = STEM_WUXING[day_master]
    month_branch = branches["month"]
    season = BRANCH_SEASON.get(month_branch, "土")
    season_state = _season_state(month_branch, dm_wx)

    rationale: list[str] = []

    # --- 得令 ---
    de_ling = season_state == "旺"
    rationale.append(
        f"月令 {month_branch}（{SEASON_CN.get(season, '')}，{season}当令）中，"
        f"日主五行「{dm_wx}」处于「{season_state}」→ {'得令' if de_ling else '不得令'}"
    )

    # --- 得地（有根） ---
    roots: list[str] = []
    root_score = 0.0
    for pos, branch in branches.items():
        hidden = BRANCH_HIDDEN_STEMS.get(branch, ())
        total = len(hidden)
        for idx, hs in enumerate(hidden):
            if STEM_WUXING.get(hs) == dm_wx:
                weight = hidden_stem_weight(idx, total) * BRANCH_ROOT_WEIGHT.get(pos, 0.5)
                root_score += weight
                roots.append(f"{pos}:{branch}藏{hs}")
    de_di = root_score >= 1.0
    rationale.append(
        f"日主在四支中的根：{('、'.join(roots) if roots else '无')}，根力量 {round(root_score, 3)} "
        f"→ {'得地' if de_di else '不得地'}"
    )

    # --- 力量分布 ---
    scores = wuxing.scores
    same_wx = dm_wx                                  # 比劫
    resource_wx = WUXING_GENERATED_BY[dm_wx]         # 印星
    output_wx = WUXING_GENERATES[dm_wx]              # 食伤
    wealth_wx = WUXING_OVERCOMES[dm_wx]              # 财星
    officer_wx = WUXING_OVERCOME_BY[dm_wx]           # 官杀

    support = scores.get(same_wx, 0.0) + scores.get(resource_wx, 0.0)
    drain = scores.get(output_wx, 0.0) + scores.get(wealth_wx, 0.0) + scores.get(officer_wx, 0.0)
    total = support + drain or 1.0
    ratio = support / total

    # 得势：帮扶方是否占优（考虑月令加成后的近似判定）
    de_shi = ratio >= 0.5

    if ratio >= 0.62:
        level, conf = "身强", 0.78
    elif ratio >= 0.55:
        level, conf = "偏强", 0.72
    elif ratio > 0.45:
        level, conf = "中和", 0.62
    elif ratio > 0.38:
        level, conf = "偏弱", 0.72
    else:
        level, conf = "身弱", 0.78

    # 得令与得地都缺、且比例居中时，置信度下调（如实反映分歧）
    if not de_ling and not de_di and 0.42 < ratio < 0.58:
        conf = max(0.45, conf - 0.12)

    rationale.append(
        f"帮扶力量（比劫 {same_wx} + 印星 {resource_wx}）= {round(support, 3)}；"
        f"耗泄力量（食伤 {output_wx} + 财 {wealth_wx} + 官杀 {officer_wx}）= {round(drain, 3)}；"
        f"帮扶占比 {round(ratio, 4)} → 判定「{level}」"
    )

    return StrengthResult(
        day_master=day_master,
        day_master_wuxing=dm_wx,
        month_branch=month_branch,
        season=season,
        season_state=season_state,
        de_ling=de_ling,
        de_di=de_di,
        de_shi=de_shi,
        support_score=round(support, 4),
        drain_score=round(drain, 4),
        balance_ratio=round(ratio, 4),
        strength_level=level,
        confidence=conf,
        rationale=rationale,
        roots=roots,
    )


# ---------------------------------------------------------------------------
# 格局
# ---------------------------------------------------------------------------

PATTERN_BY_TEN_GOD: dict[str, tuple[str, str]] = {
    # 十神 → (格局名, 大类)
    "正官": ("正官格", "官格"),
    "七杀": ("七杀格", "官格"),
    "正财": ("正财格", "财格"),
    "偏财": ("偏财格", "财格"),
    "正印": ("正印格", "印格"),
    "偏印": ("偏印格", "印格"),
    "食神": ("食神格", "食伤格"),
    "伤官": ("伤官格", "食伤格"),
}


@dataclass
class PatternResult:
    primary: str
    category: str
    candidates: list[dict] = field(default_factory=list)
    confidence: float = 0.5
    availability: str = "ok"
    method: str = "月令本气/透干取格（子平通行法）"
    rationale: list[str] = field(default_factory=list)


def compute_pattern(stems: dict[str, str], branches: dict[str, str]) -> PatternResult:
    """取格局。

    子平通行法：

    1. 看月支本气藏干是否**透干**（出现在年/月/时干）→ 透则取该十神为格；
    2. 本气未透，看中气、余气是否透干；
    3. 皆不透，则以月支本气十神取格（"月令不透，以本气取"）；
    4. 月令为日主临官（禄）取「建禄格」；月令为帝旺（刃）取「月刃格」。
    """
    day_master = stems["day"]
    month_branch = branches["month"]
    hidden = BRANCH_HIDDEN_STEMS.get(month_branch, ())
    visible = {pos: s for pos, s in stems.items() if pos != "day"}
    visible_stems = set(visible.values())

    rationale: list[str] = []
    candidates: list[dict] = []

    rank_names = ("本气", "中气", "余气")
    chosen_god: str | None = None
    chosen_basis = ""

    for idx, hs in enumerate(hidden):
        god = ten_god(day_master, hs)
        rank = rank_names[idx] if idx < len(rank_names) else "余气"
        transparent = hs in visible_stems
        candidates.append(
            {
                "god": god,
                "hidden_stem": hs,
                "rank": rank,
                "transparent": transparent,
                "score": round((0.6 - 0.2 * idx) + (0.4 if transparent else 0.0), 3),
            }
        )
        if transparent and chosen_god is None:
            chosen_god = god
            chosen_basis = f"月支{month_branch}之{rank}「{hs}」透干，取{god}为格"

    if chosen_god is None and hidden:
        chosen_god = ten_god(day_master, hidden[0])
        chosen_basis = f"月支{month_branch}本气「{hidden[0]}」未透干，以本气取{chosen_god}为格"

    if chosen_god is None:
        return PatternResult(
            primary="",
            category="",
            candidates=candidates,
            confidence=0.0,
            availability="unavailable",
            rationale=["月支无可用藏干，格局判定不可用"],
        )

    # 建禄 / 月刃：月令为日主之禄或刃
    stage = twelve_stage(day_master, month_branch)
    if chosen_god in ("比肩", "劫财"):
        if stage == "临官":
            name, category = "建禄格", "比劫格"
            chosen_basis += "；月令为日主临官（禄）→ 建禄格"
        elif stage == "帝旺":
            name, category = "月刃格", "比劫格"
            chosen_basis += "；月令为日主帝旺（刃）→ 月刃格"
        else:
            name, category = ("比肩格" if chosen_god == "比肩" else "劫财格"), "比劫格"
    else:
        name, category = PATTERN_BY_TEN_GOD.get(chosen_god, (f"{chosen_god}格", "其他格"))

    rationale.append(chosen_basis)

    # --- 特殊格候选：食神生财 / 财官相生 / 官印相生 / 伤官配印 ---
    visible_gods = {ten_god(day_master, s) for s in visible_stems}
    extra = _special_pattern_candidates(visible_gods)
    for e in extra:
        candidates.append(e)
    rationale.extend([f"特殊结构候选：{e['name']}（{e['basis']}）" for e in extra])

    confidence = 0.72 if "透干" in chosen_basis else 0.58
    if category == "比劫格":
        confidence = min(confidence, 0.6)

    # 有多个强度接近的候选时，如实降低置信度
    strong_alts = [c for c in candidates if c.get("transparent") and c["god"] != chosen_god]
    if len(strong_alts) >= 2:
        confidence = max(0.4, confidence - 0.12)
        rationale.append(f"另有 {len(strong_alts)} 个透干十神，格局存在流派分歧")

    return PatternResult(
        primary=name,
        category=category,
        candidates=candidates,
        confidence=round(confidence, 3),
        availability="ok",
        rationale=rationale,
    )


def _special_pattern_candidates(visible_gods: set[str]) -> list[dict]:
    """识别常见"组合型"结构（仅作为候选标签，不改变主格局）。"""
    out: list[dict] = []
    has = visible_gods.__contains__
    if has("食神") and (has("正财") or has("偏财")):
        out.append({"name": "食神生财", "basis": "食神与财星同时透干", "score": 0.5})
    if has("伤官") and (has("正财") or has("偏财")):
        out.append({"name": "伤官生财", "basis": "伤官与财星同时透干", "score": 0.5})
    if (has("正官") or has("七杀")) and (has("正财") or has("偏财")):
        out.append({"name": "财官相生", "basis": "财星与官杀同时透干", "score": 0.5})
    if (has("正官") or has("七杀")) and (has("正印") or has("偏印")):
        out.append({"name": "官印相生", "basis": "官杀与印星同时透干", "score": 0.5})
    if has("伤官") and (has("正印") or has("偏印")):
        out.append({"name": "伤官配印", "basis": "伤官与印星同时透干", "score": 0.5})
    return out


# ---------------------------------------------------------------------------
# 喜用忌神（扶抑为主 + 调候为辅）
# ---------------------------------------------------------------------------


@dataclass
class YongShenResult:
    yong_shen: list[str] = field(default_factory=list)
    xi_shen: list[str] = field(default_factory=list)
    ji_shen: list[str] = field(default_factory=list)
    chou_shen: list[str] = field(default_factory=list)
    xian_shen: list[str] = field(default_factory=list)
    tiaohou_note: str = ""
    confidence: float = 0.5
    availability: str = "ok"
    method: str = "扶抑法（主）+ 调候法（辅）"
    rationale: list[str] = field(default_factory=list)


def compute_yongshen(strength: StrengthResult) -> YongShenResult:
    """按扶抑法确定喜 / 用 / 忌 / 仇 / 闲神，并给出调候参考。"""
    dm_wx = strength.day_master_wuxing
    same_wx = dm_wx
    resource_wx = WUXING_GENERATED_BY[dm_wx]
    output_wx = WUXING_GENERATES[dm_wx]
    wealth_wx = WUXING_OVERCOMES[dm_wx]
    officer_wx = WUXING_OVERCOME_BY[dm_wx]

    level = strength.strength_level
    rationale: list[str] = []

    if level in ("身强", "偏强"):
        yong = [officer_wx]
        xi = [output_wx, wealth_wx]
        ji = [resource_wx, same_wx]
        chou = [resource_wx]
        rationale.append(
            f"日主{level}（帮扶占比 {strength.balance_ratio}）→ 宜克泄耗："
            f"取官杀「{officer_wx}」为用，食伤「{output_wx}」/财「{wealth_wx}」为喜"
        )
    elif level in ("身弱", "偏弱"):
        yong = [resource_wx]
        xi = [same_wx]
        ji = [officer_wx, wealth_wx]
        chou = [output_wx]
        rationale.append(
            f"日主{level}（帮扶占比 {strength.balance_ratio}）→ 宜生扶："
            f"取印星「{resource_wx}」为用，比劫「{same_wx}」为喜"
        )
    else:
        # 中和：以调候与通关为主，用神取最弱且能成用之五行
        yong = [output_wx]
        xi = [wealth_wx]
        ji = []
        chou = []
        rationale.append(
            f"日主{level}（帮扶占比 {strength.balance_ratio}）→ 无明显偏枯，"
            f"以通关流通为主，暂取食伤「{output_wx}」为用"
        )

    xian = [wx for wx in WU_XING_ORDER if wx not in set(yong) | set(xi) | set(ji) | set(chou)]

    # --- 调候参考 ---
    tiaohou_note = ""
    mb = strength.month_branch
    if mb in ("亥", "子", "丑"):
        tiaohou_note = "冬月生，天寒地冻，调候宜见火（暖局）"
        if "火" not in yong and "火" not in xi:
            xi = [*xi, "火"]
    elif mb in ("巳", "午", "未"):
        tiaohou_note = "夏月生，火燥水枯，调候宜见水（润局）"
        if "水" not in yong and "水" not in xi:
            xi = [*xi, "水"]
    elif mb in ("辰", "戌", "丑", "未"):
        tiaohou_note = "四季土月生，土重，调候宜木疏土或金水润泽"
    else:
        tiaohou_note = "春秋月生，寒暖适中，调候需求较低"

    rationale.append(f"调候参考：{tiaohou_note}")

    confidence = max(0.4, min(0.78, strength.confidence - 0.08))
    if level == "中和":
        confidence = max(0.4, confidence - 0.12)

    return YongShenResult(
        yong_shen=list(dict.fromkeys(yong)),
        xi_shen=list(dict.fromkeys(xi)),
        ji_shen=list(dict.fromkeys(ji)),
        chou_shen=list(dict.fromkeys(chou)),
        xian_shen=xian,
        tiaohou_note=tiaohou_note,
        confidence=round(confidence, 3),
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# 刑冲合害
# ---------------------------------------------------------------------------


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


_SIX_HARMONY_KEYS = {_pair_key(a, b) for a, b in (
    ("子", "丑"), ("寅", "亥"), ("卯", "戌"), ("辰", "酉"), ("巳", "申"), ("午", "未"),
)}
_SIX_CLASH_KEYS = {_pair_key(a, b) for a, b in (
    ("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"), ("辰", "戌"), ("巳", "亥"),
)}
_SIX_HARM_KEYS = {_pair_key(a, b) for a, b in (
    ("子", "未"), ("丑", "午"), ("寅", "巳"), ("卯", "辰"), ("申", "亥"), ("酉", "戌"),
)}
_STEM_HARMONY_KEYS = {_pair_key(a, b) for a, b in (
    ("甲", "己"), ("乙", "庚"), ("丙", "辛"), ("丁", "壬"), ("戊", "癸"),
)}
_STEM_CLASH_KEYS = {_pair_key(a, b) for a, b in (
    ("甲", "庚"), ("乙", "辛"), ("丙", "壬"), ("丁", "癸"),
)}

_PUNISHMENT_SETS: tuple[frozenset[str], ...] = (
    frozenset({"寅", "巳", "申"}),
    frozenset({"丑", "戌", "未"}),
    frozenset({"子", "卯"}),
)


def _punishment_hit(a: str, b: str) -> str | None:
    """判断两地支是否构成相刑，返回刑的类型描述。"""
    if a == b and a in ("辰", "午", "酉", "亥"):
        return f"{a}{a}自刑"
    for grp in _PUNISHMENT_SETS:
        if a in grp and b in grp and a != b:
            return "".join(sorted(grp, key=lambda x: "子丑寅卯辰巳午未申酉戌亥".index(x)))
    return None


def compute_relations(stems: dict[str, str], branches: dict[str, str]) -> list[dict]:
    """计算四柱内部的刑冲合害（天干 + 地支，两两 + 三合/三会）。"""
    hits: list[dict] = []
    positions = ["year", "month", "day", "hour"]

    # --- 天干 ---
    for i, pa in enumerate(positions):
        for pb in positions[i + 1:]:
            sa, sb = stems.get(pa, ""), stems.get(pb, "")
            if not sa or not sb:
                continue
            key = _pair_key(sa, sb)
            if key in _STEM_HARMONY_KEYS:
                hits.append({
                    "relation_type": "天干五合",
                    "positions": [pa, pb],
                    "branches_or_stems": [sa, sb],
                    "transform_element": STEM_FIVE_HARMONY.get((sa, sb)) or STEM_FIVE_HARMONY.get((sb, sa), ""),
                    "note": f"{pa}干{sa} 与 {pb}干{sb} 相合",
                })
            if key in _STEM_CLASH_KEYS:
                hits.append({
                    "relation_type": "天干相冲",
                    "positions": [pa, pb],
                    "branches_or_stems": [sa, sb],
                    "transform_element": "",
                    "note": f"{pa}干{sa} 与 {pb}干{sb} 相冲",
                })

    # --- 地支 两两 ---
    for i, pa in enumerate(positions):
        for pb in positions[i + 1:]:
            ba, bb = branches.get(pa, ""), branches.get(pb, "")
            if not ba or not bb:
                continue
            key = _pair_key(ba, bb)
            if key in _SIX_HARMONY_KEYS:
                hits.append({
                    "relation_type": "六合",
                    "positions": [pa, pb],
                    "branches_or_stems": [ba, bb],
                    "transform_element": _six_harmony_element(ba, bb),
                    "note": f"{pa}支{ba} 与 {pb}支{bb} 六合",
                })
            if key in _SIX_CLASH_KEYS:
                hits.append({
                    "relation_type": "六冲",
                    "positions": [pa, pb],
                    "branches_or_stems": [ba, bb],
                    "transform_element": "",
                    "note": f"{pa}支{ba} 与 {pb}支{bb} 相冲",
                })
            if key in _SIX_HARM_KEYS:
                hits.append({
                    "relation_type": "相害",
                    "positions": [pa, pb],
                    "branches_or_stems": [ba, bb],
                    "transform_element": "",
                    "note": f"{pa}支{ba} 与 {pb}支{bb} 相害",
                })
            pun = _punishment_hit(ba, bb)
            if pun:
                hits.append({
                    "relation_type": "相刑",
                    "positions": [pa, pb],
                    "branches_or_stems": [ba, bb],
                    "transform_element": "",
                    "note": f"{pa}支{ba} 与 {pb}支{bb} 相刑（{pun}）",
                })

    # --- 三合 / 三会 ---
    present = {pos: branches.get(pos, "") for pos in positions}
    for combo, element in BRANCH_TRIPLE_HARMONY.items():
        matched = _match_combo(combo, present)
        if len(matched) == 3:
            hits.append({
                "relation_type": "三合",
                "positions": list(matched),
                "branches_or_stems": list(combo),
                "transform_element": element,
                "note": f"{''.join(combo)} 三合{element}局",
            })
        elif len(matched) == 2:
            hits.append({
                "relation_type": "半合",
                "positions": list(matched),
                "branches_or_stems": [present[p] for p in matched],
                "transform_element": element,
                "note": f"半合{element}局（缺一）",
            })

    for combo, element in BRANCH_TRIPLE_MEETING.items():
        matched = _match_combo(combo, present)
        if len(matched) == 3:
            hits.append({
                "relation_type": "三会",
                "positions": list(matched),
                "branches_or_stems": list(combo),
                "transform_element": element,
                "note": f"{''.join(combo)} 三会{element}方",
            })

    return hits


def _six_harmony_element(a: str, b: str) -> str:
    from src.core.constants import BRANCH_SIX_HARMONY

    for (x, y), el in BRANCH_SIX_HARMONY.items():
        if {x, y} == {a, b}:
            return el
    return ""


def _match_combo(combo: tuple[str, ...], present: dict[str, str]) -> list[str]:
    used: list[str] = []
    remaining = list(combo)
    for pos, br in present.items():
        if br in remaining:
            remaining.remove(br)
            used.append(pos)
    return used


# ---------------------------------------------------------------------------
# 地支关系与"某个外部干支"的互动（供流年/流月/流日与黄历使用）
# ---------------------------------------------------------------------------


def relations_with_external(
    natal_branches: dict[str, str],
    ext_branch: str,
    ext_stem: str = "",
    natal_stems: dict[str, str] | None = None,
) -> dict[str, list[str]]:
    """计算外部干支（流年/流月/流日）与原局四柱的互动。

    Returns:
        包含 ``clashes`` / ``harmonies`` / ``harms`` / ``punishments`` /
        ``triple_harmonies``（值为命中的原局位置列表）以及
        ``stem_harmonies`` / ``stem_clashes``（值为描述串）的字典。
    """
    out: dict[str, list[str]] = {
        "clashes": [], "harmonies": [], "harms": [], "punishments": [],
        "triple_harmonies": [], "stem_harmonies": [], "stem_clashes": [],
    }
    for pos, br in natal_branches.items():
        if not br:
            continue
        if BRANCH_CLASH_OF.get(br) == ext_branch:
            out["clashes"].append(pos)
        if BRANCH_HARMONY_OF.get(br) == ext_branch:
            out["harmonies"].append(pos)
        if BRANCH_HARM_OF.get(br) == ext_branch:
            out["harms"].append(pos)
        if _punishment_hit(br, ext_branch):
            out["punishments"].append(pos)

    for combo, element in BRANCH_TRIPLE_HARMONY.items():
        if ext_branch in combo:
            others = [b for b in combo if b != ext_branch]
            natal_values = list(natal_branches.values())
            if all(o in natal_values for o in others):
                out["triple_harmonies"].append(f"{''.join(combo)}三合{element}局")

    if ext_stem and natal_stems:
        for pos, st in natal_stems.items():
            if not st:
                continue
            key = _pair_key(st, ext_stem)
            if key in _STEM_HARMONY_KEYS:
                out["stem_harmonies"].append(f"{pos}干{st}")
            if key in _STEM_CLASH_KEYS:
                out["stem_clashes"].append(f"{pos}干{st}")
    return out
