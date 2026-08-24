"""Normalized holdings records shared by every Phase 3 source adapter.

The field contract is defined by the adapter normalized minimum fields table
in docs/external-sources-decision.md: missing source values stay null and are
never imputed; constituent_name is verbatim provenance, never a merge key.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from datetime import date, datetime
from pathlib import Path

from ..model import is_isin

# Domains fixed by docs/external-sources-decision.md.
WEIGHT_SOURCES: tuple[str, ...] = ("source_published", "derived_from_value")
IDENTIFIER_METHODS: tuple[str, ...] = ("source_isin", "crosswalk", "unresolved")
EVIDENCE_BASES: tuple[str, ...] = ("manager_published", "regulatory_filing")

@dataclass(frozen=True)
class HoldingsRecord:
    """One normalized fund-holding position from a single source document."""

    fund_isin: str
    constituent_isin: str
    constituent_name: str
    weight: float
    as_of: date
    source_quantity: float | None
    source_currency: str | None
    source_market_value: float | None
    weight_source: str
    identifier_method: str
    published_at: datetime | None
    source_document_id: str
    source_url: str
    evidence_basis: str
    source_row_id: str

    def __post_init__(self) -> None:
        for field_name in (
            "fund_isin",
            "constituent_isin",
            "constituent_name",
            "source_document_id",
            "source_url",
            "source_row_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"HoldingsRecord: {field_name} must be a nonempty string")
        if not is_isin(self.fund_isin):
            raise ValueError(f"HoldingsRecord: fund_isin is not a valid ISIN: {self.fund_isin!r}")
        if not is_isin(self.constituent_isin):
            raise ValueError(
                f"HoldingsRecord: constituent_isin is not a valid ISIN: {self.constituent_isin!r}"
            )
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)):
            raise ValueError(f"HoldingsRecord: weight must be a number: {self.weight!r}")
        if not math.isfinite(self.weight):
            raise ValueError(f"HoldingsRecord: weight must be finite: {self.weight!r}")
        if not 0 <= self.weight <= 1:
            raise ValueError(f"HoldingsRecord: weight must be between 0 and 1: {self.weight}")
        if isinstance(self.as_of, datetime) or not isinstance(self.as_of, date):
            raise ValueError("HoldingsRecord: as_of must be a date, not a datetime")
        for field_name in ("source_quantity", "source_market_value"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(
                    f"HoldingsRecord: {field_name} must be a finite number or None: {value!r}"
                )
        if self.source_currency is not None and (
            not isinstance(self.source_currency, str) or not self.source_currency.strip()
        ):
            raise ValueError("HoldingsRecord: source_currency must be a nonempty string or None")
        if self.weight_source not in WEIGHT_SOURCES:
            raise ValueError(
                f"HoldingsRecord: weight_source must be one of {list(WEIGHT_SOURCES)}: "
                f"{self.weight_source!r}"
            )
        if self.identifier_method not in IDENTIFIER_METHODS:
            raise ValueError(
                f"HoldingsRecord: identifier_method must be one of {list(IDENTIFIER_METHODS)}: "
                f"{self.identifier_method!r}"
            )
        if self.published_at is not None and not isinstance(self.published_at, datetime):
            raise ValueError("HoldingsRecord: published_at must be a datetime or None")
        if self.evidence_basis not in EVIDENCE_BASES:
            raise ValueError(f"HoldingsRecord: evidence_basis must be one of {list(EVIDENCE_BASES)}")

    @classmethod
    def create(
        cls,
        *,
        fund_isin: str,
        constituent_isin: str,
        constituent_name: str,
        weight: float | str,
        as_of: date | str,
        weight_source: str,
        identifier_method: str,
        source_document_id: str,
        source_url: str,
        evidence_basis: str,
        source_row_id: str,
        source_quantity: float | str | None = None,
        source_currency: str | None = None,
        source_market_value: float | str | None = None,
        published_at: datetime | str | None = None,
    ) -> HoldingsRecord:
        """Normalize raw adapter values, then build a validated record.

        The dataclass is frozen, so case and whitespace normalization happens
        here rather than by mutation in __post_init__: ISINs and the currency
        are uppercased, text is trimmed, and ISO 8601 date/datetime strings
        are parsed. Optional source values are preserved as published (or
        None); they are never imputed.
        """
        normalized_currency = _optional_text(source_currency, "source_currency")
        if normalized_currency is not None:
            normalized_currency = normalized_currency.strip().upper()
        return cls(
            fund_isin=_required_text(fund_isin, "fund_isin").strip().upper(),
            constituent_isin=_required_text(constituent_isin, "constituent_isin").strip().upper(),
            constituent_name=_required_text(constituent_name, "constituent_name").strip(),
            weight=_as_weight(weight),
            as_of=_as_date(as_of),
            source_quantity=_optional_number(source_quantity, "source_quantity"),
            source_currency=normalized_currency,
            source_market_value=_optional_number(source_market_value, "source_market_value"),
            weight_source=_required_text(weight_source, "weight_source").strip(),
            identifier_method=_required_text(identifier_method, "identifier_method").strip(),
            published_at=_as_datetime(published_at),
            source_document_id=_required_text(source_document_id, "source_document_id").strip(),
            source_url=_required_text(source_url, "source_url").strip(),
            evidence_basis=_required_text(evidence_basis, "evidence_basis").strip(),
            source_row_id=_required_text(source_row_id, "source_row_id").strip(),
        )

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable mapping with the canonical field keys, in order."""
        return {
            "fund_isin": self.fund_isin,
            "constituent_isin": self.constituent_isin,
            "constituent_name": self.constituent_name,
            "weight": self.weight,
            "as_of": self.as_of.isoformat(),
            "source_quantity": self.source_quantity,
            "source_currency": self.source_currency,
            "source_market_value": self.source_market_value,
            "weight_source": self.weight_source,
            "identifier_method": self.identifier_method,
            "published_at": self.published_at.isoformat() if self.published_at is not None else None,
            "source_document_id": self.source_document_id,
            "source_url": self.source_url,
            "evidence_basis": self.evidence_basis,
            "source_row_id": self.source_row_id,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> HoldingsRecord:
        """Strict parse: the keys must be exactly the canonical fields."""
        unknown = sorted(set(data) - set(CANONICAL_FIELDS))
        if unknown:
            raise ValueError(f"HoldingsRecord: unknown field(s): {', '.join(unknown)}")
        missing = sorted(set(CANONICAL_FIELDS) - set(data))
        if missing:
            raise ValueError(f"HoldingsRecord: missing field(s): {', '.join(missing)}")
        return cls.create(
            fund_isin=_required_text(data["fund_isin"], "fund_isin"),
            constituent_isin=_required_text(data["constituent_isin"], "constituent_isin"),
            constituent_name=_required_text(data["constituent_name"], "constituent_name"),
            weight=_as_weight(data["weight"]),
            as_of=_as_date(data["as_of"]),
            source_quantity=_optional_number(data["source_quantity"], "source_quantity"),
            source_currency=_optional_text(data["source_currency"], "source_currency"),
            source_market_value=_optional_number(data["source_market_value"], "source_market_value"),
            weight_source=_required_text(data["weight_source"], "weight_source"),
            identifier_method=_required_text(data["identifier_method"], "identifier_method"),
            published_at=_as_datetime(data["published_at"]),
            source_document_id=_required_text(data["source_document_id"], "source_document_id"),
            source_url=_required_text(data["source_url"], "source_url"),
            evidence_basis=_required_text(data["evidence_basis"], "evidence_basis"),
            source_row_id=_required_text(data["source_row_id"], "source_row_id"),
        )

    def to_loader_payload(self) -> dict[str, object]:
        """Preserve every canonical evidence field for graph loading."""
        return self.to_dict()


CANONICAL_FIELDS: tuple[str, ...] = tuple(field.name for field in fields(HoldingsRecord))


def write_jsonl(records: Iterable[HoldingsRecord], path: Path) -> int:
    """Overwrite path with one deterministic JSON record per line.

    A normalized artifact must reflect exactly the records passed in, so the
    file is replaced rather than appended to. Every line ends with a newline,
    including the last.
    """
    written = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            written += 1
    return written


def serialize_jsonl(records: Iterable[HoldingsRecord]) -> tuple[bytes, int]:
    selected = tuple(records)
    text = "".join(
        json.dumps(record.to_dict(), ensure_ascii=False) + "\n" for record in selected
    )
    return text.encode("utf-8"), len(selected)


def read_jsonl(path: Path) -> list[HoldingsRecord]:
    """Strict JSONL read; every nonblank line must parse via from_dict."""
    return read_jsonl_bytes(path.read_bytes())


def read_jsonl_bytes(payload: bytes) -> list[HoldingsRecord]:
    """Parse the exact verified normalized bytes without reopening a path."""
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Holdings JSONL is not UTF-8") from error
    records: list[HoldingsRecord] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"Holdings JSONL line {line_number}: invalid JSON: {error.msg}") from error
        if not isinstance(data, dict):
            raise ValueError(f"Holdings JSONL line {line_number}: expected a JSON object")
        try:
            records.append(HoldingsRecord.from_dict(data))
        except ValueError as error:
            raise ValueError(f"Holdings JSONL line {line_number}: {error}") from error
    return records


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"HoldingsRecord: {field_name} must be a nonempty string")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"HoldingsRecord: {field_name} must be a nonempty string or None")
    return value


def _optional_number(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"HoldingsRecord: {field_name} must be a number or None: {value!r}")
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value.strip())
        except ValueError as error:
            raise ValueError(f"HoldingsRecord: {field_name} must be a number or None: {value!r}") from error
    else:
        raise ValueError(f"HoldingsRecord: {field_name} must be a number or None: {value!r}")
    if not math.isfinite(result):
        raise ValueError(f"HoldingsRecord: {field_name} must be finite: {value!r}")
    return result


def _as_weight(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"HoldingsRecord: weight must be a number: {value!r}")
    try:
        result = float(value) if isinstance(value, str) else float(value)
    except ValueError as error:
        raise ValueError(f"HoldingsRecord: weight must be a number: {value!r}") from error
    if not math.isfinite(result):
        raise ValueError(f"HoldingsRecord: weight must be finite: {value!r}")
    if not 0 <= result <= 1:
        raise ValueError(f"HoldingsRecord: weight must be between 0 and 1: {result}")
    return result


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"HoldingsRecord: as_of must be an ISO 8601 date, not a datetime: {value!r}")
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as error:
            raise ValueError(f"HoldingsRecord: as_of must be an ISO 8601 date: {value!r}") from error
    raise ValueError(f"HoldingsRecord: as_of must be an ISO 8601 date: {value!r}")


def _as_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip())
        except ValueError as error:
            raise ValueError(
                f"HoldingsRecord: published_at must be an ISO 8601 datetime: {value!r}"
            ) from error
    raise ValueError(f"HoldingsRecord: published_at must be an ISO 8601 datetime or None: {value!r}")
