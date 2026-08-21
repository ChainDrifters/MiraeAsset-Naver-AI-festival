# pyright: reportMissingTypeStubs=false
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

import pytest

import mirae_asset_graph.ingest.nport as nport_module
from mirae_asset_graph.ingest.crosswalk import CROSSWALK_FIELDS, CrosswalkRow
from mirae_asset_graph.ingest.nport import NPortAdapter, NPortTarget
from mirae_asset_graph.ingest.records import read_jsonl
from mirae_asset_graph.ingest.resolver import IdentifierResolver

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "nport_mini.xml"
FIXTURE_BYTES = FIXTURE.read_bytes()

VALID_USER_AGENT = "mirae-graph/1.0 contact@example.com"
FUND_ISIN = "US0000000099"
ACCESSION = "0000000001-26-000001"
SOURCE_URL = "https://www.sec.gov/Archives/edgar/data/0000000001/000000000126000001/nport.xml"
AS_OF = date(2026, 6, 30)
PUBLISHED_AT = datetime(2026, 8, 1, 12, 0, 0)

DOCUMENT_TOTAL_VAL_USD = 950000.0


def _target(**overrides: object) -> NPortTarget:
    values: dict[str, object] = {
        "accession": ACCESSION,
        "source_url": SOURCE_URL,
        "fund_isin": FUND_ISIN,
        "as_of": AS_OF,
        "published_at": PUBLISHED_AT,
    }
    values.update(overrides)
    return NPortTarget(**values)  # type: ignore[arg-type]


def _adapter(tmp_path: Path, **overrides: object) -> NPortAdapter:
    values: dict[str, object] = {
        "targets": [_target()],
        "raw_root": tmp_path / "raw",
        "resolver": IdentifierResolver([]),
        "user_agent": VALID_USER_AGENT,
    }
    values.update(overrides)
    return NPortAdapter(**values)  # type: ignore[arg-type]


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(SOURCE_URL, code, "synthetic error", None, None)


class _SleepRecorder:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def _read_quarantine(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_user_agent_must_identify_the_caller(tmp_path: Path) -> None:
    assert _adapter(tmp_path, user_agent=VALID_USER_AGENT).user_agent == VALID_USER_AGENT
    assert _adapter(tmp_path, user_agent="mirae-graph/1.0 https://example.com/contact").user_agent

    for generic in ("", "   ", "python-urllib/3.11", "Mozilla/5.0", "nport-bot"):
        with pytest.raises(ValueError, match="user_agent"):
            _adapter(tmp_path, user_agent=generic)


def test_rate_and_retry_configuration_is_validated(tmp_path: Path) -> None:
    for invalid in (0, 0.0, -1, -0.5):
        with pytest.raises(ValueError, match="max_requests_per_second"):
            _adapter(tmp_path, max_requests_per_second=invalid)
    with pytest.raises(ValueError, match="retry_count"):
        _adapter(tmp_path, retry_count=-1)
    assert _adapter(tmp_path).max_requests_per_second == 10.0
    assert _adapter(tmp_path).retry_count == 3


def test_target_rejects_malformed_fields() -> None:
    with pytest.raises(ValueError, match="accession"):
        _target(accession=" ")
    with pytest.raises(ValueError, match="path separators"):
        _target(accession="0000000001/26/000001")
    with pytest.raises(ValueError, match="as_of"):
        _target(as_of=datetime(2026, 6, 30, 12, 0, 0))
    with pytest.raises(ValueError, match="published_at"):
        _target(published_at=AS_OF)


def test_discover_filters_window_and_cutoff(tmp_path: Path) -> None:
    q1 = _target(
        accession="0000000001-26-000001",
        as_of=date(2026, 3, 31),
        published_at=datetime(2026, 5, 1),
    )
    q2 = _target(
        accession="0000000001-26-000002",
        as_of=date(2026, 6, 30),
        published_at=datetime(2026, 8, 1),
    )
    q3 = _target(
        accession="0000000001-26-000003",
        as_of=date(2026, 9, 30),
        published_at=datetime(2026, 11, 1),
    )
    adapter = _adapter(tmp_path, targets=[q3, q1, q2])

    assert adapter.discover(start=date(2026, 1, 11), end=date(2026, 7, 11)) == [q1, q2]
    assert adapter.discover() == [q1, q2, q3]
    assert adapter.discover(
        start=date(2026, 1, 11), end=date(2026, 7, 11), cutoff=datetime(2026, 7, 1)
    ) == [q1]
    assert adapter.discover(start=date(2026, 3, 31), end=date(2026, 6, 30)) == [q1, q2]
    assert adapter.discover(end=date(2026, 12, 31), cutoff=datetime(2026, 8, 1)) == [q1, q2]

    configured = _adapter(
        tmp_path,
        targets=[q3, q1, q2],
        window_start=date(2026, 1, 11),
        window_end=date(2026, 7, 11),
        cutoff=datetime(2026, 8, 1),
    )
    assert configured.discover() == [q1, q2]


def test_fetch_cache_hit_makes_no_network_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(request: object, timeout: object = None) -> object:
        raise AssertionError("a cached raw file must not trigger urlopen")

    monkeypatch.setattr(urllib.request, "urlopen", unreachable)
    adapter = _adapter(tmp_path)
    cached = adapter.raw_root / "sec_nport" / f"{ACCESSION}.xml"
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"<edgarSubmission>already stored</edgarSubmission>")

    assert adapter.fetch(_target()) == cached
    assert cached.read_bytes() == b"<edgarSubmission>already stored</edgarSubmission>"


def test_fetch_refetches_when_cached_file_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter(tmp_path)
    cached = adapter.raw_root / "sec_nport" / f"{ACCESSION}.xml"
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"")
    monkeypatch.setattr(
        urllib.request, "urlopen", lambda request, timeout=None: _FakeResponse(FIXTURE_BYTES)
    )

    assert adapter.fetch(_target()) == cached
    assert cached.read_bytes() == FIXTURE_BYTES


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_fetch_retries_transient_failure_then_writes_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    calls: list[int] = []
    requests_seen: list[urllib.request.Request] = []

    def fake_urlopen(request: urllib.request.Request, timeout: object = None) -> _FakeResponse:
        requests_seen.append(request)
        calls.append(status_code)
        if len(calls) == 1:
            raise _http_error(status_code)
        return _FakeResponse(FIXTURE_BYTES)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    sleep_recorder = _SleepRecorder()
    monkeypatch.setattr(time, "sleep", sleep_recorder)

    adapter = _adapter(tmp_path, max_requests_per_second=1000.0)
    raw_path = adapter.fetch(_target())

    assert raw_path == adapter.raw_root / "sec_nport" / f"{ACCESSION}.xml"
    assert raw_path.read_bytes() == FIXTURE_BYTES
    assert len(calls) == 2
    assert 1.0 in sleep_recorder.calls
    assert list(raw_path.parent.glob("*.tmp")) == []

    headers = {key.lower(): value for key, value in requests_seen[0].header_items()}
    assert headers["user-agent"] == VALID_USER_AGENT
    assert headers["accept"] == "application/xml"
    assert requests_seen[0].full_url == SOURCE_URL


def test_fetch_raises_non_retryable_status_without_sleeping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def fake_urlopen(request: object, timeout: object = None) -> object:
        calls.append(404)
        raise _http_error(404)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    sleep_recorder = _SleepRecorder()
    monkeypatch.setattr(time, "sleep", sleep_recorder)

    adapter = _adapter(tmp_path, max_requests_per_second=1000.0)
    with pytest.raises(urllib.error.HTTPError):
        adapter.fetch(_target())

    assert calls == [404]
    assert sleep_recorder.calls == []


def test_normalize_yields_two_records_and_three_quarantined(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    output_dir = tmp_path / "normalized"

    records_path, quarantine_path, record_count, quarantine_count = adapter.normalize(
        _target(), FIXTURE, output_dir
    )

    assert (record_count, quarantine_count) == (2, 3)
    assert records_path == output_dir / "sec_nport" / f"{ACCESSION}.jsonl"
    assert quarantine_path == output_dir / "sec_nport" / f"{ACCESSION}.quarantine.jsonl"

    records = read_jsonl(records_path)
    assert [record.constituent_isin for record in records] == ["US0000000001", "US0000000003"]

    one = records[0]
    assert one.constituent_name == "Synthetic Holding One"
    assert one.weight == pytest.approx(0.4)
    assert one.weight_source == "source_published"
    assert one.identifier_method == "source_isin"
    assert one.fund_isin == FUND_ISIN
    assert one.as_of == AS_OF
    assert one.published_at == PUBLISHED_AT
    assert one.source_document_id == ACCESSION
    assert one.source_url == SOURCE_URL
    assert one.source_quantity == pytest.approx(4000.0)
    assert one.source_market_value == pytest.approx(400000.0)
    assert one.source_currency == "USD"

    three = records[1]
    assert three.constituent_name == "Synthetic Holding Three"
    assert three.weight == pytest.approx(200000.0 / DOCUMENT_TOTAL_VAL_USD)
    assert three.weight_source == "derived_from_value"
    assert three.identifier_method == "source_isin"
    assert three.source_market_value == pytest.approx(200000.0)

    entries = _read_quarantine(quarantine_path)
    by_identifier = {entry["source_identifier_value"]: entry for entry in entries}

    two = by_identifier["000000002"]
    assert two["source_identifier_type"] == "cusip"
    assert two["constituent_name"] == "Synthetic Holding Two"
    assert two["source_document_id"] == ACCESSION
    assert "no reviewed ISIN crosswalk entry" in two["reason"]

    four = by_identifier["US0000000004"]
    assert four["source_identifier_type"] == "isin"
    assert "balance is negative: -500.0" in four["reason"]

    five = by_identifier["US0000000005"]
    assert five["source_identifier_type"] == "isin"
    assert "exceeds 1.0" in five["reason"]


def test_normalize_rejects_report_date_mismatch(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    mismatched = tmp_path / "mismatched.xml"
    mismatched.write_text(
        FIXTURE.read_text(encoding="utf-8").replace("2026-06-30", "2026-03-31"), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="does not match the target as_of"):
        adapter.normalize(_target(), mismatched, tmp_path / "out")


def test_normalize_accepts_period_of_report_tag(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    variant = tmp_path / "period.xml"
    variant.write_text(
        FIXTURE.read_text(encoding="utf-8")
        .replace("<reportDate>", "<periodOfReport>")
        .replace("</reportDate>", "</periodOfReport>"),
        encoding="utf-8",
    )

    _, _, record_count, quarantine_count = adapter.normalize(_target(), variant, tmp_path / "out")

    assert (record_count, quarantine_count) == (2, 3)


def test_normalize_rerun_is_deterministic(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    output_dir = tmp_path / "normalized"

    first = adapter.normalize(_target(), FIXTURE, output_dir)
    first_records = first[0].read_bytes()
    first_quarantine = first[1].read_bytes()
    second = adapter.normalize(_target(), FIXTURE, output_dir)

    assert second[0].read_bytes() == first_records
    assert second[1].read_bytes() == first_quarantine
    assert second[2:] == first[2:]


def test_normalize_resolves_cusip_through_reviewed_crosswalk(tmp_path: Path) -> None:
    values = {field: "" for field in CROSSWALK_FIELDS}
    values.update(
        {
            "entity_kind": "security",
            "local_key_type": "cusip",
            "local_key": "000000002",
            "local_name": "Synthetic Holding Two",
            "standard_id_type": "isin",
            "standard_id": "US0000000002",
            "standard_name": "Synthetic Holding Two",
            "reviewed_by": "test-reviewer",
            "reviewed_at": "2026-08-21",
        }
    )
    resolver = IdentifierResolver([CrosswalkRow(**values)])
    adapter = _adapter(tmp_path, resolver=resolver)

    records_path, _, record_count, quarantine_count = adapter.normalize(
        _target(), FIXTURE, tmp_path / "out"
    )

    assert (record_count, quarantine_count) == (3, 2)
    two = next(
        record for record in read_jsonl(records_path) if record.constituent_isin == "US0000000002"
    )
    assert two.identifier_method == "crosswalk"
    assert two.weight == pytest.approx(0.25)
    assert two.weight_source == "source_published"


def test_nport_module_does_not_import_neo4j() -> None:
    source = Path(nport_module.__file__).read_text(encoding="utf-8")
    assert "import neo4j" not in source
    assert "from neo4j" not in source
