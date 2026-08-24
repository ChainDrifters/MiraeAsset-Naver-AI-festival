from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from mirae_asset_graph import ingest_cli
from mirae_asset_graph.ingest.manifest import ManifestEntry, Phase, Status, append_entry, batch_id
from mirae_asset_graph.ingest.runner import RunSummary
from mirae_asset_graph.ingest.targets import load_target_config, target_document_id

FIXTURES = Path(__file__).parent / "fixtures"


def _json_output(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)


def _clear_run_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    def skip_dotenv(_path: Path) -> bool:
        return False

    monkeypatch.setattr(ingest_cli, "load_dotenv", skip_dotenv)
    for name in (
        "SEC_USER_AGENT",
        "MANAGER_USER_AGENT",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "NEO4J_DATABASE",
        "MIRAE_ALLOW_NEO4J_WRITE",
        "MIRAE_STAGING_NEO4J_URI",
        "MIRAE_STAGING_NEO4J_DATABASE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_validate_targets_is_offline_and_prints_sorted_json(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_run_environment(monkeypatch)
    code = ingest_cli.main(
        [
            "validate-targets",
            "--targets",
            str(FIXTURES / "targets_nport.json"),
            "--start",
            "2026-04-11",
            "--end",
            "2026-07-11",
            "--cutoff",
            "2026-07-01T00:00:00+00:00",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert captured.out == json.dumps(json.loads(captured.out), ensure_ascii=False, sort_keys=True) + "\n"
    assert json.loads(captured.out)["target_count"] == 1


def test_catch_up_requires_target_completion_not_loaded_first_shard(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = load_target_config(FIXTURES / "targets_manager.json")
    same_date = [target for target in config.targets if target.as_of.isoformat() == "2026-07-11"]
    loaded = same_date[0]
    document_id = target_document_id(loaded)
    append_entry(
        ManifestEntry(
            run_id="offline-test",
            source=config.source,
            phase=Phase.LOADED,
            window_date=loaded.as_of,
            batch_id=batch_id(config.source, loaded.as_of, 0),
            status=Status.LOADED,
        ),
        tmp_path,
    )

    args = [
        "catch-up",
        "--targets",
        str(FIXTURES / "targets_manager.json"),
        "--manifest-root",
        str(tmp_path),
        "--start",
        "2026-07-11",
    ]
    code = ingest_cli.main(args)
    partial_report = _json_output(capsys)
    assert code == 0
    assert partial_report["target_count"] == 2
    assert partial_report["ready_target_count"] == 0
    assert partial_report["missing_document_ids"] == sorted(
        target_document_id(target) for target in same_date
    )

    append_entry(
        ManifestEntry(
            run_id="offline-test",
            source=config.source,
            phase=Phase.READY,
            window_date=loaded.as_of,
            batch_id="ready-test",
            status=Status.READY,
            stable_target_id=document_id,
        ),
        tmp_path,
    )
    code = ingest_cli.main(args)
    report = _json_output(capsys)
    assert code == 0
    assert report["target_count"] == 2
    assert report["ready_target_count"] == 1
    assert report["missing_document_ids"] == [target_document_id(same_date[1])]


def test_cli_loads_repo_root_dotenv_without_printing_values(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []

    def fake_load_dotenv(path: Path) -> bool:
        calls.append(path)
        monkeypatch.setenv("NEO4J_PASSWORD", "dotenv-secret-must-not-print")
        return True

    monkeypatch.setattr(ingest_cli, "load_dotenv", fake_load_dotenv)
    code = ingest_cli.main(
        ["validate-targets", "--targets", str(FIXTURES / "targets_nport.json")]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert calls == [ingest_cli.PROJECT_ROOT / ".env"]
    assert "dotenv-secret-must-not-print" not in captured.out + captured.err


@pytest.mark.parametrize(
    "fixture,user_agent_name,other_user_agent",
    [
        ("targets_nport.json", "SEC_USER_AGENT", "MANAGER_USER_AGENT"),
        ("targets_manager.json", "MANAGER_USER_AGENT", "SEC_USER_AGENT"),
    ],
)
def test_collect_requires_only_source_specific_user_agent_and_never_driver(
    fixture: str,
    user_agent_name: str,
    other_user_agent: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_run_environment(monkeypatch)
    monkeypatch.setenv(other_user_agent, "other@example.com")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "top-secret-password")
    code = ingest_cli.main(_run_args(tmp_path, fixture))
    captured = capsys.readouterr()
    assert code == 1
    assert user_agent_name in captured.err
    assert "top-secret-password" not in captured.err
    assert captured.out == ""


def test_successful_collect_builds_components_without_neo4j(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_run_environment(monkeypatch)
    monkeypatch.setenv("SEC_USER_AGENT", "sec-ops@example.com")
    monkeypatch.setenv("NEO4J_USER", "neo4j-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "never-print-this")

    crosswalk = tmp_path / "crosswalk.csv"
    crosswalk.write_text(
        "entity_kind,local_key_type,local_key,local_name,standard_id_type,standard_id,"
        "standard_name,source_url,reviewed_by,reviewed_at\n",
        encoding="utf-8",
    )

    adapter_arguments: dict[str, object] = {}

    class FakeAdapter:
        source = "sec_nport"

        def __init__(self, **kwargs: object) -> None:
            adapter_arguments.update(kwargs)

    expected = RunSummary(3, 3, 3, 12, 1, 0, 0)
    runner_arguments: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, *args: object, **kwargs: object) -> None:
            runner_arguments.update(args=args, kwargs=kwargs)

        def run(self, run_id: str, **kwargs: object) -> RunSummary:
            assert run_id.startswith("collect-")
            return expected

    monkeypatch.setattr(ingest_cli, "NPortAdapter", FakeAdapter)
    monkeypatch.setattr(ingest_cli, "CollectionRunner", FakeRunner)
    args = _run_args(tmp_path, "targets_nport.json")
    args[args.index(str(tmp_path / "crosswalk.csv"))] = str(crosswalk)
    code = ingest_cli.main(args)
    captured = capsys.readouterr()

    assert code == 0
    assert json.loads(captured.out) == expected.to_dict()
    assert captured.err == ""
    assert adapter_arguments["user_agent"] == "sec-ops@example.com"
    runner_kwargs = runner_arguments["kwargs"]
    assert isinstance(runner_kwargs, dict)
    assert runner_kwargs["stable_target_id"] is target_document_id
    assert "never-print-this" not in captured.out + captured.err
    assert "sec-ops@example.com" not in captured.out + captured.err


def test_write_environment_requires_every_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_run_environment(monkeypatch)
    args = argparse.Namespace(
        authorize_write=False,
        environment="staging",
        expected_database="mirae_staging",
    )
    with pytest.raises(ValueError, match="NEO4J_URI"):
        ingest_cli._write_environment(args)

    monkeypatch.setenv("NEO4J_URI", "neo4j+s://staging.example.invalid")
    monkeypatch.setenv("NEO4J_DATABASE", "mirae_staging")
    monkeypatch.setenv("NEO4J_USER", "writer")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("MIRAE_STAGING_NEO4J_URI", "neo4j+s://staging.example.invalid")
    monkeypatch.setenv("MIRAE_STAGING_NEO4J_DATABASE", "mirae_staging")
    with pytest.raises(ValueError, match="exactly YES"):
        ingest_cli._write_environment(args)

    monkeypatch.setenv("MIRAE_ALLOW_NEO4J_WRITE", "YES")
    with pytest.raises(ValueError, match="--authorize-write"):
        ingest_cli._write_environment(args)


def test_write_environment_rejects_database_mismatch_generic_and_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_run_environment(monkeypatch)
    for name, value in {
        "NEO4J_URI": "neo4j+s://staging.example.invalid",
        "NEO4J_DATABASE": "mirae_staging",
        "NEO4J_USER": "writer",
        "NEO4J_PASSWORD": "secret",
        "MIRAE_ALLOW_NEO4J_WRITE": "YES",
        "MIRAE_STAGING_NEO4J_URI": "neo4j+s://staging.example.invalid",
        "MIRAE_STAGING_NEO4J_DATABASE": "mirae_staging",
    }.items():
        monkeypatch.setenv(name, value)
    args = argparse.Namespace(
        authorize_write=True,
        environment="staging",
        expected_database="wrong",
    )
    with pytest.raises(ValueError, match="must match"):
        ingest_cli._write_environment(args)

    args.environment = "production"
    args.expected_database = "mirae_production"
    monkeypatch.setenv("NEO4J_DATABASE", "mirae_production")
    with pytest.raises(ValueError, match="production loading is blocked"):
        ingest_cli._write_environment(args)


def test_write_environment_binds_to_deployment_owned_staging_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_run_environment(monkeypatch)
    values = {
        "NEO4J_URI": "neo4j+s://actual.example",
        "NEO4J_DATABASE": "mirae_staging",
        "NEO4J_USER": "writer",
        "NEO4J_PASSWORD": "secret",
        "MIRAE_ALLOW_NEO4J_WRITE": "YES",
        "MIRAE_STAGING_NEO4J_URI": "neo4j+s://trusted.example",
        "MIRAE_STAGING_NEO4J_DATABASE": "mirae_staging",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    args = argparse.Namespace(
        authorize_write=True,
        environment="staging",
        expected_database="mirae_staging",
    )
    with pytest.raises(ValueError, match="trusted staging URI"):
        ingest_cli._write_environment(args)

    monkeypatch.setenv("NEO4J_URI", "neo4j://trusted.example")
    monkeypatch.setenv("MIRAE_STAGING_NEO4J_URI", "neo4j://trusted.example")
    with pytest.raises(ValueError, match=r"neo4j\+s"):
        ingest_cli._write_environment(args)


def test_remote_staging_rejects_plain_neo4j_and_generic_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_run_environment(monkeypatch)
    args = argparse.Namespace(
        authorize_write=True,
        environment="staging",
        expected_database="mirae_staging",
    )
    values = {
        "NEO4J_URI": "neo4j://remote.example:7687",
        "NEO4J_DATABASE": "mirae_staging",
        "NEO4J_USER": "writer",
        "NEO4J_PASSWORD": "secret",
        "MIRAE_ALLOW_NEO4J_WRITE": "YES",
        "MIRAE_STAGING_NEO4J_URI": "neo4j://remote.example:7687",
        "MIRAE_STAGING_NEO4J_DATABASE": "mirae_staging",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=r"non-loopback staging URI must use neo4j\+s"):
        ingest_cli._write_environment(args)

    args.expected_database = "neo4j"
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://remote.example:7687")
    monkeypatch.setenv("MIRAE_STAGING_NEO4J_URI", "neo4j+s://remote.example:7687")
    monkeypatch.setenv("NEO4J_DATABASE", "neo4j")
    monkeypatch.setenv("MIRAE_STAGING_NEO4J_DATABASE", "neo4j")
    with pytest.raises(ValueError, match="generic neo4j"):
        ingest_cli._write_environment(args)


@pytest.mark.parametrize(
    "uri",
    ["neo4j://127.0.0.1:7687", "neo4j://localhost:7687", "neo4j://[::1]:7687"],
)
def test_loopback_staging_accepts_community_neo4j_database(
    monkeypatch: pytest.MonkeyPatch, uri: str
) -> None:
    _clear_run_environment(monkeypatch)
    for name, value in {
        "NEO4J_URI": uri,
        "NEO4J_DATABASE": "neo4j",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASSWORD": "disposable-test-secret",
        "MIRAE_ALLOW_NEO4J_WRITE": "YES",
        "MIRAE_STAGING_NEO4J_URI": uri,
        "MIRAE_STAGING_NEO4J_DATABASE": "neo4j",
    }.items():
        monkeypatch.setenv(name, value)
    args = argparse.Namespace(
        authorize_write=True,
        environment="staging",
        expected_database="neo4j",
    )
    environment = ingest_cli._write_environment(args)
    assert environment["uri"] == uri
    assert environment["database"] == "neo4j"


def test_load_batch_identity_uses_normalized_digest_and_row_range() -> None:
    first = ingest_cli._load_batch_id("sec_nport", "i" * 64, "a" * 64, 0, 250)
    same = ingest_cli._load_batch_id("sec_nport", "i" * 64, "a" * 64, 0, 250)
    resized = ingest_cli._load_batch_id("sec_nport", "i" * 64, "a" * 64, 0, 500)
    amended = ingest_cli._load_batch_id("sec_nport", "i" * 64, "b" * 64, 0, 250)
    new_crosswalk = ingest_cli._load_batch_id("sec_nport", "j" * 64, "a" * 64, 0, 250)
    assert first == same
    assert len({first, resized, amended, new_crosswalk}) == 4


def test_verify_and_load_require_crosswalk_argument() -> None:
    parser = ingest_cli._parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "verify-collection",
                "--targets",
                str(FIXTURES / "targets_nport.json"),
                "--manifest-root",
                "manifest",
                "--raw-root",
                "raw",
                "--normalized-root",
                "normalized",
            ]
        )


def test_resume_with_different_batch_size_cannot_omit_rows() -> None:
    digest = "a" * 64
    input_digest = "i" * 64
    first_range = ingest_cli._load_ranges(5, 2)[0]
    loaded = {ingest_cli._load_batch_id("sec_nport", input_digest, digest, *first_range)}
    rerun_ranges = ingest_cli._load_ranges(5, 3)
    pending = [
        row_range
        for row_range in rerun_ranges
        if ingest_cli._load_batch_id("sec_nport", input_digest, digest, *row_range) not in loaded
    ]
    covered = {row for start, end in pending for row in range(start, end)}
    assert covered == set(range(5))


def _run_args(tmp_path: Path, fixture: str) -> list[str]:
    return [
        "collect",
        "--targets",
        str(FIXTURES / fixture),
        "--crosswalk",
        str(tmp_path / "crosswalk.csv"),
        "--raw-root",
        str(tmp_path / "raw"),
        "--normalized-root",
        str(tmp_path / "normalized"),
        "--manifest-root",
        str(tmp_path / "manifest"),
        "--refresh",
    ]
