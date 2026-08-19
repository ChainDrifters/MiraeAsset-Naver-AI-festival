from __future__ import annotations

import calendar
from datetime import date

DEFAULT_START = date(2026, 1, 11)
DEFAULT_END = date(2026, 7, 11)


def compute_missing(
    expected: dict[str, list[date]],
    loaded: set[tuple[str, date]],
) -> list[tuple[str, date]]:
    missing = {
        (source, window_date)
        for source, dates in expected.items()
        for window_date in dates
        if (source, window_date) not in loaded
    }
    return sorted(missing, key=lambda item: (item[0], item[1]))


def month_ends(start: date | None = None, end: date | None = None) -> list[date]:
    start = start or DEFAULT_START
    end = end or DEFAULT_END
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current = _add_month(current)
    return dates


def _add_month(value: date) -> date:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)
