"""重放冻结的 F5-EXP-001/002；输入和输出根固定使用本机 settings.data_dir。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import settings  # noqa: E402
from src.research.f5_preregistered_experiments import run_f5_preregistered_experiments  # noqa: E402


def main() -> int:
    reports = run_f5_preregistered_experiments(settings.data_dir)
    summary = [
        {
            "experiment_id": item["experiment_id"],
            "research_status": item.get("research_status"),
            "registered_tests": len(item.get("registered_tests", [])),
            "result_digest": item.get("result_digest"),
        }
        for item in reports
    ]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
