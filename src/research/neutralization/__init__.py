"""Phase 3E · 市场 / 行业 / 风格中性化。

模块划分
--------
* ``benchmark``    —— 基准策略（统一沪深 300）与 market excess 口径
* ``exposures``    —— 风格暴露（momentum / volatility / 流动性规模代理）
* ``industry``     —— 行业可得性状态 + 板块（segment）控制
* ``cross_section``—— 横截面统计（RankIC / 分组收益 / long-short / 回归）
* ``date_effect``  —— 日期效应分析（黄历"日历开关"结构的 P0 统计修正）
* ``dataset``      —— 3E/3F 共用的研究数据集组装
* ``runner``       —— 中性化执行器与 Q-E1..Q-E5 汇总
"""

from src.research.neutralization.benchmark import (
    MARKET_NEUTRAL_VERSION,
    BenchmarkPolicy,
    benchmark_policy,
)
from src.research.neutralization.exposures import (
    EXPOSURE_VERSION,
    STYLE_EXPOSURE_COLUMNS,
    exposure_availability,
)
from src.research.neutralization.industry import (
    INDUSTRY_CLASSIFICATION_UNAVAILABLE,
    INDUSTRY_VERSION,
    POINT_IN_TIME_INDUSTRY_UNAVAILABLE,
    UnavailableIndustryProvider,
)

__all__ = [
    "EXPOSURE_VERSION",
    "INDUSTRY_CLASSIFICATION_UNAVAILABLE",
    "INDUSTRY_VERSION",
    "MARKET_NEUTRAL_VERSION",
    "POINT_IN_TIME_INDUSTRY_UNAVAILABLE",
    "STYLE_EXPOSURE_COLUMNS",
    "BenchmarkPolicy",
    "UnavailableIndustryProvider",
    "benchmark_policy",
    "exposure_availability",
]
