"""Port of src/helpers/transactions.ts"""

from __future__ import annotations

import copy
import dataclasses
from datetime import datetime, timedelta
from typing import Any

from ..transactions import Transaction, TransactionTypes


def _is_normal_transaction(txn: Transaction) -> bool:
    return txn is not None and txn.type == TransactionTypes.normal


def _is_installment_transaction(txn: Transaction) -> bool:
    return txn is not None and txn.type == TransactionTypes.installments


def _is_non_initial_installment_transaction(txn: Transaction) -> bool:
    return _is_installment_transaction(txn) and bool(txn.installments) and txn.installments.number > 1


def _is_initial_installment_transaction(txn: Transaction) -> bool:
    return _is_installment_transaction(txn) and bool(txn.installments) and txn.installments.number == 1


def _add_months(iso_date: str, months: int) -> str:
    dt = datetime.fromisoformat(iso_date.replace("Z", "+00:00"))
    # simple month arithmetic (matches moment's add('month'), no need for calendar libs here)
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, 28)  # avoid month-length edge cases; dates here are transaction dates, not billing-critical
    dt = dt.replace(year=year, month=month, day=day)
    return dt.isoformat().replace("+00:00", "Z")


def fix_installments(txns: list[Transaction]) -> list[Transaction]:
    """Shift non-initial installment transactions' date forward by (installment number - 1) months."""
    result = []
    for txn in txns:
        cloned = dataclasses.replace(txn)
        if _is_installment_transaction(cloned) and _is_non_initial_installment_transaction(cloned) and cloned.installments:
            cloned.date = _add_months(cloned.date, cloned.installments.number - 1)
        result.append(cloned)
    return result


def sort_transactions_by_date(txns: list[Transaction]) -> list[Transaction]:
    return sorted(txns, key=lambda t: t.date)


def filter_old_transactions(
    txns: list[Transaction],
    start_date: str,
    combine_installments: bool,
) -> list[Transaction]:
    def keep(txn: Transaction) -> bool:
        combine_needed_and_initial_or_normal = combine_installments and (
            _is_normal_transaction(txn) or _is_initial_installment_transaction(txn)
        )
        return (not combine_installments and start_date <= txn.date) or (
            combine_needed_and_initial_or_normal and start_date <= txn.date
        )

    return [t for t in txns if keep(t)]


def _remove_empty_values(value: Any) -> Any:
    if isinstance(value, list):
        return [_remove_empty_values(item) for item in value]
    if isinstance(value, dict):
        return {
            k: _remove_empty_values(v)
            for k, v in value.items()
            if not (v is None or v == "" or (isinstance(v, list) and len(v) == 0))
        }
    return value


def get_raw_transaction(data: Any, transaction: Transaction | None = None) -> Any:
    """Clean `data` (drop null/empty values) and merge it into an existing raw_transaction, if any."""
    current = transaction.raw_transaction if transaction else None
    cleaned = _remove_empty_values(copy.deepcopy(data))

    if not current:
        return cleaned
    if isinstance(current, list):
        return [*current, cleaned]
    return [current, cleaned]
