"""Atomic, content-addressed publication for immutable derived artifacts."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def publish_immutable(directory: Path, payload: bytes, suffix: str) -> Path:
    digest = hashlib.sha256(payload).hexdigest()
    destination = directory / f"{digest}{suffix}"
    directory.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != payload:
            raise ValueError(f"content-addressed artifact conflicts with existing path: {destination}")
        return destination

    descriptor, temporary_name = tempfile.mkstemp(dir=directory, prefix=".publish-", suffix=".tmp")
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if not destination.is_file() or destination.read_bytes() != payload:
                raise ValueError(
                    f"content-addressed artifact conflicts with existing path: {destination}"
                )
        return destination
    finally:
        temporary.unlink(missing_ok=True)
