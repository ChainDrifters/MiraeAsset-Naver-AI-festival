# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest
from neo4j import GraphDatabase

from mirae_asset_graph.ingest.graph_loader import ExternalGraphLoader

FIXTURE = Path(__file__).parent / "fixtures" / "holdings_mini.csv"


pytestmark = pytest.mark.integration


def test_loaded_manifest_batch_is_skipped_on_rerun(tmp_path: Path) -> None:
    with _driver() as driver:
        loader = ExternalGraphLoader(driver, _database())
        first = loader.load_holdings_csv(
            FIXTURE,
            source="fixture_holdings_resume",
            source_url="urn:test:holdings-mini-resume",
            run_id="fixture-holdings-resume",
            manifest_root=tmp_path,
            window_date=date(2026, 7, 11),
        )
        first_counts = loader.label_counts()

        second = loader.load_holdings_csv(
            FIXTURE,
            source="fixture_holdings_resume",
            source_url="urn:test:holdings-mini-resume",
            run_id="fixture-holdings-resume",
            manifest_root=tmp_path,
            window_date=date(2026, 7, 11),
        )
        second_counts = loader.label_counts()

    assert first["skipped"] is False
    assert second["skipped"] is True
    assert second_counts == first_counts


def _driver():
    uri = os.environ["MIRAE_TEST_NEO4J_URI"]
    user = os.getenv("MIRAE_TEST_NEO4J_USER", os.getenv("NEO4J_USER", "neo4j"))
    password = os.getenv("MIRAE_TEST_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD"))
    auth = (user, password) if password else None
    return GraphDatabase.driver(uri, auth=auth)


def _database() -> str:
    return os.getenv("MIRAE_TEST_NEO4J_DATABASE", "neo4j")
