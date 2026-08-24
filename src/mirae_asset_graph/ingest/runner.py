"""Credential-independent ingestion runner and backfill coordinator.

The runner is the shared Phase 3 backfill path recorded in
docs/external-data-plan.md: it drives one :class:`HoldingsAdapter` through
discover -> fetch -> normalize, then pushes normalized shards into one
:class:`HoldingsSink`. It never imports or contacts Neo4j itself — the sink
protocol is satisfied structurally by ``ExternalGraphLoader``, and the fake
sinks used by tests prove resume/chunk/failure behavior without credentials.

Resume and amendment semantics live in the append-only manifest. Each loaded
shard is identified by ``batch_id(source, as_of, index)`` where ``index`` is
the full SHA-256 digest ``int(sha256(source_document_id).hexdigest(), 16) << 32``
combined with a running chunk ordinal per ``(as_of, source_document_id)`` in
the reserved low 32 bits over the sorted shard traversal: the same document
re-processed by a later run reproduces the same batch ids and is skipped,
while a changed ``source_document_id`` (an amendment) produces fresh batch
ids and loads again. Distinct documents only share a batch id through a full
SHA-256 collision, and renumbering after an amendment can only reload rows,
never skip them, because ids only match previously LOADED entries.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Generic, Protocol, TypeVar, runtime_checkable

from ..model import file_sha256
from .manifest import ManifestEntry, Phase, Status, append_entry, batch_id, is_loaded, read_manifest
from .records import HoldingsRecord, read_jsonl

T = TypeVar("T")

# Matches the UNWIND cap enforced by graph_loader._ensure_batch_cap.
MAX_BATCH_SIZE = 500

# Window date for manifest entries written before any record has been read,
# and for targets that expose no ``as_of`` attribute. Loaded-shard entries
# always carry the shard's true as_of date instead.
_EPOCH_WINDOW = date(1970, 1, 1)

# Chunk ordinals occupy the low 32 bits of each document's batch indexes
# (see _shard_batch_index), so one source document can address at most 2**32
# chunks before ingestion refuses to mint further indexes.
_MAX_CHUNKS_PER_DOCUMENT = 1 << 32

_TARGET_COMPLETION_NAMESPACE = "mirae-asset-graph:ingest:target-completion:v1"

# scheme://user:password@host -> scheme://<redacted>@host
_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)([^\s/@:]+):([^\s/@]+)@")
# ?password=... / &token=... query parameters
_SECRET_PARAM = re.compile(r"(?i)([?&])(password|passwd|token|api[_-]?key|secret)=([^\s&]+)")
_MAX_ERROR_LENGTH = 500


@runtime_checkable
class HoldingsAdapter(Protocol[T]):
    """Structural contract satisfied by NPortAdapter and ManagerBasketAdapter."""

    source: str
    raw_root: Path

    def discover(
        self,
        start: date | None = None,
        end: date | None = None,
        cutoff: datetime | None = None,
    ) -> list[T]:
        """Return fetch targets for the window, deterministically ordered."""
        ...

    def fetch(self, target: T) -> Path:
        """Fetch one target and return the raw artifact path."""
        ...

    def normalize(self, target: T, raw_path: Path, output_dir: Path) -> tuple[Path, Path, int, int]:
        """Normalize one raw artifact; return (records, quarantine, counts)."""
        ...


@runtime_checkable
class HoldingsSink(Protocol):
    """Structural contract satisfied by ExternalGraphLoader."""

    def load_holdings_rows(
        self,
        rows: Iterable[Mapping[str, object]],
        *,
        source: str,
        source_url: str,
        artifact_sha256: str,
        artifact_bytes: int,
        run_id: str,
        retrieved_at: datetime,
    ) -> dict[str, int]:
        """Load one shard of at most MAX_BATCH_SIZE rows into the graph."""
        ...


@dataclass(frozen=True)
class RunSummary:
    """Outcome counters for one IngestRunner.run call."""

    discovered: int
    fetched: int
    normalized: int
    loaded_rows: int
    quarantined: int
    skipped_batches: int
    failed_targets: int

    def to_dict(self) -> dict[str, int]:
        """JSON-friendly copy of every counter, in declaration order."""
        return {
            "discovered": self.discovered,
            "fetched": self.fetched,
            "normalized": self.normalized,
            "loaded_rows": self.loaded_rows,
            "quarantined": self.quarantined,
            "skipped_batches": self.skipped_batches,
            "failed_targets": self.failed_targets,
        }


@dataclass
class _RunCounters:
    """Mutable per-run accumulators so partial progress survives a target failure."""

    fetched: int = 0
    normalized: int = 0
    loaded_rows: int = 0
    quarantined: int = 0
    skipped_batches: int = 0
    failed_targets: int = 0


class IngestRunner(Generic[T]):
    """Coordinate one adapter and one sink over the append-only manifest."""

    def __init__(
        self,
        adapter: HoldingsAdapter[T],
        sink: HoldingsSink,
        manifest_root: Path,
        normalized_root: Path,
        batch_size: int = MAX_BATCH_SIZE,
        continue_on_error: bool = True,
        document_id: Callable[[T], str] | None = None,
    ) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise ValueError(
                f"IngestRunner: batch_size must be an integer in 1..{MAX_BATCH_SIZE}: {batch_size!r}"
            )
        if not 1 <= batch_size <= MAX_BATCH_SIZE:
            raise ValueError(
                f"IngestRunner: batch_size must be an integer in 1..{MAX_BATCH_SIZE}: {batch_size}"
            )
        self.adapter: HoldingsAdapter[T] = adapter
        self.sink: HoldingsSink = sink
        self.manifest_root: Path = Path(manifest_root)
        self.normalized_root: Path = Path(normalized_root)
        self.batch_size: int = batch_size
        self.continue_on_error: bool = continue_on_error
        self.document_id: Callable[[T], str] = document_id or _default_document_id

    def run(
        self,
        run_id: str,
        start: date | None = None,
        end: date | None = None,
        cutoff: datetime | None = None,
    ) -> RunSummary:
        """Process every discovered target; return the run's counters.

        Targets are processed in the adapter's order, re-sorted by ``repr`` so
        the sequence stays deterministic even if an adapter forgets to sort.
        A target exception appends a sanitized FAILED manifest entry and either
        continues to the next target or re-raises, per ``continue_on_error``.
        """
        targets = sorted(self.adapter.discover(start=start, end=end, cutoff=cutoff), key=repr)
        counters = _RunCounters()
        for target in targets:
            try:
                self._process_target(run_id, target, counters)
            except Exception as error:
                counters.failed_targets += 1
                now = _utc_now()
                self._append(
                    run_id,
                    target,
                    Phase.FAILED,
                    Status.FAILED,
                    now,
                    now,
                    error=_sanitize_error(error),
                )
                if not self.continue_on_error:
                    raise
        return RunSummary(
            discovered=len(targets),
            fetched=counters.fetched,
            normalized=counters.normalized,
            loaded_rows=counters.loaded_rows,
            quarantined=counters.quarantined,
            skipped_batches=counters.skipped_batches,
            failed_targets=counters.failed_targets,
        )

    def _process_target(self, run_id: str, target: T, counters: _RunCounters) -> None:
        """Fetch, normalize, and load one target, appending manifest entries."""
        target_document_id: object = self.document_id(target)
        if not isinstance(target_document_id, str) or not target_document_id:
            raise ValueError("IngestRunner: document_id must return a nonempty string")
        now = _utc_now()
        self._append(run_id, target, Phase.DISCOVERED, Status.PENDING, now)

        raw_path = self.adapter.fetch(target)
        artifact_sha256 = file_sha256(raw_path)
        artifact_bytes = raw_path.stat().st_size
        retrieved_at = _utc_now()
        counters.fetched += 1
        self._append(
            run_id,
            target,
            Phase.FETCHED,
            Status.RUNNING,
            retrieved_at,
            artifact_sha256=artifact_sha256,
        )

        records_path, _quarantine_path, _records_count, quarantine_count = self.adapter.normalize(
            target, raw_path, self.normalized_root
        )
        counters.quarantined += quarantine_count
        counters.normalized += 1
        self._append(
            run_id,
            target,
            Phase.NORMALIZED,
            Status.RUNNING,
            _utc_now(),
            artifact_sha256=artifact_sha256,
        )

        records = read_jsonl(records_path)
        normalized_sha256 = file_sha256(records_path)
        groups: dict[tuple[date, str, str], list[HoldingsRecord]] = {}
        for record in records:
            key = (record.as_of, record.source_url, record.source_document_id)
            groups.setdefault(key, []).append(record)

        # Deterministic shard order: sorted (as_of, source_url, document) keys,
        # records in normalized-file order inside each group. Chunk ordinals
        # run per (as_of, document) across that sorted traversal, so two
        # source_url groups of one document never share a batch index.
        for as_of, source_url, group_document_id in sorted(groups):
            group = groups[(as_of, source_url, group_document_id)]
            for offset in range(0, len(group), self.batch_size):
                chunk = group[offset : offset + self.batch_size]
                end = offset + len(chunk)
                shard_batch_id = immutable_shard_batch_id(
                    self.adapter.source,
                    normalized_sha256,
                    as_of,
                    group_document_id,
                    source_url,
                    offset,
                    end,
                )
                if is_loaded(self.adapter.source, as_of, shard_batch_id, self.manifest_root):
                    counters.skipped_batches += 1
                    continue
                result = self.sink.load_holdings_rows(
                    [record.to_loader_payload() for record in chunk],
                    source=self.adapter.source,
                    source_url=source_url,
                    artifact_sha256=artifact_sha256,
                    artifact_bytes=artifact_bytes,
                    run_id=run_id,
                    retrieved_at=retrieved_at,
                )
                counters.loaded_rows += int(result.get("rows", len(chunk)))
                loaded_at = _utc_now()
                self._append(
                    run_id,
                    target,
                    Phase.LOADED,
                    Status.LOADED,
                    loaded_at,
                    window_date=as_of,
                    batch_id_value=shard_batch_id,
                    artifact_sha256=artifact_sha256,
                )

        completion_batch_id = target_completion_batch_id(target_document_id)
        target_as_of = _target_window_date(target)
        if not _has_target_completion(
            self.adapter.source,
            target_as_of,
            completion_batch_id,
            self.manifest_root,
        ):
            completed_at = _utc_now()
            self._append(
                run_id,
                target,
                Phase.VALIDATED,
                Status.LOADED,
                completed_at,
                completed_at,
                window_date=target_as_of,
                batch_id_value=completion_batch_id,
                artifact_sha256=artifact_sha256,
            )

    def _append(
        self,
        run_id: str,
        target: T,
        phase: Phase,
        status: Status,
        started_at: datetime,
        finished_at: datetime | None = None,
        *,
        window_date: date | None = None,
        batch_id_value: str | None = None,
        artifact_sha256: str | None = None,
        error: str | None = None,
    ) -> None:
        """Append one manifest entry for the target's source and run.

        Pre-load phases (and failures) identify the target by a deterministic
        key derived from ``repr(target)`` and are never written with
        ``Status.LOADED``, so they can never satisfy :func:`is_loaded`. Loaded
        shards override both the window date and the batch id with the shard's
        true identity.
        """
        _ = append_entry(
            ManifestEntry(
                run_id=run_id,
                source=self.adapter.source,
                phase=phase,
                window_date=window_date if window_date is not None else _target_window_date(target),
                batch_id=batch_id_value if batch_id_value is not None else _target_key(target),
                status=status,
                artifact_sha256=artifact_sha256,
                started_at=started_at,
                finished_at=finished_at,
                error=error,
            ),
            self.manifest_root,
        )


def _document_base_index(source_document_id: str) -> int:
    """Deterministic batch-index base for one source document.

    ``int(sha256(source_document_id).hexdigest(), 16) << 32`` uses the full
    256-bit digest and zeroes the low 32 bits, which ``_shard_batch_index``
    fills with chunk ordinals. Two distinct documents sharing an as_of
    therefore yield disjoint batch indexes — and distinct :func:`batch_id`
    values — unless their full SHA-256 digests collide.
    """
    digest = hashlib.sha256(source_document_id.encode("utf-8")).hexdigest()
    return int(digest, 16) << 32


def target_completion_batch_id(source_document_id: str) -> str:
    """Return the stable, source-document-aware identity of target completion."""
    raw = f"{_TARGET_COMPLETION_NAMESPACE}|{source_document_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def immutable_shard_batch_id(
    source: str,
    normalized_sha256: str,
    as_of: date,
    source_document_id: str,
    source_url: str,
    start: int,
    end: int,
) -> str:
    """Stable shard identity bound to exact normalized content and row range."""
    raw = (
        f"load-shard-v2|{source}|{normalized_sha256}|{as_of.isoformat()}|"
        f"{source_document_id}|{source_url}|{start}|{end}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _shard_batch_index(source_document_id: str, ordinal: int) -> int:
    """Batch index for one chunk: document base with the ordinal in the low bits.

    Raises :class:`ValueError` when ``ordinal`` falls outside ``[0, 2**32)``
    so a runaway chunk count can never wrap into another document's index
    space; ``|`` is exact because the base zeroes those low bits.
    """
    if not 0 <= ordinal < _MAX_CHUNKS_PER_DOCUMENT:
        raise ValueError(
            f"IngestRunner: chunk ordinal must be in 0..{_MAX_CHUNKS_PER_DOCUMENT - 1}: {ordinal}"
        )
    return _document_base_index(source_document_id) | ordinal


def _target_key(target: object) -> str:
    """Stable manifest batch_id for pre-load phases: sha256 of ``repr(target)``."""
    return hashlib.sha256(repr(target).encode("utf-8")).hexdigest()


def _default_document_id(target: object) -> str:
    """Derive document identity for built-in targets and structural test targets."""
    accession = getattr(target, "accession", None)
    if isinstance(accession, str) and accession:
        return accession

    manager_code = getattr(target, "manager_code", None)
    fund_code = getattr(target, "fund_code", None)
    as_of = getattr(target, "as_of", None)
    if (
        isinstance(manager_code, str)
        and manager_code
        and isinstance(fund_code, str)
        and fund_code
        and isinstance(as_of, date)
    ):
        target_date = as_of.date() if isinstance(as_of, datetime) else as_of
        return f"{manager_code}:{fund_code}:{target_date.isoformat()}"

    source_document_id = getattr(target, "source_document_id", None)
    if isinstance(source_document_id, str) and source_document_id:
        return source_document_id
    raise TypeError(f"IngestRunner: cannot derive document id for {type(target).__name__}")


def _has_target_completion(source: str, as_of: date, completion_batch_id: str, root: Path) -> bool:
    """Return whether the exact target-level completion marker already exists."""
    return any(
        entry.phase is Phase.VALIDATED
        and entry.status is Status.LOADED
        and entry.window_date == as_of
        and entry.batch_id == completion_batch_id
        for entry in read_manifest(source, root)
    )


def _target_window_date(target: object) -> date:
    """Window date for pre-load manifest entries.

    Both existing target types (``NPortTarget``, ``ManagerBasketTarget``)
    expose an ``as_of`` date; anything else falls back to the epoch placeholder.
    """
    as_of = getattr(target, "as_of", None)
    if isinstance(as_of, datetime):
        return as_of.date()
    if isinstance(as_of, date):
        return as_of
    return _EPOCH_WINDOW


def _sanitize_error(error: BaseException) -> str:
    """``ClassName: message`` with URL credentials and secrets redacted.

    Tracebacks are never included, control characters become spaces, and the
    result is capped so a hostile message cannot flood the manifest.
    """
    text = f"{type(error).__name__}: {error}"
    text = _URL_CREDENTIALS.sub(r"\1<redacted>@", text)
    text = _SECRET_PARAM.sub(r"\1\2=<redacted>", text)
    text = "".join(character if character.isprintable() else " " for character in text).strip()
    if len(text) > _MAX_ERROR_LENGTH:
        text = text[:_MAX_ERROR_LENGTH] + "...(truncated)"
    return text


def _utc_now() -> datetime:
    return datetime.now(UTC)
