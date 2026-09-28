"""导入首日阴阳及其字段级来源证据；冲突值只登记，不覆盖。"""

from __future__ import annotations

import argparse
import hashlib
import math
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl
from sqlalchemy import select

from src.core.fortune.market_sessions import AShareMarketSessionAdapter
from src.core.schemas.common import Exchange
from src.core.stock.exchange_sessions import resolve_session
from src.core.stock.trading_calendar import KNOWN_SOURCES, get_trading_calendar_provider
from src.db.base import session_scope
from src.db.models import StockMasterRow


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _can_fill_source_values(item: dict, master: StockMasterRow) -> bool:
    """仅完整、无冲突的来源证据允许补空值。"""
    if item.get("status") != "available":
        return False
    flag = item.get("first_day_yinyang")
    pct = item.get("first_day_pct_chg")
    if master.first_day_yinyang not in (None, flag):
        return False
    if master.first_day_pct_chg is not None and (
        not isinstance(pct, (int, float))
        or not math.isclose(float(master.first_day_pct_chg), float(pct), rel_tol=0.0, abs_tol=1e-12)
    ):
        return False
    return flag in {"阳", "阴"} and isinstance(pct, (int, float)) and math.isfinite(float(pct))


def _source_rows(path: Path) -> tuple[dict[str, tuple[date | None, float, str, float | None, float | None]], str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    parsed: dict[str, tuple[date | None, float, str, float | None, float | None]] = {}
    for row in workbook["总表"].iter_rows(min_row=2, values_only=True):
        if not row[0]:
            continue
        code = str(row[0]).split(".")[0].strip().zfill(6)
        pct, flag = row[5], str(row[6] or "").strip()
        if not isinstance(pct, (int, float)) or not math.isfinite(float(pct)) or flag not in {"阳", "阴"}:
            continue
        parsed[code] = (
            _as_date(row[2]),
            float(pct),
            flag,
            float(row[3]) if isinstance(row[3], (int, float)) else None,
            float(row[4]) if isinstance(row[4], (int, float)) else None,
        )
    workbook.close()
    return parsed, digest


def _evidence(
    *,
    code: str,
    master: StockMasterRow,
    observation_date: date | None,
    pct: float,
    flag: str,
    open_price: float | None,
    close_price: float | None,
    source_version: str,
    calendar_provider,
) -> dict:
    reasons: list[str] = []
    if observation_date is None:
        reasons.append("权威表缺少可解析的首日观测日期")
    elif master.listing_date is None or master.listing_date != observation_date:
        reasons.append("权威表观测日期与 stock_master 上市日期不一致或主档缺失")
    expected = "阳" if pct > 0 else ("阴" if pct < 0 else None)
    if expected is not None and expected != flag:
        reasons.append("首日涨跌幅符号与阴阳标识冲突")
    if (
        open_price is None or close_price is None
        or not math.isfinite(open_price) or not math.isfinite(close_price)
        or open_price <= 0 or close_price <= 0
    ):
        reasons.append("来源表缺少有效首日开盘价/收盘价，无法核验涨跌幅基准")
    elif not math.isclose(pct, close_price / open_price - 1.0, rel_tol=0.0, abs_tol=1e-12):
        reasons.append("来源表首日涨跌幅与收盘价/开盘价-1 不一致")
    if master.first_day_yinyang not in (None, flag):
        reasons.append("数据库已有阴阳值与权威表冲突")
    if master.first_day_pct_chg is not None and not math.isclose(
        float(master.first_day_pct_chg), pct, rel_tol=0.0, abs_tol=1e-12
    ):
        reasons.append("数据库已有首日涨跌幅与权威表冲突")

    try:
        exchange = Exchange(master.exchange)
    except ValueError:
        exchange = Exchange.UNKNOWN
        reasons.append("股票主档交易所代码无法识别")
    trading: dict[str, object]
    if observation_date is None:
        trading = {"is_trading_day": None, "source": "unavailable", "status": "unknown"}
    else:
        try:
            market_calendar = calendar_provider.for_exchange(exchange)
            query = market_calendar.is_trading_day(observation_date)
        except (LookupError, ValueError, KeyError, TypeError):
            query = None
        if query is None:
            trading = {
                "is_trading_day": None,
                "source": "unavailable",
                "status": "unknown",
                "reason": "无法解析适用的交易日历",
            }
            reasons.append("无法解析适用的交易日历")
        elif query.value is False:
            trading = {
                "is_trading_day": False,
                "source": query.source,
                "status": "conflict",
                "reason": "来源表记录的首日与市场交易日历冲突",
            }
            reasons.append("市场交易日历将来源观测日标记为非交易日")
        elif query.value is True and query.source in KNOWN_SOURCES:
            trading = {"is_trading_day": True, "source": query.source, "status": "confirmed"}
        elif (
            open_price is not None and close_price is not None
            and math.isfinite(open_price) and math.isfinite(close_price)
            and open_price > 0 and close_price > 0
        ):
            trading = {
                "is_trading_day": True,
                "source": "authoritative_table_open_close_prices",
                "status": "confirmed_by_source_record",
                "reason": "市场日历未覆盖；权威表包含该日有效开盘价与收盘价，本记录保留该交易日证据",
            }
        else:
            trading = {
                "is_trading_day": None,
                "source": query.source,
                "status": "unknown",
                "reason": "市场日历未覆盖且来源记录不足以确认当日交易",
            }
            reasons.append("缺少可验证的交易日证据")

    market_session: dict[str, object] = {"version": AShareMarketSessionAdapter.source_version}
    visible_at = None
    if observation_date is not None:
        try:
            if exchange == Exchange.UNKNOWN:
                raise LookupError("交易所未知，不能验证专属时段")
            session, matched_key = resolve_session(exchange, on_date=observation_date)
            visible_at = datetime.combine(
                observation_date, session.close_time, tzinfo=ZoneInfo(session.timezone)
            ).isoformat()
            market_session.update({
                "source": session.source,
                "matched_key": matched_key,
                "timezone": session.timezone,
                "close_time": session.close_time.isoformat(),
            })
        except (FileNotFoundError, LookupError, ValueError, KeyError):
            reasons.append("无法解析观测日适用的版本化市场收盘时段")

    if trading.get("is_trading_day") is not True:
        reasons.append("首日阴阳不能关联到已确认的交易日")
    if not visible_at:
        reasons.append("首日阴阳缺少可验证的收盘可见时点")

    return {
        "schema_version": "first-day-polarity-evidence-v1",
        "status": "conflict" if reasons else "available",
        "source": "user_authoritative_first_day_table",
        "source_version": source_version,
        "stock_code": code,
        "first_day_yinyang": flag,
        "first_day_pct_chg": pct,
        "price_basis": "工作簿首日涨跌幅原值；经核验等于收盘价/开盘价-1，字段单位为比率；阴阳标识直接沿用工作簿，未重新推算",
        "observation_date": observation_date.isoformat() if observation_date else None,
        "listing_date": master.listing_date.isoformat() if master.listing_date else None,
        "trading_day_evidence": trading,
        "market_session": market_session,
        "market_session_version": AShareMarketSessionAdapter.source_version,
        "visible_at": visible_at,
        "unavailability_reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="权威首日数据工作簿；不会复制到仓库")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source_path = Path(args.source)
    parsed, digest = _source_rows(source_path)
    source_version = f"sha256:{digest}"
    print(f"有效来源记录：{len(parsed)}；source_version={source_version}")
    print("来源路径不会写入数据库或输出完整路径。")

    matched = values_updated = evidence_updated = conflicts = missing = skipped = 0
    status_counts: Counter[str] = Counter()
    calendar_provider = get_trading_calendar_provider()
    with session_scope() as db:
        masters = {
            row.stock_code: row
            for row in db.execute(select(StockMasterRow)).scalars().all()
        }
        for code, (observation_date, pct, flag, open_price, close_price) in parsed.items():
            master = masters.get(code)
            if master is None:
                missing += 1
                continue
            matched += 1
            item = _evidence(
                code=code,
                master=master,
                observation_date=observation_date,
                pct=pct,
                flag=flag,
                open_price=open_price,
                close_price=close_price,
                source_version=source_version,
                calendar_provider=calendar_provider,
            )
            status_counts[item["status"]] += 1
            existing_evidence = master.first_day_evidence_json
            if existing_evidence and existing_evidence.get("source_version") != source_version:
                conflicts += 1
                skipped += 1
                continue
            if item["status"] == "conflict":
                conflicts += 1
            # 仅完整可用的来源记录可以补空值；冲突记录只保存冲突原因，不能写成可用阴阳。
            if _can_fill_source_values(item, master):
                if master.first_day_yinyang is None:
                    values_updated += 1
                    if not args.dry_run:
                        master.first_day_yinyang = flag
                if master.first_day_pct_chg is None:
                    values_updated += 1
                    if not args.dry_run:
                        master.first_day_pct_chg = pct
            if existing_evidence != item:
                evidence_updated += 1
                if not args.dry_run:
                    master.first_day_evidence_json = item

        print(
            f"匹配={matched}，未匹配={missing}，值字段拟补={values_updated}，"
            f"证据元数据拟写={evidence_updated}，冲突={conflicts}，版本冲突跳过={skipped}"
        )
        print(f"来源证据状态：{dict(status_counts)}")
        if args.dry_run:
            db.rollback()
            print("[DRY-RUN] 未写入数据库")
            return 0

    with session_scope() as db:
        rows = db.execute(select(StockMasterRow)).scalars().all()
        yin_yang = Counter(row.first_day_yinyang or "缺失" for row in rows)
        evidence_status = Counter(
            (row.first_day_evidence_json or {}).get("status", "无来源证据")
            for row in rows
        )
        print(f"数据库阴阳/缺失：{dict(yin_yang)}")
        print(f"数据库字段级证据状态：{dict(evidence_status)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
