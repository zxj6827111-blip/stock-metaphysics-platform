"""紫微引擎测试（Phase 2A）。

分两类
------
1. **快照契约测试**（永远运行，不依赖 Node）：读 `tests/fixtures/ziwei/*.json`
   （真实 iztro 2.6.1 输出经 Adapter 映射的结果），验证 Schema、不变量、方向变体语义。
2. **实时测试**（`@pytest.mark.ziwei_live`）：直接调用 `services/ziwei-service`，
   确认当前环境的真实实现与快照口径一致。缺少 node / 未构建时跳过（并在报告中说明）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from src.core.schemas.common import Availability, VariantMode
from src.core.schemas.ziwei import ZiweiChart
from src.engines.base import EngineContext, MetaphysicsEngine
from src.engines.ziwei import constants as zc
from src.engines.ziwei.ziwei_engine import (
    TIME_INDEX_RANGES,
    ZiweiEngine,
    ZiweiUnavailableError,
    hour_to_time_index,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ziwei"
MANIFEST = json.loads((FIXTURE_DIR / "_manifest.json").read_text(encoding="utf-8"))
CASE_NAMES = [c["name"] for c in MANIFEST["cases"]]


def load_chart(name: str) -> ZiweiChart:
    return ZiweiChart.model_validate(
        json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    )


def live_transport():  # type: ignore[no-untyped-def]
    from src.engines.ziwei.transport import SubprocessZiweiTransport

    return SubprocessZiweiTransport()


LIVE = live_transport().available()
live_only = pytest.mark.skipif(
    not LIVE,
    reason="本机缺少 node 或 services/ziwei-service 未构建（make ziwei-build）",
)


# ---------------------------------------------------------------------------
# 1. 静态映射与工具函数
# ---------------------------------------------------------------------------


class TestTimeIndexMapping:
    def test_hour_boundaries(self):
        cases = {
            0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3, 7: 4, 8: 4, 9: 5, 10: 5,
            11: 6, 12: 6, 13: 7, 14: 7, 15: 8, 16: 8, 17: 9, 18: 9, 19: 10,
            20: 10, 21: 11, 22: 11, 23: 12,
        }
        for hour, expected in cases.items():
            got = hour_to_time_index(datetime(2024, 1, 1, hour, 30))
            assert got == expected, f"{hour} 时映射错误：{got} != {expected}"

    def test_late_zishi_is_index_12_not_next_day(self):
        """晚子时（23:00-24:00）必须映射到 12，而不是次日子时 0。

        这是显式固化的流派口径（ADR-0010），不是默认行为。
        """
        assert hour_to_time_index(datetime(2024, 1, 1, 23, 59)) == 12
        assert hour_to_time_index(datetime(2024, 1, 2, 0, 0)) == 0

    def test_ranges_cover_full_day(self):
        assert TIME_INDEX_RANGES[0][0] == 0
        assert TIME_INDEX_RANGES[-1][1] == 24
        assert len(TIME_INDEX_RANGES) == 13, "0..12 共 13 个时辰序号"
        for (_s1, e1), (s2, _e2) in zip(TIME_INDEX_RANGES, TIME_INDEX_RANGES[1:], strict=False):
            assert e1 == s2, f"时辰区间不连续：{_s1}-{e1} 与 {s2}"


class TestSelfOwnedTables:
    def test_palace_branch_order_starts_at_yin(self):
        assert zc.ZIWEI_PALACE_BRANCHES[0] == "寅"
        assert len(zc.ZIWEI_PALACE_BRANCHES) == 12

    def test_trine_indices_fixed_structure(self):
        assert zc.trine_indices(0) == [0, 6, 8, 4]
        assert zc.trine_indices(11) == [11, 5, 7, 3]

    def test_major_stars_are_14(self):
        assert len(zc.MAJOR_STARS) == 14

    def test_star_category_classification(self):
        assert zc.star_category("紫微") == "major"
        assert zc.star_category("左辅") == "lucky"
        assert zc.star_category("禄存") == "wealth_move"
        assert zc.star_category("擎羊") == "malefic"
        assert zc.star_category("红鸾") == "flower"
        assert zc.star_category("天刑") == "adjective"

    def test_brightness_scores_ordered(self):
        assert zc.brightness_score("庙") > zc.brightness_score("旺") > zc.brightness_score("平")
        assert zc.brightness_score("陷") < 0
        assert zc.brightness_score("未知") == 0.0


# ---------------------------------------------------------------------------
# 2. 快照契约
# ---------------------------------------------------------------------------


class TestZiweiChartContract:
    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_twelve_palaces_with_fixed_branches(self, name):
        chart = load_chart(name)
        assert len(chart.palaces) == 12
        for i, p in enumerate(chart.palaces):
            assert p.index == i, "宫位 index 必须等于数组下标（坐标系契约）"
            assert p.earthly_branch == zc.ZIWEI_PALACE_BRANCHES[i], (
                f"第 {i} 宫地支应为 {zc.ZIWEI_PALACE_BRANCHES[i]}，实际 {p.earthly_branch}"
            )

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_palace_names_are_the_canonical_twelve(self, name):
        chart = load_chart(name)
        got = sorted(zc.canonical_palace_name(p.name) for p in chart.palaces)
        assert got == sorted(zc.ZIWEI_PALACE_NAMES), f"宫名集合异常：{got}"

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_soul_and_body_palace_resolved(self, name):
        chart = load_chart(name)
        assert 0 <= chart.soul_palace_index <= 11
        assert 0 <= chart.body_palace_index <= 11
        assert chart.palaces[chart.soul_palace_index].name == "命宫"
        assert chart.palaces[chart.body_palace_index].is_body_palace is True

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_trine_indices_match_local_rule(self, name):
        """三方四正必须与本项目自持的索引规则一致（对拍 iztro surroundedPalaces）。"""
        chart = load_chart(name)
        for p in chart.palaces:
            assert p.trine_indices == zc.trine_indices(p.index), (
                f"{p.name}宫({p.index}) 三方四正 {p.trine_indices} != {zc.trine_indices(p.index)}"
            )
        soul_trine = [p.name for p in chart.trine_of(chart.soul_palace_index)]
        assert soul_trine[0] == "命宫"
        assert set(soul_trine[1:]) == {"迁移", "财帛", "官禄"}

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_natal_mutagens_are_four_distinct(self, name):
        chart = load_chart(name)
        assert [m.mutagen for m in chart.natal_mutagens] == list(zc.MUTAGEN_ORDER), (
            "生年四化必须恰好是 禄/权/科/忌 各一，顺序固定"
        )
        for m in chart.natal_mutagens:
            assert m.star, "四化必须落在具体星曜上"
            assert chart.palaces[m.palace_index].name == m.palace_name

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_horoscope_layers_present_with_12_slots(self, name):
        chart = load_chart(name)
        assert chart.horoscope is not None
        for scope in ("decadal", "age", "yearly", "monthly", "daily"):
            sec = getattr(chart.horoscope, scope)
            assert sec is not None, f"缺少 {scope} 运限层"
            assert sec.scope == scope
            assert len(sec.palace_names) == 12, f"{scope}.palace_names 必须 12 项"
            assert len(sec.mutagen) == 4, f"{scope}.mutagen 必须是 禄/权/科/忌"
            if scope == "age":
                # iztro 的小限层**不提供流曜**（实测：stars 字段不存在）。
                # 这里锁定"缺失被如实保留"，防止未来有人用推算补全它。
                assert sec.stars == [], "小限层不应有 stars（iztro 不提供）"
                assert sec.nominal_age is not None
            else:
                assert len(sec.stars) == 12, f"{scope}.stars 必须 12 项"

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_only_age_layer_carries_nominal_age(self, name):
        chart = load_chart(name)
        assert chart.horoscope.age.nominal_age is not None
        for scope in ("yearly", "monthly", "daily"):
            assert getattr(chart.horoscope, scope).nominal_age is None

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_horoscope_yearly_palace_names_form_a_permutation(self, name):
        """流年十二宫名必须是全部 12 宫名的一个排列（流年命宫一定在某一宫上）。"""
        chart = load_chart(name)
        names = chart.horoscope.yearly.palace_names
        assert sorted(names) == sorted(zc.ZIWEI_PALACE_NAMES)
        assert names.count("命宫") == 1

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_metadata_recorded(self, name):
        chart = load_chart(name)
        assert chart.engine_version.startswith("iztro-2.6.1")
        assert chart.config_version
        assert "iztro" in chart.third_party
        assert isinstance(chart.calculated_at, datetime)

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_assumptions_include_no_gender_statement(self, name):
        chart = load_chart(name)
        keys = {a.key for a in chart.assumptions}
        assert "ziwei.variant_mode" in keys
        assert "ziwei.stock_mapping" in keys
        variant_assumption = next(a for a in chart.assumptions if a.key == "ziwei.variant_mode")
        assert "性别" in variant_assumption.reason
        assert "不是两条独立证据" in variant_assumption.impact

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_five_elements_class_is_known(self, name):
        chart = load_chart(name)
        assert chart.five_elements_class in zc.FIVE_ELEMENTS_CLASS

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_star_names_are_non_empty_strings(self, name):
        chart = load_chart(name)
        for p in chart.palaces:
            for s in p.all_stars():
                assert s.name and isinstance(s.name, str)


class TestGoldenSnapshotsStable:
    """快照本身必须能重新序列化为同一内容（防止 Schema 丢字段）。"""

    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_roundtrip_is_lossless(self, name):
        raw = json.loads((FIXTURE_DIR / f"{name}.json").read_text(encoding="utf-8"))
        chart = ZiweiChart.model_validate(raw)
        dumped = chart.model_dump(mode="json")
        assert dumped == raw, "ZiweiChart 往返序列化丢字段（Schema 与快照不一致）"


class TestVariantSemantics:
    """ADR-0010 的核心断言：variant 只影响方向相关字段。"""

    def test_forward_and_reverse_differ_only_in_direction_fields(self):
        fwd = load_chart("600519-listing-forward")
        rev = load_chart("600519-listing-reverse")

        # --- 必须不同：大限/小限/长生十二神/博士十二神/运限的 decadal,age 层 ---
        assert fwd.palaces[0].decadal_range != rev.palaces[0].decadal_range
        assert fwd.palaces[0].ages != rev.palaces[0].ages
        assert [p.changsheng12 for p in fwd.palaces] != [p.changsheng12 for p in rev.palaces]
        assert fwd.horoscope.decadal.index != rev.horoscope.decadal.index
        assert fwd.horoscope.age.index != rev.horoscope.age.index

        # --- 必须相同：宫名 / 宫干支 / 星曜 / 四化 / 三方四正 / 流年流月流日 ---
        for a, b in zip(fwd.palaces, rev.palaces, strict=True):
            assert a.index == b.index
            assert a.name == b.name
            assert a.heavenly_stem == b.heavenly_stem
            assert a.earthly_branch == b.earthly_branch
            assert a.major_stars == b.major_stars
            assert a.minor_stars == b.minor_stars
            assert a.adjective_stars == b.adjective_stars
            assert a.trine_indices == b.trine_indices
            assert a.is_body_palace == b.is_body_palace

        assert fwd.natal_mutagens == rev.natal_mutagens
        assert fwd.soul_palace_index == rev.soul_palace_index
        assert fwd.body_palace_index == rev.body_palace_index
        assert fwd.five_elements_class == rev.five_elements_class
        assert fwd.chinese_date == rev.chinese_date

        for scope in ("yearly", "monthly", "daily"):
            a = getattr(fwd.horoscope, scope)
            b = getattr(rev.horoscope, scope)
            assert a.palace_names == b.palace_names, f"{scope} 不应随 variant 变化"
            assert a.stars == b.stars, f"{scope} 星曜不应随 variant 变化"
            assert a.mutagen == b.mutagen, f"{scope} 四化不应随 variant 变化"

    def test_variant_basis_is_readable_and_honest(self):
        fwd = load_chart("600519-listing-forward")
        rev = load_chart("600519-listing-reverse")
        assert "顺行" in fwd.variant_basis
        assert "逆行" in rev.variant_basis
        for c in (fwd, rev):
            assert "股票无真实性别" in c.variant_basis

    def test_gender_parameter_recorded_but_labelled_as_audit_only(self):
        """gender_parameter 必须保存，但字段语义是"实现方向的参数"，不是股票性别。"""
        fwd = load_chart("600519-listing-forward")   # 辛巳（阴年）顺行 → 女
        rev = load_chart("600519-listing-reverse")   # 辛巳（阴年）逆行 → 男
        assert fwd.gender_parameter == "女"
        assert rev.gender_parameter == "男"
        doc = (ZiweiChart.model_fields["gender_parameter"].description or "")
        assert "仅供审计" in doc
        assert "不代表股票有性别" in doc


# ---------------------------------------------------------------------------
# 3. 引擎行为（不依赖真实服务）
# ---------------------------------------------------------------------------


class _StubTransport:
    """把快照当作"服务返回"，用于验证引擎装配逻辑。"""

    name = "stub"

    def __init__(self, chart: ZiweiChart) -> None:
        self.chart = chart
        self.calls: list[list[dict]] = []

    def available(self) -> bool:
        return True

    def describe(self) -> str:
        return "stub"

    def batch(self, requests: list[dict]) -> list[ZiweiChart]:
        self.calls.append(requests)
        return [self.chart.model_copy(deep=True) for _ in requests]


class _DownTransport:
    name = "none"

    def available(self) -> bool:
        return False

    def describe(self) -> str:
        return "服务故意下线（测试故障隔离）"

    def batch(self, requests: list[dict]):  # type: ignore[no-untyped-def]
        raise AssertionError("不可用时不应被调用")


class TestEngineContract:
    def test_implements_metaphysics_engine(self):
        assert issubclass(ZiweiEngine, MetaphysicsEngine)

    def test_metadata_complete(self):
        meta = ZiweiEngine.metadata
        assert meta.engine_id == "ziwei"
        assert meta.engine_version.startswith("iztro-2.6.1")
        assert "iztro" in meta.third_party
        assert meta.display_name

    def test_not_applicable_refuses_to_chart(self):
        """默认 variant 必须拒绝排盘，而不是偷偷用男命。"""
        engine = ZiweiEngine(transport=_StubTransport(load_chart(CASE_NAMES[0])))  # type: ignore[arg-type]
        with pytest.raises(ZiweiUnavailableError) as exc:
            engine.calculate_chart(
                EngineContext(stock_code="600519"),
                birth_datetime=datetime(2001, 8, 27, 9, 30),
            )
        assert "not_applicable" in str(exc.value)
        assert "性别" in str(exc.value)

    def test_unavailable_transport_raises_with_reason(self):
        engine = ZiweiEngine(transport=_DownTransport())  # type: ignore[arg-type]
        assert engine.availability == Availability.UNAVAILABLE
        assert "故意下线" in engine.unavailable_reason()
        with pytest.raises(ZiweiUnavailableError):
            engine.calculate_chart(
                EngineContext(stock_code="600519"),
                birth_datetime=datetime(2001, 8, 27, 9, 30),
                variant_mode=VariantMode.FORWARD,
            )

    def test_unavailable_produces_warning_not_zero_score(self):
        engine = ZiweiEngine(transport=_DownTransport())  # type: ignore[arg-type]
        warnings = engine.collect_warnings()
        assert any(w.code == "ZIWEI_SERVICE_UNAVAILABLE" for w in warnings)
        # 引擎自身不产出分数；拿不到分数时应为 None，而不是 0
        assert engine.score([])["score"] is None

    def test_engine_stamps_context_and_metadata(self):
        stub = _StubTransport(load_chart(CASE_NAMES[0]))
        engine = ZiweiEngine(transport=stub)  # type: ignore[arg-type]
        chart = engine.calculate_chart(
            EngineContext(stock_code="600519", as_of=datetime(2024, 11, 15, 14, 32)),
            birth_datetime=datetime(2001, 8, 27, 9, 30),
            as_of=datetime(2024, 11, 15, 14, 32),
            variant_mode=VariantMode.FORWARD,
        )
        assert chart.stock_code == "600519"
        assert chart.birth_datetime == datetime(2001, 8, 27, 9, 30)
        assert chart.engine_version == ZiweiEngine.metadata.engine_version
        assert chart.assumptions, "引擎必须写入 assumptions"
        assert {a.key for a in chart.assumptions} >= {"ziwei.variant_mode", "ziwei.stock_mapping"}
        # 传给服务的请求参数
        req = stub.calls[0][0]
        assert req["solarDate"] == "2001-8-27"
        assert req["timeIndex"] == 5
        assert req["variantMode"] == "variant_forward"
        assert req["asOfDate"] == "2024-11-15"

    def test_extract_factors_is_empty_by_design(self):
        """因子必须只有一条计算入口（src/factors/ziwei/），引擎不重复实现。"""
        engine = ZiweiEngine(transport=_StubTransport(load_chart(CASE_NAMES[0])))  # type: ignore[arg-type]
        assert engine.extract_factors(load_chart(CASE_NAMES[0]), EngineContext()) == []

    def test_explain_rules_never_asserts_price_direction(self):
        engine = ZiweiEngine(transport=_DownTransport())  # type: ignore[arg-type]
        lines = engine.explain_rules(load_chart(CASE_NAMES[0]), [])
        text = "".join(lines)
        for forbidden in ("必涨", "一定上涨", "保证上涨", "利好股价", "上涨概率"):
            assert forbidden not in text
        assert "不构成" in text

    def test_evidence_query_terms_are_ziwei_domain(self):
        engine = ZiweiEngine(transport=_DownTransport())  # type: ignore[arg-type]
        q = engine.build_evidence_query(load_chart(CASE_NAMES[0]), [])
        assert q, "紫微引擎必须能构造古籍检索词"
        assert any("命" in x for x in q)


# ---------------------------------------------------------------------------
# 4. 实时服务（需要 node + 已构建服务）
# ---------------------------------------------------------------------------


@live_only
class TestLiveService:
    """直接调用真实服务，确认快照口径与当前实现一致。"""

    @pytest.mark.ziwei_live
    def test_transport_reports_available(self):
        t = live_transport()
        assert t.available(), t.describe()

    @pytest.mark.ziwei_live
    @pytest.mark.parametrize("name", CASE_NAMES)
    def test_live_matches_snapshot(self, name):
        """实时服务的输出必须与冻结快照逐字段一致（口径漂移会被立刻发现）。"""
        case = next(c for c in MANIFEST["cases"] if c["name"] == name)
        engine = ZiweiEngine(transport=live_transport())
        mode = (VariantMode.FORWARD if case["variant_mode"] == "variant_forward"
                else VariantMode.REVERSE)
        y, m, d = (int(x) for x in case["solar_date"].split("-"))
        birth = datetime(y, m, d, TIME_INDEX_RANGES[case["time_index"]][0], 30)
        ay, am, ad = (int(x) for x in case["as_of"].split("-"))
        as_of = datetime(ay, am, ad, TIME_INDEX_RANGES[case["as_of_time_index"]][0], 30)

        chart = engine.calculate_chart(
            EngineContext(stock_code="FIXTURE", as_of=as_of),
            birth_datetime=birth,
            as_of=as_of,
            variant_mode=mode,
        )
        snap = load_chart(name)
        assert chart.chinese_date == snap.chinese_date
        assert chart.lunar_date == snap.lunar_date
        assert chart.five_elements_class == snap.five_elements_class
        assert chart.soul_palace_index == snap.soul_palace_index
        assert chart.body_palace_index == snap.body_palace_index
        assert [p.name for p in chart.palaces] == [p.name for p in snap.palaces]
        assert [p.heavenly_stem + p.earthly_branch for p in chart.palaces] == \
               [p.heavenly_stem + p.earthly_branch for p in snap.palaces]
        assert [(m.mutagen, m.star, m.palace_index) for m in chart.natal_mutagens] == \
               [(m.mutagen, m.star, m.palace_index) for m in snap.natal_mutagens]
        assert [p.decadal_range for p in chart.palaces] == [p.decadal_range for p in snap.palaces]
        # 完整盘面（除时间戳与 stock_code）必须逐字段一致
        drop = {"calculated_at", "stock_code"}
        assert chart.model_dump(mode="json", exclude=drop) == snap.model_dump(mode="json", exclude=drop)

    @pytest.mark.ziwei_live
    def test_live_is_deterministic(self):
        engine = ZiweiEngine(transport=live_transport())
        kwargs = dict(
            birth_datetime=datetime(2001, 8, 27, 9, 30),
            as_of=datetime(2024, 11, 15, 14, 32),
            variant_mode=VariantMode.FORWARD,
        )
        a = engine.calculate_chart(EngineContext(stock_code="600519"), **kwargs)  # type: ignore[arg-type]
        b = engine.calculate_chart(EngineContext(stock_code="600519"), **kwargs)  # type: ignore[arg-type]
        da = a.model_dump(mode="json", exclude={"calculated_at"})
        db = b.model_dump(mode="json", exclude={"calculated_at"})
        assert da == db, "紫微排盘必须可复现（同输入同输出）"

    @pytest.mark.ziwei_live
    def test_live_batch_returns_in_order(self):
        t = live_transport()
        reqs = [
            {"solarDate": "2001-08-27", "timeIndex": 5, "variantMode": "variant_forward",
             "asOfDate": "2024-11-15", "asOfTimeIndex": 7},
            {"solarDate": "1991-04-03", "timeIndex": 5, "variantMode": "variant_forward",
             "asOfDate": "2024-11-15", "asOfTimeIndex": 7},
        ]
        charts = t.batch(reqs)
        assert len(charts) == 2, "批量返回必须按请求顺序一一对应"
        assert charts[0].solar_date == "2001-08-27"
        assert charts[1].solar_date == "1991-04-03"

    @pytest.mark.ziwei_live
    def test_live_rejects_invalid_variant_with_message(self):
        t = live_transport()
        from src.engines.ziwei.transport import ZiweiRequestError

        with pytest.raises(ZiweiRequestError) as exc:
            t.batch([{"solarDate": "2001-08-27", "timeIndex": 5, "variantMode": "not_applicable"}])
        assert "性别" in str(exc.value) or "variant" in str(exc.value)
