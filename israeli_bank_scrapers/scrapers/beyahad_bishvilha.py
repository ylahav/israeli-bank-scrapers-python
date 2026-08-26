"""Port of src/scrapers/beyahad-bishvilha.ts"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from ..constants import (
    DOLLAR_CURRENCY,
    DOLLAR_CURRENCY_SYMBOL,
    EURO_CURRENCY,
    EURO_CURRENCY_SYMBOL,
    SHEKEL_CURRENCY,
    SHEKEL_CURRENCY_SYMBOL,
)
from ..helpers.debug import get_debug
from ..helpers.elements_interactions import page_eval, page_eval_all, wait_until_element_found
from ..helpers.transactions import filter_old_transactions, get_raw_transaction
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Page

debug = get_debug("beyahadBishvilha")

DATE_FORMAT = "%d/%m/%y"
LOGIN_URL = "https://www.hist.org.il/login"
SUCCESS_URL = "https://www.hist.org.il/"
CARD_URL = "https://www.hist.org.il/card/balanceAndUses"


@dataclass
class BeyahadBishvilhaCredentials:
    id: str
    password: str


def _get_amount_data(amount_str: str) -> dict:
    cleaned = amount_str.replace(",", "")
    if SHEKEL_CURRENCY_SYMBOL in cleaned:
        return {"amount": float(cleaned.replace(SHEKEL_CURRENCY_SYMBOL, "")), "currency": SHEKEL_CURRENCY}
    if DOLLAR_CURRENCY_SYMBOL in cleaned:
        return {"amount": float(cleaned.replace(DOLLAR_CURRENCY_SYMBOL, "")), "currency": DOLLAR_CURRENCY}
    if EURO_CURRENCY_SYMBOL in cleaned:
        return {"amount": float(cleaned.replace(EURO_CURRENCY_SYMBOL, "")), "currency": EURO_CURRENCY}
    parts = cleaned.split(" ")
    return {"amount": float(parts[1]), "currency": parts[0]}


def _convert_transactions(txns: list[dict], options: ScraperOptions) -> list[Transaction]:
    debug.debug("convert %d raw transactions to official Transaction structure", len(txns))
    result = []
    for txn in txns:
        charged = _get_amount_data(txn.get("chargedAmount") or "")
        processed_date = datetime.strptime(txn["date"], DATE_FORMAT).isoformat() + "Z"
        t = Transaction(
            type=TransactionTypes.normal,
            status=TransactionStatuses.completed,
            date=processed_date,
            processed_date=processed_date,
            original_amount=charged["amount"],
            original_currency=charged["currency"],
            charged_amount=charged["amount"],
            charged_currency=charged["currency"],
            description=txn.get("description") or "",
            memo="",
            identifier=txn.get("identifier"),
        )
        if options.include_raw_transaction:
            t.raw_transaction = get_raw_transaction(txn)
        result.append(t)
    return result


async def _fetch_transactions(page: "Page", options: ScraperOptions) -> TransactionsAccount:
    await page.goto(CARD_URL)
    await wait_until_element_found(page, ".react-loading.hide", only_visible=False)
    default_start = date.today() - timedelta(days=365)
    start_date = options.start_date or default_start
    start_moment = max(default_start, start_date)

    account_number = await page_eval(
        page,
        ".wallet-details div:nth-of-type(2)",
        None,
        "(el) => el.innerText.replace('\u05de\u05e1\u05e4\u05e8 \u05db\u05e8\u05d8\u05d9\u05e1 ', '')",
    )
    balance_str = await page_eval(
        page, ".wallet-details div:nth-of-type(4) > span:nth-of-type(2)", None, "(el) => el.innerText"
    )

    debug.debug("fetch raw transactions from page")
    raw_transactions = await page_eval_all(
        page,
        ".transaction-container, .transaction-component-container",
        [],
        """(items) => items.map((el) => {
            const columns = el.querySelectorAll('.transaction-item > span');
            if (columns.length === 7) {
                return {
                    date: columns[0].innerText,
                    identifier: columns[1].innerText,
                    description: columns[3].innerText,
                    type: columns[5].innerText,
                    chargedAmount: columns[6].innerText,
                };
            }
            return null;
        })""",
    )
    debug.debug("fetched %d raw transactions from page", len(raw_transactions or []))

    account_transactions = _convert_transactions([t for t in (raw_transactions or []) if t], options)

    debug.debug("filter out old transactions")
    enable_filter = options.output_data.enable_transactions_filter_by_date if options.output_data else True
    if enable_filter or True:
        start_iso = start_moment.isoformat() + "T00:00:00.000Z"
        txns = filter_old_transactions(account_transactions, start_iso, False)
    else:
        txns = account_transactions

    return TransactionsAccount(
        account_number=account_number,
        balance=_get_amount_data(balance_str or "")["amount"],
        txns=txns,
    )


def _get_possible_login_results() -> dict[str, list]:
    return {
        LoginResults.success: [SUCCESS_URL],
        LoginResults.change_password: [],  # TODO (matches upstream — not yet known)
        LoginResults.invalid_password: [],  # TODO
        LoginResults.unknown_error: [],  # TODO
    }


def _create_login_fields(credentials: BeyahadBishvilhaCredentials) -> list[dict[str, str]]:
    return [
        {"selector": "#loginId", "value": credentials.id},
        {"selector": "#loginPassword", "value": credentials.password},
    ]


class BeyahadBishvilhaScraper(BaseScraperWithBrowser[BeyahadBishvilhaCredentials]):
    DEFAULT_VIEWPORT = {"width": 1500, "height": 800}

    def get_login_options(self, credentials: BeyahadBishvilhaCredentials) -> LoginOptions:
        async def _submit() -> None:
            button = await self.page.query_selector('xpath=//button[contains(., "\u05d4\u05ea\u05d7\u05d1\u05e8")]')
            if button:
                await button.click()

        return LoginOptions(
            login_url=LOGIN_URL,
            fields=_create_login_fields(credentials),
            submit_button_selector=_submit,
            possible_results=_get_possible_login_results(),
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        account = await _fetch_transactions(self.page, self.options)
        return ScraperScrapingResult(success=True, accounts=[account])
