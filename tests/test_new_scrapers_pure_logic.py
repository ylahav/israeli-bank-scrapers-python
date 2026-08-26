"""Layer 1 (cont.): pure-logic tests for the transaction-conversion functions
of the newly ported scrapers (hapoalim, discount, mercantile, isracard, amex,
max, visaCal). These don't touch a browser or network — they feed synthetic
API-shaped dicts through each scraper's private conversion function and check
the resulting Transaction objects.
"""

from datetime import date

import pytest

from israeli_bank_scrapers.interface import ScraperOptions
from israeli_bank_scrapers.transactions import TransactionStatuses, TransactionTypes


@pytest.fixture
def options():
    return ScraperOptions(company_id="test", start_date=date.today())


class TestDiscountConversion:
    def test_converts_basic_transaction(self, options):
        from israeli_bank_scrapers.scrapers.discount import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "OperationNumber": 1,
                    "OperationDate": "20260115",
                    "ValueDate": "20260116",
                    "OperationAmount": 55.5,
                    "OperationDescriptionToDisplay": "coffee",
                }
            ],
            TransactionStatuses.completed,
            options,
        )
        assert txn.date == "2026-01-15T00:00:00Z"
        assert txn.processed_date == "2026-01-16T00:00:00Z"
        assert txn.original_amount == 55.5
        assert txn.description == "coffee"

    def test_handles_integer_date_fields(self, options):
        """Same class of bug found live in Hapoalim (int date fields from a
        JSON API where Python's strptime expects a string) — Discount shares
        Hapoalim's exact %Y%m%d format, so it's equally at risk."""
        from israeli_bank_scrapers.scrapers.discount import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "OperationNumber": 1,
                    "OperationDate": 20260115,
                    "ValueDate": 20260116,
                    "OperationAmount": 55.5,
                    "OperationDescriptionToDisplay": "coffee",
                }
            ],
            TransactionStatuses.completed,
            options,
        )
        assert txn.date == "2026-01-15T00:00:00Z"

    def test_empty_list_returns_empty(self, options):
        from israeli_bank_scrapers.scrapers.discount import _convert_transactions

        assert _convert_transactions(None, TransactionStatuses.completed, options) == []


class TestHapoalimConversion:
    def test_outbound_transaction_is_negative(self, options):
        from israeli_bank_scrapers.scrapers.hapoalim import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "eventActivityTypeCode": 2,
                    "eventAmount": 120,
                    "eventDate": "20260110",
                    "valueDate": "20260111",
                    "referenceNumber": 5,
                    "activityDescription": "withdrawal",
                    "serialNumber": 1,
                }
            ],
            options,
        )
        assert txn.original_amount == -120
        assert txn.status == TransactionStatuses.completed

    def test_inbound_transaction_is_positive(self, options):
        from israeli_bank_scrapers.scrapers.hapoalim import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "eventActivityTypeCode": 1,
                    "eventAmount": 300,
                    "eventDate": "20260110",
                    "valueDate": "20260111",
                    "referenceNumber": 6,
                    "activityDescription": "deposit",
                    "serialNumber": 1,
                }
            ],
            options,
        )
        assert txn.original_amount == 300

    def test_serial_number_zero_is_pending(self, options):
        from israeli_bank_scrapers.scrapers.hapoalim import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "eventActivityTypeCode": 1,
                    "eventAmount": 10,
                    "eventDate": "20260110",
                    "valueDate": "20260111",
                    "referenceNumber": 7,
                    "activityDescription": "x",
                    "serialNumber": 0,
                }
            ],
            options,
        )
        assert txn.status == TransactionStatuses.pending

    def test_handles_integer_date_fields(self, options):
        """Regression test: Hapoalim's live API returns eventDate/valueDate
        as integers (e.g. 20260110), not strings — this broke in production
        testing since Python's strptime is stricter than JS's moment()."""
        from israeli_bank_scrapers.scrapers.hapoalim import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "eventActivityTypeCode": 1,
                    "eventAmount": 10,
                    "eventDate": 20260110,
                    "valueDate": 20260111,
                    "referenceNumber": 7,
                    "activityDescription": "x",
                    "serialNumber": 1,
                }
            ],
            options,
        )
        assert txn.date == "2026-01-10T00:00:00Z"
        assert txn.processed_date == "2026-01-11T00:00:00Z"


class TestMaxConversion:
    def test_maps_normal_plan_transaction(self, options):
        from israeli_bank_scrapers.scrapers.max import _map_transaction

        raw = {
            "shortCardNumber": "1234",
            "paymentDate": "2026-02-01T00:00:00Z",
            "purchaseDate": "2026-01-15T00:00:00Z",
            "actualPaymentAmount": 100.0,
            "paymentCurrency": 376,
            "originalCurrency": "ILS",
            "originalAmount": 100.0,
            "planName": "\u05e8\u05d2\u05d9\u05dc\u05d4",
            "planTypeId": 5,
            "comments": "",
            "merchantName": "Shop ",
            "categoryId": 1,
            "dealData": {"arn": "abc"},
        }
        txn = _map_transaction(raw, options)
        assert txn.description == "Shop"  # stripped
        assert txn.type == TransactionTypes.normal
        assert txn.status == TransactionStatuses.completed
        assert txn.original_amount == -100.0

    def test_pending_when_payment_date_missing(self, options):
        from israeli_bank_scrapers.scrapers.max import _map_transaction

        raw = {
            "shortCardNumber": "1234",
            "paymentDate": None,
            "purchaseDate": "2026-01-15T00:00:00Z",
            "actualPaymentAmount": 50.0,
            "paymentCurrency": 376,
            "originalCurrency": "ILS",
            "originalAmount": 50.0,
            "planName": "\u05e8\u05d2\u05d9\u05dc\u05d4",
            "planTypeId": 5,
            "comments": "",
            "merchantName": "Shop",
            "categoryId": 1,
            "dealData": {"arn": "xyz"},
        }
        txn = _map_transaction(raw, options)
        assert txn.status == TransactionStatuses.pending

    def test_unknown_plan_name_falls_back_to_plan_type_id(self, options):
        from israeli_bank_scrapers.scrapers.max import _get_transaction_type

        assert _get_transaction_type("some unrecognized plan", 2) == TransactionTypes.installments
        assert _get_transaction_type("some unrecognized plan", 5) == TransactionTypes.normal

    def test_unknown_plan_name_and_type_id_raises(self):
        from israeli_bank_scrapers.scrapers.max import _get_transaction_type

        with pytest.raises(Exception, match="Unknown transaction type"):
            _get_transaction_type("totally unknown", 999)


class TestIsracardAmexConversion:
    def test_converts_domestic_transaction(self, options):
        from israeli_bank_scrapers.scrapers.base_isracard_amex import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "dealSumType": "0",
                    "voucherNumberRatz": "12345",
                    "voucherNumberRatzOutbound": "99999",
                    "dealSumOutbound": False,
                    "currencyId": '\u05e9"\u05d7',
                    "currentPaymentCurrency": None,
                    "dealSum": 80,
                    "fullPurchaseDate": "15/01/2026",
                    "fullSupplierNameHeb": "Store",
                    "moreInfo": "",
                    "paymentSum": 80,
                    "paymentSumOutbound": 0,
                }
            ],
            "2026-01-01T00:00:00Z",
            options,
        )
        assert txn.original_currency == "ILS"
        assert txn.original_amount == -80
        assert txn.description == "Store"

    def test_filters_out_zero_voucher_transactions(self, options):
        from israeli_bank_scrapers.scrapers.base_isracard_amex import _convert_transactions

        result = _convert_transactions(
            [
                {
                    "dealSumType": "0",
                    "voucherNumberRatz": "000000000",
                    "voucherNumberRatzOutbound": "99999",
                    "dealSumOutbound": False,
                    "currencyId": "ILS",
                    "dealSum": 10,
                    "fullPurchaseDate": "15/01/2026",
                    "fullSupplierNameHeb": "X",
                    "paymentSum": 10,
                }
            ],
            "2026-01-01T00:00:00Z",
            options,
        )
        assert result == []

    def test_installments_detected_from_more_info(self):
        from israeli_bank_scrapers.scrapers.base_isracard_amex import _get_installments_info

        info = _get_installments_info({"moreInfo": "\u05ea\u05e9\u05dc\u05d5\u05dd 2 \u05de\u05ea\u05d5\u05da 5"})
        assert info is not None
        assert info.number == 2
        assert info.total == 5

    def test_no_installments_when_keyword_absent(self):
        from israeli_bank_scrapers.scrapers.base_isracard_amex import _get_installments_info

        assert _get_installments_info({"moreInfo": "regular purchase"}) is None

    def test_handles_string_amount_fields(self, options):
        """Regression test: Amex's live API returns dealSum/paymentSum as
        strings, not numbers — Python's unary `-` (unlike JS) can't negate a
        string directly, so this crashed with
        'bad operand type for unary -: str' before being fixed."""
        from israeli_bank_scrapers.scrapers.base_isracard_amex import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "dealSumType": "0",
                    "voucherNumberRatz": "12345",
                    "voucherNumberRatzOutbound": "99999",
                    "dealSumOutbound": "0",  # string "0" — must NOT be treated as outbound
                    "currencyId": "ILS",
                    "dealSum": "80.50",  # string, not float
                    "paymentSum": "80.50",
                    "fullPurchaseDate": "15/01/2026",
                    "fullSupplierNameHeb": "Store",
                    "moreInfo": "",
                }
            ],
            "2026-01-01T00:00:00Z",
            options,
        )
        assert txn.original_amount == -80.5
        assert txn.charged_amount == -80.5

    def test_string_zero_deal_sum_outbound_is_not_outbound(self, options):
        """Python's bool("0") is True (non-empty string) even though the
        value numerically means "domestic, not outbound" — is_outbound must
        be derived from the coerced float, not a raw bool() check."""
        from israeli_bank_scrapers.scrapers.base_isracard_amex import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "dealSumType": "0",
                    "voucherNumberRatz": "12345",
                    "voucherNumberRatzOutbound": "99999",
                    "dealSumOutbound": "0",
                    "currencyId": "ILS",
                    "dealSum": 50,
                    "paymentSum": 50,
                    "fullPurchaseDate": "15/01/2026",
                    "fullSupplierNameHeb": "DomesticStore",
                    "fullSupplierNameOutbound": "ShouldNotBeUsed",
                    "moreInfo": "",
                }
            ],
            "2026-01-01T00:00:00Z",
            options,
        )
        # description picks fullSupplierNameHeb (domestic path), not
        # fullSupplierNameOutbound — confirms is_outbound resolved to False
        assert txn.description == "DomesticStore"
        assert txn.original_amount == -50


class TestVisaCalConversion:
    def test_converts_completed_transaction(self, options):
        from israeli_bank_scrapers.scrapers.visa_cal import _convert_parsed_data_to_transactions

        data = [
            {
                "result": {
                    "bankAccounts": [
                        {
                            "debitDates": [
                                {
                                    "transactions": [
                                        {
                                            "trnAmt": 50,
                                            "trnTypeCode": "5",
                                            "trnPurchaseDate": "2026-01-10T00:00:00Z",
                                            "debCrdDate": "2026-02-01T00:00:00Z",
                                            "amtBeforeConvAndIndex": 50,
                                            "trnCurrencySymbol": "ILS",
                                            "debCrdCurrencySymbol": "ILS",
                                            "merchantName": "Cafe",
                                            "transTypeCommentDetails": [],
                                            "branchCodeDesc": "food",
                                        }
                                    ]
                                }
                            ],
                            "immidiateDebits": {"debitDays": []},
                        }
                    ]
                }
            }
        ]
        [txn] = _convert_parsed_data_to_transactions(data, None, options)
        assert txn.description == "Cafe"
        assert txn.charged_amount == -50
        assert txn.status == TransactionStatuses.completed
        assert txn.type == TransactionTypes.normal

    def test_pending_transaction_has_no_charged_currency(self, options):
        from israeli_bank_scrapers.scrapers.visa_cal import _convert_parsed_data_to_transactions

        pending_data = {
            "result": {
                "cardsList": [
                    {
                        "authDetalisList": [
                            {
                                "trnAmt": 30,
                                "trnTypeCode": "5",
                                "trnPurchaseDate": "2026-01-12T00:00:00Z",
                                "trnCurrencySymbol": "ILS",
                                "merchantName": "Kiosk",
                                "transTypeCommentDetails": [],
                                "branchCodeDesc": "misc",
                            }
                        ]
                    }
                ]
            }
        }
        [txn] = _convert_parsed_data_to_transactions([], pending_data, options)
        assert txn.status == TransactionStatuses.pending
        assert txn.charged_currency is None
