"""因子定义表（因子字典的数据源）。

**语义纪律（必须反复强调）**

    factor 的 direction / rule_score 表达的是「传统规则认为的方向与强度」，
    不是预期收益率，也不是上涨概率。

    财星 ≠ 股票上涨；食神生财 ≠ 股票一定上涨；三合 ≠ 股票上涨。

    这些因子全部是**研究变量**，其统计有效性由 ``src/research`` 的历史检验回答。
"""

from __future__ import annotations

from src.core.config import settings
from src.core.schemas.common import Direction, EngineId
from src.core.schemas.factor import FactorCategory, FactorDefinition

_RULE_SCORE_MEANING = (
    "传统规则强度分（0-10）。0 表示中性/无该结构，10 表示该结构在传统命理中最强。"
    "该分数不使用任何历史行情数据，不代表预期收益率，也不代表上涨概率。"
)

_EXPL = "本因子为研究变量，其与未来收益的关系必须由历史回测验证，禁止直接解读为涨跌结论。"


def _d(
    factor_id: str,
    name: str,
    engine: EngineId,
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
        engine=engine,
        category=category,
        definition=definition,
        computation=computation,
        raw_unit=raw_unit,
        normalized_hint=normalized_hint,
        default_direction=direction,
        rule_score_meaning=_RULE_SCORE_MEANING,
        # rule_version 全局唯一来源 = settings.factor_rule_version；
        # 修复 BUG（如 v1.1 的流年冲刑害接线错误）只升配置一处。
        rule_version=settings.factor_rule_version,
        enabled=True,
        requires=requires or [],
        tags=tags or [],
    )


# ---------------------------------------------------------------------------
# B_NATAL_* 原局结构因子
# ---------------------------------------------------------------------------

NATAL_DEFINITIONS: list[FactorDefinition] = [
    _d("B_NATAL_001", "日主强弱", EngineId.BAZI, FactorCategory.NATAL,
       "日主在月令与全局中的旺衰等级。传统命理认为身强身弱决定取用方向，"
       "但股票不存在『命主』，此处仅作为原局结构特征。",
       "support/(support+drain) 比值映射：>=0.62 身强 / >=0.55 偏强 / >0.45 中和 / >0.38 偏弱 / 其余身弱",
       raw_unit="strength_level",
       normalized_hint="身强→+1，偏强→+0.5，中和→0，偏弱→-0.5，身弱→-1",
       requires=["day_master_analysis.strength_level"], tags=["旺衰"]),
    _d("B_NATAL_002", "财星数量", EngineId.BAZI, FactorCategory.NATAL,
       "四柱天干地支十神中『正财 + 偏财』的出现次数（含藏干）。"
       "传统命理视财星为财源象征；本项目仅视其为可检验的结构变量。",
       "count(ten_god ∈ {正财, 偏财})，统计 3 个天干 + 4 支全部藏干",
       raw_unit="count", normalized_hint="min(count/4, 1) 线性映射到 [0,1]",
       requires=["ten_god_counts"], tags=["财星"]),
    _d("B_NATAL_003", "财星透干", EngineId.BAZI, FactorCategory.NATAL,
       "财星是否透出天干（年/月/时干）。传统认为透干者显，不透者藏。",
       "any(stem_ten_god ∈ {正财,偏财} for year/month/hour)",
       raw_unit="bool", normalized_hint="True→+1，False→0",
       requires=["visible_ten_gods"], tags=["财星", "透干"]),
    _d("B_NATAL_004", "财星得令", EngineId.BAZI, FactorCategory.NATAL,
       "月令地支是否为财星（月支藏干含财星，或月支五行即日主所克者）。",
       "月支五行 == 日主所克五行", raw_unit="bool",
       normalized_hint="True→+1，False→0", requires=["month_pillar"], tags=["财星", "月令"]),
    _d("B_NATAL_005", "食伤结构", EngineId.BAZI, FactorCategory.NATAL,
       "食神 + 伤官的出现次数。传统认为食伤为『生财之源』。",
       "count(ten_god ∈ {食神, 伤官})", raw_unit="count",
       normalized_hint="min(count/4, 1)", requires=["ten_god_counts"], tags=["食伤"]),
    _d("B_NATAL_006", "官杀结构", EngineId.BAZI, FactorCategory.NATAL,
       "正官 + 七杀的出现次数。传统认为官杀主约束、规制。",
       "count(ten_god ∈ {正官, 七杀})", raw_unit="count",
       normalized_hint="min(count/4, 1)", requires=["ten_god_counts"], tags=["官杀"]),
    _d("B_NATAL_007", "印星结构", EngineId.BAZI, FactorCategory.NATAL,
       "正印 + 偏印的出现次数。传统认为印星主资源、庇护。",
       "count(ten_god ∈ {正印, 偏印})", raw_unit="count",
       normalized_hint="min(count/4, 1)", requires=["ten_god_counts"], tags=["印星"]),
    _d("B_NATAL_008", "比劫结构", EngineId.BAZI, FactorCategory.NATAL,
       "比肩 + 劫财的出现次数（不含日主本身）。传统认为比劫主竞争、分夺。",
       "count(ten_god ∈ {比肩, 劫财})", raw_unit="count",
       normalized_hint="min(count/4, 1)", requires=["ten_god_counts"], tags=["比劫"]),
    _d("B_NATAL_009", "格局类型", EngineId.BAZI, FactorCategory.NATAL,
       "月令取格所得的格局大类。仅作为分类特征，不对应收益方向。",
       "月令本气/透干取格（子平通行法）", raw_unit="pattern_category",
       normalized_hint="分类变量编码为整数（财格=1/官格=2/印格=3/食伤格=4/比劫格=5/其他=0）",
       requires=["pattern.category"], tags=["格局"]),
    _d("B_NATAL_010", "用神五行", EngineId.BAZI, FactorCategory.NATAL,
       "扶抑法所取用神五行。作为分类特征，不映射为收益方向。",
       "扶抑法（主）+ 调候法（辅）", raw_unit="wuxing",
       normalized_hint="五行编码 木=1/火=2/土=3/金=4/水=5",
       requires=["yong_shen.yong_shen"], tags=["用神"]),
    _d("B_NATAL_011", "五行缺失数", EngineId.BAZI, FactorCategory.NATAL,
       "四柱天干地支中完全未出现的五行个数。传统认为五行偏枯需补。",
       "count(wuxing not in stems+branches)", raw_unit="count",
       normalized_hint="min(count/3, 1)", requires=["wuxing.missing"], tags=["五行"]),
    _d("B_NATAL_012", "五行偏枯度", EngineId.BAZI, FactorCategory.NATAL,
       "五行百分比最大值与最小值之差，衡量原局五行分布的不均衡程度。",
       "max(percentages) - min(percentages)", raw_unit="percentage_point",
       normalized_hint="min(diff/60, 1)", requires=["wuxing.percentages"], tags=["五行"]),
    _d("B_NATAL_013", "原局合冲强度", EngineId.BAZI, FactorCategory.NATAL,
       "原局内部六合/三合/三会（合类）与六冲/相刑/相害（冲类）的数量差。"
       "传统认为合主稳定、冲主变动；本项目仅作为结构变量。",
       "count(合类) - count(冲类)", raw_unit="count",
       normalized_hint="tanh(diff/3)", requires=["relations"], tags=["刑冲合害"]),
    _d("B_NATAL_014", "财星力量占比", EngineId.BAZI, FactorCategory.NATAL,
       "财星五行在五行力量估算中的百分比。",
       "wuxing.percentages[日主所克五行]", raw_unit="percent",
       normalized_hint="percentage/100", requires=["wuxing.percentages"], tags=["财星"]),
    _d("B_NATAL_015", "食伤力量占比", EngineId.BAZI, FactorCategory.NATAL,
       "食伤五行（日主所生）在五行力量估算中的百分比。",
       "wuxing.percentages[日主所生五行]", raw_unit="percent",
       normalized_hint="percentage/100", requires=["wuxing.percentages"], tags=["食伤"]),
    _d("B_NATAL_016", "身财对比", EngineId.BAZI, FactorCategory.NATAL,
       "帮扶力量与财星力量的比值关系，传统『身财两停』概念的量化近似。",
       "(比劫+印) / 财星力量", raw_unit="ratio",
       normalized_hint="tanh(log(ratio))，>0 表示身强于财", requires=["wuxing.scores"], tags=["财星", "旺衰"]),
    _d("B_NATAL_017", "调候适宜度", EngineId.BAZI, FactorCategory.NATAL,
       "按调候法判断原局寒暖燥湿是否需要调候，以及用神是否已含调候五行。",
       "月支季节 + 用神/喜神是否覆盖调候五行", raw_unit="0-3",
       normalized_hint="score/3", requires=["yong_shen.tiaohou_note"], tags=["调候"]),
    _d("B_NATAL_018", "日主阴阳", EngineId.BAZI, FactorCategory.NATAL,
       "日主天干阴阳属性（阳干/阴干）。仅作为分类特征。",
       "STEM_YANG[day_master]", raw_unit="bool",
       normalized_hint="阳→+1，阴→-1", requires=["day_master"], tags=["日主"]),
]

# ---------------------------------------------------------------------------
# B_YEAR_* 流年因子
# ---------------------------------------------------------------------------

YEAR_DEFINITIONS: list[FactorDefinition] = [
    _d("B_YEAR_001", "流年天干喜忌", EngineId.BAZI, FactorCategory.YEAR,
       "流年天干五行相对日主喜用忌神的位置。",
       "classify(流年天干五行 ∈ {用神,喜神,忌神,仇神,闲神})", raw_unit="category",
       normalized_hint="用神→+1，喜神→+0.6，闲神→0，忌神/仇神→-1",
       requires=["current_year_pillar.stem_is"], tags=["流年"]),
    _d("B_YEAR_002", "流年地支喜忌", EngineId.BAZI, FactorCategory.YEAR,
       "流年地支五行相对日主喜用忌神的位置。", "classify(流年地支五行)",
       raw_unit="category", normalized_hint="同 B_YEAR_001",
       requires=["current_year_pillar.branch_is"], tags=["流年"]),
    _d("B_YEAR_003", "流年财星", EngineId.BAZI, FactorCategory.YEAR,
       "流年干支所引动的十神是否属财星。", "十神(流年天干/支藏干) ∈ {正财,偏财}",
       raw_unit="bool/count", normalized_hint="命中→+1，未命中→0",
       requires=["current_year_pillar.stem_ten_god"], tags=["流年", "财星"]),
    _d("B_YEAR_004", "流年食伤", EngineId.BAZI, FactorCategory.YEAR,
       "流年是否引动食伤。", "十神(流年天干/支藏干) ∈ {食神,伤官}",
       raw_unit="bool/count", normalized_hint="命中→+1，未命中→0",
       requires=["current_year_pillar.branch_ten_gods"], tags=["流年", "食伤"]),
    _d("B_YEAR_005", "流年冲原局", EngineId.BAZI, FactorCategory.YEAR,
       "流年地支是否冲原局四支。传统认为冲主变动。",
       "六冲关系匹配数", raw_unit="count", normalized_hint="min(count/2, 1)",
       requires=["current_year_pillar.clashes_with_natal"], tags=["流年", "冲"]),
    _d("B_YEAR_006", "流年合原局", EngineId.BAZI, FactorCategory.YEAR,
       "流年地支是否与原局四支六合。", "六合关系匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_year_pillar.harmonies_with_natal"],
       tags=["流年", "合"]),
    _d("B_YEAR_007", "流年刑原局", EngineId.BAZI, FactorCategory.YEAR,
       "流年地支是否与原局相刑。", "相刑关系匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_year_pillar.punishments_with_natal"],
       tags=["流年", "刑"]),
    _d("B_YEAR_008", "流年害原局", EngineId.BAZI, FactorCategory.YEAR,
       "流年地支是否与原局相害。", "相害关系匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_year_pillar.harms_with_natal"],
       tags=["流年", "害"]),
    _d("B_YEAR_009", "流年十二长生", EngineId.BAZI, FactorCategory.YEAR,
       "日主在流年地支的十二长生阶段。", "twelve_stage(day_master, 流年支)",
       raw_unit="stage", normalized_hint="按长生序映射：长生/临官/帝旺→+1，衰病死墓绝→-1",
       requires=["current_year_pillar.di_shi"], tags=["流年", "旺衰"]),
    _d("B_YEAR_010", "流年三合", EngineId.BAZI, FactorCategory.YEAR,
       "流年支与原局构成三合局。", "三合局匹配", raw_unit="bool",
       normalized_hint="命中→+1，未命中→0", requires=["current_year_pillar.triple_harmonies"],
       tags=["流年", "三合"]),
]

# ---------------------------------------------------------------------------
# B_MONTH_* 流月因子
# ---------------------------------------------------------------------------

MONTH_DEFINITIONS: list[FactorDefinition] = [
    _d("B_MONTH_001", "流月天干喜忌", EngineId.BAZI, FactorCategory.MONTH,
       "流月天干五行相对日主喜用忌神的位置。", "classify(流月天干五行)",
       raw_unit="category", normalized_hint="用神→+1，喜神→+0.6，闲神→0，忌/仇→-1",
       requires=["current_month_pillar.stem_is"], tags=["流月"]),
    _d("B_MONTH_002", "流月地支喜忌", EngineId.BAZI, FactorCategory.MONTH,
       "流月地支五行相对日主喜用忌神的位置。", "classify(流月地支五行)",
       raw_unit="category", normalized_hint="同 B_MONTH_001",
       requires=["current_month_pillar.branch_is"], tags=["流月"]),
    _d("B_MONTH_003", "流月财星引动", EngineId.BAZI, FactorCategory.MONTH,
       "流月干支是否引动财星（十神属财或财星为喜用）。",
       "十神(流月) ∈ {正财,偏财} 或 流月五行 ∈ 喜用",
       raw_unit="bool", normalized_hint="命中→+1，未命中→0",
       requires=["current_month_pillar"], tags=["流月", "财星"]),
    _d("B_MONTH_004", "流月食伤生财", EngineId.BAZI, FactorCategory.MONTH,
       "流月引动食伤，且原局有财星。传统『食伤生财』结构的时点近似。"
       "注意：该结构**不代表**股价上涨。",
       "流月十神 ∈ {食神,伤官} 且 ten_god_counts 含财星", raw_unit="bool",
       normalized_hint="命中→+1，未命中→0", requires=["current_month_pillar", "ten_god_counts"],
       tags=["流月", "食伤", "财星"]),
    _d("B_MONTH_005", "流月官杀变化", EngineId.BAZI, FactorCategory.MONTH,
       "流月是否引动官杀。", "十神(流月) ∈ {正官,七杀}", raw_unit="bool",
       normalized_hint="命中→+1，未命中→0", requires=["current_month_pillar"],
       tags=["流月", "官杀"]),
    _d("B_MONTH_006", "流月三合", EngineId.BAZI, FactorCategory.MONTH,
       "流月支与原局构成三合局。", "三合局匹配", raw_unit="list",
       normalized_hint="命中→+1，未命中→0",
       requires=["current_month_pillar.triple_harmonies"], tags=["流月", "三合"]),
    _d("B_MONTH_007", "流月六合", EngineId.BAZI, FactorCategory.MONTH,
       "流月支与原局支六合的数量。", "六合匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_month_pillar.harmonies_with_natal"],
       tags=["流月", "合"]),
    _d("B_MONTH_008", "流月冲原局", EngineId.BAZI, FactorCategory.MONTH,
       "流月支冲原局支的数量。", "六冲匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_month_pillar.clashes_with_natal"],
       tags=["流月", "冲"]),
    _d("B_MONTH_009", "流月刑原局", EngineId.BAZI, FactorCategory.MONTH,
       "流月支与原局相刑的数量。", "相刑匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_month_pillar.punishments_with_natal"],
       tags=["流月", "刑"]),
    _d("B_MONTH_010", "流月害原局", EngineId.BAZI, FactorCategory.MONTH,
       "流月支与原局相害的数量。", "相害匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_month_pillar.harms_with_natal"],
       tags=["流月", "害"]),
    _d("B_MONTH_011", "流月十神", EngineId.BAZI, FactorCategory.MONTH,
       "流月天干相对日主的十神，作为分类特征。", "ten_god(day_master, 流月干)",
       raw_unit="category", normalized_hint="编码为 0-9 的类别整数",
       requires=["current_month_pillar.stem_ten_god"], tags=["流月", "十神"]),
    _d("B_MONTH_012", "流月十二长生", EngineId.BAZI, FactorCategory.MONTH,
       "日主在流月地支的十二长生阶段。", "twelve_stage(day_master, 流月支)",
       raw_unit="stage", normalized_hint="长生/临官/帝旺→+1，衰病死墓绝→-1",
       requires=["current_month_pillar.di_shi"], tags=["流月", "旺衰"]),
]

# ---------------------------------------------------------------------------
# B_DAY_* 流日因子（用于周度聚合）
# ---------------------------------------------------------------------------

DAY_DEFINITIONS: list[FactorDefinition] = [
    _d("B_DAY_001", "流日天干喜忌", EngineId.BAZI, FactorCategory.DAY,
       "流日天干五行相对日主喜用忌神的位置。", "classify(流日天干五行)",
       raw_unit="category", normalized_hint="用神→+1，喜神→+0.6，闲神→0，忌/仇→-1",
       requires=["current_day_pillar.stem_is"], tags=["流日"]),
    _d("B_DAY_002", "流日冲原局", EngineId.BAZI, FactorCategory.DAY,
       "流日支冲原局支的数量。", "六冲匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_day_pillar.clashes_with_natal"],
       tags=["流日", "冲"]),
    _d("B_DAY_003", "流日合原局", EngineId.BAZI, FactorCategory.DAY,
       "流日支与原局六合的数量。", "六合匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_day_pillar.harmonies_with_natal"],
       tags=["流日", "合"]),
    _d("B_DAY_004", "流日地支喜忌", EngineId.BAZI, FactorCategory.DAY,
       "流日地支五行相对日主喜用忌神的位置。", "classify(流日地支五行)",
       raw_unit="category", normalized_hint="同 B_DAY_001",
       requires=["current_day_pillar.branch_is"], tags=["流日"]),
    _d("B_DAY_005", "流日十神", EngineId.BAZI, FactorCategory.DAY,
       "流日天干相对日主的十神，作为分类特征。", "ten_god(day_master, 流日干)",
       raw_unit="category", normalized_hint="编码 0-9",
       requires=["current_day_pillar.stem_ten_god"], tags=["流日", "十神"]),
    _d("B_DAY_006", "流日十二长生", EngineId.BAZI, FactorCategory.DAY,
       "日主在流日地支的十二长生阶段。", "twelve_stage(day_master, 流日支)",
       raw_unit="stage", normalized_hint="长生/临官/帝旺→+1，衰病死墓绝→-1",
       requires=["current_day_pillar.di_shi"], tags=["流日", "旺衰"]),
    _d("B_DAY_007", "流日刑原局", EngineId.BAZI, FactorCategory.DAY,
       "流日支与原局相刑的数量。", "相刑匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_day_pillar.punishments_with_natal"],
       tags=["流日", "刑"]),
    _d("B_DAY_008", "流日害原局", EngineId.BAZI, FactorCategory.DAY,
       "流日支与原局相害的数量。", "相害匹配数", raw_unit="count",
       normalized_hint="min(count/2, 1)", requires=["current_day_pillar.harms_with_natal"],
       tags=["流日", "害"]),
]

# ---------------------------------------------------------------------------
# H_DAY_* 黄历 × 原局 交叉因子
# ---------------------------------------------------------------------------

HUANGLI_DAY_DEFINITIONS: list[FactorDefinition] = [
    _d("H_DAY_001", "当日天干喜忌", EngineId.HUANGLI, FactorCategory.CROSS,
       "黄历当日天干五行相对股票日主喜用忌神的位置。",
       "classify(当日日干五行 vs 原局喜用忌)", raw_unit="category",
       normalized_hint="用神→+1，喜神→+0.6，闲神→0，忌/仇→-1",
       requires=["huangli.day_ganzhi", "chart.yong_shen"], tags=["黄历", "交叉"]),
    _d("H_DAY_002", "当日地支喜忌", EngineId.HUANGLI, FactorCategory.CROSS,
       "黄历当日地支五行相对股票日主喜用忌神的位置。", "classify(当日日支五行)",
       raw_unit="category", normalized_hint="同 H_DAY_001",
       requires=["huangli.day_ganzhi"], tags=["黄历", "交叉"]),
    _d("H_DAY_003", "当日冲股票日支", EngineId.HUANGLI, FactorCategory.CROSS,
       "当日地支是否冲股票八字的日支（坐下）。传统认为日支为『身位』。",
       "六冲(当日支, 原局日支)", raw_unit="bool",
       normalized_hint="命中→-1，未命中→0", requires=["huangli.day_ganzhi", "chart.day_pillar"],
       tags=["黄历", "冲"]),
    _d("H_DAY_004", "当日合股票日支", EngineId.HUANGLI, FactorCategory.CROSS,
       "当日地支是否与原局日支六合。", "六合(当日支, 原局日支)", raw_unit="bool",
       normalized_hint="命中→+1，未命中→0", requires=["huangli.day_ganzhi", "chart.day_pillar"],
       tags=["黄历", "合"]),
    _d("H_DAY_005", "当日与原局合冲净值", EngineId.HUANGLI, FactorCategory.CROSS,
       "当日地支与原局四支的互动净值：合类命中数 − 冲类命中数。",
       "count(合/六合/三合) − count(冲/刑/害)", raw_unit="count",
       normalized_hint="tanh(net/3)", requires=["huangli.day_ganzhi", "chart"], tags=["黄历", "交叉"]),
    _d("H_DAY_006", "建除十二值", EngineId.HUANGLI, FactorCategory.CROSS,
       "当日建除十二值（建/除/满/平/定/执/破/危/成/收/开/闭）。"
       "传统通书对十二值有吉凶分类，本项目仅作分类特征。",
       "lunar-python getZhiXing()", raw_unit="category",
       normalized_hint="按传统吉凶分类：开/成/定/危/除→偏正，破/闭/平→偏负，其余 0",
       requires=["huangli.duty_officer"], tags=["黄历", "建除"]),
    _d("H_DAY_007", "黄黑道", EngineId.HUANGLI, FactorCategory.CROSS,
       "当日为黄道日或黑道日（十二神所属）。", "lunar-python getDayTianShenType()",
       raw_unit="category", normalized_hint="黄道→+1，黑道→-1",
       requires=["huangli.day_tian_shen_type"], tags=["黄历", "黄黑道"]),
    _d("H_DAY_008", "十二神", EngineId.HUANGLI, FactorCategory.CROSS,
       "当日十二神（青龙/明堂/天刑/朱雀/…）。", "lunar-python getDayTianShen()",
       raw_unit="category", normalized_hint="走 H_DAY_007 的统一映射，本因子保留原始类别",
       requires=["huangli.day_tian_shen"], tags=["黄历", "十二神"]),
    _d("H_DAY_009", "当日与原局关系数", EngineId.HUANGLI, FactorCategory.CROSS,
       "当日地支与原局四支发生刑冲合害的总次数，衡量当日与原局的『互动强度』。",
       "count(全部关系命中)", raw_unit="count", normalized_hint="min(count/4, 1)",
       requires=["huangli.day_ganzhi", "chart"], tags=["黄历", "交叉"]),
    _d("H_DAY_010", "当日纳音五行", EngineId.HUANGLI, FactorCategory.CROSS,
       "当日日柱纳音所属五行相对日主喜用的位置。", "纳音五行 classify",
       raw_unit="wuxing", normalized_hint="喜用→+1，忌→-1，其他 0",
       requires=["huangli.day_nayin"], tags=["黄历", "纳音"]),
    _d("H_DAY_011", "星宿吉凶", EngineId.HUANGLI, FactorCategory.CROSS,
       "当日二十八宿的吉凶属性。", "lunar-python getXiuLuck()", raw_unit="category",
       normalized_hint="吉→+1，凶→-1，其余 0", requires=["huangli.xiu_luck"], tags=["黄历", "星宿"]),
    _d("H_DAY_012", "当日刑股票日支", EngineId.HUANGLI, FactorCategory.CROSS,
       "当日地支是否与原局日支相刑。", "相刑(当日支, 原局日支)", raw_unit="bool",
       normalized_hint="命中→-1，未命中→0", requires=["huangli.day_ganzhi", "chart.day_pillar"],
       tags=["黄历", "刑"]),
]

# ---------------------------------------------------------------------------
# H_MONTH_* 黄历月度聚合因子
# ---------------------------------------------------------------------------

HUANGLI_MONTH_DEFINITIONS: list[FactorDefinition] = [
    _d("H_MONTH_001", "本月黄道日占比", EngineId.HUANGLI, FactorCategory.MONTH,
       "未来一个自然月内黄道日占全部自然日的比例。",
       "count(day_tian_shen_type == 黄道) / days_in_month", raw_unit="ratio",
       normalized_hint="(ratio - 0.5) * 2", requires=["huangli.month_scan"], tags=["黄历", "月度"]),
    _d("H_MONTH_002", "本月吉神日占比", EngineId.HUANGLI, FactorCategory.MONTH,
       "本月 day_tian_shen_luck == 吉 的自然日占比。",
       "count(luck == 吉) / days_in_month", raw_unit="ratio",
       normalized_hint="(ratio - 0.5) * 2", requires=["huangli.month_scan"], tags=["黄历", "月度"]),
    _d("H_MONTH_003", "本月合股票日支天数", EngineId.HUANGLI, FactorCategory.MONTH,
       "本月内当日地支与原局日支六合的自然日数量。", "count(六合)", raw_unit="days",
       normalized_hint="min(days/4, 1)", requires=["huangli.month_scan", "chart.day_pillar"],
       tags=["黄历", "月度", "合"]),
    _d("H_MONTH_004", "本月冲股票日支天数", EngineId.HUANGLI, FactorCategory.MONTH,
       "本月内当日地支与原局日支六冲的自然日数量。", "count(六冲)", raw_unit="days",
       normalized_hint="min(days/4, 1)", requires=["huangli.month_scan", "chart.day_pillar"],
       tags=["黄历", "月度", "冲"]),
    _d("H_MONTH_005", "本月喜神日占比", EngineId.HUANGLI, FactorCategory.MONTH,
       "本月内当日日干或日支五行属于原局喜用神的自然日占比。",
       "count(day ganzhi wuxing ∈ 喜用) / days_in_month", raw_unit="ratio",
       normalized_hint="(ratio - 0.5) * 2", requires=["huangli.month_scan"], tags=["黄历", "月度"]),
]


# Phase 2B：紫微因子（``Z_*``）。使用独立的 rule_version（zv1，观测再按 variant
# 后缀区分为 zv1.fwd / zv1.rev），与八字/黄历因子的修复节奏解耦。
from src.factors.registry.relation_definitions import relation_definitions  # noqa: E402
from src.factors.ziwei.definitions import (  # noqa: E402 - 避免循环导入，置于此处
    ALL_ZIWEI_DEFINITIONS,
)

RELATION_DEFINITIONS: list[FactorDefinition] = relation_definitions()

ALL_DEFINITIONS: list[FactorDefinition] = [
    *NATAL_DEFINITIONS,
    *YEAR_DEFINITIONS,
    *MONTH_DEFINITIONS,
    *DAY_DEFINITIONS,
    *HUANGLI_DAY_DEFINITIONS,
    *HUANGLI_MONTH_DEFINITIONS,
    *ALL_ZIWEI_DEFINITIONS,
]

#: Phase 1 因子（八字 + 黄历）—— 用于"Phase 1 因子未变"的机器校验
PHASE1_DEFINITIONS: list[FactorDefinition] = [
    *NATAL_DEFINITIONS,
    *YEAR_DEFINITIONS,
    *MONTH_DEFINITIONS,
    *DAY_DEFINITIONS,
    *HUANGLI_DAY_DEFINITIONS,
    *HUANGLI_MONTH_DEFINITIONS,
]

#: 因子 ID → 定义
DEFINITION_INDEX: dict[str, FactorDefinition] = {d.factor_id: d for d in ALL_DEFINITIONS}
#: 关系历史研究专用因子定义；不混入个股分析因子集合，避免普通分析误把关系事件当作必算因子。
RELATION_DEFINITION_INDEX: dict[str, FactorDefinition] = {d.factor_id: d for d in RELATION_DEFINITIONS}

#: 因子 ID → 定义（仅 Phase 1 的 65 个），供紫微因子与 Phase 1 因子做隔离校验
PHASE1_DEFINITION_INDEX: dict[str, FactorDefinition] = {
    d.factor_id: d for d in PHASE1_DEFINITIONS
}

#: 每类因子的解释（用于 observation.explanation）
FACTOR_DISCLAIMER = _EXPL
