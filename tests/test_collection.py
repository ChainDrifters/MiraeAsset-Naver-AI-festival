from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from mirae_asset_graph.ingest.basket_kr import ManagerBasketTarget
from mirae_asset_graph.ingest.artifacts import publish_immutable
from mirae_asset_graph.ingest.collection import (
    CollectionRunner,
    _ready_batch_id,
    manager_document_id,
    verify_collection,
)
from mirae_asset_graph.ingest.manifest import ManifestEntry, Phase, Status, append_entry, read_manifest
from mirae_asset_graph.ingest.records import HoldingsRecord, serialize_jsonl, write_jsonl


@dataclass(frozen=True)
class _Target:
    target_id: str
    as_of: date
    published_at: datetime
    source_url: str
    fund_isin: str = "US5007676944"

    @property
    def accession(self) -> str:
        return self.target_id


class _Adapter:
    source = "sec_nport"

    def __init__(self, target: _Target, root: Path, *, include_new_resolution: bool = False) -> None:
        self.target = target
        self.root = root
        self.raw_root = root
        self.include_new_resolution = include_new_resolution

    def discover(self, start=None, end=None, cutoff=None):
        return [self.target]

    def fetch(self, target: _Target) -> Path:
        path = self.root / "raw.xml"
        path.write_bytes(b"immutable raw")
        return path

    def normalize(self, target: _Target, raw_path: Path, output_dir: Path):
        record = HoldingsRecord.create(
            fund_isin="US5007676944",
            constituent_isin="CNE1000041K3",
            constituent_name="Cambricon",
            weight=0.1,
            as_of=target.as_of,
            source_quantity=1,
            source_currency="USD",
            source_market_value=10,
            weight_source="source_published",
            identifier_method="source_isin",
            published_at=target.published_at,
            source_document_id=target.target_id,
            source_url=target.source_url,
            evidence_basis="regulatory_filing",
            source_row_id="position:1",
        )
        selected = [record]
        if self.include_new_resolution:
            selected.append(
                HoldingsRecord.create(
                    fund_isin=target.fund_isin,
                    constituent_isin="US0000000002",
                    constituent_name="Newly resolved holding",
                    weight=0.2,
                    as_of=target.as_of,
                    weight_source="source_published",
                    identifier_method="crosswalk",
                    published_at=target.published_at,
                    source_document_id=target.target_id,
                    source_url=target.source_url,
                    evidence_basis="regulatory_filing",
                    source_row_id="position:2",
                )
            )
        payload, count = serialize_jsonl(selected)
        records = publish_immutable(output_dir / "records", payload, ".jsonl")
        quarantine = publish_immutable(
            output_dir / "quarantine", b"", ".quarantine.jsonl"
        )
        return records, quarantine, count, 0


class _FailingAdapter(_Adapter):
    def fetch(self, target: _Target) -> Path:
        raise RuntimeError("failed https://user:secret@www.sec.gov/file.xml?token=secret")


def _target() -> _Target:
    return _Target(
        target_id="0000000001-26-000001",
        as_of=date(2026, 4, 11),
        published_at=datetime(2026, 4, 20, tzinfo=UTC),
        source_url="https://www.sec.gov/example.xml",
    )


def test_collection_writes_ready_metadata_and_verifies_offline(tmp_path: Path) -> None:
    target = _target()
    runner = CollectionRunner(
        _Adapter(target, tmp_path),
        tmp_path / "manifest",
        tmp_path / "normalized",
        stable_target_id=lambda item: item.target_id,
        document_id=lambda item, raw_sha: item.target_id,
        config_digest="c" * 64,
        crosswalk_sha256="a" * 64,
        normalization_input_digest="b" * 64,
    )

    summary = runner.run("collect-test")
    entry = read_manifest("sec_nport", tmp_path / "manifest")[-1]
    verified = verify_collection(
        "sec_nport",
        [target],
        tmp_path / "manifest",
        stable_target_id=lambda item: item.target_id,
        expected_config_digest="c" * 64,
        expected_crosswalk_sha256="a" * 64,
        expected_normalization_input_digest="b" * 64,
        raw_root=tmp_path,
        normalized_root=tmp_path / "normalized",
    )

    assert summary.loaded_rows == 0
    assert entry.phase is Phase.READY and entry.status is Status.READY
    assert entry.artifact_sha256 and len(entry.artifact_sha256) == 64
    assert entry.normalized_sha256 and entry.quarantine_sha256
    assert entry.normalized_count == 1 and entry.quarantine_count == 0
    assert len(verified) == 1 and len(verified[0].records) == 1


def test_verification_rejects_tampering(tmp_path: Path) -> None:
    target = _target()
    runner = CollectionRunner(
        _Adapter(target, tmp_path),
        tmp_path / "manifest",
        tmp_path / "normalized",
        stable_target_id=lambda item: item.target_id,
        document_id=lambda item, raw_sha: item.target_id,
        config_digest="c" * 64,
        crosswalk_sha256="a" * 64,
        normalization_input_digest="b" * 64,
    )
    runner.run("collect-test")
    entry = read_manifest("sec_nport", tmp_path / "manifest")[-1]
    assert entry.normalized_path is not None
    (tmp_path / "normalized" / entry.normalized_path).write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="normalized checksum mismatch"):
        verify_collection(
            "sec_nport",
            [target],
            tmp_path / "manifest",
            stable_target_id=lambda item: item.target_id,
            expected_config_digest="c" * 64,
            expected_crosswalk_sha256="a" * 64,
            expected_normalization_input_digest="b" * 64,
            raw_root=tmp_path,
            normalized_root=tmp_path / "normalized",
        )


def test_collection_failure_appends_sanitized_failed_manifest(tmp_path: Path) -> None:
    target = _target()
    runner = CollectionRunner(
        _FailingAdapter(target, tmp_path),
        tmp_path / "manifest",
        tmp_path / "normalized",
        stable_target_id=lambda item: item.target_id,
        document_id=lambda item, raw_sha: item.target_id,
        config_digest="d" * 64,
        crosswalk_sha256="a" * 64,
        normalization_input_digest="b" * 64,
        continue_on_error=True,
    )
    summary = runner.run("failed-run")
    entry = read_manifest("sec_nport", tmp_path / "manifest")[-1]
    assert summary.failed_targets == 1
    assert entry.phase is Phase.FAILED and entry.status is Status.FAILED
    assert entry.stable_target_id == target.target_id
    assert entry.config_digest == "d" * 64
    assert entry.error is not None
    assert "secret" not in entry.error


def test_verification_rejects_config_digest_mismatch(tmp_path: Path) -> None:
    target = _target()
    runner = CollectionRunner(
        _Adapter(target, tmp_path),
        tmp_path / "manifest",
        tmp_path / "normalized",
        stable_target_id=lambda item: item.target_id,
        document_id=lambda item, raw_sha: item.target_id,
        config_digest="e" * 64,
        crosswalk_sha256="a" * 64,
        normalization_input_digest="b" * 64,
    )
    runner.run("collect-test")
    with pytest.raises(ValueError, match="normalization-input digest"):
        verify_collection(
            "sec_nport",
            [target],
            tmp_path / "manifest",
            stable_target_id=lambda item: item.target_id,
            expected_config_digest="f" * 64,
            expected_crosswalk_sha256="a" * 64,
            expected_normalization_input_digest="b" * 64,
            raw_root=tmp_path,
            normalized_root=tmp_path / "normalized",
        )


def test_verification_rejects_symlink_artifact(tmp_path: Path) -> None:
    target = _target()
    runner = CollectionRunner(
        _Adapter(target, tmp_path),
        tmp_path / "manifest",
        tmp_path / "normalized",
        stable_target_id=lambda item: item.target_id,
        document_id=lambda item, raw_sha: item.target_id,
        config_digest="1" * 64,
        crosswalk_sha256="a" * 64,
        normalization_input_digest="b" * 64,
    )
    runner.run("collect-test")
    entry = read_manifest("sec_nport", tmp_path / "manifest")[-1]
    assert entry.normalized_path is not None
    normalized = tmp_path / "normalized" / entry.normalized_path
    original = normalized.with_suffix(".original")
    normalized.rename(original)
    normalized.symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        verify_collection(
            "sec_nport",
            [target],
            tmp_path / "manifest",
            stable_target_id=lambda item: item.target_id,
            expected_config_digest="1" * 64,
            expected_crosswalk_sha256="a" * 64,
            expected_normalization_input_digest="b" * 64,
            raw_root=tmp_path,
            normalized_root=tmp_path / "normalized",
        )


def test_verification_keeps_all_manager_amendment_versions(tmp_path: Path) -> None:
    target = ManagerBasketTarget(
        manager_code="reviewed-manager",
        fund_code="fund-a",
        fund_isin="US5007676944",
        source_url="https://holdings.manager.example/fund.csv",
        as_of=date(2026, 4, 11),
        published_at=datetime(2026, 4, 12, tzinfo=UTC),
        format_hint="csv",
        reviewed_hosts=("holdings.manager.example",),
    )
    raw_root = tmp_path / "raw"
    normalized_root = tmp_path / "normalized"
    manifest_root = tmp_path / "manifest"
    for index, raw_bytes in enumerate((b"version-one", b"version-two"), start=1):
        raw_sha = hashlib.sha256(raw_bytes).hexdigest()
        document_id = manager_document_id(target, raw_sha)
        raw_rel = f"manager/{raw_sha}.csv"
        normalized_rel = f"manager/{raw_sha}.jsonl"
        quarantine_rel = f"manager/{raw_sha}.quarantine.jsonl"
        raw_path = raw_root / raw_rel
        normalized_path = normalized_root / normalized_rel
        quarantine_path = normalized_root / quarantine_rel
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        normalized_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(raw_bytes)
        record = HoldingsRecord.create(
            fund_isin=target.fund_isin,
            constituent_isin="CNE1000041K3",
            constituent_name=f"Cambricon amendment {index}",
            weight=0.1,
            as_of=target.as_of,
            weight_source="source_published",
            identifier_method="source_isin",
            source_document_id=document_id,
            source_url=target.source_url,
            published_at=target.published_at,
            evidence_basis="manager_published",
            source_row_id="row:2",
        )
        write_jsonl([record], normalized_path)
        quarantine_path.write_bytes(b"")
        append_entry(
            ManifestEntry(
                run_id=f"amendment-{index}",
                source="manager_basket",
                phase=Phase.READY,
                window_date=target.as_of,
                batch_id=_ready_batch_id(
                    "manager_basket", document_id, raw_sha, "b" * 64
                ),
                status=Status.READY,
                artifact_sha256=raw_sha,
                raw_path=raw_rel,
                normalized_path=normalized_rel,
                quarantine_path=quarantine_rel,
                normalized_sha256=hashlib.sha256(normalized_path.read_bytes()).hexdigest(),
                quarantine_sha256=hashlib.sha256(b"").hexdigest(),
                artifact_bytes=len(raw_bytes),
                normalized_bytes=normalized_path.stat().st_size,
                quarantine_bytes=0,
                normalized_count=1,
                quarantine_count=0,
                source_url=target.source_url,
                stable_target_id="reviewed-manager:fund-a:2026-04-11",
                source_document_id=document_id,
                published_at=target.published_at,
                config_digest="2" * 64,
                crosswalk_sha256="a" * 64,
                normalization_input_digest="b" * 64,
            ),
            manifest_root,
        )
    verified = verify_collection(
        "manager_basket",
        [target],
        manifest_root,
        stable_target_id=lambda item: "reviewed-manager:fund-a:2026-04-11",
        expected_config_digest="2" * 64,
        expected_crosswalk_sha256="a" * 64,
        expected_normalization_input_digest="b" * 64,
        raw_root=raw_root,
        normalized_root=normalized_root,
    )
    assert len(verified) == 2
    assert len({item.entry.source_document_id for item in verified}) == 2


def test_changed_crosswalk_selects_new_normalization_and_keeps_old_artifacts(
    tmp_path: Path,
) -> None:
    target = _target()
    manifest_root = tmp_path / "manifest"
    normalized_root = tmp_path / "normalized"
    first_runner = CollectionRunner(
        _Adapter(target, tmp_path),
        manifest_root,
        normalized_root,
        stable_target_id=lambda item: item.target_id,
        document_id=lambda item, raw_sha: item.target_id,
        config_digest="3" * 64,
        crosswalk_sha256="4" * 64,
        normalization_input_digest="5" * 64,
    )
    first_runner.run("crosswalk-old")
    first_entry = read_manifest("sec_nport", manifest_root)[-1]
    assert first_entry.normalized_path is not None
    first_path = normalized_root / first_entry.normalized_path
    first_bytes = first_path.read_bytes()

    second_runner = CollectionRunner(
        _Adapter(target, tmp_path, include_new_resolution=True),
        manifest_root,
        normalized_root,
        stable_target_id=lambda item: item.target_id,
        document_id=lambda item, raw_sha: item.target_id,
        config_digest="3" * 64,
        crosswalk_sha256="6" * 64,
        normalization_input_digest="7" * 64,
    )
    second_runner.run("crosswalk-new")
    verified = verify_collection(
        "sec_nport",
        [target],
        manifest_root,
        stable_target_id=lambda item: item.target_id,
        expected_config_digest="3" * 64,
        expected_crosswalk_sha256="6" * 64,
        expected_normalization_input_digest="7" * 64,
        raw_root=tmp_path,
        normalized_root=normalized_root,
    )
    assert len(verified) == 1
    assert len(verified[0].records) == 2
    assert first_path.read_bytes() == first_bytes
    assert verified[0].entry.normalized_path != first_entry.normalized_path


def test_conflicting_duplicate_ready_identity_is_rejected(tmp_path: Path) -> None:
    target = _target()
    runner = CollectionRunner(
        _Adapter(target, tmp_path),
        tmp_path / "manifest",
        tmp_path / "normalized",
        stable_target_id=lambda item: item.target_id,
        document_id=lambda item, raw_sha: item.target_id,
        config_digest="8" * 64,
        crosswalk_sha256="9" * 64,
        normalization_input_digest="a" * 64,
    )
    runner.run("duplicate-original")
    original = read_manifest("sec_nport", tmp_path / "manifest")[-1]
    append_entry(
        replace(
            original,
            run_id="duplicate-conflict",
            normalized_sha256="f" * 64,
        ),
        tmp_path / "manifest",
    )
    with pytest.raises(ValueError, match="conflicting READY normalized checksums"):
        verify_collection(
            "sec_nport",
            [target],
            tmp_path / "manifest",
            stable_target_id=lambda item: item.target_id,
            expected_config_digest="8" * 64,
            expected_crosswalk_sha256="9" * 64,
            expected_normalization_input_digest="a" * 64,
            raw_root=tmp_path,
            normalized_root=tmp_path / "normalized",
        )


def test_ready_batch_id_must_be_canonical(tmp_path: Path) -> None:
    target = _target()
    runner = CollectionRunner(
        _Adapter(target, tmp_path),
        tmp_path / "manifest",
        tmp_path / "normalized",
        stable_target_id=lambda item: item.target_id,
        document_id=lambda item, raw_sha: item.target_id,
        config_digest="b" * 64,
        crosswalk_sha256="c" * 64,
        normalization_input_digest="d" * 64,
    )
    runner.run("canonical")
    original = read_manifest("sec_nport", tmp_path / "manifest")[-1]
    append_entry(replace(original, run_id="forged", batch_id="reused-invalid"), tmp_path / "manifest")
    with pytest.raises(ValueError, match="canonical READY batch ID"):
        verify_collection(
            "sec_nport",
            [target],
            tmp_path / "manifest",
            stable_target_id=lambda item: item.target_id,
            expected_config_digest="b" * 64,
            expected_crosswalk_sha256="c" * 64,
            expected_normalization_input_digest="d" * 64,
            raw_root=tmp_path,
            normalized_root=tmp_path / "normalized",
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"raw_path": "different/raw.xml"},
        {"quarantine_sha256": "0" * 64},
        {"quarantine_count": 99},
        {"artifact_bytes": 999},
    ],
)
def test_duplicate_ready_requires_all_immutable_evidence_to_agree(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    target = _target()
    runner = CollectionRunner(
        _Adapter(target, tmp_path),
        tmp_path / "manifest",
        tmp_path / "normalized",
        stable_target_id=lambda item: item.target_id,
        document_id=lambda item, raw_sha: item.target_id,
        config_digest="e" * 64,
        crosswalk_sha256="f" * 64,
        normalization_input_digest="1" * 64,
    )
    runner.run("evidence-original")
    original = read_manifest("sec_nport", tmp_path / "manifest")[-1]
    append_entry(
        replace(original, run_id="evidence-conflict", **changes),
        tmp_path / "manifest",
    )
    with pytest.raises(ValueError, match="conflicting immutable READY evidence"):
        verify_collection(
            "sec_nport",
            [target],
            tmp_path / "manifest",
            stable_target_id=lambda item: item.target_id,
            expected_config_digest="e" * 64,
            expected_crosswalk_sha256="f" * 64,
            expected_normalization_input_digest="1" * 64,
            raw_root=tmp_path,
            normalized_root=tmp_path / "normalized",
        )
