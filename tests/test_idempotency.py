# pyright: reportMissingTypeStubs=false, reportUnknownMemberType=false
from __future__ import annotations

import os
from pathlib import Path

import pytest
from neo4j import GraphDatabase

from mirae_asset_graph.ingest.graph_loader import ExternalGraphLoader

FIXTURE = Path(__file__).parent / "fixtures" / "holdings_mini.csv"


pytestmark = pytest.mark.integration


def test_holdings_load_is_idempotent() -> None:
    with _driver() as driver:
        loader = ExternalGraphLoader(driver, _database())
        _ = loader.load_holdings_csv(
            FIXTURE,
            source="fixture_holdings",
            source_url="urn:test:holdings-mini",
            run_id="fixture-holdings-idempotency",
        )
        first_counts = loader.label_counts()

        _ = loader.load_holdings_csv(
            FIXTURE,
            source="fixture_holdings",
            source_url="urn:test:holdings-mini",
            run_id="fixture-holdings-idempotency",
        )
        second_counts = loader.label_counts()

    assert second_counts == first_counts


def _driver():
    uri = os.environ["MIRAE_TEST_NEO4J_URI"]
    user = os.getenv("MIRAE_TEST_NEO4J_USER", os.getenv("NEO4J_USER", "neo4j"))
    password = os.getenv("MIRAE_TEST_NEO4J_PASSWORD", os.getenv("NEO4J_PASSWORD"))
    auth = (user, password) if password else None
    return GraphDatabase.driver(uri, auth=auth)


def _database() -> str:
    return os.getenv("MIRAE_TEST_NEO4J_DATABASE", "neo4j")
