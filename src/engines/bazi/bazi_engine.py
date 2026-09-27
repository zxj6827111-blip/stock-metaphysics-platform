"""BaziEngine —— 八字排盘与结构化分析（architecture §21、two_session_plan §7）。

架构说明（ADR-0002）
-------------------
仓库尚未 fork bazi-pro，因此 Phase 1 使用**自研确定性引擎** ``smx-bazi-native``：

* 四柱 / 藏干 / 十神 / 纳音 / 十二长生 → 来自 ``CalendarEngine``（lunar-python，权威历法）
* 五行力量 / 日主旺衰 / 格局 / 喜用忌 / 刑冲合害 → ``src/engines/bazi/rules.py``
  （全部为版本化的确定性规则，含 rationale 与 confidence）

引擎保留 ``backend`` 概念：Phase 2 可挂 bazi-pro adapter 做**双引擎交叉验证**，
不一致时必须写入 ``docs/calculation-differences.md``，禁止静默忽略。

所有输出必须落 ``chart_artifact.raw_chart``，且记录 engine_version / config_version。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from src.core.config import settings
from src.core.constants import (
    BRANCH_HIDDEN_STEMS,
    STEM_WUXING,
    TEN_GOD_GROUP,
    hidden_stem_weight,
    ten_god,
    twelve_stage,
)
from src.core.schemas.bazi import (
    BaziLuckCyclePeriod,
    BaziChart,
    DayMasterAnalysis,
    HiddenStem,
    PatternAnalysis,
    Pillar,
    RelationHit,
    TemporalPillar,
    WuxingStrength,
    YongShenAnalysis,
)
from src.core.schemas.calendar import CalendarSnapshot, GanZhi
from src.core.schemas.common import (
    Assumption,
    Availability,
    SourceRef,
    VariantMode,
    Warning_,
)
from src.engines.base import EngineContext, EngineMetadata, MetaphysicsEngine
from src.engines.bazi import rules
from src.engines.calendar.calendar_engine import CalendarEngine

POSITIONS = ("year", "month", "day", "hour")
RANK_NAMES = ("本气", "中气", "余气")


class BaziEngine(MetaphysicsEngine[BaziChart]):
    """八字引擎。"""

    metadata = EngineMetadata(
        engine_id="bazi",
        display_name="八字引擎",
        engine_version=settings.bazi_engine_version,
        config_version=settings.config_version,
        third_party="6tail/lunar-python（仅历法）+ 自研确定性规则内核",
        third_party_commit="v1.4.8 (PyPI release) / smx-bazi-native",
        notes="bazi-pro 尚未 fork 固定 commit，Phase 1 使用自研确定性规则内核（ADR-0002）",
    )

    def __init__(self, calendar_engine: CalendarEngine | None = None) -> None:
        self._calendar = calendar_engine or CalendarEngine()

    # ------------------------------------------------------------------
    def calculate_chart(  # type: ignore[override]
        self,
        context: EngineContext,
        *,
        birth_datetime: datetime | None = None,
        as_of: datetime | None = None,
        variant_mode: VariantMode = VariantMode.NOT_APPLICABLE,
        stock_code: str | None = None,
        natal_snapshot: CalendarSnapshot | None = None,
        reference_snapshot: CalendarSnapshot | None = None,
        **_: Any,
    ) -> BaziChart:
        """排八字盘。

        Args:
            birth_datetime: 股票"出生时刻"（StockBirthProfile.birth_datetime）。
            as_of: 分析基准时间，用于计算"当前流年 / 流月 / 流日"。
            variant_mode: 运限顺逆变体（股票无性别 → 默认 not_applicable）。
        """
        birth = birth_datetime or context.as_of
        if birth is None:
            raise ValueError("BaziEngine.calculate_chart 需要 birth_datetime 或 context.as_of")
        reference = as_of or context.as_of or datetime.now()
        return self.build_chart(
            birth_datetime=birth,
            as_of=reference,
            variant_mode=variant_mode,
            stock_code=stock_code or context.stock_code or None,
            natal_snapshot=natal_snapshot,
            reference_snapshot=reference_snapshot,
        )

    # ------------------------------------------------------------------
    def build_chart(
        self,
        *,
        birth_datetime: datetime,
        as_of: datetime,
        variant_mode: VariantMode = VariantMode.NOT_APPLICABLE,
        stock_code: str | None = None,
        natal_snapshot: CalendarSnapshot | None = None,
        reference_snapshot: CalendarSnapshot | None = None,
    ) -> BaziChart:
        warnings: list[Warning_] = []
        assumptions: list[Assumption] = []

        natal = natal_snapshot or self._calendar.snapshot(birth_datetime)
        reference = reference_snapshot or self._calendar.snapshot(as_of)

        stems = {
            "year": natal.year_ganzhi.stem,
            "month": natal.month_ganzhi.stem,
            "day": natal.day_ganzhi.stem,
            "hour": natal.hour_ganzhi.stem,
        }
        branches = {
            "year": natal.year_ganzhi.branch,
            "month": natal.month_ganzhi.branch,
            "day": natal.day_ganzhi.branch,
            "hour": natal.hour_ganzhi.branch,
        }
        day_master = stems["day"]

        # --- 四柱 ---
        pillars: dict[str, Pillar] = {}
        ganzhis = {
            "year": natal.year_ganzhi,
            "month": natal.month_ganzhi,
            "day": natal.day_ganzhi,
            "hour": natal.hour_ganzhi,
        }
        for pos in POSITIONS:
            pillars[pos] = self._build_pillar(pos, ganzhis[pos], day_master)

        # --- 五行 / 旺衰 / 格局 / 喜用 ---
        wuxing_score = rules.compute_wuxing_scores(stems, branches)
        strength = rules.compute_strength(stems, branches, wuxing_score)
        pattern = rules.compute_pattern(stems, branches)
        yong = rules.compute_yongshen(strength)

        if pattern.availability != "ok":
            warnings.append(Warning_(
                code="BAZI_PATTERN_UNAVAILABLE",
                message="格局无法可靠判定，已返回 unavailable（禁止业务层自行补算）",
                severity="warning",
            ))
        if pattern.confidence < 0.55:
            warnings.append(Warning_(
                code="BAZI_PATTERN_LOW_CONFIDENCE",
                message=f"格局判定置信度偏低（{pattern.confidence}），不同流派可能存在分歧",
                severity="info",
                context={"confidence": pattern.confidence},
            ))
        if strength.confidence < 0.55:
            warnings.append(Warning_(
                code="BAZI_STRENGTH_LOW_CONFIDENCE",
                message=f"旺衰判定处于临界区间（帮扶占比 {strength.balance_ratio}），置信度 {strength.confidence}",
                severity="info",
                context={"balance_ratio": strength.balance_ratio},
            ))

        # --- 十神统计 ---
        ten_god_counts, group_counts, visible_gods = self._ten_god_stats(pillars, day_master)

        # --- 刑冲合害 ---
        relations = rules.compute_relations(stems, branches)

        # --- 时间流 ---
        current_year = self._build_temporal("year", reference.year_ganzhi, day_master, stems, branches,
                                             self._year_range(as_of))
        current_month = self._build_temporal("month", reference.month_ganzhi, day_master, stems, branches,
                                             self._month_range(as_of))
        current_day = self._build_temporal("day", reference.day_ganzhi, day_master, stems, branches,
                                           (as_of.date(), as_of.date()))

        # --- 运限（股票无性别） ---
        da_yun: list[dict] = []
        if variant_mode == VariantMode.NOT_APPLICABLE:
            da_yun_note = (
                "大运顺逆由性别与年干阴阳共同决定；股票不存在真实性别，"
                "因此 Phase 1 不输出大运，也不将其纳入因子（variant_mode=not_applicable）。"
            )
            assumptions.append(Assumption(
                key="bazi.variant_mode",
                value="not_applicable",
                reason="股票无真实性别，禁止默认按男命或女命起运",
                impact="大运/小限不参与 Phase 1 因子与评分；Phase 2 可并行回测 forward/reverse 两种假设",
            ))
        else:
            da_yun = self._da_yun(birth_datetime, variant_mode)
            da_yun_note = f"运限按 {variant_mode} 假设计算，仅用于研究对比，暂不进入因子。"

        chart = BaziChart(
            stock_code=stock_code,
            birth_datetime=birth_datetime,
            year_pillar=pillars["year"],
            month_pillar=pillars["month"],
            day_pillar=pillars["day"],
            hour_pillar=pillars["hour"],
            day_master=day_master,
            day_master_wuxing=STEM_WUXING[day_master],
            wuxing=WuxingStrength(
                scores=wuxing_score.scores,
                percentages=wuxing_score.percentages,
                dominant=wuxing_score.dominant,
                weakest=wuxing_score.weakest,
                missing=wuxing_score.missing,
            ),
            day_master_analysis=DayMasterAnalysis(
                day_master=day_master,
                day_master_wuxing=strength.day_master_wuxing,
                day_master_yang=self._is_yang(day_master),
                month_branch=strength.month_branch,
                month_season=f"{strength.month_branch}月（{strength.season}，{strength.season_state}）",
                de_ling=strength.de_ling,
                de_di=strength.de_di,
                de_shi=strength.de_shi,
                support_score=strength.support_score,
                drain_score=strength.drain_score,
                balance_ratio=strength.balance_ratio,
                strength_level=strength.strength_level,
                confidence=strength.confidence,
            ),
            pattern=PatternAnalysis(
                primary=pattern.primary,
                category=pattern.category,
                candidates=[
                    {
                        "name": c.get("name") or c.get("god", ""),
                        "basis": c.get("basis") or f"月支{c.get('rank','')}「{c.get('hidden_stem','')}」"
                                                   f"{'透干' if c.get('transparent') else '不透'}",
                        "score": float(c.get("score", 0.0)),
                        "is_primary": c.get("name") == pattern.primary,
                    }
                    for c in pattern.candidates
                ],
                confidence=pattern.confidence,
                availability=Availability(pattern.availability),
                method=pattern.method,
            ),
            yong_shen=YongShenAnalysis(
                yong_shen=yong.yong_shen,
                xi_shen=yong.xi_shen,
                ji_shen=yong.ji_shen,
                chou_shen=yong.chou_shen,
                xian_shen=yong.xian_shen,
                tiaohou_note=yong.tiaohou_note,
                confidence=yong.confidence,
                availability=Availability.OK,
                rationale=yong.rationale,
            ),
            ten_god_counts=ten_god_counts,
            ten_god_group_counts=group_counts,
            visible_ten_gods=visible_gods,
            relations=[RelationHit(**r) for r in relations],
            tai_yuan=self._auxiliary(birth_datetime, "tai_yuan"),
            ming_gong=self._auxiliary(birth_datetime, "ming_gong"),
            shen_gong=self._auxiliary(birth_datetime, "shen_gong"),
            tai_xi=self._auxiliary(birth_datetime, "tai_xi"),
            current_year_pillar=current_year,
            current_month_pillar=current_month,
            current_day_pillar=current_day,
            variant_mode=variant_mode,
            da_yun=da_yun,
            da_yun_note=da_yun_note,
            engine_id=self.engine_id,
            engine_version=self.engine_version,
            config_version=settings.config_version,
            calculated_at=datetime.now(),
            availability=Availability.OK,
            assumptions=assumptions,
            warnings=warnings,
            source=SourceRef(
                source="smx-bazi-native",
                extra={
                    "calendar": "lunar-python 1.4.8",
                    "rules": "src/engines/bazi/rules.py",
                    "as_of": as_of.isoformat(),
                },
            ),
        )

        # 补充依赖 yong_shen 的时间流标注（需要日主喜忌才能判定）
        for tp in (chart.current_year_pillar, chart.current_month_pillar, chart.current_day_pillar):
            if tp is not None:
                self._annotate_temporal(tp, chart.yong_shen)

        return chart

    # ------------------------------------------------------------------
    # 内部构造
    # ------------------------------------------------------------------
    def _build_pillar(self, position: str, gz: GanZhi, day_master: str) -> Pillar:
        hidden: list[HiddenStem] = []
        hidden_gods: list[str] = []
        stems_in_branch = BRANCH_HIDDEN_STEMS.get(gz.branch, ())
        total = len(stems_in_branch)
        for idx, hs in enumerate(stems_in_branch):
            god = ten_god(day_master, hs)
            hidden.append(HiddenStem(
                stem=hs,
                ten_god=god,
                wuxing=STEM_WUXING[hs],
                weight=round(hidden_stem_weight(idx, total), 3),
                rank=RANK_NAMES[idx] if idx < len(RANK_NAMES) else "余气",
            ))
            hidden_gods.append(god)

        stem_god = "日主" if position == "day" else ten_god(day_master, gz.stem)

        return Pillar(
            position=position,
            ganzhi=gz,
            stem_ten_god=stem_god,
            hidden_stems=hidden,
            hidden_ten_gods=hidden_gods,
            nayin=gz.nayin,
            di_shi=twelve_stage(day_master, gz.branch),
        )

    def _ten_god_stats(
        self, pillars: dict[str, Pillar], day_master: str
    ) -> tuple[dict[str, int], dict[str, int], list[str]]:
        counts: dict[str, int] = {}
        visible: list[str] = []
        for pos in POSITIONS:
            if pos == "day":
                continue
            god = pillars[pos].stem_ten_god
            if god:
                counts[god] = counts.get(god, 0) + 1
                visible.append(god)
        for pos in POSITIONS:
            for god in pillars[pos].hidden_ten_gods:
                counts[god] = counts.get(god, 0) + 1

        groups: dict[str, int] = {}
        for god, n in counts.items():
            grp = TEN_GOD_GROUP.get(god, "其他")
            groups[grp] = groups.get(grp, 0) + n
        return counts, groups, visible

    def _build_temporal(
        self,
        kind: str,
        gz: GanZhi,
        day_master: str,
        natal_stems: dict[str, str],
        natal_branches: dict[str, str],
        span: tuple[date, date] | None,
    ) -> TemporalPillar:
        hidden = BRANCH_HIDDEN_STEMS.get(gz.branch, ())
        branch_gods = [ten_god(day_master, hs) for hs in hidden]
        interact = rules.relations_with_external(
            natal_branches, gz.branch, gz.stem, natal_stems=natal_stems
        )
        return TemporalPillar(
            kind=kind,
            label=f"{gz.text}",
            ganzhi=gz,
            start_date=span[0] if span else None,
            end_date=span[1] if span else None,
            stem_ten_god=ten_god(day_master, gz.stem),
            branch_ten_gods=branch_gods,
            di_shi=twelve_stage(day_master, gz.branch),
            clashes_with_natal=interact["clashes"],
            harmonies_with_natal=interact["harmonies"],
            triple_harmonies=interact["triple_harmonies"],
            punishments_with_natal=interact["punishments"],
            harms_with_natal=interact["harms"],
        )

    def _annotate_temporal(self, tp: TemporalPillar, yong: YongShenAnalysis) -> None:
        """标注流年/流月/流日干支与喜用忌的关系。"""
        favor = set(yong.yong_shen) | set(yong.xi_shen)
        against = set(yong.ji_shen) | set(yong.chou_shen)

        def classify(wx: str) -> str:
            if wx in yong.yong_shen:
                return "用神"
            if wx in favor:
                return "喜神"
            if wx in against:
                return "忌神"
            return "闲神"

        tp.stem_is = classify(tp.ganzhi.stem_wuxing)
        tp.branch_is = classify(tp.ganzhi.branch_wuxing)

        bits: list[str] = []
        if tp.stem_is in ("用神", "喜神"):
            bits.append(f"天干{gz_label(tp.ganzhi.stem, tp.stem_is)}")
        if tp.branch_is in ("用神", "喜神"):
            bits.append(f"地支{gz_label(tp.ganzhi.branch, tp.branch_is)}")
        if tp.clashes_with_natal:
            bits.append(f"冲原局{','.join(tp.clashes_with_natal)}")
        if tp.triple_harmonies:
            bits.append("形成" + "、".join(tp.triple_harmonies))
        tp.note = "；".join(bits) if bits else "与原局无显著互动"

    # ------------------------------------------------------------------
    def _da_yun(self, birth_datetime: datetime, variant_mode: VariantMode) -> list[dict]:
        """按 variant_mode 计算大运（仅研究用）。

        注意：Phase 1 默认不启用（股票无性别）。此处只在显式传入
        forward/reverse 时计算，用于 Phase 2 的历史对比实验。
        """
        try:
            yun = self._build_yun_adapter(birth_datetime, variant_mode)
            return [
                {
                    "start_year": d.getStartYear(),
                    "end_year": d.getEndYear(),
                    "ganzhi": d.getGanZhi(),
                    "start_age": d.getStartAge(),
                }
                for d in yun.getDaYun()[:10]
            ]
        except Exception:  # noqa: BLE001 - 大运为可选研究字段
            return []

    def build_luck_cycle_periods(
        self,
        birth_datetime: datetime,
        variant_mode: VariantMode,
        *,
        count: int = 12,
    ) -> list[BaziLuckCyclePeriod]:
        """把同一 lunar-python 排运结果扩展为可比较的左闭右开时间区间。

        ``getStartSolar`` 与 ``Solar.nextYear`` 负责处理起运锚点和年界，
        这里不再复制起运年龄换算。只有明确的兼容参数才允许调用。
        """

        if birth_datetime.tzinfo is None or birth_datetime.utcoffset() is None:
            raise ValueError("大运出生时刻必须带时区")
        if variant_mode not in {VariantMode.FORWARD, VariantMode.REVERSE}:
            return []
        if count < 1:
            raise ValueError("大运周期数量必须大于零")

        yun = self._build_yun_adapter(birth_datetime, variant_mode)
        first_start = yun.getStartSolar()
        tzinfo = birth_datetime.tzinfo
        periods: list[BaziLuckCyclePeriod] = []
        for dayun in yun.getDaYun(count + 1):
            index = int(dayun.getIndex())
            if index < 1:
                continue
            start_solar = first_start.nextYear((index - 1) * 10)
            end_solar = first_start.nextYear(index * 10)
            periods.append(
                BaziLuckCyclePeriod(
                    index=index,
                    start_year=int(dayun.getStartYear()),
                    end_year=int(dayun.getEndYear()),
                    start_age=int(dayun.getStartAge()),
                    end_age=int(dayun.getEndAge()),
                    ganzhi=str(dayun.getGanZhi()),
                    start_at=self._solar_to_aware_datetime(start_solar, tzinfo),
                    end_at=self._solar_to_aware_datetime(end_solar, tzinfo),
                )
            )
        return periods

    @staticmethod
    def _build_yun_adapter(birth_datetime: datetime, variant_mode: VariantMode):
        """唯一的 lunar-python 大运 Adapter 入口。"""

        gender_flag = 1 if variant_mode == VariantMode.FORWARD else 0
        from lunar_python import Solar

        lunar = Solar.fromYmdHms(
            birth_datetime.year, birth_datetime.month, birth_datetime.day,
            birth_datetime.hour, birth_datetime.minute, birth_datetime.second or 0,
        ).getLunar()
        return lunar.getEightChar().getYun(gender_flag)

    @staticmethod
    def _solar_to_aware_datetime(solar: Any, tzinfo) -> datetime:
        return datetime(
            int(solar.getYear()), int(solar.getMonth()), int(solar.getDay()),
            int(solar.getHour()), int(solar.getMinute()), int(solar.getSecond()),
            tzinfo=tzinfo,
        )

    def _auxiliary(self, birth_datetime: datetime, which: str) -> str:
        """胎元 / 命宫 / 身宫 / 胎息。"""
        try:
            from lunar_python import Solar

            ec = Solar.fromYmdHms(
                birth_datetime.year, birth_datetime.month, birth_datetime.day,
                birth_datetime.hour, birth_datetime.minute, birth_datetime.second or 0,
            ).getLunar().getEightChar()
            return {
                "tai_yuan": ec.getTaiYuan,
                "ming_gong": ec.getMingGong,
                "shen_gong": ec.getShenGong,
                "tai_xi": ec.getTaiXi,
            }[which]()
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _is_yang(stem: str) -> bool:
        from src.core.constants import STEM_YANG

        return STEM_YANG.get(stem, True)

    @staticmethod
    def _year_range(as_of: datetime) -> tuple[date, date]:
        return (date(as_of.year, 1, 1), date(as_of.year, 12, 31))

    @staticmethod
    def _month_range(as_of: datetime) -> tuple[date, date]:
        first = date(as_of.year, as_of.month, 1)
        if as_of.month == 12:
            last = date(as_of.year, 12, 31)
        else:
            last = date(as_of.year, as_of.month + 1, 1) - timedelta(days=1)
        return (first, last)

    # ------------------------------------------------------------------
    def collect_assumptions(self) -> list[Assumption]:
        return [
            Assumption(
                key="bazi.engine_backend",
                value="smx-bazi-native",
                reason="bazi-pro 尚未 fork 固定 commit（ADR-0002）",
                impact="Phase 2 需接入 bazi-pro 做双引擎交叉验证",
            ),
            Assumption(
                key="bazi.wuxing_weights",
                value="天干1.0 / 月支×1.5 / 日支×1.2 / 藏干本气0.6-中气0.3-余气0.1",
                reason="五行力量估算是工程近似，不同流派算法差异较大",
                impact="影响旺衰、喜用神判定；所有相关因子带 rule_version，可回归对比",
            ),
        ]


def gz_label(text: str, label: str) -> str:
    return f"{text}为{label}"


def get_bazi_engine() -> BaziEngine:
    return BaziEngine()
