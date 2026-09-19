"""在真实导入快照上跑一次多模型共振研究（Phase 2C 交付证据）。

输出：artifacts/acceptance/consensus_research.json

用法：
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/run_consensus_research.py
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

UNIVERSE = [
    "600519", "000001", "300750", "688981", "600036",
    "000858", "601318", "002594", "600000", "601899",
    "300059", "600030", "601012", "000333", "600276",
    "601888", "002415", "600887", "601166", "000651",
]


def main() -> int:
    from apps.api.main import app

    payload = {
        "universe": UNIVERSE,
        "horizon": 20,
        "date_from": "2021-01-01",
        "date_to": "2026-06-01",
        "sample_step_months": 3,
        "variant_mode": "forward",
        "run_negative_controls": True,
        "persist": False,
    }

    out_dir = ROOT / "artifacts" / "acceptance"
    out_dir.mkdir(parents=True, exist_ok=True)

    with TestClient(app) as client:
        resp = client.post("/api/v1/research/consensus", json=payload)
        body = resp.json()
        (out_dir / "consensus_research.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if resp.status_code != 200:
            print(f"共振研究失败 [{resp.status_code}]:\n{json.dumps(body, ensure_ascii=False)[:2000]}",
                  file=sys.stderr)
            return 1

    print(f"实验 {body['experiment_id']}")
    print(f"样本 {body['data_source']['rows']} 行 / 股票 {body['universe_size']} 只 / "
          f"采样点 {body['sample_dates']}")
    print(f"整体状态：{body['overall_research_status']}")
    for r in body["overall_reasons"]:
        print(f"  · {r}")
    print()
    print("组合结果：")
    for c in body["combos"]:
        print(f"  {c['combo_id']:26s} ev={c['event_count']:4d} "
              f"up={c['up_rate']} mean={c['mean_return']} "
              f"ctrl={c['control_mean_return']} jacc={c['jaccard_with_real']} "
              f"p={c['p_value']} -> {c['control_result']}/{c['research_status']}")
    print()
    print(f"多重比较：{body['multiple_testing']['warning_level']} "
          f"alpha={body['multiple_testing']['bonferroni_alpha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
