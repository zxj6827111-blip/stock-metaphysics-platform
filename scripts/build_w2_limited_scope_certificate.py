"""Build one replayable exploratory certificate without upgrading full W2."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_W2_ROOT = ROOT / "artifacts" / "w2-data-certification-20260927-full-06"
DEFAULT_MARKET_ROOT = Path("E:/AStockData/datasets/market_data")
DEFAULT_DATABASE = ROOT / "data" / "w8-local-runtime" / "smp.sqlite3"
DEFAULT_OUTPUT = (
    ROOT / "artifacts" / "w2-limited-scope-002561-2012-2018" / "scope_certificate.json"
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str,
    )


def build_certificate(*, w2_root: Path, market_root: Path, database: Path) -> dict[str, Any]:
    from scripts.build_w4_historical_dataset import _db_birth_inputs
    from scripts.w2_limited_scope_evidence import load_scope_evidence
    from src.research.scoped_data_certificate import build_limited_scope_certificate

    w2_root = w2_root.resolve(strict=True)
    market_root = market_root.resolve(strict=True)
    database = database.resolve(strict=True)
    material = load_scope_evidence(w2_root=w2_root, market_root=market_root)
    inputs = material["inputs"]
    scope = inputs["scope"]
    birth = _db_birth_inputs(database, "002561", "v2-phase4b-listing_open")
    if birth["master"]["exchange"] != "SZSE":
        raise ValueError("本机 stock master 与冻结证券身份交易所不一致")
    if birth["listing_date"].isoformat() != str(scope["listing_date"]):
        raise ValueError("本机 listing date 与 W2 SecurityMaster 不一致")
    profile_payload = _canonical_json(birth["profile"]).encode("utf-8")
    input_versions = {
        **material["input_versions"],
        "birth_profile_version": birth["profile_version"],
        "birth_profile_recorded_at": birth["profile_recorded_at"],
        "birth_profile_row_sha256": hashlib.sha256(profile_payload).hexdigest(),
    }
    certificate = build_limited_scope_certificate(
        audit=material["audit"],
        input_versions=input_versions,
        observed_listing_date=birth["listing_date"],
        pit_effective_start=date.fromisoformat(str(scope["pit_effective_start"])),
        pit_effective_end_exclusive=(
            date.fromisoformat(str(scope["pit_effective_end_exclusive"]))
            if scope.get("pit_effective_end_exclusive")
            else None
        ),
        evidence_cutoff=inputs["evidence_cutoff"],
    )
    return certificate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w2-root", type=Path, default=DEFAULT_W2_ROOT)
    parser.add_argument("--market-root", type=Path, default=DEFAULT_MARKET_ROOT)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    allowed_root = (
        ROOT / "artifacts" / "w2-limited-scope-002561-2012-2018"
    ).resolve()
    output = args.output.resolve()
    if not output.is_relative_to(allowed_root):
        parser.error(f"证书只能写入 {allowed_root}")
    if output.exists():
        parser.error(f"拒绝覆盖已存在证书：{output}")
    try:
        certificate = build_certificate(
            w2_root=args.w2_root,
            market_root=args.market_root,
            database=args.database,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(_canonical_json(certificate))
            stream.write("\n")
    except (KeyError, FileNotFoundError, RuntimeError, ValueError, OSError) as exc:
        parser.exit(2, f"W2 有限范围证书未完成：{type(exc).__name__}: {exc}\n")
    print(json.dumps({
        "certificate_path": str(output),
        "certificate_id": certificate["certificate_id"],
        "certificate_sha256": certificate["certificate_sha256"],
        "status": certificate["status"],
        "research_observation_count": certificate["scope"]["observation_count"],
        "outcome_maturity_end_date": certificate["audit"]["outcome_maturity_end_date"],
        "corporate_action_count": certificate["audit"]["corporate_action_reconciliation"]["action_count"],
        "confirmatory_research_eligible": certificate["confirmatory_research_eligible"],
        "full_pit_universe_status": certificate["input_versions"]["full_pit_universe_status"],
        "limitations": certificate["limitations"],
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
