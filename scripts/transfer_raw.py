"""Transfer raw ingestion artifacts to the remote raw store with checksum proof."""

from __future__ import annotations

import argparse
import hashlib
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_DIR = PROJECT_ROOT / "var" / "raw"
DEFAULT_MIN_FREE_MB = 5120


@dataclass(frozen=True)
class CliArgs:
    local_dir: Path
    min_free_mb: int
    dry_run: bool


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rsync raw artifacts and verify sha256 checksums.")
    _ = parser.add_argument("--local-dir", type=Path, default=DEFAULT_LOCAL_DIR)
    _ = parser.add_argument("--min-free-mb", type=int, default=DEFAULT_MIN_FREE_MB)
    _ = parser.add_argument("--dry-run", action="store_true", help="Pass -n to rsync and skip verification.")
    return parser


def _parse_args() -> CliArgs:
    namespace = _parser().parse_args()
    return CliArgs(
        local_dir=cast(Path, namespace.local_dir),
        min_free_mb=cast(int, namespace.min_free_mb),
        dry_run=cast(bool, namespace.dry_run),
    )


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        print(f"error: {name} is required in the process environment", file=sys.stderr)
        raise SystemExit(2)
    return value


def _run(args: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _ensure_success(result: subprocess.CompletedProcess[str], action: str, exit_code: int = 3) -> None:
    if result.returncode == 0:
        return
    message = result.stderr.strip() or result.stdout.strip() or f"{action} failed"
    print(f"error: {action} failed: {message}", file=sys.stderr)
    raise SystemExit(exit_code)


def _remote_free_mb(remote: str, root: str) -> int:
    command = f"df -P {shlex.quote(root)}"
    result = _run(["ssh", remote, command])
    _ensure_success(result, "remote disk-space check")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        print("error: remote df output was not parseable", file=sys.stderr)
        raise SystemExit(3)
    columns = lines[-1].split()
    if len(columns) < 4:
        print("error: remote df output was not parseable", file=sys.stderr)
        raise SystemExit(3)
    try:
        available_kb = int(columns[3])
    except ValueError:
        print("error: remote df available space was not numeric", file=sys.stderr)
        raise SystemExit(3)
    return available_kb // 1024


def _local_checksums(local_dir: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for path in sorted(p for p in local_dir.rglob("*") if p.is_file()):
        relative = path.relative_to(local_dir).as_posix()
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        checksums[relative] = digest.hexdigest()
    return checksums


def _remote_checksums(remote: str, root: str, files: list[str]) -> dict[str, str]:
    if not files:
        return {}
    quoted_files = " ".join(shlex.quote(name) for name in files)
    command = f"cd {shlex.quote(root)} && sha256sum -- {quoted_files}"
    result = _run(["ssh", remote, command])
    _ensure_success(result, "remote checksum verification", exit_code=4)

    checksums: dict[str, str] = {}
    for line in result.stdout.splitlines():
        digest, separator, name = line.partition("  ")
        if not separator:
            digest, separator, name = line.partition(" ")
        if not separator or not digest or not name:
            print("error: remote sha256sum output was not parseable", file=sys.stderr)
            raise SystemExit(4)
        checksums[name.lstrip("*")] = digest
    return checksums


def main() -> int:
    args = _parse_args()
    local_dir = args.local_dir.expanduser().resolve()
    remote = _required_env("MIRAE_RAW_REMOTE")
    remote_root = _required_env("MIRAE_RAW_ROOT")
    destination = f"{remote}:{remote_root.rstrip('/')}/"

    if not local_dir.is_dir():
        print(f"error: local directory does not exist: {local_dir}", file=sys.stderr)
        return 2

    free_mb = _remote_free_mb(remote, remote_root)
    if free_mb < args.min_free_mb:
        print(
            (
                f"error: remote free space below threshold: {free_mb} MB available, "
                f"{args.min_free_mb} MB required"
            ),
            file=sys.stderr,
        )
        return 5

    rsync_command = ["rsync", "-av", "--checksum"]
    if args.dry_run:
        rsync_command.append("-n")
    rsync_command.extend([f"{local_dir}/", destination])
    rsync_result = _run(rsync_command)
    _ensure_success(rsync_result, "rsync transfer")

    if args.dry_run:
        print(f"dry-run transfer checked: {local_dir}/ -> {destination}")
        print(f"remote free space: {free_mb} MB")
        print("verification skipped for dry run")
        return 0

    local = _local_checksums(local_dir)
    remote_hashes = _remote_checksums(remote, remote_root, list(local))
    if local != remote_hashes:
        missing = sorted(set(local) - set(remote_hashes))
        extra = sorted(set(remote_hashes) - set(local))
        changed = sorted(name for name in set(local) & set(remote_hashes) if local[name] != remote_hashes[name])
        print(
            (
                "error: checksum verification failed "
                f"(missing={len(missing)}, extra={len(extra)}, changed={len(changed)})"
            ),
            file=sys.stderr,
        )
        return 4

    print(f"transferred {len(local)} files from {local_dir}/ to {destination}")
    print(f"remote free space before transfer: {free_mb} MB")
    print("checksum verification: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
