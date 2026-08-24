"""Strict, credential-independent target configuration and planning."""

from __future__ import annotations

import json
import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TypeAlias, cast
from urllib.parse import urlsplit

from ..model import is_isin
from .basket_kr import MANAGER_BASKET_SOURCE, ManagerBasketTarget
from .nport import NPORT_SOURCE, NPortTarget
from .source_policy import normalize_reviewed_hosts, validate_source_url

Target: TypeAlias = NPortTarget | ManagerBasketTarget

_SOURCES = frozenset({NPORT_SOURCE, MANAGER_BASKET_SOURCE})
POLICY_START = date(2026, 1, 11)
POLICY_END = date(2026, 7, 11)
POLICY_CUTOFF = datetime(2026, 7, 11, 23, 59, 59, tzinfo=UTC)
_BASE_TOP_LEVEL_KEYS = frozenset({"source", "targets"})
_NPORT_KEYS = frozenset({"accession", "source_url", "fund_isin", "as_of", "published_at"})
_MANAGER_KEYS = frozenset(
    {
        "manager_code",
        "fund_code",
        "fund_isin",
        "source_url",
        "as_of",
        "published_at",
        "format_hint",
    }
)


@dataclass(frozen=True)
class TargetConfig:
    """One homogeneous source and its immutable target list."""

    source: str
    targets: tuple[Target, ...]
    allowed_hosts: tuple[str, ...]
    config_digest: str

    def summary(self, targets: Iterable[Target] | None = None) -> dict[str, object]:
        """Return deterministic, JSON-serializable target/date counts and bounds."""
        return summarize_targets(self.targets if targets is None else targets, source=self.source)


def load_target_config(path: Path | str) -> TargetConfig:
    """Load a strict ``{source, targets}`` JSON configuration.

    Unknown or missing keys, duplicate JSON member names, malformed values,
    mixed source rows, and duplicate source-document identities are rejected.
    """
    config_path = Path(path)
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except json.JSONDecodeError as error:
        raise ValueError(f"Target config is not valid JSON: {error.msg}") from error
    if not isinstance(loaded, dict):
        raise ValueError("Target config top level must be an object")
    values = cast(dict[str, object], loaded)
    allowed_top_keys = _BASE_TOP_LEVEL_KEYS | {"allowed_hosts"}
    if set(values) - allowed_top_keys or not _BASE_TOP_LEVEL_KEYS <= set(values):
        _require_exact_keys(values, allowed_top_keys, "Target config")

    source = values["source"]
    if isinstance(source, str) and "krx" in source.lower():
        raise ValueError("KRX automated acquisition is blocked by source policy")
    if not isinstance(source, str) or source not in _SOURCES:
        raise ValueError(f"Target config source must be one of {sorted(_SOURCES)}")
    raw_targets = values["targets"]
    if not isinstance(raw_targets, list):
        raise ValueError("Target config targets must be an array")

    raw_allowed_hosts = values.get("allowed_hosts", [])
    if not isinstance(raw_allowed_hosts, list) or not all(
        isinstance(host, str) for host in raw_allowed_hosts
    ):
        raise ValueError("Target config allowed_hosts must be an array of strings")
    allowed_hosts = (
        normalize_reviewed_hosts(raw_allowed_hosts)
        if source == MANAGER_BASKET_SOURCE
        else tuple()
    )
    if source == NPORT_SOURCE and raw_allowed_hosts:
        raise ValueError("SEC target config cannot override the official SEC host policy")

    targets: list[Target] = []
    identities: set[str] = set()
    for index, raw_target in enumerate(raw_targets):
        label = f"Target config targets[{index}]"
        if not isinstance(raw_target, dict):
            raise ValueError(f"{label} must be an object")
        row = cast(dict[str, object], raw_target)
        target = _parse_target(
            source,
            row,
            label,
            allowed_hosts=allowed_hosts,
            allow_test_urls=_is_test_fixture(config_path),
        )
        identity = target_document_id(target)
        if identity in identities:
            raise ValueError(f"Duplicate source-document identity: {identity}")
        identities.add(identity)
        targets.append(target)

    config_digest = hashlib.sha256(
        json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return TargetConfig(
        source=source,
        targets=tuple(targets),
        allowed_hosts=allowed_hosts,
        config_digest=config_digest,
    )


def target_document_id(target: Target) -> str:
    """Return the adapter-compatible source-document identity for a target."""
    if isinstance(target, NPortTarget):
        return target.accession
    if isinstance(target, ManagerBasketTarget):
        return f"{target.manager_code}:{target.fund_code}:{target.as_of.isoformat()}"
    raise TypeError(f"Unsupported target type: {type(target).__name__}")


def target_window(
    targets: Iterable[Target],
    start: date | None = None,
    end: date | None = None,
    cutoff: datetime | None = None,
) -> tuple[Target, ...]:
    """Filter targets to inclusive dates and a publication cutoff, then sort."""
    if start is not None and (isinstance(start, datetime) or not isinstance(start, date)):
        raise ValueError("start must be a date")
    if end is not None and (isinstance(end, datetime) or not isinstance(end, date)):
        raise ValueError("end must be a date")
    if start is not None and end is not None and start > end:
        raise ValueError("start must be on or before end")
    if cutoff is not None and not isinstance(cutoff, datetime):
        raise ValueError("cutoff must be a datetime")
    if start is not None and start < POLICY_START:
        raise ValueError("start cannot widen the production policy window")
    if end is not None and end > POLICY_END:
        raise ValueError("end cannot widen the production policy window")
    if cutoff is not None:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("cutoff must be timezone-aware")
        if cutoff > POLICY_CUTOFF:
            raise ValueError("cutoff cannot widen the production policy window")

    selected: list[Target] = []
    for target in targets:
        if start is not None and target.as_of < start:
            continue
        if end is not None and target.as_of > end:
            continue
        if cutoff is not None:
            try:
                published = target.published_at <= cutoff
            except TypeError as error:
                raise ValueError(
                    "cutoff and target published_at must both include a timezone or both omit it"
                ) from error
            if not published:
                continue
        selected.append(target)
    return tuple(sorted(selected, key=lambda target: (target.as_of, target_document_id(target))))


def summarize_targets(targets: Iterable[Target], *, source: str | None = None) -> dict[str, object]:
    """Return counts and min/max as-of dates suitable for direct JSON output."""
    selected = tuple(targets)
    inferred_sources = {_target_source(target) for target in selected}
    if source is None:
        if len(inferred_sources) > 1:
            raise ValueError("Cannot summarize mixed target sources")
        source = next(iter(inferred_sources), None)
    elif source not in _SOURCES:
        raise ValueError(f"Target source must be one of {sorted(_SOURCES)}")
    if inferred_sources and inferred_sources != {source}:
        raise ValueError("Target rows do not match the declared source")

    dates = sorted({target.as_of for target in selected})
    return {
        "as_of_date_count": len(dates),
        "document_count": len({target_document_id(target) for target in selected}),
        "max_as_of": dates[-1].isoformat() if dates else None,
        "min_as_of": dates[0].isoformat() if dates else None,
        "source": source,
        "target_count": len(selected),
    }


def parse_iso_date(value: object, label: str) -> date:
    """Parse a canonical ISO calendar date, rejecting datetimes and basic form."""
    text = _required_string(value, label)
    try:
        parsed = date.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO date (YYYY-MM-DD)") from error
    if parsed.isoformat() != text:
        raise ValueError(f"{label} must be an ISO date (YYYY-MM-DD)")
    return parsed


def parse_iso_datetime(value: object, label: str) -> datetime:
    """Parse an ISO datetime, accepting the standard ``Z`` UTC suffix."""
    text = _required_string(value, label)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ValueError(f"{label} must be an ISO datetime") from error
    if "T" not in text and " " not in text:
        raise ValueError(f"{label} must be an ISO datetime")
    return parsed


def _parse_target(
    source: str,
    row: dict[str, object],
    label: str,
    *,
    allowed_hosts: tuple[str, ...],
    allow_test_urls: bool,
) -> Target:
    keys = _NPORT_KEYS if source == NPORT_SOURCE else _MANAGER_KEYS
    _require_exact_keys(row, keys, label)
    source_url = validate_source_url(
        source,
        _required_string(row["source_url"], f"{label}.source_url"),
        manager_hosts=allowed_hosts,
        allow_test_hosts=allow_test_urls,
    )
    fund_isin = _required_string(row["fund_isin"], f"{label}.fund_isin").upper()
    if not is_isin(fund_isin):
        raise ValueError(f"{label}.fund_isin must be a valid ISIN")
    as_of = parse_iso_date(row["as_of"], f"{label}.as_of")
    published_at = parse_iso_datetime(row["published_at"], f"{label}.published_at")
    if not POLICY_START <= as_of <= POLICY_END:
        raise ValueError(f"{label}.as_of is outside the production policy window")
    if published_at.tzinfo is None or published_at.utcoffset() is None:
        raise ValueError(f"{label}.published_at must be timezone-aware")
    if published_at > POLICY_CUTOFF:
        raise ValueError(f"{label}.published_at exceeds the production publication cutoff")

    if source == NPORT_SOURCE:
        return NPortTarget(
            accession=_required_string(row["accession"], f"{label}.accession"),
            source_url=source_url,
            fund_isin=fund_isin,
            as_of=as_of,
            published_at=published_at,
            allow_test_hosts=allow_test_urls,
        )
    return ManagerBasketTarget(
        manager_code=_required_string(row["manager_code"], f"{label}.manager_code"),
        fund_code=_required_string(row["fund_code"], f"{label}.fund_code"),
        fund_isin=fund_isin,
        source_url=source_url,
        as_of=as_of,
        published_at=published_at,
        format_hint=_required_string(row["format_hint"], f"{label}.format_hint"),
        reviewed_hosts=allowed_hosts,
        allow_test_hosts=allow_test_urls,
    )


def _target_source(target: Target) -> str:
    if isinstance(target, NPortTarget):
        return NPORT_SOURCE
    if isinstance(target, ManagerBasketTarget):
        return MANAGER_BASKET_SOURCE
    raise TypeError(f"Unsupported target type: {type(target).__name__}")


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def _require_exact_keys(values: Mapping[str, object], expected: frozenset[str], label: str) -> None:
    actual = set(values)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing keys: {missing}")
        if unknown:
            details.append(f"unknown keys: {unknown}")
        raise ValueError(f"{label} has invalid keys ({'; '.join(details)})")


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    if value != value.strip():
        raise ValueError(f"{label} must not have surrounding whitespace")
    return value


def _is_test_fixture(path: Path) -> bool:
    parts = path.resolve().parts
    return "tests" in parts and "fixtures" in parts
