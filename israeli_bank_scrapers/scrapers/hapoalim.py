"""Port of src/scrapers/hapoalim.ts"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional

from ..helpers.debug import get_debug
from ..helpers.fetch import fetch_get_within_page, fetch_post_within_page
from ..helpers.navigation import wait_for_redirect
from ..helpers.transactions import get_raw_transaction
from ..helpers.waiting import wait_until
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Page

debug = get_debug("hapoalim")

DATE_FORMAT = "%Y%m%d"


@dataclass
class HapoalimCredentials:
    userCode: str  # noqa: N815 (matches SCRAPERS metadata field name)
    password: str


def _convert_transactions(txns: list[dict], options: ScraperOptions) -> list[Transaction]:
    result = []
    for txn in txns:
        is_outbound = txn.get("eventActivityTypeCode") == 2

        memo = ""
        beneficiary = txn.get("beneficiaryDetailsData")
        if beneficiary:
            memo_lines = []
            if beneficiary.get("partyHeadline"):
                memo_lines.append(beneficiary["partyHeadline"])
            if beneficiary.get("partyName"):
                memo_lines.append(f"{beneficiary['partyName']}.")
            if beneficiary.get("messageHeadline"):
                memo_lines.append(beneficiary["messageHeadline"])
            if beneficiary.get("messageDetail"):
                memo_lines.append(f"{beneficiary['messageDetail']}.")
            if memo_lines:
                memo = " ".join(memo_lines)

        # Hapoalim's API returns these as integers (e.g. 20260115), not
        # strings — moment.js in the original TS tolerates either; Python's
        # strptime does not, so coerce explicitly.
        event_date = (
            datetime.strptime(str(txn["eventDate"]), DATE_FORMAT).isoformat() + "Z" if txn.get("eventDate") else ""
        )
        value_date = (
            datetime.strptime(str(txn["valueDate"]), DATE_FORMAT).isoformat() + "Z" if txn.get("valueDate") else ""
        )
        amount = txn["eventAmount"]

        t = Transaction(
            type=TransactionTypes.normal,
            identifier=txn.get("referenceNumber"),
            date=event_date,
            processed_date=value_date,
            original_amount=-amount if is_outbound else amount,
            original_currency="ILS",
            charged_amount=-amount if is_outbound else amount,
            description=txn.get("activityDescription") or "",
            status=TransactionStatuses.pending if txn.get("serialNumber") == 0 else TransactionStatuses.completed,
            memo=memo,
        )
        if options.include_raw_transaction:
            t.raw_transaction = get_raw_transaction(txn)
        result.append(t)
    return result


async def _get_rest_context(page: "Page") -> str:
    async def check():
        return await page.evaluate("() => !!window.bnhpApp")

    await wait_until(check, "waiting for app data load")
    result = await page.evaluate("() => window.bnhpApp.restContext")
    return result[1:]


async def _fetch_poalim_xsrf_within_page(page: "Page", url: str, page_uuid: str) -> Optional[dict]:
    cookies = await page.context.cookies()
    xsrf_cookie = next((c for c in cookies if c["name"] == "XSRF-TOKEN"), None)
    headers: dict[str, str] = {}
    if xsrf_cookie is not None:
        headers["X-XSRF-TOKEN"] = xsrf_cookie["value"]
    headers["pageUuid"] = page_uuid
    headers["uuid"] = str(uuid.uuid4())
    headers["Content-Type"] = "application/json;charset=UTF-8"
    return await fetch_post_within_page(page, url, {}, headers)


async def _get_extra_scrap(txns_result: dict, base_url: str, page: "Page", account_number: str) -> dict:
    import asyncio

    async def _enrich(transaction: dict) -> dict:
        pfm_details = transaction.get("pfmDetails")
        serial_number = transaction.get("serialNumber")
        if serial_number != 0 and pfm_details:
            url = f"{base_url}{pfm_details}&accountId={account_number}&lang=he"
            extra = await fetch_get_within_page(page, url) or []
            if extra:
                txn_number = extra[0].get("transactionNumber")
                if txn_number:
                    return {**transaction, "referenceNumber": txn_number, "additionalInformation": extra}
        return transaction

    updated = await asyncio.gather(*[_enrich(t) for t in txns_result.get("transactions", [])])
    return {"transactions": list(updated)}


async def _get_account_transactions(
    base_url: str,
    api_site_url: str,
    page: "Page",
    account_number: str,
    start_date: str,
    end_date: str,
    additional_transaction_information: bool,
    options: ScraperOptions,
) -> list[Transaction]:
    txns_url = (
        f"{api_site_url}/current-account/transactions?accountId={account_number}"
        f"&numItemsPerPage=1000&retrievalEndDate={end_date}&retrievalStartDate={start_date}&sortCode=1"
    )
    txns_result = await _fetch_poalim_xsrf_within_page(page, txns_url, "/current-account/transactions")

    final_result = txns_result
    if additional_transaction_information and txns_result and txns_result.get("transactions"):
        final_result = await _get_extra_scrap(txns_result, base_url, page, account_number)

    return _convert_transactions((final_result or {}).get("transactions") or [], options)


async def _get_account_balance(api_site_url: str, page: "Page", account_number: str) -> Optional[float]:
    url = f"{api_site_url}/current-account/composite/balanceAndCreditLimit?accountId={account_number}&view=details&lang=he"
    result = await fetch_get_within_page(page, url)
    return (result or {}).get("currentBalance")


async def _fetch_account_data(page: "Page", base_url: str, options: ScraperOptions) -> ScraperScrapingResult:
    rest_context = await _get_rest_context(page)
    api_site_url = f"{base_url}/{rest_context}"
    account_data_url = f"{base_url}/ServerServices/general/accounts"

    debug.debug("fetching accounts data")
    accounts_info = await fetch_get_within_page(page, account_data_url) or []
    open_accounts = [a for a in accounts_info if a.get("accountClosingReasonCode") == 0]
    debug.debug("got %d open accounts from %d total accounts", len(open_accounts), len(accounts_info))

    default_start = date.today() - timedelta(days=365 - 1)
    start_date = options.start_date or default_start
    start_moment = max(default_start, start_date)

    start_date_str = start_moment.strftime(DATE_FORMAT)
    end_date_str = date.today().strftime(DATE_FORMAT)

    accounts: list[TransactionsAccount] = []
    for account in open_accounts:
        account_number = f"{account['bankNumber']}-{account['branchNumber']}-{account['accountNumber']}"
        balance = await _get_account_balance(api_site_url, page, account_number)
        txns = await _get_account_transactions(
            base_url,
            api_site_url,
            page,
            account_number,
            start_date_str,
            end_date_str,
            options.additional_transaction_information,
            options,
        )
        accounts.append(TransactionsAccount(account_number=account_number, balance=balance, txns=txns))

    debug.debug("fetching ended")
    return ScraperScrapingResult(success=True, accounts=accounts)


def _get_possible_login_results(base_url: str) -> dict[str, list]:
    return {
        LoginResults.success: [
            f"{base_url}/portalserver/HomePage",
            f"{base_url}/ng-portals-bt/rb/he/homepage",
            f"{base_url}/ng-portals/rb/he/homepage",
        ],
        LoginResults.invalid_password: [
            f"{base_url}/AUTHENTICATE/LOGON?flow=AUTHENTICATE&state=LOGON&errorcode=1.6&callme=false"
        ],
        LoginResults.change_password: [
            f"{base_url}/MCP/START?flow=MCP&state=START&expiredDate=null",
            re.compile(r"/ABOUTTOEXPIRE/START", re.I),
        ],
    }


def _create_login_fields(credentials: HapoalimCredentials) -> list[dict[str, str]]:
    return [
        {"selector": "#userCode", "value": credentials.userCode},
        {"selector": "#password", "value": credentials.password},
    ]


class HapoalimScraper(BaseScraperWithBrowser[HapoalimCredentials]):
    @property
    def base_url(self) -> str:
        return "https://login.bankhapoalim.co.il"

    def get_login_options(self, credentials: HapoalimCredentials) -> LoginOptions:
        return LoginOptions(
            login_url=f"{self.base_url}/cgi-bin/poalwwwc?reqName=getLogonPage",
            fields=_create_login_fields(credentials),
            submit_button_selector=".login-btn",
            post_action=lambda: wait_for_redirect(self.page),
            possible_results=_get_possible_login_results(self.base_url),
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        return await _fetch_account_data(self.page, self.base_url, self.options)
