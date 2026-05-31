from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from PySide6.QtCore import QDate


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date
    swapped: bool = False


def qdate_to_date(qdate: QDate) -> date:
    if hasattr(qdate, "toPython"):
        return qdate.toPython()
    return date(qdate.year(), qdate.month(), qdate.day())


def normalize_date_range(start: date, end: date) -> DateRange:
    if start <= end:
        return DateRange(start=start, end=end, swapped=False)
    return DateRange(start=end, end=start, swapped=True)


def day_timestamp_bounds(start: date, end: date) -> tuple[int, int]:
    start_dt = datetime(start.year, start.month, start.day, 0, 0, 0)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59)
    return int(start_dt.timestamp()), int(end_dt.timestamp())

