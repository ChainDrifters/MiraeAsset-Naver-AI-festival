"""Smoke-test the approved Neo4j proxy route without exposing credentials.

The proxy route policy is to keep UNWIND batches capped at 500 rows for later
loaders, with explicit statement timeouts and retry/backoff around batch writes.
"""
# pyright: reportUnknownMemberType=false

from __future__ import annotations

import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, LiteralString, TypeVar, cast

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase, Query, Record
from neo4j.exceptions import Neo4jError, ServiceUnavailable, SessionExpired

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URI = "neo4j+s://neo4j-2.yeongmin.net:443"
DEFAULT_USER = "neo4j"
CONNECT_TIMEOUT_SECONDS = 10.0
STATEMENT_TIMEOUT_SECONDS = 30.0

T = TypeVar("T")


def _timed(label: str, action: Callable[[], T]) -> T:
    started = time.perf_counter()
    result = action()
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"{label}: {elapsed_ms:.0f} ms")
    return result


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"error: {name} is required in .env or the process environment", file=sys.stderr)
        raise SystemExit(2)
    return value


def _query(text: LiteralString) -> Query:
    return Query(text, timeout=STATEMENT_TIMEOUT_SECONDS)


def _resource_count(record: Record) -> int:
    return cast(int, record["count"])


def _open_driver(uri: str, user: str, password: str) -> Driver:
    return GraphDatabase.driver(
        uri,
        auth=(user, password),
        connection_timeout=CONNECT_TIMEOUT_SECONDS,
    )


def main() -> int:
    _ = load_dotenv(PROJECT_ROOT / ".env")

    uri = os.getenv("NEO4J_URI", DEFAULT_URI)
    user = os.getenv("NEO4J_USER", DEFAULT_USER)
    password = _required_env("NEO4J_PASSWORD")
    probe_uri = "urn:miraeasset:ops:connect-probe:" + datetime.now(UTC).date().isoformat()

    try:
        with _open_driver(uri, user, password) as driver:
            _timed("verify connectivity", lambda: driver.verify_connectivity())

            with driver.session() as session:
                resource_count = _timed(
                    "read probe",
                    lambda: session.run(
                        _query("MATCH (resource:Resource) RETURN count(resource) AS count")
                    ).single(strict=True),
                )
                print(f"read probe result: Resource count={_resource_count(resource_count)}")

                summary = _timed(
                    "write probe",
                    lambda: session.run(
                        _query(
                            """
                            MERGE (p:Resource:OpsConnectProbe {uri: $uri})
                            WITH p DETACH DELETE p
                            RETURN 1 AS ok
                            """
                        ),
                        uri=probe_uri,
                    ).consume(),
                )
                _ = summary
    except (Neo4jError, ServiceUnavailable, SessionExpired, OSError) as exc:
        print(f"error: Neo4j connectivity/query probe failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
