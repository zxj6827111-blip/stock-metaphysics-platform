"""20 股真实数据 smoke research（验收 §十五）。

与测试的区别：本脚本在 **真实导入行情**（hfq 快照）上跑一次完整研究流水线
（事件研究 + 四类负对照），并把完整响应写入 artifacts/acceptance/。

它回答的问题不是"术数准不准"，而是：
    在真实数据上，整个研究链路是否能跑通、状态机是否正确判别、
    负对照是否真正独立、报告是否如实呈现。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PYTHONUTF8", "1")
os.environ["SMP_MARKET_PROVIDER"] = "offline"

from fastapi.testclient import TestClient  # noqa: E402


def main() -> int:
    from apps.api.main import app

    payload = {
        # 20 只全池：覆盖 上交所主板/深交所主板/创业板/科创板/白酒-消费/金融/科技/制造
        "universe": [
            "600519", "000001", "300750", "688981", "600036",
            "000858", "601318", "002594", "600000", "601899",
            "300059", "600030", "601012", "000333", "600276",
            "601888", "002415", "600887", "601166", "000651",
        ],
        # 挑选 3 个"设计上应有区分度"的因子做事件研究
        "factor_ids": ["B_MONTH_003", "B_DAY_001", "H_DAY_003"],
        "horizons": [5, 10, 20, 60],
        "sample_step_months": 3,
        "date_from": "2021-01-01",
        "date_to": "2026-09-01",
        "run_negative_controls": True,
        "persist": True,
    }

    out_dir = ROOT / "artifacts" / "acceptance"
    out_dir.mkdir(parents=True, exist_ok=True)

    with TestClient(app) as client:
        resp = client.post("/api/v1/research/run", json=payload)
        body = resp.json()
        (out_dir / "real_research_run.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if resp.status_code != 200:
            print(f"研究运行失败 [{resp.status_code}]:\n{json.dumps(body, ensure_ascii=False)[:2000]}",
                  file=sys.stderr)
            return 1

    es = body["event_study"]
    print(f"实验: {body['experiment_id']}")
    print(f"research_status: {body['research_status']}")
    print(f"  理由: {body['research_status_reasons']}")
    print(f"事件数: {es['event_count']}  股票覆盖: {es['universe_size']}")
    print(f"数据源: {body['data_source']}")
    print()
    print("持有期统计：")
    for h in es["horizons"]:
        print(f"  {h['horizon']}D  n={h['sample_count']:>4} up={h.get('up_rate')} "
              f"mean={h.get('mean_return')} median={h.get('median_return')}")
    nc = body.get("negative_controls")
    if nc:
        print("\n负对照：")
        for r in nc["results"]:
            jac = r.get("jaccard_with_real")
            print(f"  {r['kind']:<20} verdict={r['verdict']:<14} "
                  f"Jaccard={jac if jac is None else round(jac, 3)} "
                  f"真实n={r.get('real_event_count')} 对照n={r.get('event_count')}")
        print(f"\n总结论: {nc['conclusion']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
