"""Port of src/scrapers/discount.ts"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from ..errors import ScraperErrorTypes
from ..helpers.elements_interactions import wait_until_element_found
from ..helpers.fetch import fetch_get_within_page
from ..helpers.navigation import get_current_url, wait_for_redirect
from ..helpers.transactions import get_raw_transaction
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Page

BASE_URL = "https://start.telebank.co.il"
DATE_FORMAT = "%Y%m%d"


@dataclass
class DiscountCredentials:
    id: str
    password: str
    num: str


def _convert_transactions(
    txns: list[dict] | None, status: TransactionStatuses, options: ScraperOptions
) -> list[Transaction]:
    if not txns:
        return []
    from datetime import datetime

    result = []
    for txn in txns:
        op_date = datetime.strptime(str(txn["OperationDate"]), DATE_FORMAT).isoformat() + "Z"
        value_date = datetime.strptime(str(txn["ValueDate"]), DATE_FORMAT).isoformat() + "Z"
        t = Transaction(
            type=TransactionTypes.normal,
            identifier=txn.get("OperationNumber"),
            date=op_date,
            processed_date=value_date,
            original_amount=txn["OperationAmount"],
            original_currency="ILS",
            charged_amount=txn["OperationAmount"],
            description=txn.get("OperationDescriptionToDisplay") or "",
            status=status,
        )
        if options.include_raw_transaction:
            t.raw_transaction = get_raw_transaction(txn)
        result.append(t)
    return result


async def _fetch_account_data(page: "Page", options: ScraperOptions) -> ScraperScrapingResult:
    api_site_url = f"{BASE_URL}/Titan/gatewayAPI"
    account_data_url = f"{api_site_url}/userAccountsData"
    account_info = await fetch_get_within_page(page, account_data_url)

    if not account_info:
        return ScraperScrapingResult(success=False, error_type=ScraperErrorTypes.generic, error_message="failed to get account data")

    default_start = date.today() - timedelta(days=365 - 2)
    start_date = options.start_date or default_start
    start_moment = max(default_start, start_date)
    start_date_str = start_moment.strftime(DATE_FORMAT)

    accounts = [acc["NewAccountInfo"]["AccountID"] for acc in account_info["UserAccountsData"]["UserAccounts"]]
    accounts_data: list[TransactionsAccount] = []

    for account_number in accounts:
        txns_url = (
            f"{api_site_url}/lastTransactions/{account_number}/Date"
            f"?IsCategoryDescCode=True&IsTransactionDetails=True&IsEventNames=True"
            f"&IsFutureTransactionFlag=True&FromDate={start_date_str}"
        )
        txns_result = await fetch_get_within_page(page, txns_url)
        if not txns_result or txns_result.get("Error") or not txns_result.get("CurrentAccountLastTransactions"):
            error_msg = txns_result["Error"]["MsgText"] if txns_result and txns_result.get("Error") else "unknown error"
            return ScraperScrapingResult(success=False, error_type=ScraperErrorTypes.generic, error_message=error_msg)

        current = txns_result["CurrentAccountLastTransactions"]
        completed = _convert_transactions(current.get("OperationEntry"), TransactionStatuses.completed, options)
        raw_future = (current.get("FutureTransactionsBlock") or {}).get("FutureTransactionEntry") or []
        pending = _convert_transactions(raw_future, TransactionStatuses.pending, options)

        accounts_data.append(
            TransactionsAccount(
                account_number=account_number,
                balance=current["CurrentAccountInfo"]["AccountBalance"],
                txns=[*completed, *pending],
            )
        )

    return ScraperScrapingResult(success=True, accounts=accounts_data)


async def _navigate_or_error_label(page: "Page") -> None:
    # Discount's post-login redirect is client-side (Angular SPA route change),
    # not a full page load — wait_for_navigation's "wait for current load state"
    # check resolves instantly with nothing to wait for and lets us check the URL
    # before the real redirect has happened (same failure mode fixed in
    # visa_cal.py's post_action). Poll for an actual URL change instead.
    try:
        await wait_for_redirect(page, timeout=20.0)
    except Exception:
        try:
            await wait_until_element_found(page, "#general-error", only_visible=False, timeout=0.1)
        except Exception:
            pass


def _get_possible_login_results() -> dict[str, list[str]]:
    return {
        LoginResults.success: [
            f"{BASE_URL}/apollo/retail/#/MY_ACCOUNT_HOMEPAGE",
            f"{BASE_URL}/apollo/retail2/#/MY_ACCOUNT_HOMEPAGE",
            f"{BASE_URL}/apollo/retail2/",
            f"{BASE_URL}/apollo/retail3/#/MY_ACCOUNT_HOMEPAGE",
            f"{BASE_URL}/apollo/retail3/",
        ],
        LoginResults.invalid_password: [f"{BASE_URL}/apollo/core/templates/lobby/masterPage.html#/LOGIN_PAGE"],
        LoginResults.change_password: [f"{BASE_URL}/apollo/core/templates/lobby/masterPage.html#/PWD_RENEW"],
    }


def _create_login_fields(credentials: DiscountCredentials) -> list[dict[str, str]]:
    return [
        {"selector": "#tzId", "value": credentials.id},
        {"selector": "#tzPassword", "value": credentials.password},
        {"selector": "#aidnum", "value": credentials.num},
    ]


class DiscountScraper(BaseScraperWithBrowser[DiscountCredentials]):
    LOGIN_URL = f"{BASE_URL}/login/#/LOGIN_PAGE"

    def get_login_options(self, credentials: DiscountCredentials) -> LoginOptions:
        return LoginOptions(
            login_url=self.LOGIN_URL,
            check_readiness=lambda: wait_until_element_found(self.page, "#tzId"),
            fields=_create_login_fields(credentials),
            submit_button_selector=".sendBtn",
            post_action=lambda: _navigate_or_error_label(self.page),
            possible_results=_get_possible_login_results(),
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        return await _fetch_account_data(self.page, self.options)
