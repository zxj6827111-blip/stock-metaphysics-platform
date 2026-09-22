import fs from "node:fs";
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
    candidate = Image.open(candidate_path).convert("RGBA")
    reference = Image.open(reference_path).convert("RGBA")
    if candidate.size != (1672, 941) or reference.size != (1672, 941):
        raise SystemExit(f"{key}: expected 1672x941 candidate={candidate.size} reference={reference.size}")
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
    }
    (directory / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    results.append(metrics)
(root / "metrics.json").write_text(json.dumps({"viewport": {"width": 1672, "height": 941}, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
for item in results:
    print(f"{item['key']}: diff={item['pixel_diff_ratio'] * 100:.2f}% {'PASS' if item['pass'] else 'FAIL'}")
if any(not item["pass"] for item in results):
    raise SystemExit(1)
`;

const result = spawnSync("python", ["-c", script, root, referenceRoot, JSON.stringify(map)], { stdio: "inherit" });
process.exit(result.status ?? 1);
