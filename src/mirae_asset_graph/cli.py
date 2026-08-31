from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import cast

from dotenv import load_dotenv
from neo4j import Driver, GraphDatabase

from .loader import FinancialProductsLoader
from .model import DATASETS

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORGANIZER_BASELINE_INPUT_DIR = PROJECT_ROOT / "data" / "1.금융상품"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mirae-graph",
        description="Load the financial-product Excel snapshots into Neo4j.",
    )
    parser.add_argument(
        "command",
        choices=("prepare", "load", "dry-run", "validate"),
        help="Prepare n10s/schema, load data, profile without writing, or validate.",
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=ORGANIZER_BASELINE_INPUT_DIR,
        help="Directory containing the fixed 2026-07-11 organizer baseline workbooks.",
    )
    parser.add_argument(
        "--ontology",
        type=Path,
        default=PROJECT_ROOT / "ontology",
        help="Directory containing the five ontology modules, or one Turtle file.",
    )
    parser.add_argument(
        "--dataset",
        action="append",
        choices=[spec.code for spec in DATASETS],
        help="Limit the operation to one or more datasets. May be repeated.",
    )
    parser.add_argument("--batch-size", type=int, default=500)
    parser.add_argument("--database", default=os.getenv("NEO4J_DATABASE", "neo4j"))
    parser.add_argument(
        "--fail-on-validation-error",
        action="store_true",
        help="Exit with an error when validation finds duplicate resource URIs or unlinked source records.",
    )
    parser.add_argument("--uri", help="Neo4j URI; defaults to the local Compose Bolt port.")
    parser.add_argument("--user", default=os.getenv("NEO4J_USER", "neo4j"))
    return parser


def _connection(args: argparse.Namespace) -> tuple[str, str, str]:
    load_dotenv(PROJECT_ROOT / ".env")
    bolt_port = os.getenv("NEO4J_BOLT_PORT", "7687")
    uri = args.uri or os.getenv("NEO4J_URI") or f"bolt://127.0.0.1:{bolt_port}"
    user = os.getenv("NEO4J_USER", args.user)
    password = os.getenv("NEO4J_PASSWORD")
    if not password:
        raise SystemExit("NEO4J_PASSWORD is required in .env or the process environment")
    return uri, user, password


def main() -> None:
    args = _parser().parse_args()
    selected = set(args.dataset) if args.dataset else None

    if args.command == "dry-run":
        loader = FinancialProductsLoader(
            driver=cast(Driver, object()),
            input_dir=args.input_dir,
            ontology_path=args.ontology,
            batch_size=args.batch_size,
            database=args.database,
        )
        report = loader.dry_run(selected)
        print(FinancialProductsLoader.format_report(report))
        return

    uri, user, password = _connection(args)
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        driver.verify_connectivity()
        loader = FinancialProductsLoader(
            driver,
            input_dir=args.input_dir,
            ontology_path=args.ontology,
            batch_size=args.batch_size,
            database=args.database,
        )
        if args.command in {"prepare", "load"}:
            loader.prepare()
        if args.command == "load":
            load_stats = loader.load(selected)
            print("Load statistics:")
            print(FinancialProductsLoader.format_report(load_stats))
        validation = loader.validate()
        print("Validation:")
        print(FinancialProductsLoader.format_report(validation))
        metrics = validation.get("metrics", {})
        if args.fail_on_validation_error and (
            metrics.get("duplicateResourceUris", 0) > 0
            or metrics.get("unlinkedNonRejectedSourceRecords", 0) > 0
        ):
            raise SystemExit("Validation failed: duplicate resource URIs or unlinked source records found.")


if __name__ == "__main__":
    main()
