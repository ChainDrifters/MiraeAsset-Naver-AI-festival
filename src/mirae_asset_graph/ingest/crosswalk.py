from __future__ import annotations

import csv
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

# Column order mirrors data/crosswalks/contest_entities.csv exactly.
CROSSWALK_FIELDS: tuple[str, ...] = (
    "entity_kind",
    "local_key_type",
    "local_key",
    "local_name",
    "standard_id_type",
    "standard_id",
    "standard_name",
    "source_url",
    "reviewed_by",
    "reviewed_at",
)

REQUIRED_FIELDS: tuple[str, ...] = (
    "entity_kind",
    "local_key_type",
    "local_key",
    "standard_id_type",
    "standard_id",
)

# Identifier-style key/id types safe to case-normalize; company names are never touched.
CASE_SAFE_LOCAL_KEY_TYPES: frozenset[str] = frozenset({"isin", "ticker"})
CASE_SAFE_STANDARD_ID_TYPES: frozenset[str] = frozenset({"isin", "ticker"})


@dataclass(frozen=True)
class CrosswalkRow:
    entity_kind: str
    local_key_type: str
    local_key: str
    local_name: str
    standard_id_type: str
    standard_id: str
    standard_name: str
    source_url: str
    reviewed_by: str
    reviewed_at: str


def load_crosswalk(path: Path) -> list[CrosswalkRow]:
    """Parse and strictly validate a crosswalk CSV.

    Raises ValueError naming the CSV row number and field for any invalid row;
    no row is ever skipped silently.
    """
    rows: list[CrosswalkRow] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [name.strip() if name else "" for name in reader.fieldnames or []]
        if tuple(fieldnames) != CROSSWALK_FIELDS:
            raise ValueError(
                f"Crosswalk header must be exactly {list(CROSSWALK_FIELDS)}, got {fieldnames}"
            )
        for raw in reader:
            row_number = reader.line_num
            values = {key: (value or "").strip() for key, value in raw.items() if key is not None}
            for field in CROSSWALK_FIELDS:
                if field in REQUIRED_FIELDS and not values.get(field, ""):
                    raise ValueError(f"Crosswalk row {row_number}: missing required field: {field}")
            rows.append(CrosswalkRow(**{field: values.get(field, "") for field in CROSSWALK_FIELDS}))
    return rows


def is_reviewed(row: CrosswalkRow) -> bool:
    return bool(row.reviewed_by.strip()) and bool(row.reviewed_at.strip())


def mapping_key(row: CrosswalkRow) -> tuple[str, str, str]:
    """Stable (entity_kind, local_key_type, local_key) key for identifier joins.

    Whitespace is stripped everywhere; identifier-style local keys are uppercased
    (ISIN targets, or isin/ticker local keys) while company names stay untouched.
    """
    entity_kind = row.entity_kind.strip().lower()
    local_key_type = row.local_key_type.strip().lower()
    local_key = row.local_key.strip()
    if row.standard_id_type.strip().lower() in CASE_SAFE_STANDARD_ID_TYPES or (
        local_key_type in CASE_SAFE_LOCAL_KEY_TYPES
    ):
        local_key = local_key.upper()
    return (entity_kind, local_key_type, local_key)


def standard_identifier(row: CrosswalkRow) -> str:
    standard_id_type = row.standard_id_type.strip().lower()
    standard_id = row.standard_id.strip()
    if standard_id_type in CASE_SAFE_STANDARD_ID_TYPES:
        standard_id = standard_id.upper()
    return f"{standard_id_type}:{standard_id}"


def group_by_standard_id(rows: list[CrosswalkRow]) -> dict[str, list[CrosswalkRow]]:
    groups: dict[str, list[CrosswalkRow]] = {}
    for row in rows:
        groups.setdefault(standard_identifier(row), []).append(row)
    return groups


def detect_name_only_merge(rows: list[CrosswalkRow]) -> list[str]:
    """Flag pairs of distinct entities that share a standard_name but no identifier.

    Guards the 'never merge by name alone' rule: two rows with the same
    standard_name are only acceptable when they also share a standard identifier.
    Returns sorted 'left|right' identifier-pair strings; an empty list passes.
    """
    by_name: dict[str, list[CrosswalkRow]] = {}
    for row in rows:
        name = row.standard_name.strip()
        if name:
            by_name.setdefault(name.casefold(), []).append(row)
    conflicts: list[str] = []
    for group in by_name.values():
        identifiers = sorted({standard_identifier(row) for row in group})
        for left, right in combinations(identifiers, 2):
            conflicts.append(f"{left}|{right}")
    return sorted(conflicts)


def to_payload(row: CrosswalkRow) -> dict[str, str]:
    """Flat mapping of exactly the CSV field names; feeds upsert_crosswalk."""
    return {field: getattr(row, field) for field in CROSSWALK_FIELDS}
