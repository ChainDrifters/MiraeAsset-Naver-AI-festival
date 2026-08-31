from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import pytest
from neo4j import Driver
from openpyxl import Workbook

from mirae_asset_graph.cli import ORGANIZER_BASELINE_INPUT_DIR, _parser
from mirae_asset_graph.loader import FinancialProductsLoader, validate_organizer_schema_baseline
from mirae_asset_graph.model import DATASETS, validate_organizer_datarows_baseline


def _loader(input_dir: Path) -> FinancialProductsLoader:
    return FinancialProductsLoader(
        cast(Driver, object()),
        input_dir=input_dir,
        ontology_path=input_dir,
    )


def _touch(path: Path) -> Path:
    path.touch()
    return path


def _schema_workbook(path: Path, declaration: str | list[str] | None) -> Path:
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    if isinstance(declaration, str):
        worksheet["A1"] = declaration
    elif declaration is not None:
        for row_number, value in enumerate(declaration, 1):
            worksheet.cell(row=row_number, column=1, value=value)
    workbook.save(path)
    workbook.close()
    return path


def test_cli_default_input_dir_is_fixed_organizer_baseline() -> None:
    args = _parser().parse_args(["dry-run"])

    assert args.input_dir == ORGANIZER_BASELINE_INPUT_DIR


def test_cli_explicit_input_dir_overrides_default(tmp_path: Path) -> None:
    args = _parser().parse_args(["dry-run", "--input-dir", str(tmp_path)])

    assert args.input_dir == tmp_path


def test_accepts_organizer_20260711_datarows(tmp_path: Path) -> None:
    path = _touch(tmp_path / "PRBD01N001_20260711_datarows.xlsx")

    assert validate_organizer_datarows_baseline(path) == date(2026, 7, 11)
    assert _loader(tmp_path)._organizer_data_file(DATASETS[0]) == path


@pytest.mark.parametrize("stamp", ["20260822", "20260823"])
def test_rejects_later_organizer_datarows_dates(tmp_path: Path, stamp: str) -> None:
    path = _touch(tmp_path / f"PRBD01N001_{stamp}_datarows.xlsx")

    with pytest.raises(ValueError, match=r"2026-07-11.*20260711"):
        _ = validate_organizer_datarows_baseline(path)
    with pytest.raises(ValueError, match=stamp):
        _ = _loader(tmp_path)._organizer_data_file(DATASETS[0])


@pytest.mark.parametrize(
    "filename",
    [
        "PRBD01N001_datarows.xlsx",
        "PRBD01N001_latest_datarows.xlsx",
        "PRBD01N001_2026071_datarows.xlsx",
    ],
)
def test_rejects_missing_or_malformed_organizer_datarows_date(tmp_path: Path, filename: str) -> None:
    _touch(tmp_path / filename)

    with pytest.raises(ValueError, match=r"must include the fixed baseline date 20260711"):
        _ = _loader(tmp_path)._organizer_data_file(DATASETS[0])


def test_rejects_directory_with_baseline_and_later_organizer_file(tmp_path: Path) -> None:
    _touch(tmp_path / "PRBD01N001_20260711_datarows.xlsx")
    _touch(tmp_path / "PRBD01N001_20260822_datarows.xlsx")

    with pytest.raises(ValueError, match=r"Rejected organizer datarows files.*20260822"):
        _ = _loader(tmp_path)._organizer_data_file(DATASETS[0])


def test_rejects_impossible_calendar_organizer_datarows_date(tmp_path: Path) -> None:
    path = _touch(tmp_path / "PRBD01N001_20261340_datarows.xlsx")

    with pytest.raises(ValueError, match=r"malformed date"):
        _ = validate_organizer_datarows_baseline(path)


def test_accepts_organizer_schema_declaring_20260711(tmp_path: Path) -> None:
    path = _schema_workbook(
        tmp_path / "PRBD01N001_schema.xlsx",
        "[ 데이터 최종 추출일자 ] 2026-07-11",
    )

    assert validate_organizer_schema_baseline(path) == date(2026, 7, 11)


@pytest.mark.parametrize("declared", ["2026-08-22", "2026-08-23"])
def test_rejects_later_organizer_schema_extraction_dates(tmp_path: Path, declared: str) -> None:
    path = _schema_workbook(
        tmp_path / "PRBD01N001_schema.xlsx",
        f"[ 데이터 최종 추출일자 ] {declared}",
    )

    with pytest.raises(ValueError, match=declared):
        _ = validate_organizer_schema_baseline(path)


@pytest.mark.parametrize(
    "declaration",
    [
        None,
        "[ 데이터 최종 추출일자 ] latest",
        "데이터 최종 추출일자 2026-07-11",
        "[ 데이터 최종 추출일자 ] 2026-13-40",
    ],
)
def test_rejects_missing_or_malformed_organizer_schema_extraction_date(
    tmp_path: Path,
    declaration: str | None,
) -> None:
    path = _schema_workbook(tmp_path / "PRBD01N001_schema.xlsx", declaration)

    with pytest.raises(ValueError, match=r"must declare the fixed extraction date 2026-07-11|malformed"):
        _ = validate_organizer_schema_baseline(path)


def test_rejects_schema_with_baseline_and_later_extraction_dates(tmp_path: Path) -> None:
    path = _schema_workbook(
        tmp_path / "PRBD01N001_schema.xlsx",
        [
            "[ 데이터 최종 추출일자 ] 2026-07-11",
            "[ 데이터 최종 추출일자 ] 2026-08-22",
        ],
    )

    with pytest.raises(ValueError, match=r"2026-08-22"):
        _ = validate_organizer_schema_baseline(path)


def test_dry_run_validates_schema_before_reading_datarows(tmp_path: Path) -> None:
    _touch(tmp_path / "PRBD01N001_20260711_datarows.xlsx")
    _schema_workbook(
        tmp_path / "PRBD01N001_20260711_schema.xlsx",
        "[ 데이터 최종 추출일자 ] 2026-08-22",
    )

    with pytest.raises(ValueError, match=r"schema workbook extraction date.*2026-08-22"):
        _ = _loader(tmp_path).dry_run({"domestic_bonds"})
