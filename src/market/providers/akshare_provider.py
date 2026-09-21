"""AKShare 行情适配器（唯一允许 ``import akshare`` 的位置之一）。

降级链路（保证"第三方挂了应用不崩"）：

    1. 本地 SQLite 缓存命中且未过期 → 直接用缓存（``source=cache``）
    2. 调用 AKShare，带 retry + 指数退避
    3. 调用失败 → 若有历史缓存（即使过期）→ 用缓存并标 ``is_degraded``
    4. 仍失败 → 若允许 → 使用确定性合成行情 ``synthetic_demo``，
       显式标注 ``is_degraded=True`` 与 warning，**绝不伪装成真实数据**
    5. 否则抛出结构化 ``ProviderUnavailableError``

另外提供 ``offline`` 模式（``SMP_MARKET_PROVIDER=synthetic``），
用于无网络环境的开发与自动化测试。
"""

from __future__ import annotations

import time
from datetime import date, datetime

import pandas as pd

from src.core.config import settings
from src.core.schemas.common import MarketDataSource, SourceRef, Warning_
from src.core.schemas.market import BarSeries
from src.core.schemas.stock import StockMaster
from src.core.stock import codes
from src.core.stock.exchange_sessions import ex_value
from src.db.models import MarketFetchLogRow
from src.market.normalization.errors import (
    ProviderUnavailableError,
    SymbolNotFoundError,
)
from src.market.normalization.frames import build_series, detect_anomalies
from src.market.providers.base import MarketDataProvider
from src.market.providers.synthetic import SyntheticMarketProvider

# 内置的常用股票兜底清单（当 AKShare 全挂且无缓存时，至少能识别主流标的）
BUILTIN_STOCKS: list[dict] = [
    {"stock_code": "600519", "name": "贵州茅台", "listing_date": "2001-08-27", "industry": "白酒"},
    {"stock_code": "000001", "name": "平安银行", "listing_date": "1991-04-03", "industry": "银行"},
    {"stock_code": "300750", "name": "宁德时代", "listing_date": "2018-06-11", "industry": "电池"},
    {"stock_code": "600036", "name": "招商银行", "listing_date": "2002-04-09", "industry": "银行"},
    {"stock_code": "000858", "name": "五粮液", "listing_date": "1998-04-27", "industry": "白酒"},
    {"stock_code": "601318", "name": "中国平安", "listing_date": "2007-03-01", "industry": "保险"},
    {"stock_code": "002594", "name": "比亚迪", "listing_date": "2011-06-30", "industry": "汽车整车"},
    {"stock_code": "688981", "name": "中芯国际", "listing_date": "2020-07-16", "industry": "半导体"},
    {"stock_code": "600000", "name": "浦发银行", "listing_date": "1999-11-10", "industry": "银行"},
    {"stock_code": "601899", "name": "紫金矿业", "listing_date": "2008-04-25", "industry": "小金属"},
    {"stock_code": "300059", "name": "东方财富", "listing_date": "2010-03-19", "industry": "证券"},
    {"stock_code": "600030", "name": "中信证券", "listing_date": "2003-01-06", "industry": "证券"},
    {"stock_code": "601012", "name": "隆基绿能", "listing_date": "2012-04-11", "industry": "光伏设备"},
    {"stock_code": "000333", "name": "美的集团", "listing_date": "2013-09-18", "industry": "白色家电"},
    {"stock_code": "600276", "name": "恒瑞医药", "listing_date": "2000-10-18", "industry": "化学制药"},
    {"stock_code": "601888", "name": "中国中免", "listing_date": "2009-10-15", "industry": "旅游零售"},
    {"stock_code": "002415", "name": "海康威视", "listing_date": "2010-05-28", "industry": "安防设备"},
    {"stock_code": "600887", "name": "伊利股份", "listing_date": "1996-03-12", "industry": "乳品"},
    {"stock_code": "601166", "name": "兴业银行", "listing_date": "2007-02-05", "industry": "银行"},
    {"stock_code": "000651", "name": "格力电器", "listing_date": "1996-11-18", "industry": "白色家电"},
]

BENCHMARK_INDEXES: dict[str, str] = {
    "000300": "沪深300",
    "000905": "中证500",
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
}


_LOCAL_CATALOG: dict[str, dict] | None = None


def _get_local_catalog() -> dict[str, dict]:
    global _LOCAL_CATALOG
    if _LOCAL_CATALOG is not None:
        return _LOCAL_CATALOG

    catalog: dict[str, dict] = {}

    # 1. BUILTIN_STOCKS (高优先级准确历史)
    for s in BUILTIN_STOCKS:
        catalog[s["stock_code"]] = dict(s)

    # 2. data/import/stocks.csv
    import csv
    from pathlib import Path

    stocks_csv = Path("data/import/stocks.csv")
    if stocks_csv.exists():
        try:
            with open(stocks_csv, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    code = row.get("stock_code")
                    if code and row.get("listing_date") and code not in catalog:
                        catalog[code] = {
                            "stock_code": code,
                            "name": row.get("name", ""),
                            "listing_date": row.get("listing_date"),
                            "industry": row.get("industry", ""),
                        }
        except Exception:
            pass

    # 3. data/phase3_universe/sina_hs_a_snapshot.json (5564 只全市场名称快照)
    sina_json = Path("data/phase3_universe/sina_hs_a_snapshot.json")
    sina_names: dict[str, str] = {}
    if sina_json.exists():
        try:
            import json

            with open(sina_json, mode="r", encoding="utf-8") as f:
                data = json.load(f)
                for s in data.get("stocks", []):
                    code = s.get("code")
                    name = s.get("name")
                    if code and name:
                        sina_names[code] = name
        except Exception:
            pass

    # 4. AStockDataBlobStore (5541 只本地挂载历史数据，提供权威首个交易日作为上市日)
    try:
        from src.market.providers.astockdata_store import AStockDataBlobStore

        store = AStockDataBlobStore.latest_composite_none()
        for sym, entry in store.manifest.symbols.items():
            code = entry.stock_code
            if code not in catalog or not catalog[code].get("listing_date"):
                fd = str(entry.first_date)
                listing_date = f"{fd[:4]}-{fd[4:6]}-{fd[6:8]}" if len(fd) == 8 else ""
                name = sina_names.get(code, "") or catalog.get(code, {}).get("name", "")
                catalog[code] = {
                    "stock_code": code,
                    "name": name,
                    "listing_date": listing_date,
                    "industry": catalog.get(code, {}).get("industry", ""),
                }
            elif code in sina_names and not catalog[code].get("name"):
                catalog[code]["name"] = sina_names[code]
    except Exception:
        pass

    # 补充新浪快照中的其余股票
    for code, name in sina_names.items():
        if code in catalog and not catalog[code].get("name"):
            catalog[code]["name"] = name
        elif code not in catalog:
            catalog[code] = {
                "stock_code": code,
                "name": name,
                "listing_date": None,
                "industry": "",
            }

    _LOCAL_CATALOG = catalog
    return _LOCAL_CATALOG


class AkshareMarketProvider(MarketDataProvider):
    """AKShare 适配器。"""

    provider_id = "akshare"

    def __init__(self, *, allow_synthetic_fallback: bool | None = None) -> None:
        self._fallback = SyntheticMarketProvider()
        self._allow_fallback = (
            settings.allow_synthetic_market_fallback
            if allow_synthetic_fallback is None
            else allow_synthetic_fallback
        )
        self._last_error: str = ""

    # ------------------------------------------------------------------
    # 股票基础资料
    # ------------------------------------------------------------------
    def search(self, query: str, limit: int = 20) -> list[StockMaster]:
        query = (query or "").strip()
        if not query:
            return []

        # 优先检索本地 5800+ 标的名册（0ms 响应，避免外网东财请求超时阻塞）
        catalog = _get_local_catalog()
        lowered = query.lower()
        matches = [
            s for s in catalog.values()
            if lowered in s["stock_code"] or (s.get("name") and lowered in s["name"].lower())
        ][:limit]
        if matches:
            return [self._dict_to_stock(m) for m in matches]

        try:
            df = self._call_with_retry("stock_zh_a_spot_em", lambda ak: ak.stock_zh_a_spot_em())
            if df is not None and len(df):
                df = df.rename(columns={"代码": "stock_code", "名称": "name"})
                mask = df["stock_code"].astype(str).str.contains(query, na=False) | df["name"].astype(
                    str
                ).str.contains(query, na=False)
                subset = df[mask].head(limit)
                out = [self._row_to_stock(r) for r in subset.to_dict("records")]
                if out:
                    return out
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"

        try:
            code = codes.normalize_code(query)
        except ValueError:
            return []
        try:
            return [self.get_stock(code)]
        except Exception:  # noqa: BLE001
            return []

    def get_stock(self, code: str) -> StockMaster:
        code, exchange, board, wind = codes.parse(code)

        # 1) 优先查验本地资料库（含 AStockData 与全市场名册）
        #    本地名册是主源（AKShare）不可达时的兜底：资料完整但未经主源核验，
        #    必须显式标注来源降级（grade B + notes），不得伪装成主源结果。
        catalog = _get_local_catalog()
        if code in catalog and catalog[code].get("listing_date"):
            meta = catalog[code]
            stock = self._dict_to_stock(meta)
            stock.wind_code = wind
            stock.data_quality.grade = "B"
            stock.data_quality.score = 0.75
            stock.data_quality.notes.append(
                "AKShare 实时接口不可用，使用本地名册兜底（来源已降级）"
            )
            stock.source = SourceRef(source="local_catalog", extra={"matched": True})
            return stock

        # 2) 尝试真实数据源
        try:
            info = self._call_with_retry("stock_individual_info_em", lambda ak: ak.stock_individual_info_em(symbol=code))
            stock = self._info_frame_to_stock(code, exchange, board, wind, info)
            if stock.name and stock.listing_date:
                return stock
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"

        # 3) 代码可解析但无资料 —— 返回最小可用对象并降级，而非直接报错
        if ex_value(exchange) != "UNKNOWN":
            return StockMaster(
                stock_code=code,
                wind_code=wind,
                name=catalog.get(code, {}).get("name", ""),
                exchange=exchange,
                board=board,
                data_quality={
                    "grade": "D",
                    "score": 0.3,
                    "notes": ["无法获取股票上市日期；分析可继续但结论不可靠"],
                },
                source=SourceRef(source="code_prefix_only", extra={"error": self._last_error[:200]}),
            )
        raise SymbolNotFoundError(f"无法识别股票代码 {code}")

    # ------------------------------------------------------------------
    # 行情
    # ------------------------------------------------------------------
    def get_daily_bars(
        self,
        code: str,
        start: date | None = None,
        end: date | None = None,
        *,
        adjust: str = "qfq",
    ) -> BarSeries:
        code = codes.normalize_code(code)
        start = start or date.fromisoformat(settings.market_history_start)
        end = end or date.today()
        return self._fetch(code, start, end, adjust=adjust, is_benchmark=False)

    def get_benchmark_bars(
        self,
        index_code: str = "000300",
        start: date | None = None,
        end: date | None = None,
        *,
        adjust: str = "qfq",
    ) -> BarSeries:
        start = start or date.fromisoformat(settings.market_history_start)
        end = end or date.today()
        return self._fetch(index_code, start, end, adjust=adjust, is_benchmark=True)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------
    def _fetch(
        self,
        code: str,
        start: date,
        end: date,
        *,
        adjust: str = "qfq",
        is_benchmark: bool = False,
    ) -> BarSeries:
        cache = self._read_cache(code, start, end, adjust)
        if cache is not None and not cache.bars and is_benchmark:
            cache = None

        # 1) 新鲜缓存
        if cache is not None and self._cache_is_fresh(code):
            return self._mark_source(cache, MarketDataSource.CACHE, "cache",
                                     "命中本地行情缓存（未调用第三方接口）")

        # 2) 真实接口
        err = ""
        try:
            df = self._call_with_retry(
                "index_zh_a_hist" if is_benchmark else "stock_zh_a_hist",
                lambda ak: (
                    ak.index_zh_a_hist(symbol=code, period="daily",
                                       start_date=start.strftime("%Y%m%d"),
                                       end_date=end.strftime("%Y%m%d"))
                    if is_benchmark else
                    ak.stock_zh_a_hist(symbol=code, period="daily",
                                       start_date=start.strftime("%Y%m%d"),
                                       end_date=end.strftime("%Y%m%d"),
                                       adjust=adjust)
                ),
            )
            series = build_series(
                code, df, adjust=adjust,
                source=MarketDataSource.AKSHARE, source_name=self.provider_id,
                is_degraded=False,
            )
            if series.bars:
                series.warnings.extend(detect_anomalies(series))
                self._write_cache(code, series, is_benchmark=is_benchmark)
                self._log_fetch(code, "ok", len(series.bars), "AKShare 实时获取成功")
                return series
            err = "AKShare 返回空数据集"
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            self._last_error = err

        # 3) 过期缓存兜底
        if cache is not None and cache.bars:
            self._log_fetch(code, "cached", len(cache.bars), f"实时接口失败，使用历史缓存：{err[:160]}")
            return self._mark_source(
                cache, MarketDataSource.CACHE, "cache_stale",
                f"AKShare 实时接口失败（{err[:120]}），已回退到本地历史缓存。数据可能不是最新。",
                degraded=True,
            )

        # 4) 合成行情兜底（仅当显式允许）
        if self._allow_fallback:
            self._log_fetch(code, "degraded", 0, f"实时接口与缓存均不可用，使用合成行情：{err[:160]}")
            synthetic = (
                self._fallback.get_benchmark_bars(code, start, end, adjust=adjust)
                if is_benchmark else
                self._fallback.get_daily_bars(code, start, end, adjust=adjust)
            )
            synthetic.warnings.append(Warning_(
                code="MARKET_SYNTHETIC_FALLBACK",
                message=(
                    "真实行情接口不可用，当前展示的是**确定性合成行情**（synthetic_demo），"
                    "仅用于系统联调与 UI 演示，**不可用于任何投资判断**。"
                ),
                severity="error",
                context={"provider_error": err[:200]},
            ))
            return synthetic

        raise ProviderUnavailableError(
            f"无法获取 {code} 的行情数据",
            detail=err[:500],
        )

    def _mark_source(
        self, series: BarSeries, source: MarketDataSource, name: str, note: str, *, degraded: bool = False
    ) -> BarSeries:
        series.source = source
        series.source_ref = SourceRef(source=name, extra={"note": note})
        series.is_degraded = degraded
        series.warnings.append(Warning_(
            code="MARKET_CACHE_USED",
            message=note,
            severity="warning" if degraded else "info",
        ))
        return series

    def _call_with_retry(self, name: str, fn) -> pd.DataFrame:  # type: ignore[no-untyped-def]
        import akshare as ak

        last: Exception | None = None
        for attempt in range(1, settings.market_retry_attempts + 1):
            try:
                return fn(ak)
            except Exception as exc:  # noqa: BLE001
                last = exc
                if attempt < settings.market_retry_attempts:
                    time.sleep(settings.market_retry_backoff_seconds * attempt)
        raise ProviderUnavailableError(f"AKShare 接口 {name} 调用失败", detail=str(last)[:400]) from last

    # ------------------------------------------------------------------
    # 缓存
    # ------------------------------------------------------------------
    def _read_cache(self, code: str, start: date, end: date, adjust: str) -> BarSeries | None:
        try:
            from sqlalchemy import select

            from src.db.base import session_scope
            from src.db.models import MarketBarDailyRow

            with session_scope() as db:
                rows = db.execute(
                    select(MarketBarDailyRow).where(
                        MarketBarDailyRow.stock_code == code,
                        MarketBarDailyRow.adjust == adjust,
                        MarketBarDailyRow.trade_date >= start,
                        MarketBarDailyRow.trade_date <= end,
                    ).order_by(MarketBarDailyRow.trade_date)
                ).scalars().all()

            if not rows:
                return None

            records = [
                {
                    "trade_date": r.trade_date, "open": r.open, "high": r.high, "low": r.low,
                    "close": r.close, "volume": r.volume, "amount": r.amount,
                    "turnover": r.turnover, "pct_change": r.pct_change, "adjust": r.adjust,
                }
                for r in rows
            ]
            df = pd.DataFrame(records)
            return build_series(
                code, df, adjust=adjust,
                source=MarketDataSource.CACHE, source_name="sqlite_cache",
                is_degraded=False,
            )
        except Exception:  # noqa: BLE001 - 缓存不可用不应阻塞主流程
            return None

    def _cache_is_fresh(self, code: str) -> bool:
        try:
            from sqlalchemy import desc, select

            from src.db.base import session_scope
            from src.db.models import MarketFetchLogRow

            with session_scope() as db:
                row = db.execute(
                    select(MarketFetchLogRow)
                    .where(MarketFetchLogRow.stock_code == code, MarketFetchLogRow.status == "ok")
                    .order_by(desc(MarketFetchLogRow.fetched_at))
                    .limit(1)
                ).scalars().first()
            if row is None:
                return False
            age = (datetime.now() - row.fetched_at).total_seconds()
            return age < settings.market_cache_ttl_seconds
        except Exception:  # noqa: BLE001
            return False

    def _write_cache(self, code: str, series: BarSeries, *, is_benchmark: bool) -> None:
        try:
            from sqlalchemy import delete

            from src.db.base import session_scope
            from src.db.models import MarketBarDailyRow

            with session_scope() as db:
                db.execute(
                    delete(MarketBarDailyRow).where(
                        MarketBarDailyRow.stock_code == code,
                        MarketBarDailyRow.adjust == series.adjust,
                    )
                )
                for b in series.bars:
                    db.add(MarketBarDailyRow(
                        stock_code=code, trade_date=b.trade_date, open=b.open, high=b.high,
                        low=b.low, close=b.close, volume=b.volume, amount=b.amount,
                        turnover=b.turnover, pct_change=b.pct_change, adjust=series.adjust,
                        is_benchmark=is_benchmark, source=series.source_ref.source,
                        is_degraded=series.is_degraded,
                    ))
        except Exception:  # noqa: BLE001 - 缓存写入失败不影响主流程
            pass

    def _log_fetch(self, code: str, status: str, count: int, message: str) -> None:
        try:
            from src.db.base import session_scope

            with session_scope() as db:
                db.add(MarketFetchLogRow(
                    stock_code=code, provider=self.provider_id, status=status,
                    row_count=count, message=message[:500],
                ))
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    @staticmethod
    def _row_to_stock(row: dict) -> StockMaster:
        code, exchange, board, wind = codes.parse(str(row.get("stock_code", "")))
        return StockMaster(
            stock_code=code, wind_code=wind,
            name=str(row.get("name", "") or ""),
            exchange=exchange, board=board,
            source=SourceRef(source="akshare:stock_zh_a_spot_em"),
        )

    @staticmethod
    def _dict_to_stock(meta: dict) -> StockMaster:
        code, exchange, board, wind = codes.parse(meta["stock_code"])
        return StockMaster(
            stock_code=code, wind_code=wind, name=meta.get("name", ""),
            exchange=exchange, board=board, industry=meta.get("industry", ""),
            listing_date=date.fromisoformat(meta["listing_date"]) if meta.get("listing_date") else None,
            source=SourceRef(source="builtin"),
        )

    @staticmethod
    def _info_frame_to_stock(
        code: str, exchange, board: str, wind: str, info: pd.DataFrame
    ) -> StockMaster:
        """解析 ``stock_individual_info_em`` 的 key-value 长表。"""
        kv: dict[str, str] = {}
        if info is not None and len(info):
            cols = list(info.columns)
            if len(cols) >= 2:
                kv = {str(k): str(v) for k, v in zip(info[cols[0]], info[cols[1]], strict=False)}

        listing_raw = kv.get("上市时间", "")
        listing_date: date | None = None
        if listing_raw and listing_raw not in ("-", "None", "nan"):
            for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
                try:
                    listing_date = datetime.strptime(listing_raw.strip(), fmt).date()
                    break
                except ValueError:
                    continue

        stock = StockMaster(
            stock_code=code, wind_code=wind,
            name=kv.get("股票简称", "") or "",
            exchange=exchange, board=board,
            industry=kv.get("行业", "") or "",
            listing_date=listing_date,
            total_market_cap=_to_float(kv.get("总市值")),
            circulating_market_cap=_to_float(kv.get("流通市值")),
            source=SourceRef(source="akshare:stock_individual_info_em"),
        )
        if listing_date is None:
            stock.data_quality.grade = "C"
            stock.data_quality.score = 0.55
            stock.data_quality.notes.append("未能解析上市日期，出生档案可能无法构造")
        return stock


def _to_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_market_provider(*, offline: bool = False) -> MarketDataProvider:
    """工厂：按配置返回行情提供者。

    * ``SMP_MARKET_PROVIDER=synthetic`` 或显式 ``offline=True``：
      确定性合成数据源（仅用于联调/演示，研究结论禁止使用）。
    * ``SMP_MARKET_PROVIDER=offline``：离线真实导入源（data/import/），
      AKShare 网络不可用时完成真实数据研究的正式通道（P0-2 验收路径）。
    * ``SMP_MARKET_PROVIDER=vendor_parquet``（Phase 4）：供应商全市场 Parquet 仓库
      （6,104 只 + 逐日 PIT 估值）。**基准指数不在供应商仓库里**，因此基准查询
      自动回退到 ``offline`` 通道（IDX000300 来自 data/import/）。
      仓库不存在时**显式报错**，不静默退回 AKShare —— 后者在本环境不可达，
      静默降级会让人误以为"数据加载失败是网络问题"。
    """
    if offline or settings.market_provider == "synthetic":
        return SyntheticMarketProvider()
    if settings.market_provider == "offline":
        from src.market.providers.offline import OfflineMarketDataProvider

        return OfflineMarketDataProvider()
    if settings.market_provider == "vendor_parquet":
        from src.market.providers.offline import OfflineMarketDataProvider
        from src.market.providers.vendor_parquet import (
            VendorParquetProvider,
            vendor_available,
        )

        if not vendor_available():
            raise RuntimeError(
                "SMP_MARKET_PROVIDER=vendor_parquet 但供应商 Parquet 仓库不存在。"
                "请先运行 scripts/phase4_import_vendor.py（NAS 上用 import-data.sh）。"
            )
        return VendorParquetProvider(benchmark_fallback=OfflineMarketDataProvider())
    return AkshareMarketProvider()
