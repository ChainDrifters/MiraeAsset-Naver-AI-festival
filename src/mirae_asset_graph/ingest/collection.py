"""Offline-verifiable collection artifacts, with no Neo4j dependency."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Generic, TypeVar

from ..model import file_sha256
from .manifest import ManifestEntry, Phase, Status, append_entry, read_manifest
from .records import HoldingsRecord, read_jsonl, read_jsonl_bytes
from .runner import HoldingsAdapter, RunSummary, _sanitize_error

T = TypeVar("T")


@dataclass(frozen=True)
class VerifiedCollection:
    entry: ManifestEntry
    records: tuple[HoldingsRecord, ...]


class CollectionRunner(Generic[T]):
    """Fetch and normalize targets, then seal each artifact as READY."""

    def __init__(
        self,
        adapter: HoldingsAdapter[T],
        manifest_root: Path,
        normalized_root: Path,
        *,
        stable_target_id: Callable[[T], str],
        document_id: Callable[[T, str], str],
        config_digest: str,
        crosswalk_sha256: str,
        normalization_input_digest: str,
        continue_on_error: bool = True,
    ) -> None:
        self.adapter = adapter
        self.manifest_root = Path(manifest_root)
        self.normalized_root = Path(normalized_root)
        self.stable_target_id = stable_target_id
        self.document_id = document_id
        self.config_digest = config_digest
        self.crosswalk_sha256 = crosswalk_sha256
        self.normalization_input_digest = normalization_input_digest
        self.continue_on_error = continue_on_error

    def run(
        self,
        run_id: str,
        start: date | None = None,
        end: date | None = None,
        cutoff: datetime | None = None,
    ) -> RunSummary:
        targets = sorted(self.adapter.discover(start=start, end=end, cutoff=cutoff), key=repr)
        fetched = normalized = quarantined = failed = 0
        for target in targets:
            try:
                raw_path = self.adapter.fetch(target)
                fetched += 1
                raw_sha256 = file_sha256(raw_path)
                retrieved_at = datetime.now(UTC)
                records_path, quarantine_path, record_count, quarantine_count = (
                    self.adapter.normalize(target, raw_path, self.normalized_root)
                )
                normalized += 1
                quarantined += quarantine_count
                records = read_jsonl(records_path)
                source_document_id = self.document_id(target, raw_sha256)
                _validate_normalized_identity(target, records, source_document_id)
                if len(records) != record_count:
                    raise ValueError("normalized record count does not match adapter result")
                ready_at = datetime.now(UTC)
                _ = append_entry(
                    ManifestEntry(
                        run_id=run_id,
                        source=self.adapter.source,
                        phase=Phase.READY,
                        window_date=_target_date(target),
                        batch_id=_ready_batch_id(
                            self.adapter.source,
                            source_document_id,
                            raw_sha256,
                            self.normalization_input_digest,
                        ),
                        status=Status.READY,
                        artifact_sha256=raw_sha256,
                        started_at=retrieved_at,
                        finished_at=ready_at,
                        raw_path=_relative_path(raw_path, self.adapter.raw_root),
                        normalized_path=_relative_path(records_path, self.normalized_root),
                        quarantine_path=_relative_path(quarantine_path, self.normalized_root),
                        normalized_sha256=file_sha256(records_path),
                        quarantine_sha256=file_sha256(quarantine_path),
                        artifact_bytes=raw_path.stat().st_size,
                        normalized_bytes=records_path.stat().st_size,
                        quarantine_bytes=quarantine_path.stat().st_size,
                        normalized_count=record_count,
                        quarantine_count=quarantine_count,
                        source_url=_target_text(target, "source_url"),
                        stable_target_id=self.stable_target_id(target),
                        source_document_id=source_document_id,
                        published_at=_target_datetime(target, "published_at"),
                        retrieved_at=retrieved_at,
                        config_digest=self.config_digest,
                        crosswalk_sha256=self.crosswalk_sha256,
                        normalization_input_digest=self.normalization_input_digest,
                    ),
                    self.manifest_root,
                )
            except Exception as error:
                failed += 1
                now = datetime.now(UTC)
                stable_id = self.stable_target_id(target)
                _ = append_entry(
                    ManifestEntry(
                        run_id=run_id,
                        source=self.adapter.source,
                        phase=Phase.FAILED,
                        window_date=_target_date(target),
                        batch_id=hashlib.sha256(
                            f"failed|{self.adapter.source}|{stable_id}|{run_id}".encode("utf-8")
                        ).hexdigest(),
                        status=Status.FAILED,
                        started_at=now,
                        finished_at=now,
                        error=_sanitize_error(error),
                        source_url=_target_text(target, "source_url"),
                        stable_target_id=stable_id,
                        published_at=_target_datetime(target, "published_at"),
                        config_digest=self.config_digest,
                        crosswalk_sha256=self.crosswalk_sha256,
                        normalization_input_digest=self.normalization_input_digest,
                    ),
                    self.manifest_root,
                )
                if not self.continue_on_error:
                    raise
        return RunSummary(
            discovered=len(targets),
            fetched=fetched,
            normalized=normalized,
            loaded_rows=0,
            quarantined=quarantined,
            skipped_batches=0,
            failed_targets=failed,
        )


def verify_collection(
    source: str,
    targets: Iterable[T],
    manifest_root: Path,
    *,
    stable_target_id: Callable[[T], str],
    expected_config_digest: str,
    expected_crosswalk_sha256: str,
    expected_normalization_input_digest: str,
    raw_root: Path,
    normalized_root: Path,
) -> tuple[VerifiedCollection, ...]:
    """Recompute artifact evidence and reject identity/policy mismatches offline."""
    target_map = {stable_target_id(target): target for target in targets}
    ready: dict[str, list[ManifestEntry]] = {}
    evidence_by_identity: dict[tuple[str, ...], tuple[object, ...]] = {}
    for entry in read_manifest(source, manifest_root):
        if entry.phase is Phase.READY and entry.status is Status.READY and entry.stable_target_id:
            if entry.source != source:
                raise ValueError("READY entry source does not match its manifest source")
            source_document_id = _required(entry.source_document_id, "source_document_id")
            artifact_sha256 = _required(entry.artifact_sha256, "artifact_sha256")
            input_digest = _required(
                entry.normalization_input_digest, "normalization_input_digest"
            )
            canonical_batch_id = _ready_batch_id(
                entry.source, source_document_id, artifact_sha256, input_digest
            )
            if entry.batch_id != canonical_batch_id:
                raise ValueError("READY entry does not use its canonical READY batch ID")
            identity = (
                entry.source,
                entry.stable_target_id,
                source_document_id,
                artifact_sha256,
                _required(entry.config_digest, "config_digest"),
                _required(entry.crosswalk_sha256, "crosswalk_sha256"),
                input_digest,
            )
            evidence = _immutable_ready_evidence(entry)
            previous = evidence_by_identity.get(identity)
            if previous is not None:
                if previous == evidence:
                    continue
                if previous[4] != evidence[4]:
                    raise ValueError(
                        "conflicting READY normalized checksums for one normalization-input identity"
                    )
                raise ValueError(
                    "conflicting immutable READY evidence for one normalization-input identity"
                )
            evidence_by_identity[identity] = evidence
            ready.setdefault(entry.stable_target_id, []).append(entry)
    missing = sorted(set(target_map) - set(ready))
    if missing:
        raise ValueError(f"Collection is not READY for target(s): {', '.join(missing)}")

    verified: list[VerifiedCollection] = []
    for target_id in sorted(target_map):
        target = target_map[target_id]
        matching = [
            entry
            for entry in ready[target_id]
            if entry.config_digest == expected_config_digest
            and entry.crosswalk_sha256 == expected_crosswalk_sha256
            and entry.normalization_input_digest == expected_normalization_input_digest
        ]
        if not matching:
            raise ValueError(
                f"READY manifest normalization-input digest mismatch for target: {target_id}"
            )
        seen_versions: set[tuple[str, str]] = set()
        for entry in sorted(
            matching, key=lambda item: (item.source_document_id or "", item.batch_id)
        ):
            raw_bytes = _read_safe_file(raw_root, _required(entry.raw_path, "raw_path"), "raw")
            normalized_bytes = _read_safe_file(
                normalized_root, _required(entry.normalized_path, "normalized_path"), "normalized"
            )
            quarantine_bytes = _read_safe_file(
                normalized_root, _required(entry.quarantine_path, "quarantine_path"), "quarantine"
            )
            _verify_bytes(raw_bytes, entry.artifact_sha256, entry.artifact_bytes, "raw")
            _verify_bytes(
                normalized_bytes, entry.normalized_sha256, entry.normalized_bytes, "normalized"
            )
            _verify_bytes(
                quarantine_bytes, entry.quarantine_sha256, entry.quarantine_bytes, "quarantine"
            )
            raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
            expected_document_id = (
                accession_document_id(target, raw_sha256)
                if source == "sec_nport"
                else manager_document_id(target, raw_sha256)
            )
            if entry.source_document_id != expected_document_id:
                raise ValueError("collection policy/identity mismatch: source_document_id")
            version_key = (expected_document_id, raw_sha256)
            if version_key in seen_versions:
                continue
            seen_versions.add(version_key)
            records = tuple(read_jsonl_bytes(normalized_bytes))
            if len(records) != entry.normalized_count:
                raise ValueError("normalized count mismatch")
            if _nonblank_line_count_bytes(quarantine_bytes) != entry.quarantine_count:
                raise ValueError("quarantine count mismatch")
            if entry.window_date != _target_date(target):
                raise ValueError("collection policy/identity mismatch: as_of")
            if entry.source_url != _target_text(target, "source_url"):
                raise ValueError("collection policy/identity mismatch: source_url")
            if entry.published_at != _target_datetime(target, "published_at"):
                raise ValueError("collection policy/identity mismatch: published_at")
            _validate_normalized_identity(target, records, expected_document_id)
            verified.append(VerifiedCollection(entry=entry, records=records))
    return tuple(verified)


def manager_document_id(target: object, raw_sha256: str) -> str:
    return f"{_target_text(target, 'manager_code')}:{_target_text(target, 'fund_code')}:" \
        f"{_target_date(target).isoformat()}:{raw_sha256}"


def accession_document_id(target: object, raw_sha256: str) -> str:
    _ = raw_sha256
    return _target_text(target, "accession")


def _validate_normalized_identity(
    target: object, records: Iterable[HoldingsRecord], source_document_id: str
) -> None:
    expected_date = _target_date(target)
    expected_url = _target_text(target, "source_url")
    expected_published = _target_datetime(target, "published_at")
    expected_fund_isin = _target_text(target, "fund_isin")
    for record in records:
        if (
            record.as_of != expected_date
            or record.source_url != expected_url
            or record.published_at != expected_published
            or record.source_document_id != source_document_id
            or record.fund_isin != expected_fund_isin
        ):
            raise ValueError("normalized record policy/identity mismatch")


def _verify_bytes(payload: bytes, checksum: str | None, size: int | None, label: str) -> None:
    if hashlib.sha256(payload).hexdigest() != _required(checksum, f"{label}_sha256"):
        raise ValueError(f"{label} checksum mismatch")
    if len(payload) != size:
        raise ValueError(f"{label} byte count mismatch")


def _nonblank_line_count_bytes(payload: bytes) -> int:
    return sum(1 for line in payload.decode("utf-8").splitlines() if line.strip())


def _relative_path(path: Path, root: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as error:
        raise ValueError("collection artifact path escapes its configured root") from error


def _read_safe_file(root: Path, relative: str, label: str) -> bytes:
    if root.is_symlink():
        raise ValueError(f"{label} artifact root must not be a symlink")
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"{label} artifact path escapes its configured root")
    candidate = root / relative_path
    current = root
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} artifact path contains a symlink")
    resolved_root = root.resolve()
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"{label} artifact path escapes its configured root")
    if not resolved.is_file():
        raise ValueError(f"{label} artifact is not a regular file")
    return resolved.read_bytes()


def _ready_batch_id(
    source: str, document_id: str, raw_sha256: str, normalization_input_digest: str
) -> str:
    value = f"ready|{source}|{document_id}|{raw_sha256}|{normalization_input_digest}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _immutable_ready_evidence(entry: ManifestEntry) -> tuple[object, ...]:
    """Fields that must agree for duplicate complete normalization identities."""
    return (
        entry.raw_path,
        entry.normalized_path,
        entry.quarantine_path,
        entry.artifact_sha256,
        entry.normalized_sha256,
        entry.quarantine_sha256,
        entry.artifact_bytes,
        entry.normalized_bytes,
        entry.quarantine_bytes,
        entry.normalized_count,
        entry.quarantine_count,
        entry.source_url,
        entry.window_date,
        entry.stable_target_id,
        entry.source_document_id,
        entry.published_at,
        entry.retrieved_at,
        entry.config_digest,
        entry.crosswalk_sha256,
        entry.normalization_input_digest,
    )


def _target_date(target: object) -> date:
    value = getattr(target, "as_of", None)
    if isinstance(value, datetime) or not isinstance(value, date):
        raise ValueError("target as_of must be a date")
    return value


def _target_datetime(target: object, name: str) -> datetime:
    value = getattr(target, name, None)
    if not isinstance(value, datetime):
        raise ValueError(f"target {name} must be a datetime")
    return value


def _target_text(target: object, name: str) -> str:
    value = getattr(target, name, None)
    if not isinstance(value, str) or not value:
        raise ValueError(f"target {name} must be a nonempty string")
    return value


def _required(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"READY manifest is missing {name}")
    return value
