"""确定性合成行情源（``synthetic_demo``）。

**用途与边界（务必阅读）**

* 用途：在没有网络 / 第三方限流 / 自动化测试环境下，让完整链路
  （行情 → 标签 → 事件研究 → 负对照 → UI）仍然可以**真实跑通**。
* 边界：这不是真实行情！所有数据都带 ``source=synthetic_demo``、
  ``is_degraded=True`` 与 error 级 warning，API 与 UI 必须显著展示该状态。
* 生成方式：以股票代码为随机种子 + 几何布朗运动，保证**同一代码同一日期
  的取值完全可复现**（可重复性要求）。
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

from src.core.schemas.common import MarketDataSource, SourceRef, Warning_
from src.core.schemas.market import Bar, BarSeries
from src.core.schemas.stock import StockMaster
from src.core.stock import codes
from src.market.providers.base import MarketDataProvider

DEFAULT_START = date(2016, 1, 4)


def _seed_for(code: str) -> int:
    return int(hashlib.sha256(code.encode("utf-8")).hexdigest()[:8], 16)


class SyntheticMarketProvider(MarketDataProvider):
    """确定性合成行情（可复现）。"""

    provider_id = "synthetic_demo"

    def __init__(self, *, start: date | None = None) -> None:
        self._start = start or DEFAULT_START

    # ------------------------------------------------------------------
    def search(self, query: str, limit: int = 20) -> list[StockMaster]:
        from src.market.providers.akshare_provider import BUILTIN_STOCKS

        q = (query or "").strip().lower()
        out: list[StockMaster] = []
        for meta in BUILTIN_STOCKS:
            if not q or q in meta["stock_code"] or q in meta["name"]:
                out.append(self.get_stock(meta["stock_code"]))
            if len(out) >= limit:
                break
        if not out and q:
            try:
                out.append(self.get_stock(q))
            except Exception:  # noqa: BLE001
                pass
        return out

    def get_stock(self, code: str) -> StockMaster:
        from src.market.providers.akshare_provider import BUILTIN_STOCKS

        code, exchange, board, wind = codes.parse(code)
        for meta in BUILTIN_STOCKS:
            if meta["stock_code"] == code:
                return StockMaster(
                    stock_code=code, wind_code=wind, name=meta["name"],
                    exchange=exchange, board=board, industry=meta.get("industry", ""),
                    listing_date=date.fromisoformat(meta["listing_date"]),
                    source=SourceRef(source=self.provider_id),
                    data_quality={
                        "grade": "C", "score": 0.5,
                        "notes": ["当前为离线合成模式，股票资料来自内置清单"],
                    },
                )
        return StockMaster(
            stock_code=code, wind_code=wind, exchange=exchange, board=board,
            source=SourceRef(source=self.provider_id),
            data_quality={"grade": "D", "score": 0.2, "notes": ["离线合成模式，无该股票资料"]},
        )

    def get_daily_bars(
        self, code: str, start: date | None = None, end: date | None = None, *, adjust: str = "qfq"
    ) -> BarSeries:
        code = codes.normalize_code(code)
        return self._generate(code, start, end, adjust=adjust, drift=0.0004, vol=0.021)

    def get_benchmark_bars(
        self, index_code: str = "000300", start: date | None = None, end: date | None = None,
        *, adjust: str = "qfq"
    ) -> BarSeries:
        return self._generate(f"IDX{index_code}", start, end, adjust=adjust, drift=0.0002, vol=0.011)

    # ------------------------------------------------------------------
    def _generate(
        self, code: str, start: date | None, end: date | None, *, adjust: str,
        drift: float, vol: float,
    ) -> BarSeries:
        # 延迟导入 numpy：保持模块导入轻量
        import numpy as np

        start = start or self._start
        end = end or date.today()
        if end < start:
            start, end = end, start

        seed = _seed_for(code)
        rng = np.random.default_rng(seed)

        days: list[date] = []
        cursor = start
        while cursor <= end:
            if cursor.weekday() < 5:  # 仅工作日近似交易日
                days.append(cursor)
            cursor += timedelta(days=1)

        n = len(days)
        if n == 0:
            return BarSeries(
                stock_code=code, bars=[], source=MarketDataSource.SYNTHETIC_DEMO,
                source_ref=SourceRef(source=self.provider_id), adjust=adjust, is_degraded=True,
                warnings=[Warning_(code="MARKET_EMPTY", message="合成行情区间为空", severity="error")],
            )

        returns = rng.normal(drift, vol, n)
        base_price = 8.0 + (seed % 400) / 4.0
        closes = base_price * np.exp(np.cumsum(returns))
        opens = closes * (1 + rng.normal(0, 0.004, n))
        highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, 0.006, n)))
        lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, 0.006, n)))
        volumes = np.abs(rng.normal(2.5e7, 9e6, n))
        amounts = volumes * closes

        bars: list[Bar] = []
        prev_close = float(closes[0])
        for i, d in enumerate(days):
            c = float(closes[i])
            pct = (c / prev_close - 1.0) * 100.0 if prev_close else 0.0
            bars.append(Bar(
                trade_date=d,
                open=round(float(opens[i]), 3),
                high=round(float(highs[i]), 3),
                low=round(float(lows[i]), 3),
                close=round(c, 3),
                volume=round(float(volumes[i]), 0),
                amount=round(float(amounts[i]), 0),
                turnover=round(float(volumes[i] / 1e8), 4),
                pct_change=round(pct, 4),
                adjust=adjust,
                source=self.provider_id,
            ))
            prev_close = c

        return BarSeries(
            stock_code=code,
            bars=bars,
            source=MarketDataSource.SYNTHETIC_DEMO,
            source_ref=SourceRef(source=self.provider_id, extra={"seed": seed}),
            adjust=adjust,
            start=bars[0].trade_date,
            end=bars[-1].trade_date,
            is_degraded=True,
            warnings=[Warning_(
                code="MARKET_SYNTHETIC_DATA",
                message=(
                    "当前行情为确定性合成数据（synthetic_demo），"
                    "仅用于系统联调与 UI 演示，不可用于任何投资判断。"
                ),
                severity="error",
                context={"seed": seed, "provider": self.provider_id},
            )],
        )
