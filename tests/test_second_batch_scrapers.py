"""Layer 1 (cont.): pure-logic tests for the second batch of ported scrapers
(Mizrahi, Union, the Beinleumi group, Yahav, One Zero, Behatsdaa, Beyahad
Bishvilha). Synthetic API/DOM-shaped data, no browser or network.
"""

from datetime import date

import pytest

from israeli_bank_scrapers.interface import ScraperOptions
from israeli_bank_scrapers.transactions import TransactionStatuses, TransactionTypes


@pytest.fixture
def options():
    return ScraperOptions(company_id="test", start_date=date.today())


class TestBeinleumiGroupConversion:
    def test_converts_credit_transaction(self, options):
        from israeli_bank_scrapers.scrapers.base_beinleumi_group import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "date": "15/01/2026",
                    "reference": "123",
                    "credit": "50.00",
                    "debit": "",
                    "status": TransactionStatuses.completed,
                    "description": "deposit",
                    "memo": "",
                }
            ],
            options,
        )
        assert txn.original_amount == 50.0
        assert txn.identifier == 123

    def test_converts_debit_transaction(self, options):
        from israeli_bank_scrapers.scrapers.base_beinleumi_group import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "date": "15/01/2026",
                    "reference": "124",
                    "credit": "",
                    "debit": "30.00",
                    "status": TransactionStatuses.completed,
                    "description": "withdrawal",
                    "memo": "",
                }
            ],
            options,
        )
        assert txn.original_amount == -30.0

    def test_all_four_banks_share_the_base(self):
        from israeli_bank_scrapers.scrapers.beinleumi import BeinleumiScraper
        from israeli_bank_scrapers.scrapers.massad import MassadScraper
        from israeli_bank_scrapers.scrapers.otsar_hahayal import OtsarHahayalScraper
        from israeli_bank_scrapers.scrapers.pagi import PagiScraper
        from israeli_bank_scrapers.scrapers.base_beinleumi_group import BeinleumiGroupBaseScraper

        for cls in (BeinleumiScraper, MassadScraper, OtsarHahayalScraper, PagiScraper):
            assert issubclass(cls, BeinleumiGroupBaseScraper)
            assert cls.BASE_URL  # each sets its own
            assert cls.LOGIN_URL != BeinleumiScraper.LOGIN_URL or cls is BeinleumiScraper


class TestUnionBankConversion:
    def test_converts_transaction(self, options):
        from israeli_bank_scrapers.scrapers.union_bank import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "date": "15/01/26",
                    "reference": "456",
                    "credit": "",
                    "debit": "30.00",
                    "status": TransactionStatuses.completed,
                    "description": "withdrawal",
                    "memo": "",
                }
            ],
            options,
        )
        assert txn.original_amount == -30.0

    def test_expanded_desc_row_appends_to_previous(self):
        from israeli_bank_scrapers.scrapers.union_bank import _handle_transaction_row

        txns = []
        headers = {
            "\u05ea\u05d0\u05e8\u05d9\u05da": 0,
            "\u05ea\u05d9\u05d0\u05d5\u05e8": 1,
            "\u05d0\u05e1\u05de\u05db\u05ea\u05d0": 2,
            "\u05d7\u05d5\u05d1\u05d4": 3,
            "\u05d6\u05db\u05d5\u05ea": 4,
        }
        _handle_transaction_row(
            txns, headers, {"id": "", "innerTds": ["15/01/26", "desc", "1", "10", ""]}, TransactionStatuses.completed
        )
        _handle_transaction_row(txns, headers, {"id": "rowAdded", "innerTds": ["extra detail"]}, TransactionStatuses.completed)
        assert len(txns) == 1
        assert txns[0]["description"] == "desc extra detail"

    def test_expanded_desc_row_without_prior_raises(self):
        from israeli_bank_scrapers.scrapers.union_bank import _handle_transaction_row

        with pytest.raises(Exception, match="internal union-bank error"):
            _handle_transaction_row([], {}, {"id": "rowAdded", "innerTds": ["x"]}, TransactionStatuses.completed)


class TestYahavConversion:
    def test_handle_transaction_row_strips_non_digits_from_reference(self):
        from israeli_bank_scrapers.scrapers.yahav import _handle_transaction_row

        txns = []
        _handle_transaction_row(txns, {"innerDivs": ["x", "15/01/2026", "ref#789", "desc", "", "75.50"]})
        assert txns[0]["reference"] == "789"
        assert txns[0]["credit"] == "75.50"

    def test_convert_transactions(self, options):
        from israeli_bank_scrapers.scrapers.yahav import _convert_transactions

        [txn] = _convert_transactions(
            [
                {
                    "date": "15/01/2026",
                    "reference": "789",
                    "memo": "",
                    "description": "desc",
                    "debit": "",
                    "credit": "75.50",
                    "status": TransactionStatuses.completed,
                }
            ],
            options,
        )
        assert txn.original_amount == 75.5
        assert txn.identifier == 789


class TestBehatsdaaConversion:
    def test_variant_to_transaction(self, options):
        from israeli_bank_scrapers.scrapers.behatsdaa import _variant_to_transaction

        variant = {
            "customerPrice": 42.0,
            "orderDate": "2026-01-15T10:00:00Z",
            "tTransactionID": "abc",
            "name": "Gym",
            "variantName": "Monthly",
        }
        txn = _variant_to_transaction(variant, options)
        assert txn.original_amount == -42.0  # price flipped negative (expense)
        assert txn.description == "Gym"
        assert txn.memo == "Monthly"
        assert txn.date == "2026-01-15"


class TestBeyahadBishvilhaConversion:
    def test_shekel_amount_parsing(self):
        from israeli_bank_scrapers.scrapers.beyahad_bishvilha import _get_amount_data

        result = _get_amount_data("\u20aa120.00")
        assert result == {"amount": 120.0, "currency": "ILS"}

    def test_dollar_amount_parsing(self):
        from israeli_bank_scrapers.scrapers.beyahad_bishvilha import _get_amount_data

        result = _get_amount_data("$50.00")
        assert result == {"amount": 50.0, "currency": "USD"}

    def test_convert_transactions(self, options):
        from israeli_bank_scrapers.scrapers.beyahad_bishvilha import _convert_transactions

        [txn] = _convert_transactions(
            [{"date": "15/01/26", "description": "Purchase", "identifier": "xyz", "chargedAmount": "\u20aa120.00"}],
            options,
        )
        assert txn.original_currency == "ILS"
        assert txn.original_amount == 120.0


class TestMizrahiConversion:
    def test_get_transaction_identifier_single_installment(self):
        from israeli_bank_scrapers.scrapers.mizrahi import _get_transaction_identifier

        row = {"MC02AsmahtaMekoritEZ": "12345", "TransactionNumber": "1"}
        assert _get_transaction_identifier(row) == 12345

    def test_get_transaction_identifier_multi_installment(self):
        from israeli_bank_scrapers.scrapers.mizrahi import _get_transaction_identifier

        row = {"MC02AsmahtaMekoritEZ": "12345", "TransactionNumber": "2"}
        assert _get_transaction_identifier(row) == "12345-2"

    def test_get_transaction_identifier_missing_returns_none(self):
        from israeli_bank_scrapers.scrapers.mizrahi import _get_transaction_identifier

        assert _get_transaction_identifier({"MC02AsmahtaMekoritEZ": ""}) is None

    @pytest.mark.asyncio
    async def test_convert_transactions(self, options):
        from israeli_bank_scrapers.scrapers.mizrahi import _convert_transactions

        async def get_more_details_stub(row):
            return {"entries": {}, "memo": None}

        row = {
            "MC02AsmahtaMekoritEZ": "12345",
            "TransactionNumber": "1",
            "MC02PeulaTaaEZ": "2026-01-15T00:00:00",
            "MC02SchumEZ": 88.5,
            "MC02TnuaTeurEZ": "Payment",
            "IsTodayTransaction": False,
        }
        [txn] = await _convert_transactions([row], get_more_details_stub, False, options)
        assert txn.original_amount == 88.5
        assert txn.status == TransactionStatuses.completed

    @pytest.mark.asyncio
    async def test_pending_if_today_transaction_flag(self, options):
        from israeli_bank_scrapers.scrapers.mizrahi import _convert_transactions

        async def get_more_details_stub(row):
            return {"entries": {}, "memo": None}

        row = {
            "MC02AsmahtaMekoritEZ": "1",
            "TransactionNumber": "1",
            "MC02PeulaTaaEZ": "2026-01-15T00:00:00",
            "MC02SchumEZ": 10.0,
            "MC02TnuaTeurEZ": "x",
            "IsTodayTransaction": True,
        }
        [txn] = await _convert_transactions([row], get_more_details_stub, True, options)
        assert txn.status == TransactionStatuses.pending


class TestOneZeroSanitizeHebrew:
    def _make_scraper(self, options):
        from israeli_bank_scrapers.scrapers.one_zero import OneZeroScraper

        return OneZeroScraper(options)

    def test_no_marker_just_strips(self, options):
        scraper = self._make_scraper(options)
        assert scraper._sanitize_hebrew("  hello world  ") == "hello world"

    def test_reverses_hebrew_substrings_with_marker(self, options):
        scraper = self._make_scraper(options)
        # Construct: marker + reversed hebrew word "\u05e9\u05dc\u05d5\u05dd" (shalom) stored backwards
        reversed_word = "\u05dd\u05d5\u05dc\u05e9"  # reverse of שלום
        text = f"\u202d{reversed_word}"
        result = scraper._sanitize_hebrew(text)
        assert result == "\u05e9\u05dc\u05d5\u05dd"


class TestOneZeroCredentialsShape:
    def test_otp_long_term_token_only(self):
        from israeli_bank_scrapers.scrapers.one_zero import OneZeroCredentials

        creds = OneZeroCredentials(email="e", password="p", otpLongTermToken="tok")
        assert creds.otpLongTermToken == "tok"
        assert creds.otpCodeRetriever is None

    def test_defaults_are_none(self):
        from israeli_bank_scrapers.scrapers.one_zero import OneZeroCredentials

        creds = OneZeroCredentials(email="e", password="p")
        assert creds.otpCodeRetriever is None
        assert creds.phoneNumber is None
        assert creds.otpLongTermToken is None
