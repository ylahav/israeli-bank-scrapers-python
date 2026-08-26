"""Layer 1 (cont.): the CLI protocol boundary — request parsing, credential
building, and JSON serialization. No subprocess/browser involved; these test
cli.py's internal functions directly.
"""

import json

import pytest

from israeli_bank_scrapers.credentials import build_credentials, credential_fields
from israeli_bank_scrapers.serialization import account_to_dict, scrape_result_to_dict
from israeli_bank_scrapers.transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from israeli_bank_scrapers.interface import ScraperScrapingResult


class TestCredentialsRegistry:
    def test_builds_leumi_credentials(self):
        creds = build_credentials("leumi", {"username": "u", "password": "p"})
        assert creds.username == "u"
        assert creds.password == "p"

    def test_builds_isracard_credentials_with_card6digits(self):
        creds = build_credentials("isracard", {"id": "1", "password": "p", "card6Digits": "123456"})
        assert creds.card6Digits == "123456"

    def test_raises_on_missing_field(self):
        with pytest.raises(ValueError, match="password"):
            build_credentials("leumi", {"username": "u"})

    def test_raises_on_unknown_company(self):
        with pytest.raises(ValueError, match="Unknown company_id"):
            build_credentials("not_a_real_bank", {})

    def test_ignores_extra_fields(self):
        # extra fields in the input dict beyond what the dataclass needs should be fine
        creds = build_credentials("leumi", {"username": "u", "password": "p", "extra": "ignored"})
        assert creds.username == "u"

    def test_credential_fields_matches_dataclass(self):
        assert set(credential_fields("leumi")) == {"username", "password"}
        assert set(credential_fields("isracard")) == {"id", "password", "card6Digits"}


class TestSerialization:
    def test_account_to_dict_shape(self):
        txn = Transaction(
            type=TransactionTypes.normal,
            date="2026-01-01T00:00:00Z",
            processed_date="2026-01-01T00:00:00Z",
            original_amount=-10.0,
            original_currency="ILS",
            charged_amount=-10.0,
            description="Coffee",
            status=TransactionStatuses.completed,
        )
        account = TransactionsAccount(account_number="123", balance=500.0, txns=[txn])
        result = account_to_dict(account)

        assert result["account_number"] == "123"
        assert result["balance"] == 500.0
        assert result["txns"][0]["type"] == "normal"  # enum -> its .value, not repr
        assert result["txns"][0]["status"] == "completed"
        assert result["txns"][0]["description"] == "Coffee"

    def test_scrape_result_success_shape(self):
        account = TransactionsAccount(account_number="1", txns=[])
        result = ScraperScrapingResult(success=True, accounts=[account])
        d = scrape_result_to_dict(result)
        assert d["success"] is True
        assert d["accounts"][0]["account_number"] == "1"
        assert d["error_type"] is None

    def test_scrape_result_is_json_serializable(self):
        account = TransactionsAccount(account_number="1", txns=[])
        result = ScraperScrapingResult(success=True, accounts=[account])
        d = scrape_result_to_dict(result)
        # must not raise — this is the actual contract the CLI relies on
        json.dumps(d)


class TestCliRequestParsing:
    def test_parse_options_defaults_start_date(self):
        from israeli_bank_scrapers.cli import _parse_options

        opts = _parse_options({"company_id": "leumi"})
        assert opts.company_id == "leumi"
        assert opts.start_date is not None

    def test_parse_options_uses_given_start_date(self):
        from datetime import date
        from israeli_bank_scrapers.cli import _parse_options

        opts = _parse_options({"company_id": "leumi", "start_date": "2026-03-15"})
        assert opts.start_date == date(2026, 3, 15)

    def test_parse_options_applies_allowed_option(self):
        from israeli_bank_scrapers.cli import _parse_options

        opts = _parse_options({"company_id": "leumi", "options": {"show_browser": True}})
        assert opts.show_browser is True

    def test_parse_options_rejects_unknown_option(self):
        from israeli_bank_scrapers.cli import _parse_options

        with pytest.raises(ValueError, match="Unknown option field"):
            _parse_options({"company_id": "leumi", "options": {"not_a_real_option": True}})
