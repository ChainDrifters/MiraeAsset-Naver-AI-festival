# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
"""Offline IngestRunner behavior: chunking, resume, amendments, and failures.

Everything runs against FakeAdapter/FakeSink under tmp_path; no network, no
Neo4j, no credentials. Live graph loading stays blocked behind NEO4J_PASSWORD,
so these tests are the full contract for the shared Phase 3 backfill path.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from collections.abc import Iterable, Mapping
from typing import Any, Protocol, cast
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import pytest

from mirae_asset_graph.ingest import runner as runner_module
from mirae_asset_graph.ingest.basket_kr import ManagerBasketAdapter
from mirae_asset_graph.ingest.graph_loader import ExternalGraphLoader
from mirae_asset_graph.ingest.manifest import ManifestEntry, Phase, Status, read_manifest
from mirae_asset_graph.ingest.nport import NPortAdapter
from mirae_asset_graph.ingest.records import HoldingsRecord, read_jsonl, write_jsonl
from mirae_asset_graph.ingest.resolver import IdentifierResolver
from mirae_asset_graph.ingest.runner import (
    HoldingsAdapter,
    HoldingsSink,
    IngestRunner,
    RunSummary,
)
from mirae_asset_graph.model import file_sha256

SOURCE = "fake_holdings"
FUND_ISIN = "US5007676944"
CONSTITUENT_ISIN = "KR7091160005"


class _Sha256Like(Protocol):
    """Minimal hash-object surface exercised by the ingest run path."""

    def hexdigest(self) -> str:
        ...

    def update(self, data: bytes) -> None:
        ...


def _record(
    *,
    as_of: date,
    source_url: str,
    source_document_id: str,
    weight: float = 0.01,
    constituent_name: str = "포스코홀딩스",
) -> HoldingsRecord:
    return HoldingsRecord.create(
        fund_isin=FUND_ISIN,
        constituent_isin=CONSTITUENT_ISIN,
        constituent_name=constituent_name,
        weight=weight,
        as_of=as_of,
        weight_source="source_published",
        identifier_method="source_isin",
        source_document_id=source_document_id,
        source_url=source_url,
    )


@dataclass(frozen=True)
class FakeTarget:
    name: str
    as_of: date
    source_url: str
    source_document_id: str


@dataclass(frozen=True)
class FakeSpec:
    target: FakeTarget
    rows: tuple[HoldingsRecord, ...] = ()
    quarantine_count: int = 0
    normalize_error: Exception | None = None


class FakeAdapter:
    """Offline adapter writing deterministic raw and normalized artifacts."""

    source: str = SOURCE

    def __init__(self, specs: tuple[FakeSpec, ...], raw_root: Path) -> None:
        self._specs: dict[str, FakeSpec] = {spec.target.name: spec for spec in specs}
        self.raw_root: Path = Path(raw_root)
        self.fetched: list[str] = []
        self.normalized: list[str] = []

    def discover(
        self,
        start: date | None = None,
        end: date | None = None,
        cutoff: datetime | None = None,
    ) -> list[FakeTarget]:
        _ = cutoff
        selected = [
            spec.target
            for spec in self._specs.values()
            if (start is None or start <= spec.target.as_of)
            and (end is None or spec.target.as_of <= end)
        ]
        return sorted(selected, key=lambda target: target.name)

    def fetch(self, target: FakeTarget) -> Path:
        self.fetched.append(target.name)
        raw_path = self.raw_root / SOURCE / f"{target.name}.raw"
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        _ = raw_path.write_bytes(f"raw artifact for {target.name}".encode("utf-8"))
        return raw_path

    def normalize(self, target: FakeTarget, raw_path: Path, output_dir: Path) -> tuple[Path, Path, int, int]:
        _ = raw_path
        spec = self._specs[target.name]
        self.normalized.append(target.name)
        if spec.normalize_error is not None:
            raise spec.normalize_error
        records_path = Path(output_dir) / SOURCE / f"{target.name}.jsonl"
        records_path.parent.mkdir(parents=True, exist_ok=True)
        _ = write_jsonl(spec.rows, records_path)
        quarantine_path = records_path.with_name(f"{target.name}.quarantine.jsonl")
        _ = quarantine_path.write_text(
            "".join(
                json.dumps(
                    {
                        "source_document_id": spec.target.source_document_id,
                        "reason": "fake quarantine entry",
                    }
                )
                + "\n"
                for _ in range(spec.quarantine_count)
            ),
            encoding="utf-8",
        )
        return records_path, quarantine_path, len(spec.rows), spec.quarantine_count


@dataclass
class SinkCall:
    rows: list[dict[str, object]]
    source: str
    source_url: str
    artifact_sha256: str
    artifact_bytes: int
    run_id: str
    retrieved_at: datetime


class FakeSink:
    """Offline sink recording every load_holdings_rows call exactly."""

    def __init__(self) -> None:
        self.calls: list[SinkCall] = []

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
        call = SinkCall(
            rows=[dict(row) for row in rows],
            source=source,
            source_url=source_url,
            artifact_sha256=artifact_sha256,
            artifact_bytes=artifact_bytes,
            run_id=run_id,
            retrieved_at=retrieved_at,
        )
        self.calls.append(call)
        return {"rows": len(call.rows)}


def _make_runner(
    root: Path,
    specs: Iterable[FakeSpec],
    *,
    sink: FakeSink | None = None,
    batch_size: int = 500,
    continue_on_error: bool = True,
) -> tuple[FakeAdapter, FakeSink, IngestRunner[FakeTarget]]:
    adapter = FakeAdapter(tuple(specs), root / "raw")
    selected_sink = sink if sink is not None else FakeSink()
    runner = IngestRunner(
        adapter,
        selected_sink,
        root / "manifest",
        root / "normalized",
        batch_size=batch_size,
        continue_on_error=continue_on_error,
    )
    return adapter, selected_sink, runner


def _loaded_entries(root: Path) -> list[ManifestEntry]:
    return [
        entry
        for entry in read_manifest(SOURCE, root / "manifest")
        if entry.status is Status.LOADED and entry.phase is Phase.LOADED
    ]


def test_successful_target_appends_all_phases_and_loads_exact_payload(tmp_path: Path) -> None:
    as_of = date(2026, 7, 11)
    source_url = "https://example.com/fund-a/2026-07-11.csv"
    document_id = "fake:fund-a:2026-07-11"
    records = (
        _record(as_of=as_of, source_url=source_url, source_document_id=document_id, weight=0.25),
        _record(as_of=as_of, source_url=source_url, source_document_id=document_id, weight=0.75),
    )
    spec = FakeSpec(
        target=FakeTarget("fund-a", as_of, source_url, document_id),
        rows=records,
        quarantine_count=1,
    )
    adapter, sink, runner = _make_runner(tmp_path, [spec])

    summary = runner.run("run-1")

    assert summary == RunSummary(
        discovered=1,
        fetched=1,
        normalized=1,
        loaded_rows=2,
        quarantined=1,
        skipped_batches=0,
        failed_targets=0,
    )
    assert summary.to_dict() == {
        "discovered": 1,
        "fetched": 1,
        "normalized": 1,
        "loaded_rows": 2,
        "quarantined": 1,
        "skipped_batches": 0,
        "failed_targets": 0,
    }
    assert adapter.fetched == ["fund-a"]
    assert adapter.normalized == ["fund-a"]

    raw_path = tmp_path / "raw" / SOURCE / "fund-a.raw"
    artifact_sha = file_sha256(raw_path)
    entries = read_manifest(SOURCE, tmp_path / "manifest")
    assert [(entry.phase, entry.status) for entry in entries] == [
        (Phase.DISCOVERED, Status.PENDING),
        (Phase.FETCHED, Status.RUNNING),
        (Phase.NORMALIZED, Status.RUNNING),
        (Phase.LOADED, Status.LOADED),
    ]
    assert all(entry.run_id == "run-1" for entry in entries)
    assert entries[1].artifact_sha256 == artifact_sha
    assert entries[2].artifact_sha256 == artifact_sha
    assert entries[3].window_date == as_of
    assert entries[3].artifact_sha256 == artifact_sha

    assert read_jsonl(tmp_path / "normalized" / SOURCE / "fund-a.jsonl") == list(records)
    quarantine_path = tmp_path / "normalized" / SOURCE / "fund-a.quarantine.jsonl"
    assert quarantine_path.read_text(encoding="utf-8").count("\n") == 1

    assert len(sink.calls) == 1
    call = sink.calls[0]
    assert call.rows == [record.to_loader_payload() for record in records]
    assert call.source == SOURCE
    assert call.source_url == source_url
    assert call.artifact_sha256 == artifact_sha
    assert call.artifact_bytes == raw_path.stat().st_size
    assert call.run_id == "run-1"
    assert call.retrieved_at.tzinfo is not None


def test_501_records_same_as_of_load_as_two_capped_batches(tmp_path: Path) -> None:
    as_of = date(2026, 6, 30)
    source_url = "https://example.com/fund-big/2026-06-30.csv"
    document_id = "fake:fund-big:2026-06-30"
    records = tuple(
        _record(
            as_of=as_of,
            source_url=source_url,
            source_document_id=document_id,
            weight=round(0.001 * ((index % 900) + 1), 6),
        )
        for index in range(501)
    )
    spec = FakeSpec(FakeTarget("fund-big", as_of, source_url, document_id), rows=records)
    _adapter, sink, runner = _make_runner(tmp_path, [spec])

    summary = runner.run("run-1")

    assert summary.loaded_rows == 501
    assert summary.skipped_batches == 0
    assert [len(call.rows) for call in sink.calls] == [500, 1]
    assert sink.calls[0].rows == [record.to_loader_payload() for record in records[:500]]
    assert sink.calls[1].rows == [records[500].to_loader_payload()]
    loaded = _loaded_entries(tmp_path)
    assert len(loaded) == 2
    assert len({entry.batch_id for entry in loaded}) == 2
    assert {entry.window_date for entry in loaded} == {as_of}


def test_mixed_as_of_and_source_url_shards_are_grouped_deterministically(tmp_path: Path) -> None:
    first_day = date(2026, 5, 29)
    second_day = date(2026, 6, 30)
    url_a = "https://a.example.com/holdings.csv"
    url_b = "https://b.example.com/holdings.csv"
    document_id = "fake:fund-mixed:doc"
    records = (
        _record(as_of=second_day, source_url=url_a, source_document_id=document_id),
        _record(as_of=first_day, source_url=url_b, source_document_id=document_id),
        _record(as_of=first_day, source_url=url_a, source_document_id=document_id),
        _record(as_of=first_day, source_url=url_a, source_document_id=document_id, weight=0.02),
    )
    spec = FakeSpec(FakeTarget("fund-mixed", second_day, url_a, document_id), rows=records)
    _adapter, sink, runner = _make_runner(tmp_path / "one", [spec])

    summary = runner.run("run-1")

    assert summary.loaded_rows == 4
    assert summary.skipped_batches == 0
    assert [(call.source_url, len(call.rows)) for call in sink.calls] == [
        (url_a, 2),
        (url_b, 1),
        (url_a, 1),
    ]
    assert {row["as_of"] for row in sink.calls[0].rows} == {first_day.isoformat()}
    assert {row["as_of"] for row in sink.calls[1].rows} == {first_day.isoformat()}
    assert {row["as_of"] for row in sink.calls[2].rows} == {second_day.isoformat()}
    within_group_order = [records[2].to_loader_payload(), records[3].to_loader_payload()]
    assert sink.calls[0].rows == within_group_order
    assert sink.calls[1].rows == [records[1].to_loader_payload()]
    assert sink.calls[2].rows == [records[0].to_loader_payload()]

    _adapter_again, sink_again, runner_again = _make_runner(tmp_path / "two", [spec])
    _ = runner_again.run("run-1")
    assert [(call.source_url, call.rows) for call in sink_again.calls] == [
        (call.source_url, call.rows) for call in sink.calls
    ]


def test_rerun_skips_loaded_batches_without_sink_calls(tmp_path: Path) -> None:
    as_of = date(2026, 7, 11)
    source_url = "https://example.com/fund-a/2026-07-11.csv"
    document_id = "fake:fund-a:2026-07-11"
    records = tuple(
        _record(as_of=as_of, source_url=source_url, source_document_id=document_id) for _ in range(3)
    )
    spec = FakeSpec(FakeTarget("fund-a", as_of, source_url, document_id), rows=records)
    _adapter, _sink, runner = _make_runner(tmp_path, [spec])

    first = runner.run("run-1")
    assert first.loaded_rows == 3
    assert first.skipped_batches == 0
    entries_after_first = read_manifest(SOURCE, tmp_path / "manifest")
    assert len(_loaded_entries(tmp_path)) == 1

    fresh_sink = FakeSink()
    _adapter_again, _sink_again, runner_again = _make_runner(tmp_path, [spec], sink=fresh_sink)
    second = runner_again.run("run-2")

    assert second.discovered == 1
    assert second.fetched == 1
    assert second.normalized == 1
    assert second.loaded_rows == 0
    assert second.skipped_batches == 1
    assert second.failed_targets == 0
    assert fresh_sink.calls == []
    entries_after_second = read_manifest(SOURCE, tmp_path / "manifest")
    assert len(entries_after_second) == len(entries_after_first) + 3
    assert len(_loaded_entries(tmp_path)) == 1


def test_two_documents_same_as_of_do_not_collide(tmp_path: Path) -> None:
    as_of = date(2026, 4, 30)
    source_url = "https://example.com/holdings.csv"
    document_a = "fake:doc-a:2026-04-30"
    document_b = "fake:doc-b:2026-04-30"
    specs = [
        FakeSpec(
            FakeTarget("doc-a", as_of, source_url, document_a),
            rows=(_record(as_of=as_of, source_url=source_url, source_document_id=document_a),),
        ),
        FakeSpec(
            FakeTarget("doc-b", as_of, source_url, document_b),
            rows=tuple(
                _record(as_of=as_of, source_url=source_url, source_document_id=document_b) for _ in range(2)
            ),
        ),
    ]
    _adapter, sink, runner = _make_runner(tmp_path, specs)

    summary = runner.run("run-1")

    assert summary.skipped_batches == 0
    assert summary.loaded_rows == 3
    assert len(sink.calls) == 2
    loaded = _loaded_entries(tmp_path)
    assert len(loaded) == 2
    assert len({entry.batch_id for entry in loaded}) == 2
    assert {entry.window_date for entry in loaded} == {as_of}


def test_documents_sharing_first_eight_digest_hex_chars_stay_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    as_of = date(2026, 8, 21)
    source_url = "https://example.com/holdings.csv"
    document_a = "fake:prefix-pair:a"
    document_b = "fake:prefix-pair:b"
    shared_prefix = "deadbeef"
    digest_a = shared_prefix + "00" * 28
    digest_b = shared_prefix + "ff" * 28
    assert digest_a[:8] == digest_b[:8]

    class _CraftedDigest:
        def __init__(self, value: str) -> None:
            self._value: str = value

        def hexdigest(self) -> str:
            return self._value

    crafted = {
        document_a.encode("utf-8"): _CraftedDigest(digest_a),
        document_b.encode("utf-8"): _CraftedDigest(digest_b),
    }
    real_sha256 = hashlib.sha256

    def fake_sha256(data: bytes = b"") -> "_Sha256Like":
        match = crafted.get(data)
        if match is not None:
            return match
        return cast("_Sha256Like", real_sha256(data))

    monkeypatch.setattr(hashlib, "sha256", fake_sha256)
    specs = [
        FakeSpec(
            FakeTarget("prefix-a", as_of, source_url, document_a),
            rows=(_record(as_of=as_of, source_url=source_url, source_document_id=document_a),),
        ),
        FakeSpec(
            FakeTarget("prefix-b", as_of, source_url, document_b),
            rows=tuple(
                _record(as_of=as_of, source_url=source_url, source_document_id=document_b) for _ in range(2)
            ),
        ),
    ]
    _adapter, sink, runner = _make_runner(tmp_path, specs)

    summary = runner.run("run-1")

    assert summary.skipped_batches == 0
    assert summary.loaded_rows == 3
    assert len(sink.calls) == 2
    loaded = _loaded_entries(tmp_path)
    assert len(loaded) == 2
    assert len({entry.batch_id for entry in loaded}) == 2
    assert {entry.window_date for entry in loaded} == {as_of}


def test_shard_batch_index_bounds_chunk_ordinals_to_low_32_bits() -> None:
    document_id = "fake:ordinal-bound:doc"
    base = int(hashlib.sha256(document_id.encode("utf-8")).hexdigest(), 16) << 32
    last_ordinal = 2**32 - 1
    assert runner_module._shard_batch_index(document_id, 0) == base
    assert runner_module._shard_batch_index(document_id, last_ordinal) == base + last_ordinal
    with pytest.raises(ValueError, match="chunk ordinal"):
        _ = runner_module._shard_batch_index(document_id, 2**32)
    with pytest.raises(ValueError, match="chunk ordinal"):
        _ = runner_module._shard_batch_index(document_id, -1)


def test_changed_source_document_id_loads_as_amendment(tmp_path: Path) -> None:
    as_of = date(2026, 3, 31)
    source_url = "https://example.com/fund/2026-03-31.csv"
    document_v1 = "fake:fund:2026-03-31:v1"
    document_v2 = "fake:fund:2026-03-31:v2"
    spec_v1 = FakeSpec(
        FakeTarget("fund", as_of, source_url, document_v1),
        rows=tuple(
            _record(as_of=as_of, source_url=source_url, source_document_id=document_v1, weight=0.5)
            for _ in range(2)
        ),
    )
    _adapter, _sink, runner = _make_runner(tmp_path, [spec_v1])
    first = runner.run("run-1")
    assert first.loaded_rows == 2
    first_batch_ids = {entry.batch_id for entry in _loaded_entries(tmp_path)}

    spec_v2 = FakeSpec(
        FakeTarget("fund", as_of, source_url, document_v2),
        rows=tuple(
            _record(as_of=as_of, source_url=source_url, source_document_id=document_v2, weight=0.25)
            for _ in range(2)
        ),
    )
    fresh_sink = FakeSink()
    _adapter_again, _sink_again, runner_again = _make_runner(tmp_path, [spec_v2], sink=fresh_sink)
    second = runner_again.run("run-2")

    assert second.skipped_batches == 0
    assert second.loaded_rows == 2
    assert len(fresh_sink.calls) == 1
    second_batch_ids = {entry.batch_id for entry in _loaded_entries(tmp_path) if entry.run_id == "run-2"}
    assert first_batch_ids.isdisjoint(second_batch_ids)
    assert {entry.run_id for entry in _loaded_entries(tmp_path)} == {"run-1", "run-2"}


def test_normalize_failure_appends_failed_and_continues(tmp_path: Path) -> None:
    as_of = date(2026, 7, 11)
    source_url = "https://example.com/holdings.csv"
    document_a = "fake:doc-a:2026-07-11"
    document_b = "fake:doc-b:2026-07-11"
    failing = FakeSpec(
        FakeTarget("a-fail", as_of, source_url, document_a),
        normalize_error=RuntimeError(
            "normalize failed for https://user:secret@example.com/fetch?password=hunter2"
        ),
    )
    good = FakeSpec(
        FakeTarget("b-good", as_of, source_url, document_b),
        rows=(_record(as_of=as_of, source_url=source_url, source_document_id=document_b),) * 2,
    )
    adapter, sink, runner = _make_runner(tmp_path, [failing, good])

    summary = runner.run("run-1")

    assert summary.discovered == 2
    assert summary.failed_targets == 1
    assert summary.loaded_rows == 2
    assert summary.normalized == 1
    assert adapter.fetched == ["a-fail", "b-good"]
    assert adapter.normalized == ["a-fail", "b-good"]
    assert len(sink.calls) == 1

    entries = read_manifest(SOURCE, tmp_path / "manifest")
    assert [(entry.phase, entry.status) for entry in entries] == [
        (Phase.DISCOVERED, Status.PENDING),
        (Phase.FETCHED, Status.RUNNING),
        (Phase.FAILED, Status.FAILED),
        (Phase.DISCOVERED, Status.PENDING),
        (Phase.FETCHED, Status.RUNNING),
        (Phase.NORMALIZED, Status.RUNNING),
        (Phase.LOADED, Status.LOADED),
    ]
    failed = entries[2]
    assert failed.error is not None
    assert failed.error.startswith("RuntimeError: ")
    assert "<redacted>" in failed.error
    assert "secret" not in failed.error
    assert "hunter2" not in failed.error
    assert failed.error == (
        "RuntimeError: normalize failed for https://<redacted>@example.com/fetch?password=<redacted>"
    )


def test_continue_on_error_false_reraises_and_stops(tmp_path: Path) -> None:
    as_of = date(2026, 7, 11)
    source_url = "https://example.com/holdings.csv"
    failing = FakeSpec(
        FakeTarget("a-fail", as_of, source_url, "fake:doc-a:2026-07-11"),
        normalize_error=RuntimeError("normalize exploded"),
    )
    good = FakeSpec(
        FakeTarget("b-good", as_of, source_url, "fake:doc-b:2026-07-11"),
        rows=(_record(as_of=as_of, source_url=source_url, source_document_id="fake:doc-b:2026-07-11"),),
    )
    adapter, sink, runner = _make_runner(tmp_path, [failing, good], continue_on_error=False)

    with pytest.raises(RuntimeError, match="normalize exploded"):
        _ = runner.run("run-1")

    assert adapter.fetched == ["a-fail"]
    assert adapter.normalized == ["a-fail"]
    assert sink.calls == []
    entries = read_manifest(SOURCE, tmp_path / "manifest")
    assert [(entry.phase, entry.status) for entry in entries] == [
        (Phase.DISCOVERED, Status.PENDING),
        (Phase.FETCHED, Status.RUNNING),
        (Phase.FAILED, Status.FAILED),
    ]
    assert entries[2].error == "RuntimeError: normalize exploded"


def test_empty_normalized_records_make_no_sink_call(tmp_path: Path) -> None:
    as_of = date(2026, 7, 11)
    spec = FakeSpec(FakeTarget("fund-empty", as_of, "https://example.com/empty.csv", "fake:empty:doc"))
    _adapter, sink, runner = _make_runner(tmp_path, [spec])

    summary = runner.run("run-1")

    assert summary.normalized == 1
    assert summary.loaded_rows == 0
    assert summary.skipped_batches == 0
    assert summary.failed_targets == 0
    assert sink.calls == []
    entries = read_manifest(SOURCE, tmp_path / "manifest")
    assert [(entry.phase, entry.status) for entry in entries] == [
        (Phase.DISCOVERED, Status.PENDING),
        (Phase.FETCHED, Status.RUNNING),
        (Phase.NORMALIZED, Status.RUNNING),
    ]


@pytest.mark.parametrize("bad_size", [0, -1, 501, 1.5, True, "500", None])
def test_invalid_batch_size_is_rejected(tmp_path: Path, bad_size: Any) -> None:
    adapter, sink, _runner = _make_runner(tmp_path, [])
    with pytest.raises(ValueError, match="batch_size"):
        _ = IngestRunner(
            adapter,
            sink,
            tmp_path / "manifest",
            tmp_path / "normalized",
            batch_size=bad_size,
        )


@pytest.mark.parametrize("good_size", [1, 500])
def test_boundary_batch_sizes_are_accepted(tmp_path: Path, good_size: int) -> None:
    _adapter, _sink, runner = _make_runner(tmp_path, [], batch_size=good_size)
    assert runner.batch_size == good_size
    assert runner.run("run-1") == RunSummary(
        discovered=0,
        fetched=0,
        normalized=0,
        loaded_rows=0,
        quarantined=0,
        skipped_batches=0,
        failed_targets=0,
    )


def test_runner_module_does_not_import_neo4j() -> None:
    source = Path(runner_module.__file__).read_text(encoding="utf-8")
    assert "import neo4j" not in source
    assert "from neo4j" not in source


def test_real_adapters_and_loader_satisfy_the_protocols_structurally(tmp_path: Path) -> None:
    resolver = IdentifierResolver([])
    nport = NPortAdapter(
        targets=(),
        raw_root=tmp_path / "raw-nport",
        resolver=resolver,
        user_agent="ops@example.com",
    )
    basket = ManagerBasketAdapter(
        targets=(),
        raw_root=tmp_path / "raw-basket",
        resolver=resolver,
        user_agent="ops@example.com",
    )
    assert isinstance(nport, HoldingsAdapter)
    assert isinstance(basket, HoldingsAdapter)
    assert nport.source == "sec_nport"
    assert basket.source == "manager_basket"

    protocol_signature = inspect.signature(HoldingsSink.load_holdings_rows)
    loader_signature = inspect.signature(ExternalGraphLoader.load_holdings_rows)
    expected = [(parameter.name, parameter.kind) for parameter in protocol_signature.parameters.values()]
    actual = [(parameter.name, parameter.kind) for parameter in loader_signature.parameters.values()]
    assert actual == expected
