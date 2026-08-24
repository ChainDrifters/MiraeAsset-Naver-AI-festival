from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, date, datetime
from pathlib import Path

from neo4j import Driver

from ..model import component, file_sha256

from .crosswalk import CROSSWALK_FIELDS
from .manifest import ManifestEntry, Phase, Status, append_entry, batch_id, is_loaded

MAX_UNWIND_BATCH = 500

CROSSWALK_SOURCE = "crosswalk"

UPSERT_HOLDINGS = """
MERGE (source:Resource:ExternalSource {uri: $sourceUri})
SET source.code = $source,
    source.updatedAt = datetime()
MERGE (artifact:Resource:ExternalArtifact {uri: $artifactUri})
SET artifact.sourceUrl = $sourceUrl,
    artifact.sha256 = $sha256,
    artifact.bytes = $bytes,
    artifact.retrievedAt = $retrievedAt
MERGE (artifact)-[:FROM_SOURCE]->(source)
MERGE (run:Resource:IngestionRun {uri: $runUri})
SET run.runId = $runId,
    run.source = $source,
    run.startedAt = $startedAt,
    run.finishedAt = $finishedAt,
    run.status = $status
MERGE (run)-[:LOADED_ARTIFACT]->(artifact)
WITH source, artifact, run
UNWIND $rows AS row
MERGE (fund:Resource:Entity:FinancialInstrument:Security:FundUnit {uri: row.fundUri})
SET fund.isin = row.fundIsin,
    fund.updatedAt = datetime()
MERGE (constituent:Resource:Entity:FinancialInstrument:Security {uri: row.constituentUri})
SET constituent.isin = row.constituentIsin,
    constituent.name = row.constituentName,
    constituent.updatedAt = datetime()
MERGE (snapshot:Resource:PortfolioSnapshot {uri: row.snapshotUri})
SET snapshot.asOf = row.asOf,
    snapshot.sourceDocumentId = row.sourceDocumentId,
    snapshot.publishedAt = row.publishedAt,
    snapshot.sourceUrl = row.sourceUrl,
    snapshot.evidenceBasis = row.evidenceBasis,
    snapshot.source = $source,
    snapshot.updatedAt = datetime()
MERGE (fund)-[:HAS_PORTFOLIO_SNAPSHOT]->(snapshot)
MERGE (snapshot)-[:DERIVED_FROM]->(artifact)
MERGE (position:Resource:HoldingPosition {uri: row.positionUri})
SET position.weight = row.weight,
    position.asOf = row.asOf,
    position.sourceQuantity = row.sourceQuantity,
    position.sourceCurrency = row.sourceCurrency,
    position.sourceMarketValue = row.sourceMarketValue,
    position.weightSource = row.weightSource,
    position.identifierMethod = row.identifierMethod,
    position.publishedAt = row.publishedAt,
    position.sourceDocumentId = row.sourceDocumentId,
    position.sourceUrl = row.sourceUrl,
    position.evidenceBasis = row.evidenceBasis,
    position.sourceRowId = row.sourceRowId,
    position.sourcePublishedName = row.constituentName,
    position.source = $source,
    position.updatedAt = datetime()
MERGE (snapshot)-[:HAS_POSITION]->(position)
MERGE (position)-[:OF_SECURITY]->(constituent)
MERGE (snapshot)-[:HAS_HOLDING]->(position)
MERGE (position)-[:HOLDS]->(constituent)
MERGE (position)-[:DERIVED_FROM]->(artifact)
MERGE (run)-[:UPSERTED]->(snapshot)
MERGE (run)-[:UPSERTED]->(position)
"""

UPSERT_CROSSWALK = """
MERGE (run:Resource:IngestionRun {uri: $runUri})
SET run.runId = $runId,
    run.source = $source,
    run.startedAt = $startedAt,
    run.finishedAt = $finishedAt,
    run.status = $status
WITH run
UNWIND $rows AS row
MERGE (entry:Resource:ExternalCrosswalkEntry {uri: row.entryUri})
SET entry.entityKind = row.entityKind,
    entry.localKeyType = row.localKeyType,
    entry.localKey = row.localKey,
    entry.localName = row.localName,
    entry.standardIdType = row.standardIdType,
    entry.standardId = row.standardId,
    entry.standardName = row.standardName,
    entry.sourceUrl = row.sourceUrl,
    entry.reviewedBy = row.reviewedBy,
    entry.reviewedAt = row.reviewedAt,
    entry.retrievedAt = $retrievedAt,
    entry.updatedAt = datetime()
MERGE (run)-[:UPSERTED]->(entry)
"""


class ExternalGraphLoader:
    def __init__(self, driver: Driver, database: str) -> None:
        self.driver: Driver = driver
        self.database: str = database

    def load_holdings_csv(
        self,
        path: Path,
        *,
        source: str,
        source_url: str,
        run_id: str,
        manifest_root: Path | None = None,
        window_date: date | None = None,
        batch_index: int = 0,
    ) -> dict[str, object]:
        selected_window = window_date or _single_window_date(path)
        selected_batch_id = batch_id(source, selected_window, batch_index)
        if manifest_root and is_loaded(source, selected_window, selected_batch_id, manifest_root):
            return {"skipped": True, "rows": 0, "batch_id": selected_batch_id}

        rows = list(_read_holdings_csv(path))
        result = self.load_holdings_rows(
            rows,
            source=source,
            source_url=source_url,
            artifact_sha256=file_sha256(path),
            artifact_bytes=path.stat().st_size,
            run_id=run_id,
            retrieved_at=datetime.now(UTC),
        )
        if manifest_root:
            now = datetime.now(UTC)
            _ = append_entry(
                ManifestEntry(
                    run_id=run_id,
                    source=source,
                    phase=Phase.LOADED,
                    window_date=selected_window,
                    batch_id=selected_batch_id,
                    status=Status.LOADED,
                    artifact_sha256=file_sha256(path),
                    started_at=now,
                    finished_at=now,
                ),
                manifest_root,
            )
        return {**result, "skipped": False, "batch_id": selected_batch_id}

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
        payload = [_holding_payload(row) for row in rows]
        _ensure_batch_cap(payload)
        started_at = datetime.now(UTC)
        finished_at = datetime.now(UTC)
        _ = self.driver.execute_query(
            UPSERT_HOLDINGS,
            sourceUri=f"urn:miraeasset:external:source:{component(source)}",
            source=source,
            artifactUri=f"urn:miraeasset:external:artifact:{artifact_sha256}",
            sourceUrl=source_url,
            sha256=artifact_sha256,
            bytes=artifact_bytes,
            retrievedAt=retrieved_at,
            runUri=f"urn:miraeasset:external:run:{component(run_id)}",
            runId=run_id,
            startedAt=started_at,
            finishedAt=finished_at,
            status=Status.LOADED.value,
            rows=payload,
            database_=self.database,
        )
        return {"rows": len(payload)}

    def upsert_crosswalk(
        self,
        rows: Iterable[Mapping[str, object]],
        *,
        run_id: str,
        retrieved_at: datetime,
    ) -> dict[str, int]:
        payload = [_crosswalk_payload(row) for row in rows]
        _ensure_batch_cap(payload)
        _ = self.driver.execute_query(
            UPSERT_CROSSWALK,
            runUri=f"urn:miraeasset:external:run:{component(run_id)}",
            runId=run_id,
            source=CROSSWALK_SOURCE,
            startedAt=datetime.now(UTC),
            finishedAt=datetime.now(UTC),
            status=Status.LOADED.value,
            retrievedAt=retrieved_at,
            rows=payload,
            database_=self.database,
        )
        return {"rows": len(payload)}

    def label_counts(self) -> dict[str, int]:
        labels = (
            "ExternalSource",
            "ExternalArtifact",
            "ExternalCrosswalkEntry",
            "IngestionRun",
            "PortfolioSnapshot",
            "HoldingPosition",
        )
        counts: dict[str, int] = {}
        for label in labels:
            records, _, _ = self.driver.execute_query(
                f"MATCH (node:`{label}`) RETURN count(node) AS count",
                database_=self.database,
            )
            counts[label] = int(records[0]["count"] if records else 0)
        return counts


def _read_holdings_csv(path: Path) -> Iterator[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            yield {key: value or "" for key, value in row.items() if key is not None}


def _holding_payload(row: Mapping[str, object]) -> dict[str, object]:
    fund = _required_text(row, "fund_isin").upper()
    constituent = _required_text(row, "constituent_isin").upper()
    as_of = date.fromisoformat(_required_text(row, "as_of"))
    weight = float(_required_text(row, "weight"))
    if not 0 <= weight <= 1:
        raise ValueError(f"Holding weight must be between 0 and 1: {weight}")
    source_document_id = _required_text(row, "source_document_id")
    published_text = _optional_text(row, "published_at")
    published_at = datetime.fromisoformat(published_text) if published_text is not None else None
    source_quantity = _optional_float(row, "source_quantity")
    source_market_value = _optional_float(row, "source_market_value")
    source_currency = _optional_text(row, "source_currency")
    source_url = _required_text(row, "source_url")
    identity = component(source_document_id)
    source_row_id = _required_text(row, "source_row_id")
    return {
        "fundUri": f"urn:miraeasset:security:isin:{component(fund)}",
        "fundIsin": fund,
        "constituentUri": f"urn:miraeasset:security:isin:{component(constituent)}",
        "constituentIsin": constituent,
        "constituentName": _required_text(row, "constituent_name"),
        "weight": weight,
        "asOf": as_of,
        "sourceQuantity": source_quantity,
        "sourceCurrency": source_currency,
        "sourceMarketValue": source_market_value,
        "weightSource": _required_text(row, "weight_source"),
        "identifierMethod": _required_text(row, "identifier_method"),
        "publishedAt": published_at,
        "sourceDocumentId": source_document_id,
        "sourceUrl": source_url,
        "evidenceBasis": _required_text(row, "evidence_basis"),
        "sourceRowId": source_row_id,
        "snapshotUri": f"urn:miraeasset:portfolio-snapshot:{fund}:{as_of.isoformat()}:{identity}",
        "positionUri": (
            f"urn:miraeasset:holding:{fund}:{constituent}:{as_of.isoformat()}:{identity}:"
            f"{component(source_row_id)}"
        ),
    }


def _crosswalk_payload(row: Mapping[str, object]) -> dict[str, object]:
    values = {field: str(row.get(field, "") or "").strip() for field in CROSSWALK_FIELDS}
    optional = ("local_name", "standard_name", "source_url", "reviewed_by", "reviewed_at")
    payload: dict[str, object] = {
        _camel_case(field): values[field] or None if field in optional else values[field]
        for field in CROSSWALK_FIELDS
    }
    payload["entryUri"] = (
        "urn:miraeasset:crosswalk:"
        f"{component(values['standard_id_type'])}:"
        f"{component(values['standard_id'])}:"
        f"{component(values['local_key_type'])}:"
        f"{component(values['local_key'])}"
    )
    return payload


def _camel_case(field: str) -> str:
    head, *tail = field.split("_")
    return head + "".join(part.capitalize() for part in tail)


def _required_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"Missing required holdings field: {key}")
    return text


def _optional_text(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_float(row: Mapping[str, object], key: str) -> float | None:
    value = row.get(key)
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"Holdings field must be numeric or null: {key}")
    return float(value)


def _single_window_date(path: Path) -> date:
    dates = {row["as_of"] for row in _read_holdings_csv(path) if row.get("as_of")}
    if len(dates) != 1:
        return date(2026, 7, 11)
    return date.fromisoformat(next(iter(dates)))


def _ensure_batch_cap(rows: list[dict[str, object]]) -> None:
    if len(rows) > MAX_UNWIND_BATCH:
        raise ValueError(f"External graph loads are capped at {MAX_UNWIND_BATCH} rows per UNWIND batch")
