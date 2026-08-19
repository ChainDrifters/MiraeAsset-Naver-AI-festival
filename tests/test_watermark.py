# pyright: reportMissingTypeStubs=false
from __future__ import annotations

from datetime import date

from mirae_asset_graph.ingest.watermark import compute_missing, month_ends


def test_compute_missing_returns_exact_source_date_gap() -> None:
    dates = month_ends(date(2026, 1, 11), date(2026, 5, 11))
    expected = {"holdings": dates, "control": dates[:3]}
    loaded = {
        ("holdings", date(2026, 1, 11)),
        ("holdings", date(2026, 5, 11)),
        ("control", date(2026, 1, 11)),
        ("control", date(2026, 2, 11)),
        ("control", date(2026, 3, 11)),
    }

    assert compute_missing(expected, loaded) == [
        ("holdings", date(2026, 2, 11)),
        ("holdings", date(2026, 3, 11)),
        ("holdings", date(2026, 4, 11)),
    ]


def test_month_ends_default_backfill_window() -> None:
    assert month_ends() == [
        date(2026, 1, 11),
        date(2026, 2, 11),
        date(2026, 3, 11),
        date(2026, 4, 11),
        date(2026, 5, 11),
        date(2026, 6, 11),
        date(2026, 7, 11),
    ]
