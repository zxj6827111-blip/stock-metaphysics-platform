"""命令行入口：种子数据、研究流水线、诊断。

用法：
    python -m src.cli seed                 # 写入古籍语料与交易所时段
    python -m src.cli research             # 运行研究流水线（事件研究 + 四组负对照）
    python -m src.cli analyze 600519       # 对单只股票执行一次完整分析
    python -m src.cli doctor               # 环境与依赖自检
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime


def cmd_seed(args: argparse.Namespace) -> int:
    from sqlalchemy import select

    from src.db.base import init_db, session_scope
    from src.db.models import ExchangeSessionRow
    from src.knowledge.ingest.loader import seed_database
    from src.core.stock.exchange_sessions import seed_rows

    init_db()

    result = seed_database()

    with session_scope() as db:
        existing = {
            (r.exchange, r.board, r.session_name)
            for r in db.execute(select(ExchangeSessionRow)).scalars().all()
        }
        added = 0
        for row in seed_rows():
            key = (row["exchange"], row["board"], row["session_name"])
            if key in existing:
                continue
            db.add(ExchangeSessionRow(**row))
            added += 1

    print(f"古籍：{result['books']} 本 / {result['entries']} 条")
    print(f"交易所时段：新增 {added} 条")
    return 0


def cmd_research(args: argparse.Namespace) -> int:
    from fastapi.testclient import TestClient

    from apps.api.main import app

    payload = {
        "universe": args.universe or [
            "600519", "000001", "300750", "600036", "000858",
            "601318", "002594", "688981", "600000", "601899",
        ],
        "factor_ids": args.factors or ["B_MONTH_001", "B_MONTH_002", "H_DAY_001"],
        "horizons": [5, 10, 20, 60],
        "sample_step_months": args.step,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "run_negative_controls": not args.no_controls,
    }

    with TestClient(app) as client:
        resp = client.post("/api/v1/research/run", json=payload)
        if resp.status_code != 200:
            print(f"研究运行失败 ({resp.status_code})：{resp.text[:600]}", file=sys.stderr)
            return 1
        body = resp.json()

    es = body["event_study"]
    print(f"实验 ID：{body['experiment_id']}")
    print(f"股票池：{len(payload['universe'])} 只；面板：{body['panel_stats']['observation_rows']} 条因子观测 / "
          f"{body['panel_stats']['label_rows']} 条标签")
    print(f"事件数：{es['event_count']}；覆盖股票：{es['universe_size']}")
    print()
    print(f"{'持有期':<8}{'样本':<8}{'上涨率':<12}{'平均收益':<12}{'中位收益':<12}{'超额收益':<12}{'最大回撤':<12}")
    for h in es["horizons"]:
        fmt = lambda v: "—" if v is None else f"{v:.4f}"  # noqa: E731
        print(f"{str(h['horizon']) + 'D':<8}{h['sample_count']:<8}{fmt(h['up_rate']):<12}"
              f"{fmt(h['mean_return']):<12}{fmt(h['median_return']):<12}"
              f"{fmt(h['mean_excess_return']):<12}{fmt(h['max_drawdown']):<12}")

    nc = body.get("negative_controls")
    if nc:
        print()
        print("负对照：")
        for r in nc["results"]:
            print(f"  {r['kind']:<20} → {r['verdict']:<14} "
                  f"真实 {r.get('real_mean_return_20d')} / 对照 {r.get('control_mean_return_20d')}")
        print()
        print("结论：", nc["conclusion"])

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(body, fh, ensure_ascii=False, indent=2)
        print(f"\n完整结果已写入 {args.json}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    from fastapi.testclient import TestClient

    from apps.api.main import app

    as_of = args.as_of or datetime.now().replace(microsecond=0).isoformat()
    with TestClient(app) as client:
        resp = client.post(
            f"/api/v1/stocks/{args.code}/analysis/bazi",
            json={"as_of": as_of},
        )
        if resp.status_code != 200:
            print(f"分析失败 ({resp.status_code})：{resp.text[:600]}", file=sys.stderr)
            return 1
        body = resp.json()

    chart = body["chart"]
    print(f"股票：{body['stock']['name']} {body['stock']['stock_code']}")
    print(f"出生档案：{body['birth_profile']['birth_datetime']} "
          f"({body['birth_profile']['birth_basis']}, {body['birth_profile']['timezone']})")
    print(f"分析基准：{as_of}")
    print()
    print("四柱：" + " ".join(
        chart[k]["ganzhi"]["text"]
        for k in ("year_pillar", "month_pillar", "day_pillar", "hour_pillar")
    ))
    print(f"日主：{chart['day_master']}（{chart['day_master_wuxing']}）")
    print(f"旺衰：{chart['day_master_analysis']['strength_level']} "
          f"(帮扶占比 {chart['day_master_analysis']['balance_ratio']})")
    print(f"格局：{chart['pattern']['primary']}（置信度 {chart['pattern']['confidence']}）")
    print(f"喜用忌：喜 {chart['yong_shen']['xi_shen']} / 用 {chart['yong_shen']['yong_shen']} / "
          f"忌 {chart['yong_shen']['ji_shen']}")
    print(f"流年：{chart['current_year_pillar']['ganzhi']['text']}；"
          f"流月：{chart['current_month_pillar']['ganzhi']['text']}；"
          f"流日：{chart['current_day_pillar']['ganzhi']['text']}")
    print(f"运限假设：{chart['variant_mode']}（股票无性别）")
    print()
    obs = body["factors"]["observations"]
    print(f"因子：{len(obs)} 个（正向 {sum(1 for o in obs if o['direction'] == 1)} / "
          f"负向 {sum(1 for o in obs if o['direction'] == -1)} / "
          f"中性 {sum(1 for o in obs if o['direction'] == 0)}）")
    print(f"八字规则分：{body['opinion']['score']}（区间 0-100，"
          f"信心 {body['opinion']['confidence']}）")
    print()
    print("注意：规则分是传统规则强度聚合，不是收益率预测，也不代表上涨概率。")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(body, fh, ensure_ascii=False, indent=2)
        print(f"完整结果已写入 {args.json}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """环境自检：依赖、数据库、语料、引擎可用性。"""
    ok = True

    def check(label: str, fn) -> None:  # type: ignore[no-untyped-def]
        nonlocal ok
        try:
            detail = fn()
            print(f"  [OK]   {label}{f' — {detail}' if detail else ''}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"  [FAIL] {label} — {type(exc).__name__}: {exc}")

    print("环境自检")
    check("Python 版本", lambda: sys.version.split()[0])
    check("lunar-python", lambda: __import__("lunar_python").__name__ and "已安装")
    check("numpy / pandas", lambda: f"numpy {__import__('numpy').__version__}, pandas {__import__('pandas').__version__}")
    check("fastapi", lambda: __import__("fastapi").__version__)
    check("sqlalchemy", lambda: __import__("sqlalchemy").__version__)

    def _db() -> str:
        from src.db.base import get_engine

        with get_engine().connect() as conn:
            from sqlalchemy import text

            n = conn.execute(text(
                "select count(*) from sqlite_master where type='table'"
            )).scalar()
        return f"{n} 张表"

    check("数据库 schema", _db)

    def _corpus() -> str:
        from src.knowledge.ingest.loader import get_books, get_entries

        return f"{len(get_books())} 本 / {len(get_entries())} 条"

    check("古籍语料", _corpus)

    def _cal() -> str:
        from src.engines.calendar.calendar_engine import CalendarEngine

        s = CalendarEngine().snapshot(datetime(2001, 8, 27, 9, 30))
        return f"2001-08-27 → {s.year_ganzhi.text} {s.month_ganzhi.text} {s.day_ganzhi.text} {s.hour_ganzhi.text}"

    check("历法引擎", _cal)

    def _bazi() -> str:
        from src.engines.bazi.bazi_engine import BaziEngine

        c = BaziEngine().build_chart(
            birth_datetime=datetime(2001, 8, 27, 9, 30), as_of=datetime(2024, 11, 15, 14, 32)
        )
        return f"日主 {c.day_master}，{c.day_master_analysis.strength_level}，格局 {c.pattern.primary}"

    check("八字引擎", _bazi)

    def _factors() -> str:
        from src.factors.registry.definitions import ALL_DEFINITIONS

        return f"{len(ALL_DEFINITIONS)} 个因子定义"

    check("因子注册表", _factors)

    def _market() -> str:
        from src.core.config import settings

        return f"provider={settings.market_provider}"

    check("行情配置", _market)

    print()
    print("全部检查通过。" if ok else "存在失败项，请先修复。")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.cli",
        description="股票玄学多模型研究平台 · Phase 1 命令行工具",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser("seed", help="写入种子数据（古籍语料 + 交易所时段）")
    p_seed.set_defaults(func=cmd_seed)

    p_res = sub.add_parser("research", help="运行研究流水线（事件研究 + 负对照）")
    p_res.add_argument("--universe", nargs="*", help="股票池")
    p_res.add_argument("--factors", nargs="*", help="目标因子 ID")
    p_res.add_argument("--step", type=int, default=3, help="as_of 采样间隔（月）")
    p_res.add_argument("--date-from", default="2021-01-01", help="研究起始日")
    p_res.add_argument("--date-to", default=date.today().isoformat(), help="研究结束日")
    p_res.add_argument("--no-controls", action="store_true", help="跳过负对照（更快）")
    p_res.add_argument("--json", help="把完整结果写入指定 JSON 文件")
    p_res.set_defaults(func=cmd_research)

    p_an = sub.add_parser("analyze", help="对单只股票执行一次完整分析")
    p_an.add_argument("code", help="股票代码，如 600519")
    p_an.add_argument("--as-of", help="分析基准时间（ISO8601），缺省为当前时间")
    p_an.add_argument("--json", help="把完整结果写入指定 JSON 文件")
    p_an.set_defaults(func=cmd_analyze)

    p_doc = sub.add_parser("doctor", help="环境与依赖自检")
    p_doc.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
