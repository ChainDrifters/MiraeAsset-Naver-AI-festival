"""SEC Form N-PORT adapter for the Phase 3 external-evidence pipeline.

Implements decision 3 of docs/external-sources-decision.md (2026-08-19): the
public SEC Form N-PORT data sets are a GO source. The adapter honors the
recorded fair-access constraints — a real identifying User-Agent with contact
information and no more than 10 requests per second by default — fetches raw
XML over plain ``urllib.request`` (stdlib only), and normalizes positions into
HoldingsRecord JSONL with a deterministic per-position quarantine path.

Every document is checked against the target snapshot date before any position
is read, reported pctVal values are never renormalized, and a weight is only
derived from valUSD when the complete document total can be computed from
nonnegative values. Identity resolution goes exclusively through the reviewed
IdentifierResolver; names are provenance and never a merge key.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .base import Adapter
from .records import HoldingsRecord, write_jsonl
from .resolver import IdentifierResolver

NPORT_SOURCE = "sec_nport"

# Fair-access defaults recorded in docs/external-sources-decision.md, decision 3.
DEFAULT_MAX_REQUESTS_PER_SECOND = 10.0
DEFAULT_RETRY_COUNT = 3

_RETRIABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_REQUEST_TIMEOUT_SECONDS = 30.0
_BACKOFF_BASE_SECONDS = 1.0
_BACKOFF_MAX_SECONDS = 30.0

_REPORT_DATE_TAGS: tuple[str, ...] = ("reportDate", "periodOfReport")

_CUSIP = "cusip"
_SOURCE_PUBLISHED = "source_published"
_DERIVED_FROM_VALUE = "derived_from_value"


@dataclass(frozen=True)
class NPortTarget:
    """One N-PORT filing to fetch: identity plus temporal metadata."""

    accession: str
    source_url: str
    fund_isin: str
    as_of: date
    published_at: datetime

    def __post_init__(self) -> None:
        for field_name in ("accession", "source_url", "fund_isin"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"NPortTarget: {field_name} must be a nonempty string")
        if "/" in self.accession or "\\" in self.accession or self.accession.strip().startswith("."):
            raise ValueError(
                f"NPortTarget: accession becomes a raw filename and must not contain path separators: {self.accession!r}"
            )
        if isinstance(self.as_of, datetime) or not isinstance(self.as_of, date):
            raise ValueError("NPortTarget: as_of must be a date, not a datetime")
        if not isinstance(self.published_at, datetime):
            raise ValueError("NPortTarget: published_at must be a datetime")


@dataclass(frozen=True)
class QuarantineEntry:
    """One rejected position, preserved with its reason and source identifier."""

    source_document_id: str
    constituent_name: str | None
    reason: str
    source_identifier_type: str | None
    source_identifier_value: str | None

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable mapping with the canonical field keys, in order."""
        return {
            "source_document_id": self.source_document_id,
            "constituent_name": self.constituent_name,
            "reason": self.reason,
            "source_identifier_type": self.source_identifier_type,
            "source_identifier_value": self.source_identifier_value,
        }


def _validated_user_agent(value: object) -> str:
    """Require a User-Agent that identifies the caller, per SEC fair access.

    Accepts a nonempty string containing a contact email address (``@``) or a
    contact URL (``http://`` or ``https://``). Generic browser or library
    strings are rejected because they do not identify the requester.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "NPortAdapter: user_agent must be a nonempty string that identifies the caller"
        )
    text = value.strip()
    lowered = text.lower()
    if "@" not in text and "http://" not in lowered and "https://" not in lowered:
        raise ValueError(
            "NPortAdapter: user_agent must contain a contact email address or URL "
            f"for SEC fair-access identification; got: {value!r}"
        )
    return text


def _local_name(tag: str) -> str:
    """Namespace-insensitive local tag name: strips any {namespace} prefix."""
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ET.Element, local_tag: str) -> str | None:
    """Text of the first direct child with the given local tag, or None."""
    for child in element:
        if _local_name(child.tag) == local_tag:
            text = (child.text or "").strip()
            return text or None
    return None


def _atomic_write(path: Path, payload: bytes) -> None:
    """Write payload to a temp file in path's directory, then replace path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _write_quarantine_jsonl(entries: Iterable[QuarantineEntry], path: Path) -> int:
    """Overwrite path with one deterministic quarantine JSON object per line."""
    written = 0
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for entry in entries:
            handle.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            written += 1
    return written


@dataclass(frozen=True)
class _Position:
    """One parsed invstOrSec position, preserving raw texts for error messages.

    A numeric field is absent when its ``*_raw`` text is None, present but
    invalid when the raw text is set while the parsed value is None.
    """

    index: int
    name: str | None
    isin: str | None
    cusip: str | None
    currency: str | None
    balance: float | None
    balance_raw: str | None
    pct_val: float | None
    pct_val_raw: str | None
    val_usd: float | None
    val_usd_raw: str | None


def _parse_number(raw: str | None) -> tuple[str | None, float | None]:
    """Parse an optional numeric text into (raw, value); value None means invalid or absent."""
    if raw is None:
        return None, None
    try:
        return raw, float(raw)
    except ValueError:
        return raw, None


def _parse_position(element: ET.Element, index: int) -> _Position:
    balance_raw, balance = _parse_number(_child_text(element, "balance"))
    pct_val_raw, pct_val = _parse_number(_child_text(element, "pctVal"))
    val_usd_raw, val_usd = _parse_number(_child_text(element, "valUSD"))
    return _Position(
        index=index,
        name=_child_text(element, "name"),
        isin=_child_text(element, "isin"),
        cusip=_child_text(element, "cusip"),
        currency=_child_text(element, "curCd"),
        balance=balance,
        balance_raw=balance_raw,
        pct_val=pct_val,
        pct_val_raw=pct_val_raw,
        val_usd=val_usd,
        val_usd_raw=val_usd_raw,
    )


class NPortAdapter(Adapter[NPortTarget, tuple[Path, Path, int, int]]):
    """Fetch and normalize public SEC Form N-PORT filings. Never touches the graph."""

    source = NPORT_SOURCE

    def __init__(
        self,
        *,
        targets: Iterable[NPortTarget],
        raw_root: Path,
        resolver: IdentifierResolver,
        user_agent: str,
        max_requests_per_second: float = DEFAULT_MAX_REQUESTS_PER_SECOND,
        retry_count: int = DEFAULT_RETRY_COUNT,
        window_start: date | None = None,
        window_end: date | None = None,
        cutoff: datetime | None = None,
    ) -> None:
        self._targets: tuple[NPortTarget, ...] = tuple(targets)
        self.raw_root = Path(raw_root)
        self._resolver = resolver
        self.user_agent = _validated_user_agent(user_agent)
        if isinstance(max_requests_per_second, bool) or not isinstance(max_requests_per_second, (int, float)):
            raise ValueError(
                f"NPortAdapter: max_requests_per_second must be a positive number: {max_requests_per_second!r}"
            )
        if not float(max_requests_per_second) > 0:
            raise ValueError(
                f"NPortAdapter: max_requests_per_second must be greater than zero: {max_requests_per_second!r}"
            )
        if isinstance(retry_count, bool) or not isinstance(retry_count, int) or retry_count < 0:
            raise ValueError(f"NPortAdapter: retry_count must be a nonnegative integer: {retry_count!r}")
        self.max_requests_per_second = float(max_requests_per_second)
        self.retry_count = retry_count
        self._min_request_interval = 1.0 / self.max_requests_per_second
        self._next_request_at = 0.0
        self.window_start = window_start
        self.window_end = window_end
        self.cutoff = cutoff

    def discover(
        self,
        start: date | None = None,
        end: date | None = None,
        cutoff: datetime | None = None,
    ) -> list[NPortTarget]:
        """Targets with as_of inside [start, end] and published_at <= cutoff.

        Arguments fall back to the window configured on the adapter; a bound
        that is None everywhere is not applied. The result is sorted by
        (as_of, accession) for deterministic batching.
        """
        effective_start = start if start is not None else self.window_start
        effective_end = end if end is not None else self.window_end
        effective_cutoff = cutoff if cutoff is not None else self.cutoff
        selected = [
            target
            for target in self._targets
            if (effective_start is None or effective_start <= target.as_of)
            and (effective_end is None or target.as_of <= effective_end)
            and (effective_cutoff is None or target.published_at <= effective_cutoff)
        ]
        return sorted(selected, key=lambda target: (target.as_of, target.accession))

    def fetch(self, target: NPortTarget) -> Path:
        """GET target.source_url and store it atomically at the deterministic raw path.

        An existing nonempty raw file is returned without any network call.
        Requests are rate limited to max_requests_per_second and retried on
        429/500/502/503/504 with bounded exponential backoff.
        """
        raw_path = self.raw_root / NPORT_SOURCE / f"{target.accession}.xml"
        if raw_path.is_file() and raw_path.stat().st_size > 0:
            return raw_path
        request = urllib.request.Request(
            target.source_url,
            headers={"User-Agent": self.user_agent, "Accept": "application/xml"},
            method="GET",
        )
        for attempt in range(self.retry_count + 1):
            self._respect_rate_limit()
            try:
                with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
                    payload = response.read()
                _atomic_write(raw_path, payload)
                return raw_path
            except urllib.error.HTTPError as error:
                if error.code in _RETRIABLE_STATUS_CODES and attempt < self.retry_count:
                    backoff = min(_BACKOFF_BASE_SECONDS * (2**attempt), _BACKOFF_MAX_SECONDS)
                    time.sleep(backoff)
                    continue
                raise
        raise AssertionError("unreachable: retry loop always returns or raises")

    def _respect_rate_limit(self) -> None:
        """Sleep so that requests never exceed max_requests_per_second."""
        now = time.monotonic()
        wait = self._next_request_at - now
        if wait > 0:
            time.sleep(wait)
            now = self._next_request_at
        self._next_request_at = max(now, self._next_request_at) + self._min_request_interval

    def normalize(
        self,
        target: NPortTarget,
        raw_path: Path,
        output_dir: Path,
    ) -> tuple[Path, Path, int, int]:
        """Normalize one raw N-PORT XML into holdings JSONL plus quarantine JSONL.

        Returns (records_path, quarantine_path, records_count,
        quarantine_count). Both files are deterministically overwritten under
        output_dir/sec_nport/. The document is rejected with ValueError when
        its stated report date does not match target.as_of.
        """
        try:
            root = ET.parse(raw_path).getroot()
        except ET.ParseError as error:
            raise ValueError(f"N-PORT document {target.accession} is not well-formed XML: {error}") from error
        report_date = _find_report_date(root)
        if report_date is None:
            raise ValueError(
                "N-PORT document "
                f"{target.accession} has no formData/genInfo report date "
                f"(looked for {_REPORT_DATE_TAGS})"
            )
        if report_date != target.as_of:
            raise ValueError(
                f"N-PORT document {target.accession} reports holdings as of "
                f"{report_date.isoformat()}, which does not match the target as_of "
                f"{target.as_of.isoformat()}; rejecting the document"
            )

        positions = [
            _parse_position(element, index)
            for index, element in enumerate(_iter_positions(root), start=1)
        ]
        total_val_usd = _document_total_val_usd(positions)

        records: list[HoldingsRecord] = []
        quarantined: list[QuarantineEntry] = []
        for position in positions:
            outcome = self._normalize_position(target, position, total_val_usd)
            if isinstance(outcome, QuarantineEntry):
                quarantined.append(outcome)
            else:
                records.append(outcome)

        records_path = Path(output_dir) / NPORT_SOURCE / f"{target.accession}.jsonl"
        records_path.parent.mkdir(parents=True, exist_ok=True)
        _ = write_jsonl(records, records_path)
        quarantine_path = records_path.with_name(f"{target.accession}.quarantine.jsonl")
        _ = _write_quarantine_jsonl(quarantined, quarantine_path)
        return records_path, quarantine_path, len(records), len(quarantined)

    def _normalize_position(
        self,
        target: NPortTarget,
        position: _Position,
        total_val_usd: float | None,
    ) -> HoldingsRecord | QuarantineEntry:
        """Resolve, validate, and weigh one position; quarantine instead of crashing."""
        resolution = self._resolver.resolve(
            source_isin=position.isin,
            local_key_type=_CUSIP if position.cusip else None,
            local_key=position.cusip,
        )
        if resolution.isin is None:
            return self._quarantine(target, position, f"constituent identity unresolved: {resolution.reason}")
        if not position.name:
            return self._quarantine(target, position, "constituent name is missing")
        for label, raw, value in (
            ("balance", position.balance_raw, position.balance),
            ("pctVal", position.pct_val_raw, position.pct_val),
            ("valUSD", position.val_usd_raw, position.val_usd),
        ):
            if raw is not None and value is None:
                return self._quarantine(target, position, f"{label} is not a valid number: {raw!r}")
        if position.balance is not None and position.balance < 0:
            return self._quarantine(target, position, f"balance is negative: {position.balance}")

        if position.pct_val is not None:
            weight = position.pct_val / 100.0
            weight_source = _SOURCE_PUBLISHED
            if weight < 0:
                return self._quarantine(
                    target, position, f"weight {weight} from pctVal {position.pct_val} is negative"
                )
            if weight > 1:
                return self._quarantine(
                    target, position, f"weight {weight} from pctVal {position.pct_val} exceeds 1.0"
                )
        else:
            if position.val_usd is None:
                return self._quarantine(
                    target, position, "pctVal and valUSD are both missing; weight cannot be determined"
                )
            if total_val_usd is None:
                return self._quarantine(
                    target,
                    position,
                    "pctVal is missing and the document total valUSD cannot be derived "
                    "from all nonnegative values in this document",
                )
            if total_val_usd <= 0:
                return self._quarantine(
                    target, position, f"document total valUSD is not positive: {total_val_usd}"
                )
            weight = position.val_usd / total_val_usd
            weight_source = _DERIVED_FROM_VALUE

        record = HoldingsRecord.create(
            fund_isin=target.fund_isin,
            constituent_isin=resolution.isin,
            constituent_name=position.name,
            weight=weight,
            as_of=target.as_of,
            weight_source=weight_source,
            identifier_method=resolution.method,
            source_document_id=target.accession,
            source_url=target.source_url,
            source_quantity=position.balance,
            source_currency=position.currency,
            source_market_value=position.val_usd,
            published_at=target.published_at,
        )
        return record

    def _quarantine(self, target: NPortTarget, position: _Position, reason: str) -> QuarantineEntry:
        identifier_type = "isin" if position.isin else (_CUSIP if position.cusip else None)
        identifier_value = position.isin if position.isin else position.cusip
        return QuarantineEntry(
            source_document_id=target.accession,
            constituent_name=position.name,
            reason=f"position {position.index}: {reason}",
            source_identifier_type=identifier_type,
            source_identifier_value=identifier_value,
        )


def _find_report_date(root: ET.Element) -> date | None:
    """First reportDate or periodOfReport anywhere in the document, by local tag."""
    for element in root.iter():
        if _local_name(element.tag) not in _REPORT_DATE_TAGS:
            continue
        text = (element.text or "").strip()
        if not text:
            continue
        try:
            return date.fromisoformat(text)
        except ValueError as error:
            raise ValueError(f"N-PORT report date is not an ISO 8601 date: {text!r}") from error
    return None


def _iter_positions(root: ET.Element) -> Iterable[ET.Element]:
    """Every invstOrSec element in the document, in document order."""
    for element in root.iter():
        if _local_name(element.tag) == "invstOrSec":
            yield element


def _document_total_val_usd(positions: list[_Position]) -> float | None:
    """Total valUSD when every position has a valid nonnegative valUSD; else None.

    A weight may only be derived from a fully known, nonnegative document
    total; a single missing, invalid, or negative valUSD makes the derivation
    inadmissible for the whole document.
    """
    total = 0.0
    for position in positions:
        if position.val_usd is None or position.val_usd < 0:
            return None
        total += position.val_usd
    return total
