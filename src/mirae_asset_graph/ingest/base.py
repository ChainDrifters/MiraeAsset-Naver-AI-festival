from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic, TypeVar

FetchTarget = TypeVar("FetchTarget")


class Adapter(ABC, Generic[FetchTarget]):
    """Base contract for source adapters that never write to the graph."""

    source: str

    @abstractmethod
    def discover(self) -> list[FetchTarget]:
        """Return fetch targets for the adapter's configured window."""

    @abstractmethod
    def fetch(self, target: FetchTarget) -> Path:
        """Fetch one target and return the raw artifact path."""

    @abstractmethod
    def normalize(self, raw_path: Path) -> Path:
        """Normalize a raw artifact into JSONL and return that path."""
