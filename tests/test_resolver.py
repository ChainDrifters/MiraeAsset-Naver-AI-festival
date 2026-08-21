# pyright: reportMissingTypeStubs=false
from __future__ import annotations

from pathlib import Path

import pytest

from mirae_asset_graph.ingest.crosswalk import CROSSWALK_FIELDS, CrosswalkRow, load_crosswalk
from mirae_asset_graph.ingest.resolver import IdentifierResolver, ResolutionResult

REPOSITORY_CROSSWALK = (
    Path(__file__).resolve().parents[1] / "data" / "crosswalks" / "contest_entities.csv"
)


def _row(**overrides: str) -> CrosswalkRow:
    values: dict[str, str] = {field: "" for field in CROSSWALK_FIELDS}
    values.update(
        {
            "entity_kind": "etf",
            "local_key_type": "nyse_ticker",
            "local_key": "KSTR",
            "local_name": "KraneShares KSTR",
            "standard_id_type": "isin",
            "standard_id": "US5007676944",
            "standard_name": "KraneShares KSTR",
            "source_url": "https://kraneshares.com/etf/kstr/",
            "reviewed_by": "official-source-audit",
            "reviewed_at": "2026-08-21",
        }
    )
    values.update(overrides)
    return CrosswalkRow(**values)


def test_source_isin_wins_over_crosswalk() -> None:
    resolver = IdentifierResolver([_row()])

    result = resolver.resolve(
        source_isin="ie00bkpjy434", local_key_type="nyse_ticker", local_key="KSTR"
    )

    assert result == ResolutionResult(isin="IE00BKPJY434", method="source_isin", reason=None)


def test_malformed_source_isin_is_unresolved() -> None:
    resolver = IdentifierResolver([_row()])

    result = resolver.resolve(source_isin="091160")

    assert result.isin is None
    assert result.method == "unresolved"
    assert result.reason is not None and "not a valid ISIN" in result.reason


def test_reviewed_kstr_crosswalk_resolves_from_repository_freeze() -> None:
    resolver = IdentifierResolver(load_crosswalk(REPOSITORY_CROSSWALK))

    assert resolver.resolve(local_key_type="nyse_ticker", local_key="kstr") == ResolutionResult(
        isin="US5007676944", method="crosswalk", reason=None
    )
    assert resolver.resolve(local_key_type="lse_ticker", local_key="KSTR").isin == "IE00BKPJY434"
    assert resolver.resolve(local_key_type="hkex_code", local_key="3191").isin == "HK0000637832"
    assert resolver.resolve(local_key_type="hkex_code", local_key="9191").isin == "HK0000637832"


def test_unreviewed_row_is_ignored() -> None:
    resolver = IdentifierResolver([_row(reviewed_by="", reviewed_at="")])
    result = resolver.resolve(local_key_type="nyse_ticker", local_key="KSTR")
    assert result.method == "unresolved"

    half_reviewed = IdentifierResolver([_row(reviewed_by="reviewer", reviewed_at="")])
    assert half_reviewed.resolve(local_key_type="nyse_ticker", local_key="KSTR").method == "unresolved"


def test_krx_code_only_row_is_unresolved_for_isin_load() -> None:
    resolver = IdentifierResolver(
        [
            _row(
                local_key_type="krx_code",
                local_key="449450",
                local_name="PLUS K방산",
                standard_id_type="krx_code",
                standard_id="449450",
                standard_name="PLUS K Defense",
            )
        ]
    )

    result = resolver.resolve(local_key_type="krx_code", local_key="449450")

    assert result.isin is None
    assert result.method == "unresolved"
    assert result.reason is not None and "no reviewed ISIN crosswalk entry" in result.reason


def test_repository_plus_funds_stay_unresolved_for_isin_load() -> None:
    resolver = IdentifierResolver(load_crosswalk(REPOSITORY_CROSSWALK))

    for local_key in ("449450", "421320", "496770", "442580", "464920"):
        result = resolver.resolve(local_key_type="krx_code", local_key=local_key)
        assert result.isin is None
        assert result.method == "unresolved"


def test_unknown_local_key_is_unresolved() -> None:
    resolver = IdentifierResolver([_row()])

    result = resolver.resolve(local_key_type="nyse_ticker", local_key="NOPE")

    assert result == ResolutionResult(
        isin=None,
        method="unresolved",
        reason="no reviewed ISIN crosswalk entry for local key ('nyse_ticker', 'NOPE')",
    )


def test_no_identifier_supplied_is_unresolved() -> None:
    resolver = IdentifierResolver([_row()])

    result = resolver.resolve()

    assert result.isin is None
    assert result.method == "unresolved"
    assert result.reason is not None and "no identifier supplied" in result.reason


def test_names_are_never_accepted_as_lookup_keys() -> None:
    resolver = IdentifierResolver(
        [
            _row(),
            _row(
                entity_kind="company",
                local_key_type="krx_code",
                local_key="247540",
                local_name="EcoPro BM",
                standard_id_type="krx_code",
                standard_id="247540",
                standard_name="EcoPro BM",
            ),
        ]
    )

    by_name_key = resolver.resolve(local_key_type="name", local_key="KraneShares KSTR")
    assert by_name_key.method == "unresolved"
    assert by_name_key.isin is None

    by_local_name = resolver.resolve(local_key_type="local_name", local_key="EcoPro BM")
    assert by_local_name.method == "unresolved"

    name_as_source_isin = resolver.resolve(source_isin="KraneShares KSTR")
    assert name_as_source_isin.method == "unresolved"
    assert name_as_source_isin.reason is not None and "not a valid ISIN" in name_as_source_isin.reason


def test_malformed_reviewed_isin_row_raises() -> None:
    with pytest.raises(ValueError, match=r"malformed standard_id"):
        _ = IdentifierResolver([_row(standard_id="NOTANISIN")])


def test_conflicting_reviewed_isin_mappings_raise() -> None:
    with pytest.raises(ValueError, match=r"Conflicting"):
        _ = IdentifierResolver([_row(), _row(standard_id="IE00BKPJY434")])


def test_resolve_fund_and_resolve_constituent_alias_resolve() -> None:
    resolver = IdentifierResolver(load_crosswalk(REPOSITORY_CROSSWALK))
    kwargs: dict[str, str] = {"local_key_type": "nyse_ticker", "local_key": "kstr"}

    assert resolver.resolve_fund(**kwargs) == resolver.resolve(**kwargs)
    assert resolver.resolve_constituent(**kwargs) == resolver.resolve(**kwargs)
    assert resolver.resolve_fund(source_isin="us5007676944").method == "source_isin"
