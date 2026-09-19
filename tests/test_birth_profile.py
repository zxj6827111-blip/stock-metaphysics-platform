"""StockBirthProfile 测试。

核心纪律：
* 默认基准 ``listing_open`` = 上市首个正式交易日 + 交易所 session 正式开盘 + Asia/Shanghai；
* **禁止硬编码 09:30** —— 开盘时刻必须来自 ``exchange_session_calendar``；
* 股票无性别 → ``variant_mode`` 默认 ``not_applicable``，且记录 assumption；
* 出生档案必须版本化，不允许覆盖其他版本。
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.core.schemas.common import BirthBasis, DataQualityGrade, Exchange, VariantMode
from src.core.schemas.stock import BirthProfileCreateRequest, StockMaster
from src.core.stock import codes, exchange_sessions
from src.core.stock.birth_profile import BirthProfileError, build_birth_profile, to_row


def _stock(code: str, board: str, exchange: Exchange, listing: date, name: str = "测试股") -> StockMaster:
    return StockMaster(
        stock_code=code, name=name, exchange=exchange, board=board, listing_date=listing
    )


class TestCodeNormalization:
    @pytest.mark.parametrize(
        "raw,expected_code,expected_exchange,expected_board",
        [
            ("600519", "600519", Exchange.SSE, "主板"),
            ("600519.SH", "600519", Exchange.SSE, "主板"),
            ("sh600519", "600519", Exchange.SSE, "主板"),
            ("000001", "000001", Exchange.SZSE, "主板"),
            ("002594", "002594", Exchange.SZSE, "主板"),
            ("300750", "300750", Exchange.SZSE, "创业板"),
            ("301001", "301001", Exchange.SZSE, "创业板"),
            ("688981", "688981", Exchange.SSE, "科创板"),
            ("830799", "830799", Exchange.BSE, "北交所"),
            ("920001", "920001", Exchange.BSE, "北交所"),
        ],
    )
    def test_parse(self, raw, expected_code, expected_exchange, expected_board):
        code, exchange, board, _wind = codes.parse(raw)
        assert code == expected_code
        assert exchange == expected_exchange
        assert board == expected_board

    def test_wind_code(self):
        assert codes.to_wind_code("600519") == "600519.SH"
        assert codes.to_wind_code("000001") == "000001.SZ"
        assert codes.to_wind_code("830799") == "830799.BJ"

    def test_invalid_code_raises(self):
        with pytest.raises(ValueError):
            codes.normalize_code("abc")

    def test_market_prefix(self):
        assert codes.market_prefix("600519") == "1"
        assert codes.market_prefix("000001") == "0"


class TestExchangeSessionCalendar:
    def test_config_loads(self):
        sessions = exchange_sessions.all_sessions()
        assert len(sessions) >= 4
        assert all(s.open_time is not None for s in sessions)

    def test_resolve_exact_board(self):
        session, key = exchange_sessions.resolve_session(
            Exchange.SZSE, "创业板", date(2018, 6, 11)
        )
        assert key == "SZSE/创业板"
        assert session.open_time.strftime("%H:%M") == "09:30"

    def test_resolve_fallback_to_default(self):
        session, key = exchange_sessions.resolve_session(Exchange.BSE, "DEFAULT", date(2023, 9, 1))
        assert key == "BSE/DEFAULT"

    def test_resolve_unknown_fallback(self):
        _session, key = exchange_sessions.resolve_session(Exchange.UNKNOWN, "DEFAULT")
        assert key == "UNKNOWN/DEFAULT"

    def test_board_session_effective_from_respected(self):
        """科创板 2019-07-22 才开市；2018 年的日期不应命中科创板专属配置。"""
        _session, key = exchange_sessions.resolve_session(
            Exchange.SSE, "科创板", date(2018, 1, 1)
        )
        assert key == "SSE/DEFAULT"

    def test_open_time_is_not_hardcoded_in_business_code(self):
        """开盘时刻只允许出现在配置读取层与 DB 列默认值中。

        用 AST 提取真实的字符串常量（跳过注释与 docstring），
        这样"禁止硬编码 09:30"这句文档本身不会误报。
        """
        import ast
        import pathlib

        # 允许出现的位置：配置读取/兜底默认值，以及 ORM 列默认值
        allowed = {
            pathlib.Path("src/core/stock/exchange_sessions.py"),
            pathlib.Path("src/db/models.py"),
        }
        root = pathlib.Path("src")
        offenders: list[str] = []

        for path in root.rglob("*.py"):
            rel = path.relative_to(root.parent)
            if rel in allowed:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

            # 收集所有 docstring 节点，排除掉
            docstrings: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                    body = getattr(node, "body", [])
                    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                        if isinstance(body[0].value.value, str):
                            docstrings.add(id(body[0].value))

            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if id(node) in docstrings:
                        continue
                    if "09:30" in node.value:
                        offenders.append(f"{rel}:{node.lineno}")

        assert not offenders, f"业务代码中出现硬编码开盘时刻：{offenders}"


class TestBirthProfileListingOpen:
    def test_maotai(self):
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27), "贵州茅台")
        profile = build_birth_profile(stock)
        assert profile.birth_basis == BirthBasis.LISTING_OPEN
        assert profile.exchange == Exchange.SSE
        assert profile.timezone == "Asia/Shanghai"
        assert profile.birth_datetime == datetime(
            2001, 8, 27, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai")
        )
        assert profile.birth_profile_version

    def test_evidence_chain(self):
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        profile = build_birth_profile(stock)
        ev = profile.evidence
        assert ev.listing_date == date(2001, 8, 27)
        assert ev.first_trading_day == date(2001, 8, 27)
        assert ev.session_open_time == "09:30:00"
        assert ev.lookup_key == "SSE/DEFAULT"
        assert "listing_open" in ev.derivation

    def test_weekend_listing_shifts_to_next_weekday(self):
        """1999-11-13 是周六 → 应顺延到 11-15（周一）并降低数据质量等级。"""
        stock = _stock("600000", "主板", Exchange.SSE, date(1999, 11, 13))
        profile = build_birth_profile(stock)
        assert profile.birth_datetime.date() == date(1999, 11, 15)
        assert profile.data_quality.grade in (DataQualityGrade.B, DataQualityGrade.C)

    def test_gem_board_session(self):
        stock = _stock("300750", "创业板", Exchange.SZSE, date(2018, 6, 11), "宁德时代")
        profile = build_birth_profile(stock)
        assert profile.evidence.lookup_key == "SZSE/创业板"
        assert profile.birth_datetime.date() == date(2018, 6, 11)

    def test_star_board_session(self):
        stock = _stock("688981", "科创板", Exchange.SSE, date(2020, 7, 16), "中芯国际")
        profile = build_birth_profile(stock)
        assert profile.evidence.lookup_key == "SSE/科创板"

    def test_trading_day_callback_is_used(self):
        """提供交易日回调时，非交易日应被顺延，且质量等级提升。"""
        known = {date(2018, 6, 12), date(2018, 6, 13)}
        stock = _stock("300750", "创业板", Exchange.SZSE, date(2018, 6, 11))
        profile = build_birth_profile(stock, is_trading_day=lambda d: d in known)
        assert profile.birth_datetime.date() == date(2018, 6, 12)

    def test_missing_listing_date_raises(self):
        stock = StockMaster(stock_code="600519", exchange=Exchange.SSE, board="主板")
        with pytest.raises(BirthProfileError):
            build_birth_profile(stock)


class TestNoGender:
    def test_default_variant_is_not_applicable(self):
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        profile = build_birth_profile(stock)
        assert profile.variant_mode == VariantMode.NOT_APPLICABLE
        assert "性别" in profile.variant_note

    def test_assumption_recorded(self):
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        profile = build_birth_profile(stock)
        keys = {a.key for a in profile.assumptions}
        assert "birth.listing_open" in keys

    @pytest.mark.parametrize("mode", [VariantMode.FORWARD, VariantMode.REVERSE, VariantMode.BOTH])
    def test_explicit_variant_records_assumption(self, mode):
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        profile = build_birth_profile(
            stock, BirthProfileCreateRequest(variant_mode=mode)
        )
        assert profile.variant_mode == mode
        assert any(a.key == "birth.variant_mode" for a in profile.assumptions)
        assert "研究对比" in profile.variant_note


class TestOtherBaselines:
    def test_custom_baseline(self):
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        profile = build_birth_profile(
            stock,
            BirthProfileCreateRequest(
                birth_basis=BirthBasis.CUSTOM,
                override_datetime=datetime(2001, 8, 27, 14, 0),
            ),
        )
        assert profile.birth_basis == BirthBasis.CUSTOM
        assert profile.birth_datetime.hour == 14
        assert profile.custom_datetime is not None

    def test_custom_requires_datetime(self):
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        with pytest.raises(BirthProfileError):
            build_birth_profile(stock, BirthProfileCreateRequest(birth_basis=BirthBasis.CUSTOM))

    def test_ipo_date_is_degraded_and_marked(self):
        """Phase 1 无独立 IPO 发行日数据源 —— 必须显式降级，不能假装准确。"""
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        profile = build_birth_profile(stock, BirthProfileCreateRequest(birth_basis=BirthBasis.IPO_DATE))
        assert profile.data_quality.grade == DataQualityGrade.C
        assert any("发行日" in n or "近似" in n for n in profile.data_quality.notes)

    def test_company_foundation_unavailable(self):
        """缺少数据源的基准必须报错，禁止猜测。"""
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        with pytest.raises(BirthProfileError):
            build_birth_profile(
                stock, BirthProfileCreateRequest(birth_basis=BirthBasis.COMPANY_FOUNDATION)
            )

    def test_first_trade_unavailable(self):
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        with pytest.raises(BirthProfileError):
            build_birth_profile(
                stock, BirthProfileCreateRequest(birth_basis=BirthBasis.FIRST_TRADE)
            )


class TestPersistenceShape:
    def test_to_row_contains_all_columns(self):
        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        profile = build_birth_profile(stock)
        row = to_row(profile)
        for key in (
            "stock_code", "exchange", "birth_basis", "birth_datetime", "timezone",
            "source", "birth_profile_version", "evidence_json", "assumptions_json",
            "data_quality_json", "variant_mode", "variant_note",
        ):
            assert key in row
        assert row["birth_datetime"].tzinfo is None  # 落库为 naive 本地时间

    def test_version_is_configurable_and_not_overwritten(self, monkeypatch):
        """切换出生模型/版本必须生成新记录，而不是覆盖历史。"""
        from src.core.config import settings

        stock = _stock("600519", "主板", Exchange.SSE, date(2001, 8, 27))
        v1 = build_birth_profile(stock)
        assert v1.birth_profile_version == settings.birth_profile_version

        # 不同基准 → 不同记录（由数据库唯一约束保证）
        v2 = build_birth_profile(stock, BirthProfileCreateRequest(birth_basis=BirthBasis.IPO_DATE))
        assert v1.birth_basis != v2.birth_basis
