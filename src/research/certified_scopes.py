"""Pinned W2-to-W4 bindings approved for limited-scope exploratory queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class CertifiedDatasetPin:
    dataset_id: str
    dataset_digest: str
    scope_certificate_id: str
    scope_certificate_sha256: str
    w2_manifest_sha256: str
    security_id: str
    stock_code: str
    exchange: str
    date_from: date
    date_to: date
    row_count: int
    pit_version: str
    birth_profile_source_version: str
    label_version: str


CERTIFIED_DATASET_PINS: dict[str, CertifiedDatasetPin] = {
    "w4-certified-002561-20120223-20180514-v2-label-ends": CertifiedDatasetPin(
        dataset_id="w4-certified-002561-20120223-20180514-v2-label-ends",
        dataset_digest="d024ef9e2084563ce1dd3d1ce61f9dcf48daf15d49f93f2c96eb95d58156ac99",
        scope_certificate_id="w2-szse-002561-20120223-20180514-v1",
        scope_certificate_sha256="f8eabbf0223d6dbd28ea3343438c68944731ffc46a7d33eff359a91a6b19cb75",
        w2_manifest_sha256="e60d137e47073f1891d83544d0b382e9010be1063ca3764eee85f878e7da9d6e",
        security_id="dba06cf4-8e33-594d-a077-595dbcb029bd",
        stock_code="002561",
        exchange="SZSE",
        date_from=date(2012, 2, 23),
        date_to=date(2018, 5, 14),
        row_count=1513,
        pit_version="stock-fortune-pit-universe-v2",
        birth_profile_source_version="v2-phase4b-listing_open",
        label_version="w3-hfq-adjfactor-v2",
    ),
    "w4-certified-002561-20120223-20180514-v3-path-risk": CertifiedDatasetPin(
        dataset_id="w4-certified-002561-20120223-20180514-v3-path-risk",
        dataset_digest="1be932385a9531c9e7b7ce0847fb872b273248f06453d3a73d6fb0970d34b852",
        scope_certificate_id="w2-szse-002561-20120223-20180514-v1",
        scope_certificate_sha256="f8eabbf0223d6dbd28ea3343438c68944731ffc46a7d33eff359a91a6b19cb75",
        w2_manifest_sha256="e60d137e47073f1891d83544d0b382e9010be1063ca3764eee85f878e7da9d6e",
        security_id="dba06cf4-8e33-594d-a077-595dbcb029bd",
        stock_code="002561",
        exchange="SZSE",
        date_from=date(2012, 2, 23),
        date_to=date(2018, 5, 14),
        row_count=1513,
        pit_version="stock-fortune-pit-universe-v2",
        birth_profile_source_version="v2-phase4b-listing_open",
        label_version="w3-hfq-adjfactor-v3",
    ),
}


def certified_scope_state(manifest: dict[str, Any]) -> tuple[str, str, CertifiedDatasetPin | None]:
    """Check a manifest against the code-pinned certificate and dataset identity."""
    dataset_id = str(manifest.get("dataset_id", ""))
    pin = CERTIFIED_DATASET_PINS.get(dataset_id)
    if pin is None:
        return "NOT_CERTIFIED", "数据集没有本机登记的 W2 证书与 W4 digest 绑定。", None

    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        return "CERTIFICATE_MISMATCH", "数据集缺少可核验的认证元数据。", pin
    scope = metadata.get("scope")
    input_versions = metadata.get("input_versions")
    certificate = metadata.get("scope_certificate")
    if not all(isinstance(item, dict) for item in (scope, input_versions, certificate)):
        return "CERTIFICATE_MISMATCH", "认证范围、输入版本或证书副本缺失。", pin
    certificate_inputs = input_versions.get("scope_certificate_input_versions")
    research_dates = scope.get("research_dates")
    dates_are_pinned = (
        isinstance(research_dates, list)
        and len(research_dates) == pin.row_count
        and all(isinstance(value, str) for value in research_dates)
        and research_dates == sorted(set(research_dates))
        and research_dates[0] == pin.date_from.isoformat()
        and research_dates[-1] == pin.date_to.isoformat()
    )
    binding_matches = (
        manifest.get("dataset_digest") == pin.dataset_digest
        and metadata.get("status") == "CERTIFIED_LIMITED_SCOPE_EXPLORATORY"
        and metadata.get("research_eligible") is True
        and metadata.get("confirmatory_research_eligible") is False
        and scope.get("security_id") == pin.security_id
        and scope.get("stock_code") == pin.stock_code
        and scope.get("exchange") == pin.exchange
        and input_versions.get("scope_certificate_id") == pin.scope_certificate_id
        and input_versions.get("scope_certificate_sha256") == pin.scope_certificate_sha256
        and certificate.get("certificate_id") == pin.scope_certificate_id
        and certificate.get("certificate_sha256") == pin.scope_certificate_sha256
        and certificate.get("status") == "CERTIFIED_LIMITED_OBSERVATION_RANGE"
        and input_versions.get("w2_manifest_sha256") == pin.w2_manifest_sha256
        and isinstance(certificate_inputs, dict)
        and certificate_inputs.get("w2_manifest_sha256") == pin.w2_manifest_sha256
        and input_versions.get("pit_dataset_version") == pin.pit_version
        and input_versions.get("source_birth_profile_version") == pin.birth_profile_source_version
        and dates_are_pinned
        and int(manifest.get("row_count", -1)) == pin.row_count
    )
    if not binding_matches:
        return "CERTIFICATE_MISMATCH", "数据集 digest、证券/日期范围、证书或输入版本与登记绑定不一致。", pin
    if (
        manifest.get("status") != "COMPLETE"
        or int(manifest.get("complete_shard_count", -1)) != int(manifest.get("expected_shard_count", -2))
        or manifest.get("missing_shards")
        or manifest.get("failed_shards")
    ):
        return "DATA_MISSING", "认证数据集存在未完成、缺失或失败分片。", pin
    return "CERTIFIED_LIMITED_SCOPE", "仅认证 002561 在证书所列观察日期范围内的探索性研究。", pin


__all__ = ["CERTIFIED_DATASET_PINS", "CertifiedDatasetPin", "certified_scope_state"]
