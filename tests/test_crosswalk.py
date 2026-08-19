# pyright: reportMissingTypeStubs=false
from __future__ import annotations

from pathlib import Path

import pytest

from mirae_asset_graph.ingest.crosswalk import (
    CROSSWALK_FIELDS,
    CrosswalkRow,
    detect_name_only_merge,
    group_by_standard_id,
    is_reviewed,
    load_crosswalk,
    mapping_key,
    to_payload,
)

FIXTURE_LINES = [
    "security,sse_code,688256,EXAMPLE_Cambricon,isin,CNE1000041K3,Cambricon Technologies Corporation Limited,https://www.sse.com.cn/star/en/marketdata/snapshot/c/5485110.shtml,reviewer,2026-08-19",
    "company,dart_corp_name,EcoPro BM,EXAMPLE_EcoProBM,krx_code,247540,EcoPro BM Co. Ltd.,https://dart.fss.or.kr/,reviewer,2026-08-19",
    "fund,krx_ticker,091160,EXAMPLE_KODEX_Semiconductor,isin,KR7091160005,KODEX Semiconductor,https://data.krx.co.kr/,,",
    "fund,krx_ticker,391160,EXAMPLE_KODEX_Semiconductor_F,isin,KR7091160005,KODEX Semiconductor,https://data.krx.co.kr/,reviewer,2026-08-19",
]


def _write_crosswalk(path: Path, lines: list[str]) -> Path:
    _ = path.write_text("\n".join([",".join(CROSSWALK_FIELDS), *lines]) + "\n", encoding="utf-8")
    return path


def _fixture_path(tmp_path: Path) -> Path:
    return _write_crosswalk(tmp_path / "contest_entities.csv", FIXTURE_LINES)


def _row(**overrides: str) -> CrosswalkRow:
    values: dict[str, str] = {field: "" for field in CROSSWALK_FIELDS}
    values.update(
        {
            "entity_kind": "security",
            "local_key_type": "isin",
            "local_key": "US0000000001",
            "standard_id_type": "isin",
            "standard_id": "US0000000001",
            "standard_name": "Duplicate Entity",
        }
    )
    values.update(overrides)
    return CrosswalkRow(**values)


def test_load_crosswalk_parses_rows_and_review_flags(tmp_path: Path) -> None:
    rows = load_crosswalk(_fixture_path(tmp_path))

    assert [row.entity_kind for row in rows] == ["security", "company", "fund", "fund"]
    assert [row.standard_id for row in rows] == ["CNE1000041K3", "247540", "KR7091160005", "KR7091160005"]
    assert [is_reviewed(row) for row in rows] == [True, True, False, True]
    assert not is_reviewed(_row(reviewed_by="reviewer"))
    assert not is_reviewed(_row(reviewed_at="2026-08-19"))


def test_load_crosswalk_missing_standard_id_raises_with_row_number(tmp_path: Path) -> None:
    path = _write_crosswalk(
        tmp_path / "invalid.csv",
        [
            "security,sse_code,688256,EXAMPLE_Cambricon,isin,CNE1000041K3,Cambricon,,,",
            "security,sse_code,999999,EXAMPLE_Broken,isin,,Broken Inc.,,,",
        ],
    )

    with pytest.raises(ValueError, match=r"row 3.*standard_id"):
        _ = load_crosswalk(path)


def test_group_by_standard_id_merges_same_isin_fund_rows(tmp_path: Path) -> None:
    groups = group_by_standard_id(load_crosswalk(_fixture_path(tmp_path)))

    assert set(groups) == {"isin:CNE1000041K3", "krx_code:247540", "isin:KR7091160005"}
    merged = groups["isin:KR7091160005"]
    assert {row.local_key for row in merged} == {"091160", "391160"}


def test_detect_name_only_merge_flags_disjoint_identifiers_only(tmp_path: Path) -> None:
    assert detect_name_only_merge(load_crosswalk(_fixture_path(tmp_path))) == []

    flagged = detect_name_only_merge(
        [
            _row(standard_id_type="isin", standard_id="US0000000001"),
            _row(standard_id_type="krx_code", standard_id="123456"),
        ]
    )
    assert flagged == ["isin:US0000000001|krx_code:123456"]


def test_mapping_key_normalizes_identifiers_not_names(tmp_path: Path) -> None:
    cambricon, ecopro, kodex, _ = load_crosswalk(_fixture_path(tmp_path))

    assert mapping_key(cambricon) == ("security", "sse_code", "688256")
    assert mapping_key(ecopro) == ("company", "dart_corp_name", "EcoPro BM")
    assert mapping_key(kodex) == ("fund", "krx_ticker", "091160")
    assert mapping_key(_row(local_key=" kr7091160005 ")) == ("security", "isin", "KR7091160005")
    assert mapping_key(_row(local_key_type="ticker", local_key="kodex", standard_id_type="fund_code")) == (
        "security",
        "ticker",
        "KODEX",
    )


def test_to_payload_keys_are_exactly_csv_fields(tmp_path: Path) -> None:
    for row in load_crosswalk(_fixture_path(tmp_path)):
        assert set(to_payload(row)) == set(CROSSWALK_FIELDS)
    assert to_payload(_row(source_url="https://example.com"))["source_url"] == "https://example.com"
