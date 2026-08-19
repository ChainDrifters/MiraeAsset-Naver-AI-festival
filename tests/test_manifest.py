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
    )

    _ = append_entry(entry, tmp_path)

    assert read_manifest("holdings", tmp_path) == [entry]
    assert is_loaded("holdings", window, entry.batch_id, tmp_path)


def test_batch_id_is_deterministic_and_index_sensitive() -> None:
    window = date(2026, 1, 11)

    first = batch_id("holdings", window, 0)

    assert first == batch_id("holdings", window, 0)
    assert first != batch_id("holdings", window, 1)
