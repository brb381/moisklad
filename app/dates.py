from __future__ import annotations

import calendar
from datetime import date, datetime, time


def parse_month(value: str) -> tuple[date, date]:
    try:
        year, month = map(int, value.split("-", 1))
        start = date(year, month, 1)
    except Exception as exc:
        raise ValueError("month must use YYYY-MM format") from exc

    last_day = calendar.monthrange(start.year, start.month)[1]
    return start, date(start.year, start.month, last_day)


def moysklad_moment_start(day: date) -> str:
    return datetime.combine(day, time.min).strftime("%Y-%m-%d %H:%M:%S")


def moysklad_moment_after(day: date) -> str:
    return datetime.combine(day, time.max).strftime("%Y-%m-%d %H:%M:%S")


def iter_days(start: date, end: date):
    ordinal = start.toordinal()
    while ordinal <= end.toordinal():
        yield date.fromordinal(ordinal)
        ordinal += 1
