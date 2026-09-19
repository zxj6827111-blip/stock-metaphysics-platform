"""抓取紫微 Golden Fixture（真实 iztro 输出快照）。

为什么需要它
------------
`tests/engines/test_ziwei_engine.py` 需要验证「服务输出 → 本项目 Schema」的映射契约。
如果这些测试每次都依赖本机 node 服务，那么在缺少 Node 的环境下它们只能被跳过 ——
而"被跳过的契约测试"等于没有契约测试。

因此把**真实 iztro 2.6.1 的输出**冻结为 JSON 快照，放在 `tests/fixtures/ziwei/`：
* 映射 / 结构 / 不变量测试**永远运行**（不依赖 Node）；
* 另有标了 `ziwei_live` 的测试直接调用真实服务，两者都要过。

用法
----
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/capture_ziwei_fixtures.py

⚠️ 重新抓取意味着"接受新的第三方口径"。若输出与既有快照不同，
必须先判断是 iztro 升级导致的口径变化还是代码 bug，并把差异写入
`docs/calculation-differences-phase2-ziwei.md`。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "ziwei"

#: (文件名, 说明, solar_date, time_index, variant, as_of_date, as_of_time_index)
CASES: list[tuple[str, str, str, int, str, str, int]] = [
    ("600519-listing-forward", "贵州茅台上市时刻（2001-08-27 巳时，辛巳年）顺行",
     "2001-08-27", 5, "variant_forward", "2024-11-15", 7),
    ("600519-listing-reverse", "贵州茅台上市时刻 逆行（与上例仅方向不同）",
     "2001-08-27", 5, "variant_reverse", "2024-11-15", 7),
    ("000001-listing-forward", "平安银行上市时刻（1991-04-03 巳时，辛未年）顺行",
     "1991-04-03", 5, "variant_forward", "2024-11-15", 7),
    ("300750-listing-forward", "宁德时代上市时刻（2018-06-11 巳时，戊戌年）顺行",
     "2018-06-11", 5, "variant_forward", "2024-11-15", 7),
    ("2024-lichun-zishi", "2024 立春当日早子时（甲辰年）顺行",
     "2024-02-04", 0, "variant_forward", "2024-11-15", 7),
    ("1999-late-zishi", "1999-12-31 晚子时（跨年、timeIndex=12）逆行",
     "1999-12-31", 12, "variant_reverse", "2024-11-15", 7),
    ("2016-choushi", "2016-03-15 丑时（丙申年）顺行",
     "2016-03-15", 1, "variant_forward", "2024-11-15", 7),
    ("2020-haishi", "2020-07-22 亥时（庚子年，科创板时期）顺行",
     "2020-07-22", 11, "variant_forward", "2024-11-15", 7),
]


def main() -> int:
    from src.core.schemas.common import VariantMode
    from src.engines.base import EngineContext
    from src.engines.ziwei.transport import SubprocessZiweiTransport
    from src.engines.ziwei.ziwei_engine import TIME_INDEX_RANGES, ZiweiEngine

    transport = SubprocessZiweiTransport()
    if not transport.available():
        print(f"紫微服务不可用，无法抓取：{transport.describe()}", file=sys.stderr)
        return 2

    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    engine = ZiweiEngine(transport=transport)

    for (name, desc, solar, ti, variant, as_of, as_of_ti) in CASES:
        y, m, d = (int(x) for x in solar.split("-"))
        birth = datetime(y, m, d, TIME_INDEX_RANGES[ti][0], 30)
        ay, am, ad = (int(x) for x in as_of.split("-"))
        as_of_dt = datetime(ay, am, ad, TIME_INDEX_RANGES[as_of_ti][0], 30)
        chart = engine.calculate_chart(
            EngineContext(stock_code="FIXTURE", as_of=as_of_dt),
            birth_datetime=birth,
            as_of=as_of_dt,
            variant_mode=VariantMode.FORWARD if variant == "variant_forward" else VariantMode.REVERSE,
        )
        payload = chart.model_dump(mode="json")
        (FIXTURE_DIR / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
        )
        manifest.append({
            "name": name, "description": desc, "solar_date": solar, "time_index": ti,
            "variant_mode": variant, "as_of": as_of, "as_of_time_index": as_of_ti,
            "engine_version": chart.engine_version, "soul_palace_index": chart.soul_palace_index,
            "five_elements_class": chart.five_elements_class,
        })
        print(f"✓ {name}: 命宫#{chart.soul_palace_index} {chart.five_elements_class} "
              f"{chart.chinese_date}")

    (FIXTURE_DIR / "_manifest.json").write_text(
        json.dumps({
            "note": "真实 iztro 输出快照（经 ZiweiEngine 映射为本项目 ZiweiChart）。"
                    "重新抓取前请阅读 scripts/capture_ziwei_fixtures.py 的警告。",
            "iztro_version": engine.metadata.third_party,
            "engine_version": engine.metadata.engine_version,
            "cases": manifest,
        }, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"已写入 {len(manifest)} 个快照到 {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
