from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: requires a Neo4j test database")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    _ = config
    if os.getenv("MIRAE_TEST_NEO4J_URI"):
        return
    skip_integration = pytest.mark.skip(reason="MIRAE_TEST_NEO4J_URI is not set")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
