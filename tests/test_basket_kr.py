# pyright: reportMissingTypeStubs=false
from __future__ import annotations

import email.message
import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import cast

import pytest
from openpyxl import Workbook

import mirae_asset_graph.ingest.basket_kr as basket_module
from mirae_asset_graph.ingest.basket_kr import ManagerBasketAdapter, ManagerBasketTarget
from mirae_asset_graph.ingest.crosswalk import CROSSWALK_FIELDS, CrosswalkRow
from mirae_asset_graph.ingest.records import read_jsonl
from mirae_asset_graph.ingest.resolver import IdentifierResolver

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "basket_kr_mini.csv"
FIXTURE_BYTES = FIXTURE.read_bytes()

VALID_USER_AGENT = "mirae-graph/1.0 contact@example.com"
MANAGER_CODE = "sample-am"
FUND_CODE = "360200"
FUND_ISIN = "KR7360200008"
SOURCE_URL = "https://www.example.co.kr/fund/360200/holdings.csv"
AS_OF = date(2026, 6, 30)
PUBLISHED_AT = datetime(2026, 7, 10, 9, 0, 0)

DOCUMENT_ID = f"{MANAGER_CODE}:{FUND_CODE}:{AS_OF.isoformat()}"
DOCUMENT_TOTAL_MARKET_VALUE = 1_000_000.0


def _target(
    manager_code: str = MANAGER_CODE,
    fund_code: str = FUND_CODE,
    fund_isin: str = FUND_ISIN,
    source_url: str = SOURCE_URL,
    as_of: date = AS_OF,
    published_at: datetime = PUBLISHED_AT,
    format_hint: str = "csv",
) -> ManagerBasketTarget:
    return ManagerBasketTarget(
        manager_code=manager_code,
        fund_code=fund_code,
        fund_isin=fund_isin,
        source_url=source_url,
        as_of=as_of,
        published_at=published_at,
        format_hint=format_hint,
    )


def _krx_resolver() -> IdentifierResolver:
    values = {field: "" for field in CROSSWALK_FIELDS}
    values.update(
        {
            "entity_kind": "security",
            "local_key_type": "krx_code",
            "local_key": "005380",
            "local_name": "현대차",
            "standard_id_type": "isin",
            "standard_id": "KR7005380008",
            "standard_name": "현대차",
            "reviewed_by": "test-reviewer",
            "reviewed_at": "2026-08-21",
        }
    )
    return IdentifierResolver([CrosswalkRow(**values)])


def _adapter(
    tmp_path: Path,
    *,
    targets: Iterable[ManagerBasketTarget] | None = None,
    resolver: IdentifierResolver | None = None,
    user_agent: str = VALID_USER_AGENT,
    request_interval_seconds: float = 0.25,
    retry_count: int = 3,
    window_start: date | None = None,
    window_end: date | None = None,
    cutoff: datetime | None = None,
) -> ManagerBasketAdapter:
    return ManagerBasketAdapter(
        targets=targets if targets is not None else [_target()],
        raw_root=tmp_path / "raw",
        resolver=resolver if resolver is not None else _krx_resolver(),
        user_agent=user_agent,
        request_interval_seconds=request_interval_seconds,
        retry_count=retry_count,
        window_start=window_start,
        window_end=window_end,
        cutoff=cutoff,
    )


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
    return urllib.error.HTTPError(
        SOURCE_URL, code, "synthetic error", email.message.Message(), None
    )


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

    for generic in ("", "   ", "python-urllib/3.11", "Mozilla/5.0", "basket-bot"):
        with pytest.raises(ValueError, match="user_agent"):
            _adapter(tmp_path, user_agent=generic)


def test_interval_and_retry_configuration_is_validated(tmp_path: Path) -> None:
    for invalid in (0, 0.0, -1, -0.5):
        with pytest.raises(ValueError, match="request_interval_seconds"):
            _adapter(tmp_path, request_interval_seconds=invalid)
    with pytest.raises(ValueError, match="retry_count"):
        _adapter(tmp_path, retry_count=-1)
    assert _adapter(tmp_path).request_interval_seconds == 0.25
    assert _adapter(tmp_path).retry_count == 3


def test_target_rejects_malformed_fields() -> None:
    with pytest.raises(ValueError, match="manager_code"):
        _target(manager_code=" ")
    with pytest.raises(ValueError, match="path separators"):
        _target(manager_code="sample/am")
    with pytest.raises(ValueError, match="fund_code"):
        _target(fund_code="")
    with pytest.raises(ValueError, match="path separators"):
        _target(fund_code="..")
    with pytest.raises(ValueError, match="fund_isin"):
        _target(fund_isin="360200")
    with pytest.raises(ValueError, match="https"):
        _target(source_url="http://www.example.co.kr/holdings.csv")
    with pytest.raises(ValueError, match="as_of"):
        _target(as_of=cast(date, datetime(2026, 6, 30, 12, 0, 0)))
    with pytest.raises(ValueError, match="published_at"):
        _target(published_at=cast(datetime, AS_OF))


def test_target_rejects_pdf_and_other_unsupported_formats() -> None:
    for unsupported in ("pdf", "PDF", "xlsx ", "json"):
        with pytest.raises(ValueError, match="format_hint"):
            _target(format_hint=unsupported)
    assert _target(format_hint="csv").format_hint == "csv"
    assert _target(format_hint="xlsx").format_hint == "xlsx"


def test_discover_filters_window_and_cutoff(tmp_path: Path) -> None:
    q1 = _target(
        fund_code="360100",
        as_of=date(2026, 3, 31),
        published_at=datetime(2026, 5, 1),
    )
    q2 = _target(
        fund_code="360200",
        as_of=date(2026, 6, 30),
        published_at=datetime(2026, 8, 1),
    )
    q2_tie = _target(
        manager_code="zz-sample",
        fund_code="360200",
        as_of=date(2026, 6, 30),
        published_at=datetime(2026, 8, 1),
    )
    q3 = _target(
        fund_code="360300",
        as_of=date(2026, 9, 30),
        published_at=datetime(2026, 11, 1),
    )
    adapter = _adapter(tmp_path, targets=[q3, q2_tie, q2, q1])

    assert adapter.discover(start=date(2026, 1, 11), end=date(2026, 7, 11)) == [q1, q2, q2_tie]
    assert adapter.discover() == [q1, q2, q2_tie, q3]
    assert adapter.discover(
        start=date(2026, 1, 11), end=date(2026, 7, 11), cutoff=datetime(2026, 7, 1)
    ) == [q1]
    assert adapter.discover(start=date(2026, 3, 31), end=date(2026, 6, 30)) == [q1, q2, q2_tie]
    assert adapter.discover(end=date(2026, 12, 31), cutoff=datetime(2026, 8, 1)) == [q1, q2, q2_tie]

    configured = _adapter(
        tmp_path,
        targets=[q3, q2_tie, q2, q1],
        window_start=date(2026, 1, 11),
        window_end=date(2026, 7, 11),
        cutoff=datetime(2026, 8, 1),
    )
    assert configured.discover() == [q1, q2, q2_tie]


def test_normalize_utf8_fixture_yields_three_records_and_two_quarantined(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    output_dir = tmp_path / "normalized"

    records_path, quarantine_path, record_count, quarantine_count = adapter.normalize(
        _target(), FIXTURE, output_dir
    )

    assert (record_count, quarantine_count) == (3, 2)
    assert records_path == (
        output_dir / "manager_basket" / MANAGER_CODE / FUND_CODE / "2026-06-30.jsonl"
    )
    assert quarantine_path == (
        output_dir / "manager_basket" / MANAGER_CODE / FUND_CODE / "2026-06-30.quarantine.jsonl"
    )

    records = read_jsonl(records_path)
    assert [record.constituent_isin for record in records] == [
        "KR7005930003",
        "KR7005380008",
        "KR7000660001",
    ]

    one = records[0]
    assert one.constituent_name == "삼성전자"
    assert one.weight == pytest.approx(0.325)
    assert one.weight_source == "source_published"
    assert one.identifier_method == "source_isin"
    assert one.fund_isin == FUND_ISIN
    assert one.as_of == AS_OF
    assert one.published_at == PUBLISHED_AT
    assert one.source_document_id == DOCUMENT_ID
    assert one.source_url == SOURCE_URL
    assert one.source_quantity == pytest.approx(1000.0)
    assert one.source_market_value == pytest.approx(450000.0)
    assert one.source_currency == "KRW"

    two = records[1]
    assert two.constituent_name == "현대차"
    assert two.identifier_method == "crosswalk"
    assert two.weight == pytest.approx(0.25)
    assert two.weight_source == "source_published"
    assert two.source_market_value is None
    assert two.source_currency is None

    three = records[2]
    assert three.constituent_name == "SK하이닉스"
    assert three.weight == pytest.approx(300000.0 / DOCUMENT_TOTAL_MARKET_VALUE)
    assert three.weight_source == "derived_from_value"
    assert three.identifier_method == "source_isin"
    assert three.source_market_value == pytest.approx(300000.0)
    assert three.source_currency == "KRW"

    entries = _read_quarantine(quarantine_path)
    by_identifier = {entry["source_identifier_value"]: entry for entry in entries}

    unresolved = by_identifier["999999"]
    assert unresolved["source_identifier_type"] == "krx_code"
    assert unresolved["constituent_name"] == "미해결종목"
    assert unresolved["source_document_id"] == DOCUMENT_ID
    assert "no reviewed ISIN crosswalk entry" in cast(str, unresolved["reason"])

    negative = by_identifier["KR7035740009"]
    assert negative["source_identifier_type"] == "isin"
    assert negative["constituent_name"] == "음수수량종목"
    assert "quantity is negative: -50.0" in cast(str, negative["reason"])


def test_normalize_cp949_fallback_matches_utf8_result(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    cp949_path = tmp_path / "basket_cp949.csv"
    cp949_path.write_bytes(FIXTURE.read_text(encoding="utf-8").encode("cp949"))

    utf8_result = adapter.normalize(_target(), FIXTURE, tmp_path / "out-utf8")
    cp949_result = adapter.normalize(_target(), cp949_path, tmp_path / "out-cp949")

    assert cp949_result[2:] == utf8_result[2:] == (3, 2)
    assert [record.to_dict() for record in read_jsonl(cp949_result[0])] == [
        record.to_dict() for record in read_jsonl(utf8_result[0])
    ]
    assert _read_quarantine(cp949_result[1]) == _read_quarantine(utf8_result[1])


def test_normalize_xlsx_first_worksheet_matches_csv_result(tmp_path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "보유내역"
    sheet.append(["기준일", "종목명", "표준코드", "종목코드", "비중(%)", "수량", "평가금액", "통화"])
    sheet.append([date(2026, 6, 30), "삼성전자", "KR7005930003", "005930", 32.5, 1000, 450000, "KRW"])
    sheet.append(["2026.06.30", "현대차", None, "005380", 25.0, 2000, None, None])
    sheet.append([None, "SK하이닉스", "KR7000660001", None, None, 500, 300000, None])
    sheet.append([None, "미해결종목", None, "999999", 10.0, 100, 100000, "KRW"])
    sheet.append([None, "음수수량종목", "KR7035740009", None, 15.0, -50, 150000, "KRW"])
    second = workbook.create_sheet("참고")
    second.append(["무시해야 하는 시트"])
    xlsx_path = tmp_path / "basket.xlsx"
    workbook.save(xlsx_path)

    adapter = _adapter(tmp_path)
    csv_result = adapter.normalize(_target(), FIXTURE, tmp_path / "out-csv")
    xlsx_result = adapter.normalize(_target(format_hint="xlsx"), xlsx_path, tmp_path / "out-xlsx")

    assert xlsx_result[2:] == csv_result[2:] == (3, 2)
    assert [record.to_dict() for record in read_jsonl(xlsx_result[0])] == [
        record.to_dict() for record in read_jsonl(csv_result[0])
    ]
    assert _read_quarantine(xlsx_result[1]) == _read_quarantine(csv_result[1])


def test_fetch_cache_hit_makes_no_network_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(request: object, timeout: object = None) -> object:
        raise AssertionError("a cached raw file must not trigger urlopen")

    monkeypatch.setattr(urllib.request, "urlopen", unreachable)
    adapter = _adapter(tmp_path)
    cached = adapter.raw_root / "manager_basket" / MANAGER_CODE / FUND_CODE / "2026-06-30.csv"
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"already stored")

    assert adapter.fetch(_target()) == cached
    assert cached.read_bytes() == b"already stored"


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

    adapter = _adapter(tmp_path)
    raw_path = adapter.fetch(_target())

    assert raw_path == adapter.raw_root / "manager_basket" / MANAGER_CODE / FUND_CODE / "2026-06-30.csv"
    assert raw_path.read_bytes() == FIXTURE_BYTES
    assert len(calls) == 2
    assert 1.0 in sleep_recorder.calls
    assert list(raw_path.parent.glob("*.tmp")) == []

    headers = {key.lower(): value for key, value in requests_seen[0].header_items()}
    assert headers["user-agent"] == VALID_USER_AGENT
    assert headers["accept"] == "text/csv"
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

    adapter = _adapter(tmp_path)
    with pytest.raises(urllib.error.HTTPError):
        adapter.fetch(_target())

    assert calls == [404]
    assert sleep_recorder.calls == []


def test_normalize_rejects_as_of_mismatch(tmp_path: Path) -> None:
    adapter = _adapter(tmp_path)
    mismatched = tmp_path / "mismatched.csv"
    mismatched.write_text(
        FIXTURE.read_text(encoding="utf-8")
        .replace("2026-06-30", "2026-03-31")
        .replace("2026.06.30", "2026.03.31"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not match the target as_of"):
        adapter.normalize(_target(), mismatched, tmp_path / "out")


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


def test_basket_module_does_not_import_neo4j() -> None:
    source = Path(basket_module.__file__).read_text(encoding="utf-8")
    assert "import neo4j" not in source
    assert "from neo4j" not in source
