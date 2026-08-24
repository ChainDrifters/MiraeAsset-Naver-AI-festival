# pyright: reportMissingTypeStubs=false
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from mirae_asset_graph.ingest.manifest import (
    ManifestEntry,
    Phase,
    Status,
    append_entry,
    batch_id,
    is_loaded,
    read_manifest,
)


def test_manifest_append_read_round_trip(tmp_path: Path) -> None:
    window = date(2026, 1, 11)
    entry = ManifestEntry(
        run_id="run-001",
        source="holdings",
        phase=Phase.LOADED,
        window_date=window,
        batch_id=batch_id("holdings", window, 0),
        status=Status.LOADED,
        artifact_sha256="a" * 64,
        started_at=datetime(2026, 1, 11, 0, 0, tzinfo=UTC),
        finished_at=datetime(2026, 1, 11, 0, 1, tzinfo=UTC),
        raw_path="raw/sec_nport/document.xml",
        normalized_path="normalized/sec_nport/document.jsonl",
        quarantine_path="normalized/sec_nport/document.quarantine.jsonl",
        normalized_sha256="b" * 64,
        quarantine_sha256="c" * 64,
        artifact_bytes=42,
        normalized_bytes=84,
        quarantine_bytes=0,
        normalized_count=2,
        quarantine_count=0,
        source_url="https://www.sec.gov/example.xml",
        stable_target_id="sec:target:1",
        source_document_id="0000000001-26-000001",
        published_at=datetime(2026, 1, 10, 0, 0, tzinfo=UTC),
        retrieved_at=datetime(2026, 1, 11, 0, 0, tzinfo=UTC),
        crosswalk_sha256="d" * 64,
        normalization_input_digest="e" * 64,
    )

    _ = append_entry(entry, tmp_path)

    assert read_manifest("holdings", tmp_path) == [entry]
    assert is_loaded("holdings", window, entry.batch_id, tmp_path)


def test_manifest_reads_legacy_rows_without_optional_metadata(tmp_path: Path) -> None:
    path = tmp_path / "holdings" / "manifest.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(
        '{"run_id":"old","source":"holdings","phase":"normalized",'
        '"window_date":"2026-01-11","batch_id":"old-batch","status":"running",'
        '"artifact_sha256":null,"started_at":null,"finished_at":null,"error":null}\n',
        encoding="utf-8",
    )

    entry = read_manifest("holdings", tmp_path)[0]
    assert entry.normalized_path is None
    assert entry.normalized_count is None


def test_ready_state_is_distinct_from_loaded() -> None:
    assert Status.READY is not Status.LOADED
    assert Phase.READY is not Phase.LOADED


def test_batch_id_is_deterministic_and_index_sensitive() -> None:
    window = date(2026, 1, 11)

    first = batch_id("holdings", window, 0)

    assert first == batch_id("holdings", window, 0)
    assert first != batch_id("holdings", window, 1)
