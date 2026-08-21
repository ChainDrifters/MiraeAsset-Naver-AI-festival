"""Identifier resolution for ISIN-only graph loads.

The Phase-2 crosswalk freeze deliberately leaves some products without an
official ISIN (they carry an official exchange or regulator code instead).
Those entities stay unresolved here; the caller quarantines them rather than
the resolver guessing an identifier. Names are never a lookup key.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..model import is_isin

from .crosswalk import CrosswalkRow, is_reviewed

SOURCE_ISIN = "source_isin"
CROSSWALK = "crosswalk"
UNRESOLVED = "unresolved"

STANDARD_ISIN = "isin"


@dataclass(frozen=True)
class ResolutionResult:
    """Outcome of one identity resolution attempt."""

    isin: str | None
    method: str
    reason: str | None


def _lookup_key(local_key_type: str, local_key: str) -> tuple[str, str]:
    """Normalize a (local_key_type, local_key) probe for exact index lookup.

    The index only ever holds rows whose standard_id_type is isin, so every
    indexed local key is case-normalized exactly like crosswalk.mapping_key
    does for identifier-style keys; the probe follows the same rule.
    """
    return (local_key_type.strip().lower(), local_key.strip().upper())


class IdentifierResolver:
    """Resolve fund or constituent identities to verified ISINs.

    Built from crosswalk rows, but only reviewed rows whose standard
    identifier is a well-formed ISIN enter the index. A non-ISIN standard
    identifier (for example a krx_code) cannot satisfy an ISIN-only graph
    load, so those rows are simply absent and lookups through them come back
    unresolved with a reason. There is no name index and no name path.
    """

    def __init__(self, rows: list[CrosswalkRow]) -> None:
        index: dict[tuple[str, str], str] = {}
        for row in rows:
            if not is_reviewed(row):
                continue
            if row.standard_id_type.strip().lower() != STANDARD_ISIN:
                continue
            isin = row.standard_id.strip().upper()
            if not is_isin(isin):
                raise ValueError(
                    "Crosswalk row with standard_id_type=isin has a malformed standard_id: "
                    f"{row.standard_id!r}"
                )
            key = _lookup_key(row.local_key_type, row.local_key)
            existing = index.get(key)
            if existing is not None and existing != isin:
                raise ValueError(
                    f"Conflicting reviewed ISIN mappings for local key {key}: {existing} vs {isin}"
                )
            index[key] = isin
        self._index = index

    def resolve(
        self,
        *,
        source_isin: str | None = None,
        local_key_type: str | None = None,
        local_key: str | None = None,
    ) -> ResolutionResult:
        """Resolve one identity: source ISIN first, then reviewed crosswalk."""
        if source_isin is not None:
            candidate = source_isin.strip().upper()
            if is_isin(candidate):
                return ResolutionResult(isin=candidate, method=SOURCE_ISIN, reason=None)
            return ResolutionResult(
                isin=None,
                method=UNRESOLVED,
                reason=f"source_isin is not a valid ISIN: {source_isin!r}",
            )
        if local_key_type is not None or local_key is not None:
            if not local_key_type or not local_key:
                missing = "local_key_type" if not local_key_type else "local_key"
                return ResolutionResult(
                    isin=None,
                    method=UNRESOLVED,
                    reason=f"incomplete crosswalk lookup: missing {missing}",
                )
            key = _lookup_key(local_key_type, local_key)
            isin = self._index.get(key)
            if isin is not None:
                return ResolutionResult(isin=isin, method=CROSSWALK, reason=None)
            return ResolutionResult(
                isin=None,
                method=UNRESOLVED,
                reason=f"no reviewed ISIN crosswalk entry for local key {key}",
            )
        return ResolutionResult(
            isin=None,
            method=UNRESOLVED,
            reason="no identifier supplied: source_isin and local key are both empty",
        )

    def resolve_fund(
        self,
        *,
        source_isin: str | None = None,
        local_key_type: str | None = None,
        local_key: str | None = None,
    ) -> ResolutionResult:
        """Fund-side alias of resolve(); identical rules."""
        return self.resolve(source_isin=source_isin, local_key_type=local_key_type, local_key=local_key)

    def resolve_constituent(
        self,
        *,
        source_isin: str | None = None,
        local_key_type: str | None = None,
        local_key: str | None = None,
    ) -> ResolutionResult:
        """Constituent-side alias of resolve(); identical rules."""
        return self.resolve(source_isin=source_isin, local_key_type=local_key_type, local_key=local_key)
