from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic, TypeVar

FetchTarget = TypeVar("FetchTarget")
NormalizeResult = TypeVar("NormalizeResult")


class Adapter(ABC, Generic[FetchTarget, NormalizeResult]):
    """Base contract for source adapters that never write to the graph."""

    source: str

    @abstractmethod
    def discover(self) -> list[FetchTarget]:
        """Return fetch targets for the adapter's configured window."""

    @abstractmethod
    def fetch(self, target: FetchTarget) -> Path:
        """Fetch one target and return the raw artifact path."""

    @abstractmethod
    def normalize(self, target: FetchTarget, raw_path: Path, output_dir: Path) -> NormalizeResult:
        """Normalize one fetched raw artifact into the adapter's result."""
