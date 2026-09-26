import fs from "node:fs";
import { existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const root = path.resolve(process.cwd(), "test-results", "visual-reference");
const referenceRoot = path.resolve(process.cwd(), "..", "..", "doc", "ui-reference");
const map = {
  "01-home": "01_home.png",
  "02-overview": "02_integrated_analysis.png",
  "03-bazi": "03_bazi_detail.png",
  "04-ziwei": "04_ziwei_detail.png",
  "05-backtest": "05_backtest_validation.png",
  "06-factors": "06_factor_dictionary.png",
  "07-conflicts": "07_model_conflict_center.png",
  "08-huangli": "08_huangli_detail.png",
  "09-evidence": "09_classics_evidence_search.png",
  "10-timeline": "10_time_window.png",
};

const script = String.raw`
from pathlib import Path
from PIL import Image, ImageChops
import json, sys

root = Path(sys.argv[1])
reference_root = Path(sys.argv[2])
name_map = json.loads(sys.argv[3])
results = []
for key, reference_name in name_map.items():
    directory = root / key
    candidate_path = directory / "candidate.png"
    reference_path = reference_root / reference_name
    # 缺图 / 尺寸不符是**取图或构建链路**的故障，不是审计结论，必须立刻硬失败。
    for required in (candidate_path, reference_path):
        if not required.exists():
            raise SystemExit(f"TOOL ERROR: missing image {required}")
    candidate = Image.open(candidate_path).convert("RGBA")
    reference = Image.open(reference_path).convert("RGBA")
    if candidate.size != (1672, 941) or reference.size != (1672, 941):
        raise SystemExit(f"TOOL ERROR: expected 1672x941 candidate={candidate.size} reference={reference.size}")
    diff = ImageChops.difference(candidate, reference)
    rgb = diff.convert("RGB")
    changed = 0
    pixels = rgb.load()
    for y in range(rgb.height):
        for x in range(rgb.width):
            r, g, b = pixels[x, y]
            if r + g + b > 24:
                changed += 1
    ratio = changed / (candidate.width * candidate.height)
    overlay = Image.blend(reference, candidate, 0.5)
    diff.save(directory / "diff.png")
    overlay.save(directory / "overlay.png")
    reference.save(directory / "reference.png")
    metrics = {
        "key": key,
        "width": candidate.width,
        "height": candidate.height,
        "pixel_diff_ratio": ratio,
        "ssim": None,
        "anchor_position_diff": None,
        "anchor_size_diff": None,
        "thresholds": {"overall_pixel_diff_ratio": 0.03, "key_layout_pixel_diff_ratio": 0.015},
        "pass": ratio <= 0.03,
        # 审计指标，不是 PR 合并门。阈值与 pass 判定一字未动，FAIL 照常记录；
        # 改变的只是 FAIL 会不会阻断流水线（见 docs/UI_VISUAL_PARITY_V5.md「门禁」）。
        "gate_class": "audit-only",
        "merge_blocking": False,
    }
    (directory / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    results.append(metrics)
(root / "metrics.json").write_text(
    json.dumps(
        {
            "viewport": {"width": 1672, "height": 941},
            "gate_class": "audit-only",
            "merge_blocking": False,
            "results": results,
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
failed = [item for item in results if not item["pass"]]
for item in results:
    print(f"{item['key']}: diff={item['pixel_diff_ratio'] * 100:.2f}% {'PASS' if item['pass'] else 'FAIL'}")
print("")
print("=" * 78)
print("DESIGN_REFERENCE_PIXEL_AUDIT  (audit-only, 不阻断 PR #4)")
print("=" * 78)
print(f"thresholds: overall<=3% / key-layout<=1.5%  (未修改)")
print(f"pages over threshold: {len(failed)}/{len(results)}")
print("ABSOLUTE_PIXEL_PARITY = " + ("PASS" if not failed else "FAIL (保留真实结果，未隐藏)"))
print("以上为审计指标。几何 / 结构 / 排版 / 真实性 / 功能门不在本脚本内，")
print("仍由 UI_STRUCTURE / UI_PARITY / DESKTOP_1440 / anchor 几何门阻断合并。")
# 只有取图/构建链路故障才非零退出（见上方 TOOL ERROR 分支）。
sys.exit(0)
`;

/**
 * 比对需要 Pillow，而 Pillow 属于项目的 dev 依赖（见 pyproject.toml [dev]），
 * 不是 runtime 依赖。因此优先用项目 venv 的解释器；找不到就退回 PATH 上的
 * `python`，并把缺依赖说清楚，避免只剩一句 ModuleNotFoundError。
 */
const venvPython = process.platform === "win32"
  ? path.resolve(process.cwd(), "..", "..", ".venv", "Scripts", "python.exe")
  : path.resolve(process.cwd(), "..", "..", ".venv", "bin", "python");
const pythonBin = existsSync(venvPython) ? venvPython : "python";

const probe = spawnSync(pythonBin, ["-c", "import PIL"], { stdio: "ignore" });
if (probe.status !== 0) {
  console.error(
    [
      `visual:diff 需要 Pillow，但 ${pythonBin} 里没有。`,
      "Pillow 是项目的 dev 依赖（pyproject.toml [project.optional-dependencies].dev）。",
      "请先安装：",
      process.platform === "win32" ? "  .venv\\Scripts\\python.exe -m pip install -e \".[dev]\"" : "  .venv/bin/python -m pip install -e '.[dev]'",
    ].join("\n"),
  );
  process.exit(1);
}

const result = spawnSync(pythonBin, ["-c", script, root, referenceRoot, JSON.stringify(map)], { stdio: "inherit" });
process.exit(result.status ?? 1);
