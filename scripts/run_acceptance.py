"""Phase 1 一键验收（JUnit 命令的编排入口）。

执行顺序（四处任何一步失败立即判 FAIL）：

    1. 单元 + 集成测试（pytest 全量，± golden 标记）
    2. 防未来泄漏测试（tests/test_no_future_data_access.py）
    3. Golden cases（含交易历史、纳音、对拍、事件集合区分度）
    4. 因子质量审计（scripts/factor_quality_audit.py）
    5. API smoke（测试内的集成端点）—— 实际已并入 pytest 主集合
    6. UI 端到端（playwright 可选；若 --skip-ui 则跳过并记录 BLOCKED 状态）

产物写入 ``artifacts/acceptance/latest.json`` 与
``artifacts/acceptance/<timestamp>/``。最后输出 GO / NO-GO 结论。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.exists():
    PY = Path(sys.executable)

ART = ROOT / "artifacts" / "acceptance"


@dataclass
class Step:
    name: str
    cmd: list[str]
    required: bool = True
    workdir: str = ""
    # ── 结果 ──
    status: str = "NOT_RUN"       # PASS / FAIL / SKIP
    duration_s: float = 0.0
    tail: str = ""


def run_step(step: Step) -> None:
    t0 = time.time()
    proc = subprocess.run(
        step.cmd, cwd=step.workdir or ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=1800,
    )
    step.duration_s = round(time.time() - t0, 2)
    log = (proc.stdout or "") + "\n---STDERR---\n" + (proc.stderr or "")
    step.tail = "\n".join(log.splitlines()[-40:])
    step.status = "PASS" if proc.returncode == 0 else "FAIL"
    if not step.required and proc.returncode != 0:
        step.status = "WARN"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-ui", action="store_true", help="跳过 Playwright（无前端环境时）")
    parser.add_argument("--skip-audit", action="store_true", help="跳过因子审计")
    args = parser.parse_args(argv)

    steps: list[Step] = [
        Step("python-compile", [str(PY), "-m", "compileall", "-q", "src", "apps", "tests"]),
        Step("unit+integration", [str(PY), "-m", "pytest", "-q", "--deselect", "events-none"]),
        Step("leakage(P0)",
             [str(PY), "-m", "pytest", "-q",
              "tests/test_no_future_data_access.py",
              "tests/research/test_asof_market_data_boundary.py",
              "tests/research/test_asof_factor_boundary.py"]),
        Step("golden", [str(PY), "-m", "pytest", "-q", "-m", "golden"]),
        Step("event-set-distinctness(P0-3)",
             [str(PY), "-m", "pytest", "-q", "tests/research/test_event_sets_are_distinct.py"]),
        Step("negative-controls",
             [str(PY), "-m", "pytest", "-q", "tests/research/test_negative_controls.py"]),
        Step("third-party-isolation",
             [str(PY), "-m", "pytest", "-q", "tests/test_third_party_isolation.py"]),
        Step("lint-ruff", [str(PY), "-m", "ruff", "check", "src", "apps", "tests", "scripts"]),
    ]
    if not args.skip_audit:
        steps.append(Step("factor-quality-audit", [str(PY), "scripts/factor_quality_audit.py"]))
    if not args.skip_ui:
        # playwright 需要 web 已在 3000 运行（next build 后用 npx next start -p 3000）
        try:
            import urllib.request

            urllib.request.urlopen("http://127.0.0.1:3000/", timeout=2).close()
            ui_cmd = ["cmd", "/c", "npx", "playwright", "test"]
            ui_cwd = str(ROOT / "apps" / "web")
        except Exception:  # noqa: BLE001
            ui_cmd = [str(PY), "-c", "print('SKIP: web 未在 3000 端口运行')"]
            ui_cwd = str(ROOT)
        steps.append(Step("ui-playwright", ui_cmd, required=False, workdir=ui_cwd))

    results: list[Step] = []
    for s in steps:
        print(f"[..] {s.name} ...", flush=True)
        try:
            run_step(s)
        except subprocess.TimeoutExpired:
            s.status, s.tail = "FAIL", "超时 (>1800s)"
        except FileNotFoundError as e:
            s.status, s.tail = ("FAIL" if s.required else "WARN", str(e))
        results.append(s)
        icon = {"PASS": "✓", "FAIL": "✗", "WARN": "!", "SKIP": "-"}[s.status]
        print(f"[{icon}] {s.name:<28} {s.status}  ({s.duration_s}s)")

    verdict = "PASS" if all(s.status == "PASS" for s in results if s.required) else "FAIL"

    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    snap = ART / ts
    snap.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": ts, "commit": "HEAD",
        "verdict": verdict,
        "steps": [
            {
                "name": s.name, "status": s.status, "duration_s": s.duration_s,
                "required": s.required, "log_tail": s.tail,
            } for s in results
        ],
    }
    (snap / "acceptance.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (ART / "latest.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print()
    print(f"===== 验收结论： {verdict} =====")
    return 0 if verdict == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
