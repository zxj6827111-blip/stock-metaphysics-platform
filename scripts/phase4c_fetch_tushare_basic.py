"""Phase 4C · 用 TuShare ``stock_basic`` 取权威上市日（含北交所与退市股）。

用途
----
1. 补上用户表未覆盖的 249 只（多为北交所）；
2. 对用户表已覆盖的 5,389 只做**独立交叉验证**。

安全
----
* token 从环境文件读取（默认 ``E:/Software Development/StockAnalyzer/.env`` 的
  ``SA__MARKET_WAREHOUSE__TUSHARE_TOKEN``），**全程不打印、不落盘**；
* 只向 ``api.tushare.pro`` 发请求，不引入新的第三方依赖（用标准库 urllib）。

产物：``data/import/tushare_stock_basic.csv``
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "import" / "tushare_stock_basic.csv"
ENV_PATH = Path(r"E:/Software Development/StockAnalyzer/.env")
ENV_KEY = "SA__MARKET_WAREHOUSE__TUSHARE_TOKEN"
API = "https://api.tushare.pro"
FIELDS = "ts_code,symbol,name,area,industry,list_date,delist_date,list_status,exchange,market"


def read_token(path: Path, key: str) -> str:
    """从 env 文件读 token；只返回值，调用方负责不打印。"""
    if not path.is_file():
        raise SystemExit(f"env 文件不存在：{path}")
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("export "):
            stripped = stripped[len("export "):]
        if stripped.startswith(key + "="):
            value = stripped.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    raise SystemExit(f"env 文件里没有 {key}")


def call(api_name: str, token: str, params: dict, fields: str) -> tuple[list[str], list[list]]:
    body = json.dumps(
        {"api_name": api_name, "token": token, "params": params, "fields": fields}
    ).encode("utf-8")
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    if payload.get("code") != 0:
        raise SystemExit(f"TuShare 返回错误 code={payload.get('code')} msg={payload.get('msg')}")
    data = payload.get("data") or {}
    return data.get("fields") or [], data.get("items") or []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=str(ENV_PATH))
    parser.add_argument("--key", default=ENV_KEY)
    args = parser.parse_args()

    token = read_token(Path(args.env), args.key)
    print(f"已从 {args.env} 读到 token（长度 {len(token)}，内容不打印）")

    rows: list[list] = []
    fields: list[str] = []
    for status in ("L", "D"):
        got_fields, items = call("stock_basic", token, {"list_status": status}, FIELDS)
        fields = fields or got_fields
        print(f"  list_status={status}: {len(items)} 条")
        for item in items:
            record = dict(zip(got_fields, item))
            record["list_status"] = status
            rows.append(record)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n已写入 {OUT}（{len(rows)} 条）")

    by_exchange: dict[str, int] = {}
    for record in rows:
        by_exchange[record.get("exchange", "?")] = by_exchange.get(record.get("exchange", "?"), 0) + 1
    print("  按交易所:", by_exchange)
    bse = [r for r in rows if r.get("exchange") == "BSE"]
    print(f"  北交所 {len(bse)} 条；样例:", [(r["ts_code"], r["list_date"]) for r in bse[:5]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
