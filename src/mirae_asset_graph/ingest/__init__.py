"""External-data ingestion helpers for Mirae Asset graph enrichment."""

from .base import Adapter
from .crosswalk import (
    CROSSWALK_FIELDS,
    CrosswalkRow,
    detect_name_only_merge,
    group_by_standard_id,
    is_reviewed,
    load_crosswalk,
    mapping_key,
    to_payload,
)
from .manifest import ManifestEntry, Phase, Status, append_entry, batch_id, is_loaded, read_manifest
from .records import HoldingsRecord, read_jsonl, write_jsonl
from .resolver import IdentifierResolver, ResolutionResult
from .watermark import compute_missing, month_ends

__all__ = [
    "Adapter",
    "CROSSWALK_FIELDS",
    "CrosswalkRow",
    "HoldingsRecord",
    "IdentifierResolver",
    "ManifestEntry",
    "Phase",
    "ResolutionResult",
    "Status",
    "append_entry",
    "batch_id",
    "compute_missing",
    "detect_name_only_merge",
    "group_by_standard_id",
    "is_loaded",
    "is_reviewed",
    "load_crosswalk",
    "mapping_key",
    "month_ends",
    "read_jsonl",
    "read_manifest",
    "to_payload",
    "write_jsonl",
]
