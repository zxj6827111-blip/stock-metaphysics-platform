"""回归测试：流年关系因子的接线语义（防 B_YEAR_005/007/008 接错再犯）。

Phase 1.1 因子审计发现：B_YEAR_005 曾被接到三合数据上（与 B_YEAR_010 corr=1.0），
刑冲害了了错位、害从未计算——但全部测试恒绿。教训：**断言因子"算的是字典声明的东西"**。

本测试直接构造一个已知干支组合的股票盘，断言各关系因子的 raw_value
与其 factor_definition 声明一致（六合→计数、六冲→计数、刑→计数、害→计数、三合→列表）。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.core.schemas.common import VariantMode
from src.core.schemas.stock import BirthProfileCreateRequest, StockMaster
from src.core.stock.birth_profile import build_birth_profile
from src.engines.bazi.bazi_engine import BaziEngine
from src.factors.registry.compute import compute_factor_set
from src.factors.registry.definitions import DEFINITION_INDEX

#: as_of 落在 2026（丙午年）—— 午年冲子支、害丑支、刑午（自刑看库表）、合未支
AS_OF = datetime(2026, 9, 18, 15, 0)


@pytest.fixture()
def year_factor_map():
    """构造一只日支=子（子未害、子午冲都用得上）的股票盘流年因子集合。"""
    engine = BaziEngine()
    stock = StockMaster(stock_code="600519", name="测试", exchange="SSE",
                        listing_date=__import__("datetime").date(2001, 8, 27))
    profile = build_birth_profile(stock, BirthProfileCreateRequest())
    chart = engine.build_chart(
        birth_datetime=profile.birth_datetime.replace(tzinfo=None),
        as_of=AS_OF, variant_mode=VariantMode.NOT_APPLICABLE, stock_code="600519",
    )
    fset = compute_factor_set(chart, None, AS_OF, stock_code="600519")  # huangli=None 只出 B_*
    return {o.factor_id: o for o in fset.observations}, chart


class TestYearRelationWiring:
    def test_005_is_clash_not_triple(self, year_factor_map):
        obs, chart = year_factor_map
        o5 = obs["B_YEAR_005"]
        o10 = obs["B_YEAR_010"]
        tp = chart.current_year_pillar
        # B_YEAR_005 = 冲原局 → raw_value 必须等于六冲数量，不能与三合相同
        assert o5.raw_value != o10.raw_value or (tp.triple_harmonies and tp.clashes_with_natal)
        # 若该年没有三合局，B_YEAR_005 不能引用 triple
        assert o5.normalized_value != 1.0 or len(tp.clashes_with_natal) >= 2, (
            "没有双重六冲时 normalized 不应为 1（归一化 min(count/2,1)）"
        )

    def test_008_counts_harms(self, year_factor_map):
        obs, _chart = year_factor_map
        assert "B_YEAR_008" in obs, "流年害因子缺失（验收前 bug：从未计算）"

    def test_ids_match_dictionary_semantics(self, year_factor_map):
        """每个流年关系因子的 raw_value 语义必须与字典 requires 声明一致。"""
        obs, chart = year_factor_map
        tp = chart.current_year_pillar
        expected = {
            "B_YEAR_005": len(tp.clashes_with_natal),
            "B_YEAR_006": len(tp.harmonies_with_natal),
            "B_YEAR_007": len(tp.punishments_with_natal),
            "B_YEAR_008": len(tp.harms_with_natal),
        }
        for fid, want in expected.items():
            got = obs[fid].raw_value
            assert got == want, (
                f"{fid}（{DEFINITION_INDEX[fid].name}）raw_value={got} 应为 {want} "
                f"（requires={DEFINITION_INDEX[fid].requires}），接线再次错位"
            )

    def test_factor_rule_version_lifted(self):
        from src.core.config import settings

        assert settings.factor_rule_version == "v1.1", (
            "流年接线修复未经版本提升 —— 不允许在 v1 里静悄悄改语义"
        )
