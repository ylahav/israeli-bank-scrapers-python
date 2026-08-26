"""Layer 1: pure-logic unit tests. No browser, no network — run these constantly."""

from datetime import date

import pytest

from israeli_bank_scrapers.helpers.transactions import (
    fix_installments,
    get_raw_transaction,
    sort_transactions_by_date,
    filter_old_transactions,
)
from israeli_bank_scrapers.helpers.waiting import wait_until, TimeoutError as WaitTimeoutError, sleep
from israeli_bank_scrapers.transactions import (
    Transaction,
    TransactionInstallments,
    TransactionStatuses,
    TransactionTypes,
)


def _txn(**overrides) -> Transaction:
    base = dict(
        type=TransactionTypes.normal,
        date="2026-01-15T00:00:00.000Z",
        processed_date="2026-01-15T00:00:00.000Z",
        original_amount=100.0,
        original_currency="ILS",
        charged_amount=100.0,
        description="test",
        status=TransactionStatuses.completed,
    )
    base.update(overrides)
    return Transaction(**base)


class TestFixInstallments:
    def test_shifts_non_initial_installment_forward(self):
        txn = _txn(type=TransactionTypes.installments, installments=TransactionInstallments(number=3, total=6))
        [fixed] = fix_installments([txn])
        assert fixed.date == "2026-03-15T00:00:00Z"

    def test_leaves_initial_installment_unchanged(self):
        txn = _txn(type=TransactionTypes.installments, installments=TransactionInstallments(number=1, total=6))
        [fixed] = fix_installments([txn])
        assert fixed.date == txn.date

    def test_leaves_normal_transaction_unchanged(self):
        txn = _txn()
        [fixed] = fix_installments([txn])
        assert fixed.date == txn.date

    def test_does_not_mutate_input(self):
        txn = _txn(type=TransactionTypes.installments, installments=TransactionInstallments(number=2, total=6))
        original_date = txn.date
        fix_installments([txn])
        assert txn.date == original_date


class TestSortTransactionsByDate:
    def test_sorts_ascending(self):
        a = _txn(date="2026-03-01T00:00:00.000Z")
        b = _txn(date="2026-01-01T00:00:00.000Z")
        c = _txn(date="2026-02-01T00:00:00.000Z")
        result = sort_transactions_by_date([a, b, c])
        assert [t.date for t in result] == [b.date, c.date, a.date]


class TestFilterOldTransactions:
    def test_filters_by_start_date_without_combine(self):
        old = _txn(date="2025-01-01T00:00:00.000Z")
        new = _txn(date="2026-06-01T00:00:00.000Z")
        result = filter_old_transactions([old, new], "2026-01-01T00:00:00.000Z", combine_installments=False)
        assert result == [new]

    def test_combine_installments_keeps_normal_and_initial(self):
        normal = _txn(date="2026-06-01T00:00:00.000Z")
        initial = _txn(
            date="2026-06-01T00:00:00.000Z",
            type=TransactionTypes.installments,
            installments=TransactionInstallments(number=1, total=3),
        )
        result = filter_old_transactions([normal, initial], "2026-01-01T00:00:00.000Z", combine_installments=True)
        assert normal in result and initial in result


class TestGetRawTransaction:
    def test_removes_empty_values(self):
        assert get_raw_transaction({"a": 1, "b": None, "c": "", "d": []}) == {"a": 1}

    def test_removes_empty_values_recursively(self):
        assert get_raw_transaction({"a": {"b": None, "c": 2}}) == {"a": {"c": 2}}

    def test_merges_into_existing_raw_transaction(self):
        txn = _txn(raw_transaction={"first": True})
        result = get_raw_transaction({"second": True}, txn)
        assert result == [{"first": True}, {"second": True}]

    def test_extends_existing_list(self):
        txn = _txn(raw_transaction=[{"first": True}])
        result = get_raw_transaction({"second": True}, txn)
        assert result == [{"first": True}, {"second": True}]


class TestWaitUntil:
    @pytest.mark.asyncio
    async def test_resolves_when_condition_becomes_true(self):
        counter = {"n": 0}

        async def condition():
            counter["n"] += 1
            return counter["n"] >= 3

        result = await wait_until(condition, "counting", timeout=2, interval=0.02)
        assert result is True
        assert counter["n"] == 3

    @pytest.mark.asyncio
    async def test_raises_timeout_error_when_never_true(self):
        async def never():
            return False

        with pytest.raises(WaitTimeoutError):
            await wait_until(never, "never", timeout=0.2, interval=0.02)

    @pytest.mark.asyncio
    async def test_propagates_exceptions_from_condition(self):
        async def boom():
            raise ValueError("kaboom")

        with pytest.raises(ValueError, match="kaboom"):
            await wait_until(boom, "boom", timeout=1, interval=0.02)
