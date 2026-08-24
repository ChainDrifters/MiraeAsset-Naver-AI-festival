from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import cast

DEFAULT_RUN_ROOT = Path("var/run")


class Phase(str, Enum):
    DISCOVERED = "discovered"
    FETCHED = "fetched"
    NORMALIZED = "normalized"
    READY = "ready"
    LOADED = "loaded"
    VALIDATED = "validated"
    FAILED = "failed"


class Status(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    LOADED = "loaded"
    FAILED = "failed"


@dataclass(frozen=True)
class ManifestEntry:
    run_id: str
    source: str
    phase: Phase
    window_date: date
    batch_id: str
    status: Status
    artifact_sha256: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    raw_path: str | None = None
    normalized_path: str | None = None
    quarantine_path: str | None = None
    normalized_sha256: str | None = None
    quarantine_sha256: str | None = None
    artifact_bytes: int | None = None
    normalized_bytes: int | None = None
    quarantine_bytes: int | None = None
    normalized_count: int | None = None
    quarantine_count: int | None = None
    source_url: str | None = None
    stable_target_id: str | None = None
    source_document_id: str | None = None
    published_at: datetime | None = None
    retrieved_at: datetime | None = None
    config_digest: str | None = None
    crosswalk_sha256: str | None = None
    normalization_input_digest: str | None = None


def batch_id(source: str, window_date: date, batch_index: int) -> str:
    raw = f"{source}|{window_date.isoformat()}|{batch_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def manifest_path(source: str, root: Path = DEFAULT_RUN_ROOT) -> Path:
    return root / source / "manifest.jsonl"


def append_entry(entry: ManifestEntry, root: Path = DEFAULT_RUN_ROOT) -> Path:
    path = manifest_path(entry.source, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(json.dumps(_to_json(entry), sort_keys=True) + "\n")
    return path


def read_manifest(source: str, root: Path = DEFAULT_RUN_ROOT) -> list[ManifestEntry]:
    path = manifest_path(source, root)
    if not path.is_file():
        return []
    entries: list[ManifestEntry] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                loaded = cast(object, json.loads(line))
                if not isinstance(loaded, dict):
                    raise ValueError(f"Manifest line is not an object: {line!r}")
                mapping = cast(Mapping[object, object], loaded)
                entries.append(_from_json({str(key): value for key, value in mapping.items()}))
    return entries


def is_loaded(source: str, window_date: date, batch_id: str, root: Path = DEFAULT_RUN_ROOT) -> bool:
    return any(
        entry.source == source
        and entry.window_date == window_date
        and entry.batch_id == batch_id
        and entry.status == Status.LOADED
        for entry in read_manifest(source, root)
    )


def _to_json(entry: ManifestEntry) -> dict[str, object]:
    return {
        "run_id": entry.run_id,
        "source": entry.source,
        "phase": entry.phase.value,
        "window_date": entry.window_date.isoformat(),
        "batch_id": entry.batch_id,
        "status": entry.status.value,
        "artifact_sha256": entry.artifact_sha256,
        "started_at": entry.started_at.isoformat() if entry.started_at else None,
        "finished_at": entry.finished_at.isoformat() if entry.finished_at else None,
        "error": entry.error,
        "raw_path": entry.raw_path,
        "normalized_path": entry.normalized_path,
        "quarantine_path": entry.quarantine_path,
        "normalized_sha256": entry.normalized_sha256,
        "quarantine_sha256": entry.quarantine_sha256,
        "artifact_bytes": entry.artifact_bytes,
        "normalized_bytes": entry.normalized_bytes,
        "quarantine_bytes": entry.quarantine_bytes,
        "normalized_count": entry.normalized_count,
        "quarantine_count": entry.quarantine_count,
        "source_url": entry.source_url,
        "stable_target_id": entry.stable_target_id,
        "source_document_id": entry.source_document_id,
        "published_at": entry.published_at.isoformat() if entry.published_at else None,
        "retrieved_at": entry.retrieved_at.isoformat() if entry.retrieved_at else None,
        "config_digest": entry.config_digest,
        "crosswalk_sha256": entry.crosswalk_sha256,
        "normalization_input_digest": entry.normalization_input_digest,
    }


def _from_json(values: Mapping[str, object]) -> ManifestEntry:
    return ManifestEntry(
        run_id=_required_str(values, "run_id"),
        source=_required_str(values, "source"),
        phase=Phase(_required_str(values, "phase")),
        window_date=date.fromisoformat(_required_str(values, "window_date")),
        batch_id=_required_str(values, "batch_id"),
        status=Status(_required_str(values, "status")),
        artifact_sha256=_optional_str(values, "artifact_sha256"),
        started_at=_datetime_or_none(_optional_str(values, "started_at")),
        finished_at=_datetime_or_none(_optional_str(values, "finished_at")),
        error=_optional_str(values, "error"),
        raw_path=_optional_str(values, "raw_path"),
        normalized_path=_optional_str(values, "normalized_path"),
        quarantine_path=_optional_str(values, "quarantine_path"),
        normalized_sha256=_optional_str(values, "normalized_sha256"),
        quarantine_sha256=_optional_str(values, "quarantine_sha256"),
        artifact_bytes=_optional_int(values, "artifact_bytes"),
        normalized_bytes=_optional_int(values, "normalized_bytes"),
        quarantine_bytes=_optional_int(values, "quarantine_bytes"),
        normalized_count=_optional_int(values, "normalized_count"),
        quarantine_count=_optional_int(values, "quarantine_count"),
        source_url=_optional_str(values, "source_url"),
        stable_target_id=_optional_str(values, "stable_target_id"),
        source_document_id=_optional_str(values, "source_document_id"),
        published_at=_datetime_or_none(_optional_str(values, "published_at")),
        retrieved_at=_datetime_or_none(_optional_str(values, "retrieved_at")),
        config_digest=_optional_str(values, "config_digest"),
        crosswalk_sha256=_optional_str(values, "crosswalk_sha256"),
        normalization_input_digest=_optional_str(values, "normalization_input_digest"),
    )


def _datetime_or_none(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _required_str(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Manifest entry is missing string field: {key}")
    return value


def _optional_str(values: Mapping[str, object], key: str) -> str | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Manifest field must be a string or null: {key}")
    return value


def _optional_int(values: Mapping[str, object], key: str) -> int | None:
    value = values.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Manifest field must be an integer or null: {key}")
    return value
