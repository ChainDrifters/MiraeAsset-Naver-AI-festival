from __future__ import annotations

from pathlib import Path


def test_ingest_adapters_do_not_import_neo4j() -> None:
    ingest_root = Path("src/mirae_asset_graph/ingest")
    offenders: list[str] = []
    for path in sorted(ingest_root.glob("**/*.py")):
        if path.name == "graph_loader.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "import neo4j" in text or "from neo4j" in text:
            offenders.append(str(path))

    assert offenders == []
