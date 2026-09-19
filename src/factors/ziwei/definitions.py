"""紫微斗数因子定义（Phase 2B）。

**必须先读这段再读任何因子定义。**

紫微股票映射不是传统定论
------------------------
「财帛宫 = 股票资金」「官禄宫 = 公司经营」「迁移宫 = 外部市场」这类映射
**不是传统紫微斗数的规定**，而是本项目的研究假设。

因此：

* 它们被登记为 ``research_mapping``，版本号 = ``ziwei_stock_mapping_v1``
  （见 ``settings.ziwei_stock_mapping_version``）；
* **禁止**在 UI / 文档 / 报告中表述为"传统紫微规定财帛宫就是股价"；
* 映射本身必须先经历史回测检验，未通过时不得进入任何"有效"宣称。

方向语义
--------
``direction`` 与 ``rule_score`` 表达的是**传统规则认为的方向与强度**：

* 吉曜 / 庙旺 / 化禄权科 → 传统视为偏吉 → ``POSITIVE``
* 煞曜 / 化忌 → 传统视为偏凶 → ``NEGATIVE``
* 宫位阶、主星数量、五行局 → 结构性变量，**方向中性**

这些**都不是预期收益率，也不是上涨概率**。该声明写入每个因子的
``rule_score_meaning``，并由 ``tests/factors/test_ziwei_factors.py`` 机器校验。

与八字因子的隔离
----------------
紫微因子使用**独立的 rule_version**（``zv1``，观测按 variant 后缀区分为
``zv1.fwd`` / ``zv1.rev``），与八字的 ``v1.1`` 解耦 ——
两边因子的修复节奏不同，混用版本号会让"为什么分数变了"无法追溯。
"""

from __future__ import annotations

from src.core.config import settings
from src.core.schemas.common import Direction, EngineId
from src.core.schemas.factor import FactorCategory, FactorDefinition

ZIWEI_RULE_SCORE_MEANING = (
    "传统紫微斗数规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统紫微中最强。"
    "该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。"
)

ZIWEI_EXPL = (
    "本因子为研究变量，其与未来收益的关系必须由历史回测验证，"
    "禁止直接解读为涨跌结论。宫位→金融含义的映射属于本项目假设"
    f"（{settings.ziwei_stock_mapping_version}），不是传统定论。"
)

NATAL = FactorCategory.NATAL
YEAR = FactorCategory.YEAR
MONTH = FactorCategory.MONTH
DAY = FactorCategory.DAY


def _z(
    factor_id: str,
    name: str,
    category: FactorCategory,
    definition: str,
    computation: str,
    *,
    direction: Direction = Direction.NEUTRAL,
    raw_unit: str = "",
    normalized_hint: str = "",
    requires: list[str] | None = None,
    tags: list[str] | None = None,
) -> FactorDefinition:
    return FactorDefinition(
        factor_id=factor_id,
        name=name,
        engine=EngineId.ZIWEI,
        category=category,
        definition=definition,
        computation=computation,
        raw_unit=raw_unit,
        normalized_hint=normalized_hint,
        default_direction=direction,
        rule_score_meaning=ZIWEI_RULE_SCORE_MEANING,
        rule_version=settings.ziwei_factor_rule_version,
        enabled=True,
        requires=requires or [],
        tags=tags or [],
    )


# ---------------------------------------------------------------------------
# Z_LIFE_* 命宫
# ---------------------------------------------------------------------------

LIFE_DEFINITIONS: list[FactorDefinition] = [
    _z("Z_LIFE_001", "命宫主星庙旺和", NATAL,
       "命宫主星的庙旺等级之和。传统紫微以主星庙旺程度衡量该宫的力量强弱。"
       "股票研究中作为『主体结构强度』的代理变量（研究假设，非定论）。",
       "sum(BRIGHTNESS_SCORE[主星.brightness] for 主星 in 命宫)",
       direction=Direction.POSITIVE, raw_unit="score_sum",
       normalized_hint="tanh(sum / 1.5)，落在 [-1, 1]",
       requires=["ziwei.palace.命宫.major_stars"],
       tags=["紫微", "命宫", "庙旺"]),
    _z("Z_LIFE_002", "命宫主星数量", NATAL,
       "命宫主星个数。0 表示空宫（传统认为需借对宫安星），属于结构性变量，"
       "数量本身不对应收益方向。",
       "len(命宫.major_stars)", raw_unit="count",
       normalized_hint="min(count / 2, 1)（仅作强度，方向中性）",
       requires=["ziwei.palace.命宫.major_stars"], tags=["紫微", "命宫"]),
    _z("Z_LIFE_003", "命宫吉曜数量", NATAL,
       "命宫中六吉星（左辅/右弼/文昌/文曲/天魁/天钺）与禄马（禄存/天马）的数量。"
       "传统视为助力，本项目仅作为可检验的结构变量。",
       "count(star_category ∈ {lucky, wealth_move} in 命宫)",
       direction=Direction.POSITIVE, raw_unit="count",
       normalized_hint="min(count / 3, 1)",
       requires=["ziwei.palace.命宫"], tags=["紫微", "命宫", "吉曜"]),
    _z("Z_LIFE_004", "命宫煞曜数量", NATAL,
       "命宫中六煞星（擎羊/陀罗/火星/铃星/地空/地劫）的数量。"
       "传统视为阻力。**这是传统规则的看法，不构成对股价的判断。**",
       "count(star_category == malefic in 命宫)",
       direction=Direction.NEGATIVE, raw_unit="count",
       normalized_hint="-min(count / 2, 1)",
       requires=["ziwei.palace.命宫"], tags=["紫微", "命宫", "煞曜"]),
    _z("Z_LIFE_005", "命宫吉煞差", NATAL,
       "命宫吉曜数与煞曜数之差，传统『吉凶相抵』概念的量化近似。"
       "正值表示吉曜多于煞曜。这是传统规则的看法，不构成对股价的判断。",
       "(吉曜数 + 禄马数) - 煞曜数", raw_unit="count_diff",
       normalized_hint="tanh(diff / 2)",
       direction=Direction.POSITIVE,
       requires=["ziwei.palace.命宫"], tags=["紫微", "命宫"]),
    _z("Z_LIFE_006", "身宫与命宫同宫", NATAL,
       "身宫是否与命宫落在同一宫位。传统认为命身同宫者结构集中、"
       "倾向性更强。作为结构性标记，方向中性。",
       "body_palace_index == soul_palace_index", raw_unit="bool",
       normalized_hint="True→+0.5、False→0（仅作结构标记）",
       requires=["ziwei.body_palace_index"], tags=["紫微", "命宫", "身宫"]),
    _z("Z_LIFE_007", "五行局", NATAL,
       "命宫所属五行局（水二/木三/金四/土五/火六），决定起运岁数与"
       "紫微星安放起点。属于分类变量，不映射收益方向。",
       "iztro five_elements_class", raw_unit="class",
       normalized_hint="局数 2..6 线性映射到 [-1,1]；分类变量仅作结构编码",
       requires=["ziwei.five_elements_class"], tags=["紫微", "五行局"]),
]

# ---------------------------------------------------------------------------
# Z_FIN_* 财帛宫（研究映射：财帛宫 → 资金/价格结构，非传统定论）
# ---------------------------------------------------------------------------

FIN_DEFINITIONS: list[FactorDefinition] = [
    _z("Z_FIN_001", "财帛宫主星庙旺和", NATAL,
       "财帛宫主星庙旺等级之和。**研究映射**：把财帛宫视为『资金/价格结构』的代理，"
       "该映射属本项目假设（ziwei_stock_mapping_v1），不是传统紫微对股票的规定。",
       "sum(BRIGHTNESS_SCORE[主星.brightness] for 主星 in 财帛宫)",
       direction=Direction.POSITIVE, raw_unit="score_sum",
       normalized_hint="tanh(sum / 1.5)",
       requires=["ziwei.palace.财帛.major_stars"], tags=["紫微", "财帛宫", "research_mapping"]),
    _z("Z_FIN_002", "财帛宫主星数量", NATAL,
       "财帛宫主星个数（0 为空宫）。结构性变量，方向中性。",
       "len(财帛宫.major_stars)", raw_unit="count",
       normalized_hint="min(count / 2, 1)",
       requires=["ziwei.palace.财帛"], tags=["紫微", "财帛宫"]),
    _z("Z_FIN_003", "财帛宫煞曜数量", NATAL,
       "财帛宫中六煞星（擎羊/陀罗/火星/铃星/地空/地劫）的数量。传统视为财位上的阻力；"
       "**这是传统规则的看法，不构成对股价的判断。**",
       "count(malefic in 财帛宫)", direction=Direction.NEGATIVE, raw_unit="count",
       normalized_hint="-min(count / 2, 1)",
       requires=["ziwei.palace.财帛"], tags=["紫微", "财帛宫", "煞曜"]),
    _z("Z_FIN_004", "财帛宫化禄化权同宫", NATAL,
       "生年化禄或化权是否落在财帛宫。传统视为财位受化，偏吉。",
       "any(生年四化 in {禄, 权} 落于 财帛宫)",
       direction=Direction.POSITIVE, raw_unit="bool",
       normalized_hint="True→+1，False→0",
       requires=["ziwei.natal_mutagens"], tags=["紫微", "财帛宫", "四化"]),
]

# ---------------------------------------------------------------------------
# Z_CAREER_* 官禄宫（研究映射：官禄宫 → 公司经营）
# ---------------------------------------------------------------------------

CAREER_DEFINITIONS: list[FactorDefinition] = [
    _z("Z_CAREER_001", "官禄宫主星庙旺和", NATAL,
       "官禄宫主星庙旺等级之和。**研究映射**：官禄宫 → 公司经营/行业地位，属本项目假设。",
       "sum(BRIGHTNESS_SCORE[主星.brightness] for 主星 in 官禄宫)",
       direction=Direction.POSITIVE, raw_unit="score_sum",
       normalized_hint="tanh(sum / 1.5)",
       requires=["ziwei.palace.官禄.major_stars"],
       tags=["紫微", "官禄宫", "research_mapping"]),
    _z("Z_CAREER_002", "官禄宫主星数量", NATAL,
       "官禄宫主星个数（0 为空宫）。结构性变量，方向中性。",
       "len(官禄宫.major_stars)", raw_unit="count",
       normalized_hint="min(count / 2, 1)",
       requires=["ziwei.palace.官禄"], tags=["紫微", "官禄宫"]),
    _z("Z_CAREER_003", "官禄宫煞曜数量", NATAL,
       "官禄宫中六煞星的数量。**研究映射**：官禄宫 → 公司经营，"
       "故该因子被用作『经营阻力』的代理变量，属本项目假设。**不是传统定论。**",
       "count(malefic in 官禄宫)", direction=Direction.NEGATIVE, raw_unit="count",
       normalized_hint="-min(count / 2, 1)",
       requires=["ziwei.palace.官禄"], tags=["紫微", "官禄宫", "煞曜"]),
    _z("Z_CAREER_004", "官禄宫化权化科同宫", NATAL,
       "生年化权或化科是否落在官禄宫。传统视为权位/名位受化。",
       "any(生年四化 in {权, 科} 落于 官禄宫)",
       direction=Direction.POSITIVE, raw_unit="bool",
       normalized_hint="True→+1，False→0",
       requires=["ziwei.natal_mutagens"], tags=["紫微", "官禄宫", "四化"]),
]

# ---------------------------------------------------------------------------
# Z_MOVE_* 迁移宫（研究映射：迁移宫 → 外部市场）
# ---------------------------------------------------------------------------

MOVE_DEFINITIONS: list[FactorDefinition] = [
    _z("Z_MOVE_001", "迁移宫主星庙旺和", NATAL,
       "迁移宫主星庙旺等级之和。**研究映射**：迁移宫 → 外部市场/资金流入环境，属本项目假设。",
       "sum(BRIGHTNESS_SCORE[主星.brightness] for 主星 in 迁移宫)",
       direction=Direction.POSITIVE, raw_unit="score_sum",
       normalized_hint="tanh(sum / 1.5)",
       requires=["ziwei.palace.迁移.major_stars"],
       tags=["紫微", "迁移宫", "research_mapping"]),
    _z("Z_MOVE_002", "迁移宫煞曜数量", NATAL,
       "迁移宫中六煞星的数量。**研究映射**：迁移宫 → 外部市场环境，"
       "故该因子被用作『外部阻力』的代理变量，属本项目假设。**不是传统定论。**",
       "count(malefic in 迁移宫)", direction=Direction.NEGATIVE, raw_unit="count",
       normalized_hint="-min(count / 2, 1)",
       requires=["ziwei.palace.迁移"], tags=["紫微", "迁移宫", "煞曜"]),
    _z("Z_MOVE_003", "迁移宫化禄化科同宫", NATAL,
       "生年化禄或化科是否落在迁移宫。**研究映射**：迁移宫 → 外部市场，"
       "故此处把化吉入迁移解释为外部环境受化，属本项目假设。",
       "any(生年四化 in {禄, 科} 落于 迁移宫)",
       direction=Direction.POSITIVE, raw_unit="bool",
       normalized_hint="True→+1，False→0",
       requires=["ziwei.natal_mutagens"], tags=["紫微", "迁移宫", "四化"]),
]

# ---------------------------------------------------------------------------
# Z_MUTAGEN_* 生年四化
# ---------------------------------------------------------------------------

MUTAGEN_DEFINITIONS: list[FactorDefinition] = [
    _z("Z_MUTAGEN_001", "生年化禄落宫位阶", NATAL,
       "生年化禄所落宫位在『命-财-官-迁』关键宫集中的位阶。"
       "传统认为化禄入命财官迁为吉位。位阶 2=核心位（命财官迁），1=次核心位（福德/田宅），"
       "0=其他位，-1=缺失。",
       "根据 natal_mutagens[禄].palace_name 映射位阶",
       direction=Direction.POSITIVE, raw_unit="tier",
       normalized_hint="tier 2→+1，1→+0.5，0→0，-1→不可用",
       requires=["ziwei.natal_mutagens"], tags=["紫微", "四化", "禄"]),
    _z("Z_MUTAGEN_002", "生年化权落宫位阶", NATAL,
       "生年化权所落宫位的位阶（同 Z_MUTAGEN_001 的位阶定义）。",
       "根据 natal_mutagens[权].palace_name 映射位阶",
       direction=Direction.POSITIVE, raw_unit="tier",
       normalized_hint="tier 2→+1，1→+0.5，0→0，-1→不可用",
       requires=["ziwei.natal_mutagens"], tags=["紫微", "四化", "权"]),
    _z("Z_MUTAGEN_003", "生年化科落宫位阶", NATAL,
       "生年化科所落宫位的位阶（同 Z_MUTAGEN_001 的位阶定义）。",
       "根据 natal_mutagens[科].palace_name 映射位阶",
       direction=Direction.POSITIVE, raw_unit="tier",
       normalized_hint="tier 2→+1，1→+0.5，0→0，-1→不可用",
       requires=["ziwei.natal_mutagens"], tags=["紫微", "四化", "科"]),
    _z("Z_MUTAGEN_004", "生年化忌落宫位阶", NATAL,
       "生年化忌所落宫位的位阶。化忌入命财官迁传统视为该位受冲。",
       "根据 natal_mutagens[忌].palace_name 映射位阶",
       direction=Direction.NEGATIVE, raw_unit="tier",
       normalized_hint="tier 2→-1，1→-0.5，0→0，-1→不可用",
       requires=["ziwei.natal_mutagens"], tags=["紫微", "四化", "忌"]),
    _z("Z_MUTAGEN_005", "化吉入关键宫计数", NATAL,
       "生年化禄/化权/化科三者中，落在『命-财-官-迁』关键宫的数量。",
       "count(禄权科 落宫 ∈ {命宫, 财帛, 官禄, 迁移})",
       direction=Direction.POSITIVE, raw_unit="count",
       normalized_hint="min(count / 2, 1)",
       requires=["ziwei.natal_mutagens"], tags=["紫微", "四化"]),
    _z("Z_MUTAGEN_006", "化忌入关键宫", NATAL,
       "生年化忌是否落在『命-财-官-迁』任一关键宫。",
       "natal_mutagens[忌].palace_name ∈ {命宫, 财帛, 官禄, 迁移}",
       direction=Direction.NEGATIVE, raw_unit="bool",
       normalized_hint="True→-1，False→0",
       requires=["ziwei.natal_mutagens"], tags=["紫微", "四化", "忌"]),
]

# ---------------------------------------------------------------------------
# Z_TRINE_* 三方四正
# ---------------------------------------------------------------------------

TRINE_DEFINITIONS: list[FactorDefinition] = [
    _z("Z_TRINE_001", "命宫三方四正主星庙旺和", NATAL,
       "命宫三方四正（命/迁/财/官）四宫主星庙旺等级之和。"
       "传统以三方四正的整体格局判断结构强弱。",
       "sum(BRIGHTNESS_SCORE[主星.brightness] over 四宫)",
       direction=Direction.POSITIVE, raw_unit="score_sum",
       normalized_hint="tanh(sum / 4)",
       requires=["ziwei.trine.命宫"], tags=["紫微", "三方四正"]),
    _z("Z_TRINE_002", "命宫三方四正吉曜数", NATAL,
       "命宫三方四正四宫中吉曜（六吉星 + 禄存 + 天马）的总数。传统认为吉曜汇集则格局得力，本项目仅作为可检验的结构变量。",
       "count(吉曜 over 四宫)", direction=Direction.POSITIVE, raw_unit="count",
       normalized_hint="min(count / 6, 1)",
       requires=["ziwei.trine.命宫"], tags=["紫微", "三方四正", "吉曜"]),
    _z("Z_TRINE_003", "命宫三方四正煞曜数", NATAL,
       "命宫三方四正四宫中六煞星（六煞全集）的总数。传统以三方四正的整体格局"
       "判断结构强弱，本因子是该判断的一个分量。",
       "count(煞曜 over 四宫)", direction=Direction.NEGATIVE, raw_unit="count",
       normalized_hint="-min(count / 4, 1)",
       requires=["ziwei.trine.命宫"], tags=["紫微", "三方四正", "煞曜"]),
    _z("Z_TRINE_004", "命宫三方四正吉煞差", NATAL,
       "三方四正的吉曜总数与煞曜总数之差，传统『吉凶相抵』概念的量化近似。"
       "正值表示吉曜多于煞曜。这是传统规则的看法，不构成对股价的判断。",
       "吉曜数 - 煞曜数", raw_unit="count_diff",
       normalized_hint="tanh(diff / 3)",
       direction=Direction.POSITIVE,
       requires=["ziwei.trine.命宫"], tags=["紫微", "三方四正"]),
    _z("Z_TRINE_005", "三宫主星总数", NATAL,
       "财帛 / 官禄 / 迁移 三宫的主星总数（不含命宫）。结构性变量，方向中性。",
       "sum(len(主星) for 宫 ∈ {财帛, 官禄, 迁移})", raw_unit="count",
       normalized_hint="min(count / 5, 1)",
       requires=["ziwei.palace"], tags=["紫微", "三方四正"]),
]

# ---------------------------------------------------------------------------
# Z_YEAR_* 流年
# ---------------------------------------------------------------------------

YEAR_DEFINITIONS: list[FactorDefinition] = [
    _z("Z_YEAR_001", "流年命宫原盘位阶", YEAR,
       "该年流年命宫落在原盘的哪一宫（宫位 index）。属于分类/结构变量，方向中性。",
       "horoscope.yearly.index", raw_unit="palace_index",
       normalized_hint="index 映射到 [-1,1]；仅作结构编码，不含吉凶",
       requires=["ziwei.horoscope.yearly.index"], tags=["紫微", "流年"]),
    _z("Z_YEAR_002", "流年命宫主星庙旺和", YEAR,
       "流年命宫（原盘对应宫位）的主星庙旺等级之和。",
       "sum(BRIGHTNESS_SCORE[主星.brightness] at palace horoscope.yearly.index)",
       direction=Direction.POSITIVE, raw_unit="score_sum",
       normalized_hint="tanh(sum / 1.5)",
       requires=["ziwei.horoscope.yearly.index"], tags=["紫微", "流年"]),
    _z("Z_YEAR_003", "流年命宫煞曜数量", YEAR,
       "流年命宫所在宫位的原局煞曜与流年煞曜（流羊/流陀等）总数。",
       "count(malefic in 原局宫) + count(流年煞曜)",
       direction=Direction.NEGATIVE, raw_unit="count",
       normalized_hint="-min(count / 3, 1)",
       requires=["ziwei.horoscope.yearly"], tags=["紫微", "流年", "煞曜"]),
    _z("Z_YEAR_004", "流年化禄落原盘宫", YEAR,
       "该年流年四化中化禄所落星曜的原盘宫位 index。结构变量，方向中性"
       "（吉凶判断留给 Z_YEAR_006 等带方向的因子）。",
       "horoscope.yearly.mutagen[0] → 找到该星在原盘的宫位",
       raw_unit="palace_index",
       normalized_hint="index 映射到 [-1,1]；仅作结构编码",
       requires=["ziwei.horoscope.yearly.mutagen"], tags=["紫微", "流年", "四化"]),
    _z("Z_YEAR_005", "流年化忌落原盘宫", YEAR,
       "该年流年四化中化忌所落星曜的原盘宫位 index。结构变量，方向中性。",
       "horoscope.yearly.mutagen[3] → 找到该星在原盘的宫位",
       raw_unit="palace_index",
       normalized_hint="index 映射到 [-1,1]；仅作结构编码",
       requires=["ziwei.horoscope.yearly.mutagen"], tags=["紫微", "流年", "四化"]),
    _z("Z_YEAR_006", "流年命宫与原盘命宫同位", YEAR,
       "流年命宫是否与原盘命宫落在同一宫（太岁重叠）。传统视为该年"
       "原局结构被直接引动。",
       "horoscope.yearly.index == soul_palace_index", raw_unit="bool",
       normalized_hint="True→+0.5（结构集中），False→0",
       requires=["ziwei.horoscope.yearly.index"], tags=["紫微", "流年"]),
]

# ---------------------------------------------------------------------------
# Z_MONTH_* 流月
# ---------------------------------------------------------------------------

MONTH_ZW_DEFINITIONS: list[FactorDefinition] = [
    _z("Z_MONTH_001", "流月命宫原盘位阶", MONTH,
       "该月流月命宫落在原盘的哪一宫。结构变量，方向中性。",
       "horoscope.monthly.index", raw_unit="palace_index",
       normalized_hint="index 映射到 [-1,1]；仅作结构编码",
       requires=["ziwei.horoscope.monthly.index"], tags=["紫微", "流月"]),
    _z("Z_MONTH_002", "流月命宫主星庙旺和", MONTH,
       "流月命宫（原盘对应宫位）的主星庙旺等级之和。",
       "sum(BRIGHTNESS_SCORE over 流月命宫主星)",
       direction=Direction.POSITIVE, raw_unit="score_sum",
       normalized_hint="tanh(sum / 1.5)",
       requires=["ziwei.horoscope.monthly.index"], tags=["紫微", "流月"]),
    _z("Z_MONTH_003", "流月命宫煞曜数量", MONTH,
       "流月命宫所在宫位的原局煞曜与流月煞曜总数。",
       "count(煞曜)", direction=Direction.NEGATIVE, raw_unit="count",
       normalized_hint="-min(count / 3, 1)",
       requires=["ziwei.horoscope.monthly"], tags=["紫微", "流月", "煞曜"]),
    _z("Z_MONTH_004", "流月化禄落原盘宫", MONTH,
       "流月四化中化禄所落星曜的原盘宫位 index。结构变量，方向中性。",
       "horoscope.monthly.mutagen[0] → 星曜原盘落宫", raw_unit="palace_index",
       normalized_hint="index 映射到 [-1,1]",
       requires=["ziwei.horoscope.monthly.mutagen"], tags=["紫微", "流月", "四化"]),
    _z("Z_MONTH_005", "流月化忌落原盘宫", MONTH,
       "流月四化中化忌所落星曜的原盘宫位 index。结构变量，方向中性。",
       "horoscope.monthly.mutagen[3] → 星曜原盘落宫", raw_unit="palace_index",
       normalized_hint="index 映射到 [-1,1]",
       requires=["ziwei.horoscope.monthly.mutagen"], tags=["紫微", "流月", "四化"]),
]

# ---------------------------------------------------------------------------
# Z_DAY_* 流日（用于周度聚合）
# ---------------------------------------------------------------------------

DAY_ZW_DEFINITIONS: list[FactorDefinition] = [
    _z("Z_DAY_001", "流日命宫原盘位阶", DAY,
       "该日流日命宫落在原盘的哪一宫。结构变量，方向中性。"
       "本因子是周度聚合（交易日流日 → 周）的基础输入。",
       "horoscope.daily.index", raw_unit="palace_index",
       normalized_hint="index 映射到 [-1,1]；仅作结构编码",
       requires=["ziwei.horoscope.daily.index"], tags=["紫微", "流日", "周度"]),
    _z("Z_DAY_002", "流日命宫主星庙旺和", DAY,
       "流日命宫（原盘对应宫位）的主星庙旺等级之和。",
       "sum(BRIGHTNESS_SCORE over 流日命宫主星)",
       direction=Direction.POSITIVE, raw_unit="score_sum",
       normalized_hint="tanh(sum / 1.5)",
       requires=["ziwei.horoscope.daily.index"], tags=["紫微", "流日"]),
    _z("Z_DAY_003", "流日命宫煞曜数量", DAY,
       "流日命宫所在宫位的原局煞曜与流日煞曜总数。",
       "count(煞曜)", direction=Direction.NEGATIVE, raw_unit="count",
       normalized_hint="-min(count / 3, 1)",
       requires=["ziwei.horoscope.daily"], tags=["紫微", "流日", "煞曜"]),
    _z("Z_DAY_004", "流日化禄落原盘宫", DAY,
       "流日四化中化禄所落星曜的原盘宫位 index。结构变量，方向中性。",
       "horoscope.daily.mutagen[0] → 星曜原盘落宫", raw_unit="palace_index",
       normalized_hint="index 映射到 [-1,1]",
       requires=["ziwei.horoscope.daily.mutagen"], tags=["紫微", "流日", "四化"]),
    _z("Z_DAY_005", "流日化忌落原盘宫", DAY,
       "流日四化中化忌所落星曜的原盘宫位 index。结构变量，方向中性。",
       "horoscope.daily.mutagen[3] → 星曜原盘落宫", raw_unit="palace_index",
       normalized_hint="index 映射到 [-1,1]",
       requires=["ziwei.horoscope.daily.mutagen"], tags=["紫微", "流日", "四化"]),
]

# ---------------------------------------------------------------------------
# Z_DECADE_* / Z_AGE_* 大限 / 小限（**唯一随 variant 变化的因子组**）
# ---------------------------------------------------------------------------

DECADAL_DEFINITIONS: list[FactorDefinition] = [
    _z("Z_DECADE_001", "当前大限宫主星庙旺和", NATAL,
       "as_of 所处大限所在宫位的主星庙旺等级之和。"
       "**该因子随 variant（顺行/逆行）变化**，是两个 variant 对比的核心变量。",
       "sum(BRIGHTNESS_SCORE over 大限宫主星)",
       direction=Direction.POSITIVE, raw_unit="score_sum",
       normalized_hint="tanh(sum / 1.5)",
       requires=["ziwei.horoscope.decadal.index"], tags=["紫微", "大限", "variant敏感"]),
    _z("Z_DECADE_002", "当前大限宫煞曜数量", NATAL,
       "as_of 所处大限所在宫位的煞曜数量。**随 variant 变化。**",
       "count(煞曜 in 大限宫)", direction=Direction.NEGATIVE, raw_unit="count",
       normalized_hint="-min(count / 2, 1)",
       requires=["ziwei.horoscope.decadal.index"], tags=["紫微", "大限", "variant敏感"]),
    _z("Z_AGE_001", "当前小限宫主星庙旺和", NATAL,
       "as_of 所处小限所在宫位的主星庙旺等级之和。**随 variant 变化。**",
       "sum(BRIGHTNESS_SCORE over 小限宫主星)",
       direction=Direction.POSITIVE, raw_unit="score_sum",
       normalized_hint="tanh(sum / 1.5)",
       requires=["ziwei.horoscope.age.index"], tags=["紫微", "小限", "variant敏感"]),
    _z("Z_AGE_002", "当前小限宫煞曜数量", NATAL,
       "as_of 所处小限所在宫位的煞曜数量。**随 variant 变化。**"
       "注意：小限层在 iztro 中不提供流曜，因此本因子只使用原局煞曜。",
       "count(原局煞曜 in 小限宫)", direction=Direction.NEGATIVE, raw_unit="count",
       normalized_hint="-min(count / 2, 1)",
       requires=["ziwei.horoscope.age.index"], tags=["紫微", "小限", "variant敏感"]),
]


ALL_ZIWEI_DEFINITIONS: list[FactorDefinition] = [
    *LIFE_DEFINITIONS,
    *FIN_DEFINITIONS,
    *CAREER_DEFINITIONS,
    *MOVE_DEFINITIONS,
    *MUTAGEN_DEFINITIONS,
    *TRINE_DEFINITIONS,
    *YEAR_DEFINITIONS,
    *MONTH_ZW_DEFINITIONS,
    *DAY_ZW_DEFINITIONS,
    *DECADAL_DEFINITIONS,
]

ZIWEI_DEFINITION_INDEX: dict[str, FactorDefinition] = {
    d.factor_id: d for d in ALL_ZIWEI_DEFINITIONS
}

#: 随 variant（顺行/逆行）变化的因子 —— 用于"variant 影响范围"的机器校验
VARIANT_SENSITIVE_FACTOR_IDS: tuple[str, ...] = (
    "Z_DECADE_001", "Z_DECADE_002", "Z_AGE_001", "Z_AGE_002",
)

#: 关键宫（研究映射的核心位阶集合）
KEY_PALACES: tuple[str, ...] = ("命宫", "财帛", "官禄", "迁移")
#: 次核心宫
SECONDARY_PALACES: tuple[str, ...] = ("福德", "田宅")

__all__ = [
    "ALL_ZIWEI_DEFINITIONS", "ZIWEI_DEFINITION_INDEX", "ZIWEI_RULE_SCORE_MEANING",
    "ZIWEI_EXPL", "VARIANT_SENSITIVE_FACTOR_IDS", "KEY_PALACES", "SECONDARY_PALACES",
    "LIFE_DEFINITIONS", "FIN_DEFINITIONS", "CAREER_DEFINITIONS", "MOVE_DEFINITIONS",
    "MUTAGEN_DEFINITIONS", "TRINE_DEFINITIONS", "YEAR_DEFINITIONS",
    "MONTH_ZW_DEFINITIONS", "DAY_ZW_DEFINITIONS", "DECADAL_DEFINITIONS",
]
