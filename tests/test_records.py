# pyright: reportMissingTypeStubs=false
from __future__ import annotations

import json
from dataclasses import fields
from datetime import date, datetime, timezone
from pathlib import Path
from typing import cast

import pytest
from neo4j import Driver

from mirae_asset_graph.ingest.graph_loader import _holding_payload
from mirae_asset_graph.ingest.graph_loader import ExternalGraphLoader
from mirae_asset_graph.ingest.records import (
    CANONICAL_FIELDS,
    HoldingsRecord,
    read_jsonl,
    write_jsonl,
)


def _record(**overrides: object) -> HoldingsRecord:
    values: dict[str, object] = {
        "fund_isin": "US5007676944",
        "constituent_isin": "CNE1000041K3",
        "constituent_name": "Cambricon Technologies Corporation Limited",
        "weight": 0.0825,
        "as_of": date(2026, 7, 31),
        "source_quantity": 12500.0,
        "source_currency": "usd",
        "source_market_value": 1000000.0,
        "weight_source": "source_published",
        "identifier_method": "source_isin",
        "published_at": datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
        "source_document_id": "kstr-holdings-2026-07-31",
        "source_url": "https://kraneshares.com/etf/kstr/",
        "evidence_basis": "manager_published",
        "source_row_id": "row:2",
    }
    values.update(overrides)
    return HoldingsRecord.from_dict(values)


def test_create_normalizes_isins_text_and_currency() -> None:
    record = _record(
        fund_isin=" us5007676944 ",
        constituent_isin="cne1000041k3",
        constituent_name="  Cambricon Technologies Corporation Limited  ",
        source_url=" https://kraneshares.com/etf/kstr/ ",
    )

    assert record.fund_isin == "US5007676944"
    assert record.constituent_isin == "CNE1000041K3"
    assert record.constituent_name == "Cambricon Technologies Corporation Limited"
    assert record.source_currency == "USD"
    assert record.source_url == "https://kraneshares.com/etf/kstr/"


def test_create_accepts_iso_strings_and_numeric_strings() -> None:
    record = _record(
        weight="0.5",
        as_of="2026-07-31",
        source_quantity="12500",
        source_market_value="1000000.5",
        published_at="2026-08-01T12:00:00+00:00",
    )

    assert record.weight == 0.5
    assert record.as_of == date(2026, 7, 31)
    assert record.source_quantity == 12500.0
    assert record.source_market_value == 1000000.5
    assert record.published_at == datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def test_create_weight_bounds() -> None:
    assert _record(weight=0.0).weight == 0.0
    assert _record(weight=1.0).weight == 1.0

    for weight in (-0.01, 1.0001, "2"):
        with pytest.raises(ValueError, match=r"weight must be between 0 and 1"):
            _ = _record(weight=weight)


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("fund_isin", ""),
        ("fund_isin", "   "),
        ("fund_isin", "US123"),
        ("fund_isin", "KSTR"),
        ("constituent_isin", ""),
        ("constituent_isin", "247540"),
        ("constituent_name", ""),
        ("constituent_name", None),
        ("source_document_id", ""),
        ("source_url", ""),
        ("source_url", None),
    ],
)
def test_create_rejects_invalid_required_values(field_name: str, value: object) -> None:
    with pytest.raises(ValueError, match=field_name):
        _ = _record(**{field_name: value})


def test_create_rejects_invalid_enums_and_dates() -> None:
    with pytest.raises(ValueError, match=r"weight_source"):
        _ = _record(weight_source="guessed")
    with pytest.raises(ValueError, match=r"identifier_method"):
        _ = _record(identifier_method="name_match")
    with pytest.raises(ValueError, match=r"as_of"):
        _ = _record(as_of="31/07/2026")
    with pytest.raises(ValueError, match=r"as_of"):
        _ = _record(as_of=datetime(2026, 7, 31, tzinfo=timezone.utc))


def test_to_dict_is_json_serializable_with_canonical_keys() -> None:
    data = _record().to_dict()

    assert list(data) == list(CANONICAL_FIELDS)
    decoded = json.loads(json.dumps(data))
    assert decoded["as_of"] == "2026-07-31"
    assert decoded["published_at"] == "2026-08-01T12:00:00+00:00"
    assert decoded["weight"] == 0.0825


def test_optional_fields_stay_none_through_round_trip() -> None:
    sparse = _record(
        source_quantity=None,
        source_currency=None,
        source_market_value=None,
        published_at=None,
    )
    assert sparse.source_quantity is None
    assert sparse.source_currency is None
    assert sparse.source_market_value is None
    assert sparse.published_at is None

    decoded = json.loads(json.dumps(sparse.to_dict()))
    assert decoded["source_quantity"] is None
    assert decoded["source_currency"] is None
    assert decoded["source_market_value"] is None
    assert decoded["published_at"] is None

    assert HoldingsRecord.from_dict(decoded) == sparse


def test_from_dict_strict_round_trip() -> None:
    record = _record()

    assert HoldingsRecord.from_dict(json.loads(json.dumps(record.to_dict()))) == record


def test_from_dict_rejects_unknown_and_missing_keys() -> None:
    with_unknown = _record().to_dict()
    with_unknown["cusip"] = "037833100"
    with pytest.raises(ValueError, match=r"unknown field"):
        _ = HoldingsRecord.from_dict(with_unknown)

    with_missing = _record().to_dict()
    del with_missing["weight_source"]
    with pytest.raises(ValueError, match=r"weight_source"):
        _ = HoldingsRecord.from_dict(with_missing)


def test_to_loader_payload_keys_are_exactly_loader_fields() -> None:
    payload = _record().to_loader_payload()

    assert list(payload) == list(CANONICAL_FIELDS)
    assert isinstance(payload["as_of"], str)


def test_to_loader_payload_is_accepted_by_graph_loader() -> None:
    graph_row = _holding_payload(_record().to_loader_payload())

    assert graph_row["fundIsin"] == "US5007676944"
    assert graph_row["constituentIsin"] == "CNE1000041K3"
    assert graph_row["constituentName"] == "Cambricon Technologies Corporation Limited"
    assert graph_row["weight"] == pytest.approx(0.0825)
    assert graph_row["asOf"] == date(2026, 7, 31)
    assert graph_row["sourceQuantity"] == 12500.0
    assert graph_row["sourceCurrency"] == "USD"
    assert graph_row["sourceMarketValue"] == 1000000.0
    assert graph_row["weightSource"] == "source_published"
    assert graph_row["identifierMethod"] == "source_isin"
    assert graph_row["publishedAt"] == datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    assert graph_row["sourceDocumentId"] == "kstr-holdings-2026-07-31"
    assert graph_row["sourceUrl"] == "https://kraneshares.com/etf/kstr/"
    assert graph_row["fundUri"] == "urn:miraeasset:security:isin:US5007676944"
    assert graph_row["constituentUri"] == "urn:miraeasset:security:isin:CNE1000041K3"
    assert isinstance(graph_row["snapshotUri"], str)
    assert isinstance(graph_row["positionUri"], str)
    assert graph_row["snapshotUri"].endswith(":kstr-holdings-2026-07-31")
    assert graph_row["positionUri"].endswith(":kstr-holdings-2026-07-31:row%3A2")
    assert graph_row["evidenceBasis"] == "manager_published"
    assert graph_row["sourceRowId"] == "row:2"


def test_graph_identities_distinguish_amendments_and_preserve_rerun_identity() -> None:
    original = _holding_payload(_record(source_document_id="accession-original").to_loader_payload())
    rerun = _holding_payload(_record(source_document_id="accession-original").to_loader_payload())
    amendment = _holding_payload(_record(source_document_id="accession-amended").to_loader_payload())

    assert rerun["snapshotUri"] == original["snapshotUri"]
    assert rerun["positionUri"] == original["positionUri"]
    assert amendment["snapshotUri"] != original["snapshotUri"]
    assert amendment["positionUri"] != original["positionUri"]


def test_duplicate_security_rows_in_one_document_keep_distinct_positions() -> None:
    first = _holding_payload(_record(source_row_id="row:2").to_loader_payload())
    duplicate = _holding_payload(_record(source_row_id="row:3").to_loader_payload())
    assert first["snapshotUri"] == duplicate["snapshotUri"]
    assert first["positionUri"] != duplicate["positionUri"]


def test_graph_loader_uses_full_artifact_sha256() -> None:
    class FakeDriver:
        arguments: dict[str, object] = {}

        def execute_query(self, query: str, **kwargs: object):
            self.arguments = kwargs
            return [], None, None

    driver = FakeDriver()
    loader = ExternalGraphLoader(cast(Driver, cast(object, driver)), "mirae_staging")
    digest = "a" * 64
    result = loader.load_holdings_rows(
        [_record().to_loader_payload()],
        source="sec_nport",
        source_url="https://www.sec.gov/example.xml",
        artifact_sha256=digest,
        artifact_bytes=100,
        run_id="test-run",
        retrieved_at=datetime(2026, 7, 11, tzinfo=timezone.utc),
    )

    assert result == {"rows": 1}
    assert driver.arguments["artifactUri"] == f"urn:miraeasset:external:artifact:{digest}"
    assert driver.arguments["database_"] == "mirae_staging"


def test_jsonl_round_trip_and_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "holdings.jsonl"
    first = [
        _record(),
        _record(
            constituent_isin="KR7091160005",
            constituent_name="KODEX 반도체",
            weight=0.5,
            identifier_method="crosswalk",
        ),
    ]

    assert write_jsonl(first, path) == 2
    content = path.read_text(encoding="utf-8")
    assert content.endswith("\n")
    assert len(content.splitlines()) == 2
    assert read_jsonl(path) == first

    only = [_record(constituent_isin="HK0000637832")]
    assert write_jsonl(only, path) == 1
    assert read_jsonl(path) == only


def test_read_jsonl_reports_line_number_on_invalid_line(tmp_path: Path) -> None:
    path = tmp_path / "broken.jsonl"
    valid_line = json.dumps(_record().to_dict(), ensure_ascii=False)
    _ = path.write_text(valid_line + "\n{oops\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"line 2"):
        _ = read_jsonl(path)


def test_dataclass_field_order_matches_contract() -> None:
    assert [field.name for field in fields(HoldingsRecord)] == [
        "fund_isin",
        "constituent_isin",
        "constituent_name",
        "weight",
        "as_of",
        "source_quantity",
        "source_currency",
        "source_market_value",
        "weight_source",
        "identifier_method",
        "published_at",
        "source_document_id",
        "source_url",
        "evidence_basis",
        "source_row_id",
    ]
