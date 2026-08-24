from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Callable

import pytest

from mirae_asset_graph.ingest.basket_kr import ManagerBasketTarget
from mirae_asset_graph.ingest.nport import NPortTarget
from mirae_asset_graph.ingest.targets import (
    load_target_config,
    summarize_targets,
    target_document_id,
    target_window,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_strict_homogeneous_target_types_and_document_ids() -> None:
    nport = load_target_config(FIXTURES / "targets_nport.json")
    manager = load_target_config(FIXTURES / "targets_manager.json")

    assert nport.source == "sec_nport"
    assert all(isinstance(target, NPortTarget) for target in nport.targets)
    assert target_document_id(nport.targets[0]) == "0000000001-26-000001"
    assert manager.source == "manager_basket"
    assert all(isinstance(target, ManagerBasketTarget) for target in manager.targets)
    assert target_document_id(manager.targets[-1]) == "synthetic-manager:fund-b:2026-07-11"


def _write_config(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "targets.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda value: value.update({"unexpected": True}), "unknown keys"),
        (lambda value: value.pop("source"), "missing keys"),
        (lambda value: value["targets"][0].update({"manager_code": "mixed"}), "unknown keys"),
        (lambda value: value["targets"][0].update({"source_url": "http://example.invalid/a.xml"}), "HTTPS"),
        (lambda value: value["targets"][0].update({"as_of": "2026-02-30"}), "ISO date"),
        (lambda value: value["targets"][0].update({"published_at": "not-a-time"}), "ISO datetime"),
    ],
)
def test_rejects_unknown_missing_mixed_and_invalid_values(
    tmp_path: Path, mutation: Callable[[dict[str, object]], object], message: str
) -> None:
    loaded = json.loads((FIXTURES / "targets_nport.json").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    value = loaded
    if message != "HTTPS":
        value["targets"][0]["source_url"] = "https://www.sec.gov/example.xml"
    mutation(value)
    with pytest.raises(ValueError, match=message):
        load_target_config(_write_config(tmp_path, value))


def test_rejects_duplicate_source_document_identity(tmp_path: Path) -> None:
    value = json.loads((FIXTURES / "targets_nport.json").read_text(encoding="utf-8"))
    for target in value["targets"]:
        target["source_url"] = f"https://www.sec.gov/{target['accession']}.xml"
    value["targets"].append(dict(value["targets"][0]))
    with pytest.raises(ValueError, match="Duplicate source-document identity"):
        load_target_config(_write_config(tmp_path, value))


def test_date_and_cutoff_window_is_inclusive_and_sorted() -> None:
    config = load_target_config(FIXTURES / "targets_nport.json")
    selected = target_window(
        config.targets,
        start=date(2026, 4, 11),
        end=date(2026, 7, 11),
        cutoff=datetime(2026, 7, 1, tzinfo=UTC),
    )
    assert [target_document_id(target) for target in selected] == ["0000000001-26-000002"]
    with pytest.raises(ValueError, match="start must be on or before end"):
        target_window(config.targets, start=date(2026, 7, 12), end=date(2026, 7, 11))


def test_summary_has_counts_and_date_bounds() -> None:
    config = load_target_config(FIXTURES / "targets_manager.json")
    assert config.summary() == {
        "as_of_date_count": 3,
        "document_count": 4,
        "max_as_of": "2026-07-11",
        "min_as_of": "2026-01-11",
        "source": "manager_basket",
        "target_count": 4,
    }
    assert summarize_targets((), source="manager_basket")["min_as_of"] is None


@pytest.mark.parametrize("source", ["krx", "krx_basket", "KRX_API"])
def test_rejects_krx_source_identifiers(tmp_path: Path, source: str) -> None:
    value = {"source": source, "targets": []}
    with pytest.raises(ValueError, match="KRX automated acquisition is blocked"):
        load_target_config(_write_config(tmp_path, value))


@pytest.mark.parametrize(
    "url",
    [
        "https://openapi.krx.co.kr/example",
        "https://global.krx.co.kr/example.pdf",
        "https://data.krx.co.kr/example",
    ],
)
def test_rejects_krx_acquisition_urls(tmp_path: Path, url: str) -> None:
    value = json.loads((FIXTURES / "targets_nport.json").read_text(encoding="utf-8"))
    value["targets"][0]["source_url"] = url
    with pytest.raises(ValueError, match="KRX automated acquisition is blocked"):
        load_target_config(_write_config(tmp_path, value))


def test_production_config_rejects_example_invalid_outside_test_fixtures(tmp_path: Path) -> None:
    value = json.loads((FIXTURES / "targets_nport.json").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="example.invalid is test-only"):
        load_target_config(_write_config(tmp_path, value))


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("as_of", "2026-01-10", "policy window"),
        ("as_of", "2026-07-12", "policy window"),
        ("published_at", "2026-07-12T00:00:00Z", "publication cutoff"),
        ("published_at", "2026-07-11T23:59:59", "timezone-aware"),
    ],
)
def test_production_policy_is_fixed(tmp_path: Path, field: str, value: str, message: str) -> None:
    config = json.loads((FIXTURES / "targets_nport.json").read_text(encoding="utf-8"))
    config["targets"][0][field] = value
    config["targets"][0]["source_url"] = "https://www.sec.gov/example.xml"
    with pytest.raises(ValueError, match=message):
        load_target_config(_write_config(tmp_path, config))


def test_cli_window_can_narrow_but_never_widen_policy() -> None:
    config = load_target_config(FIXTURES / "targets_nport.json")
    with pytest.raises(ValueError, match="cannot widen"):
        target_window(config.targets, start=date(2026, 1, 10))
    with pytest.raises(ValueError, match="cannot widen"):
        target_window(config.targets, end=date(2026, 7, 12))
    with pytest.raises(ValueError, match="cannot widen"):
        target_window(config.targets, cutoff=datetime(2026, 7, 12, tzinfo=UTC))
