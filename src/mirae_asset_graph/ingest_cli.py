"""Production-safe collection, offline verification, and gated graph loading."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import re
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import NoReturn, TextIO
from urllib.parse import urlsplit

from dotenv import load_dotenv

from .ingest.basket_kr import MANAGER_BASKET_SOURCE, ManagerBasketAdapter, ManagerBasketTarget
from .ingest.collection import (
    CollectionRunner,
    accession_document_id,
    manager_document_id,
    verify_collection,
)
from .ingest.crosswalk import load_crosswalk_bytes
from .ingest.manifest import ManifestEntry, Phase, Status, append_entry, is_loaded, read_manifest
from .ingest.nport import NPORT_SOURCE, NPortAdapter, NPortTarget
from .ingest.resolver import IdentifierResolver
from .ingest.runner import MAX_BATCH_SIZE
from .ingest.targets import (
    Target,
    TargetConfig,
    load_target_config,
    parse_iso_date,
    parse_iso_datetime,
    target_document_id,
    target_window,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_URL_CREDENTIALS = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://)([^\s/@:]+):([^\s/@]+)@")
_SECRET_PARAM = re.compile(r"(?i)([?&])(password|passwd|token|api[_-]?key|secret)=([^\s&]+)")


class _JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        _print_json({"error": message}, stream=sys.stderr)
        raise SystemExit(2)


def _parser() -> argparse.ArgumentParser:
    parser = _JsonArgumentParser(prog="mirae-ingest")
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-targets")
    _add_target_arguments(validate)

    catch_up = commands.add_parser("catch-up")
    _add_target_arguments(catch_up)
    catch_up.add_argument("--manifest-root", type=Path, required=True)

    collect = commands.add_parser("collect")
    _add_target_arguments(collect)
    collect.add_argument("--crosswalk", type=Path, required=True)
    collect.add_argument("--raw-root", type=Path, required=True)
    collect.add_argument("--normalized-root", type=Path, required=True)
    collect.add_argument("--manifest-root", type=Path, required=True)
    collect.add_argument("--continue-on-error", action="store_true")
    collect.add_argument("--refresh", action="store_true", help="Explicitly authorize source refresh")

    verify = commands.add_parser("verify-collection")
    _add_target_arguments(verify)
    verify.add_argument("--manifest-root", type=Path, required=True)
    verify.add_argument("--raw-root", type=Path, required=True)
    verify.add_argument("--normalized-root", type=Path, required=True)
    verify.add_argument("--crosswalk", type=Path, required=True)

    load = commands.add_parser("load")
    _add_target_arguments(load)
    load.add_argument("--manifest-root", type=Path, required=True)
    load.add_argument("--raw-root", type=Path, required=True)
    load.add_argument("--normalized-root", type=Path, required=True)
    load.add_argument("--crosswalk", type=Path, required=True)
    load.add_argument("--batch-size", type=int, default=MAX_BATCH_SIZE)
    load.add_argument("--authorize-write", action="store_true")
    load.add_argument("--environment", choices=("staging", "production"), required=True)
    load.add_argument("--expected-database", required=True)
    return parser


def _add_target_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--targets", type=Path, required=True)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--cutoff")


def main(argv: Sequence[str] | None = None) -> int:
    _ = load_dotenv(PROJECT_ROOT / ".env")
    args = _parser().parse_args(argv)
    try:
        start, end, cutoff = _window_arguments(args)
        config = load_target_config(args.targets)
        selected = target_window(config.targets, start=start, end=end, cutoff=cutoff)
        if args.command == "validate-targets":
            _print_json(config.summary(selected))
        elif args.command == "catch-up":
            _print_json(_catch_up_report(config.source, selected, args.manifest_root))
        elif args.command == "collect":
            _print_json(_collect(config, selected, args, start, end, cutoff))
        elif args.command == "verify-collection":
            verified = _verify(config, selected, args)
            _print_json({"source": config.source, "verified_target_count": len(verified)})
        elif args.command == "load":
            _print_json(_load(config, selected, args))
        else:
            raise AssertionError(f"Unsupported command: {args.command}")
        return 0
    except Exception as error:
        _print_json({"error": _safe_error(error)}, stream=sys.stderr)
        return 1


def _window_arguments(args: argparse.Namespace) -> tuple[date | None, date | None, datetime | None]:
    start = parse_iso_date(args.start, "--start") if args.start is not None else None
    end = parse_iso_date(args.end, "--end") if args.end is not None else None
    cutoff = parse_iso_datetime(args.cutoff, "--cutoff") if args.cutoff is not None else None
    return start, end, cutoff


def _catch_up_report(source: str, targets: Sequence[Target], manifest_root: Path) -> dict[str, object]:
    ready_ids = {
        entry.stable_target_id
        for entry in read_manifest(source, manifest_root)
        if entry.phase is Phase.READY and entry.status is Status.READY
    }
    missing = [target for target in targets if target_document_id(target) not in ready_ids]
    return {
        "ready_target_count": len(targets) - len(missing),
        "missing_count": len(missing),
        "missing_document_ids": sorted(target_document_id(target) for target in missing),
        "source": source,
        "target_count": len(targets),
    }


def _collect(
    config: TargetConfig,
    targets: Sequence[Target],
    args: argparse.Namespace,
    start: date | None,
    end: date | None,
    cutoff: datetime | None,
) -> dict[str, int]:
    source = config.source
    user_agent = _required_environment(
        "SEC_USER_AGENT" if source == NPORT_SOURCE else "MANAGER_USER_AGENT"
    )
    crosswalk_bytes = args.crosswalk.read_bytes()
    crosswalk_sha256 = hashlib.sha256(crosswalk_bytes).hexdigest()
    input_digest = _normalization_input_digest(config.config_digest, crosswalk_sha256)
    resolver = IdentifierResolver(load_crosswalk_bytes(crosswalk_bytes))
    if source == NPORT_SOURCE:
        adapter = NPortAdapter(
            targets=_nport_targets(targets),
            raw_root=args.raw_root,
            resolver=resolver,
            user_agent=user_agent,
            refresh=args.refresh,
        )
        runner = CollectionRunner(
            adapter,
            args.manifest_root,
            args.normalized_root,
            stable_target_id=target_document_id,
            document_id=accession_document_id,
            config_digest=config.config_digest,
            crosswalk_sha256=crosswalk_sha256,
            normalization_input_digest=input_digest,
            continue_on_error=args.continue_on_error,
        )
    elif source == MANAGER_BASKET_SOURCE:
        adapter = ManagerBasketAdapter(
            targets=_manager_targets(targets),
            raw_root=args.raw_root,
            resolver=resolver,
            user_agent=user_agent,
            refresh=args.refresh,
        )
        runner = CollectionRunner(
            adapter,
            args.manifest_root,
            args.normalized_root,
            stable_target_id=target_document_id,
            document_id=manager_document_id,
            config_digest=config.config_digest,
            crosswalk_sha256=crosswalk_sha256,
            normalization_input_digest=input_digest,
            continue_on_error=args.continue_on_error,
        )
    else:
        raise ValueError(f"Unsupported target source: {source}")
    return runner.run(_run_id("collect"), start=start, end=end, cutoff=cutoff).to_dict()


def _verify(config: TargetConfig, targets: Sequence[Target], args: argparse.Namespace):
    crosswalk_sha256 = hashlib.sha256(args.crosswalk.read_bytes()).hexdigest()
    input_digest = _normalization_input_digest(config.config_digest, crosswalk_sha256)
    return verify_collection(
        config.source,
        targets,
        args.manifest_root,
        stable_target_id=target_document_id,
        expected_config_digest=config.config_digest,
        expected_crosswalk_sha256=crosswalk_sha256,
        expected_normalization_input_digest=input_digest,
        raw_root=args.raw_root,
        normalized_root=args.normalized_root,
    )


def _load(config: TargetConfig, targets: Sequence[Target], args: argparse.Namespace) -> dict[str, int]:
    environment = _write_environment(args)
    verified = _verify(config, targets, args)
    if not 1 <= args.batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch-size must be in 1..{MAX_BATCH_SIZE}")

    from neo4j import GraphDatabase

    from .ingest.graph_loader import ExternalGraphLoader

    driver = GraphDatabase.driver(
        environment["uri"], auth=(environment["user"], environment["password"])
    )
    loaded_rows = skipped_batches = 0
    try:
        driver.verify_connectivity()
        loader = ExternalGraphLoader(driver, environment["database"])
        run_id = _run_id("load")
        for collection in verified:
            entry = collection.entry
            document_id = _required_manifest(entry.source_document_id, "source_document_id")
            source_url = _required_manifest(entry.source_url, "source_url")
            artifact_sha256 = _required_manifest(entry.artifact_sha256, "artifact_sha256")
            retrieved_at = entry.retrieved_at or datetime.now(UTC)
            for offset, end in _load_ranges(len(collection.records), args.batch_size):
                rows = collection.records[offset:end]
                normalized_sha256 = _required_manifest(
                    entry.normalized_sha256, "normalized_sha256"
                )
                normalization_input_digest = _required_manifest(
                    entry.normalization_input_digest, "normalization_input_digest"
                )
                shard_id = _load_batch_id(
                    config.source,
                    normalization_input_digest,
                    normalized_sha256,
                    offset,
                    end,
                )
                if is_loaded(config.source, entry.window_date, shard_id, args.manifest_root):
                    skipped_batches += 1
                    continue
                result = loader.load_holdings_rows(
                    [record.to_loader_payload() for record in rows],
                    source=config.source,
                    source_url=source_url,
                    artifact_sha256=artifact_sha256,
                    artifact_bytes=entry.artifact_bytes or 0,
                    run_id=run_id,
                    retrieved_at=retrieved_at,
                )
                loaded_rows += result["rows"]
                now = datetime.now(UTC)
                _ = append_entry(
                    ManifestEntry(
                        run_id=run_id,
                        source=config.source,
                        phase=Phase.LOADED,
                        window_date=entry.window_date,
                        batch_id=shard_id,
                        status=Status.LOADED,
                        artifact_sha256=artifact_sha256,
                        started_at=now,
                        finished_at=now,
                        stable_target_id=entry.stable_target_id,
                        source_document_id=document_id,
                    ),
                    args.manifest_root,
                )
    finally:
        driver.close()
    return {"loaded_rows": loaded_rows, "skipped_batches": skipped_batches}


def _write_environment(args: argparse.Namespace) -> dict[str, str]:
    names = (
        "NEO4J_URI",
        "NEO4J_DATABASE",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "MIRAE_STAGING_NEO4J_URI",
        "MIRAE_STAGING_NEO4J_DATABASE",
    )
    missing = [name for name in names if not os.environ.get(name, "").strip()]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
    if os.environ.get("MIRAE_ALLOW_NEO4J_WRITE") != "YES":
        raise ValueError("MIRAE_ALLOW_NEO4J_WRITE must be exactly YES")
    if not args.authorize_write:
        raise ValueError("--authorize-write is required")
    database = os.environ["NEO4J_DATABASE"]
    if args.expected_database != database:
        raise ValueError("--expected-database must match NEO4J_DATABASE")
    if args.environment == "production":
        raise ValueError("production loading is blocked until staging receipt support is implemented")
    uri = os.environ["NEO4J_URI"]
    if uri != os.environ["MIRAE_STAGING_NEO4J_URI"]:
        raise ValueError("NEO4J_URI must match the trusted staging URI")
    if database != os.environ["MIRAE_STAGING_NEO4J_DATABASE"]:
        raise ValueError("NEO4J_DATABASE must match the trusted staging database")
    parsed_uri = urlsplit(uri)
    if parsed_uri.username is not None or parsed_uri.password is not None:
        raise ValueError("staging URI must not contain userinfo")
    if not parsed_uri.hostname:
        raise ValueError("staging URI must include a host")
    is_loopback = _is_disposable_loopback_host(parsed_uri.hostname)
    if is_loopback:
        if parsed_uri.scheme.lower() not in {"neo4j", "neo4j+s"}:
            raise ValueError("loopback staging URI must use neo4j or neo4j+s")
    else:
        if parsed_uri.scheme.lower() != "neo4j+s":
            raise ValueError("non-loopback staging URI must use neo4j+s")
        if database.lower() == "neo4j":
            raise ValueError("non-loopback staging rejects the generic neo4j database")
    return {
        "uri": uri,
        "database": database,
        "user": os.environ["NEO4J_USER"],
        "password": os.environ["NEO4J_PASSWORD"],
    }


def _is_disposable_loopback_host(host: str) -> bool:
    normalized = host.rstrip(".").casefold()
    if normalized == "localhost":
        return True
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False
    return address == ipaddress.ip_address("127.0.0.1") or address == ipaddress.ip_address("::1")


def _load_batch_id(
    source: str,
    normalization_input_digest: str,
    normalized_sha256: str,
    start: int,
    end: int,
) -> str:
    raw = (
        f"load|{source}|{normalization_input_digest}|{normalized_sha256}|{start}|{end}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_ranges(row_count: int, batch_size: int) -> tuple[tuple[int, int], ...]:
    return tuple(
        (start, min(start + batch_size, row_count))
        for start in range(0, row_count, batch_size)
    )


def _normalization_input_digest(config_digest: str, crosswalk_sha256: str) -> str:
    raw = f"normalization-input-v1|{config_digest}|{crosswalk_sha256}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _nport_targets(targets: Sequence[Target]) -> tuple[NPortTarget, ...]:
    if not all(isinstance(target, NPortTarget) for target in targets):
        raise ValueError("N-PORT config contains a mixed target definition")
    return tuple(target for target in targets if isinstance(target, NPortTarget))


def _manager_targets(targets: Sequence[Target]) -> tuple[ManagerBasketTarget, ...]:
    if not all(isinstance(target, ManagerBasketTarget) for target in targets):
        raise ValueError("Manager config contains a mixed target definition")
    return tuple(target for target in targets if isinstance(target, ManagerBasketTarget))


def _required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _required_manifest(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"READY manifest is missing {name}")
    return value


def _run_id(prefix: str) -> str:
    return datetime.now(UTC).strftime(f"{prefix}-%Y%m%dT%H%M%S%fZ")


def _safe_error(error: BaseException) -> str:
    text = f"{type(error).__name__}: {error}"
    text = _URL_CREDENTIALS.sub(r"\1<redacted>@", text)
    text = _SECRET_PARAM.sub(r"\1\2=<redacted>", text)
    for name in (
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "SEC_USER_AGENT",
        "MANAGER_USER_AGENT",
    ):
        secret = os.environ.get(name)
        if secret:
            text = text.replace(secret, "<redacted>")
    return "".join(character if character.isprintable() else " " for character in text).strip()[:500]


def _print_json(value: object, *, stream: TextIO | None = None) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True), file=stream or sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
