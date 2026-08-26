"""Port of src/helpers/dates.ts"""

from __future__ import annotations

from datetime import date


def _start_of_month(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return d.replace(year=year, month=month, day=1)


def get_all_month_moments(start_date: date, future_months: int = 0) -> list[date]:
    """Return the first-of-month date for every month from `start_date` through
    `future_months` months after the current month (inclusive).
    """
    month = _start_of_month(start_date)
    last_month = _start_of_month(date.today())
    if future_months and future_months > 0:
        last_month = _add_months(last_month, future_months)

    all_months: list[date] = []
    while month <= last_month:
        all_months.append(month)
        month = _add_months(month, 1)
    return all_months
