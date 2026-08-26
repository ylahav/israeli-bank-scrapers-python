"""Port of src/scrapers/leumi.ts

This is the one fully worked-through scraper in this port, meant as a
template for porting the rest of eshaham/israeli-bank-scrapers' ~20 scrapers.
Bank Leumi's flow: log in, scrape each linked account's transactions via a
filtered-search POST endpoint, then scrape each account's savings deposits
via a JSON GET endpoint (both captured/replayed using the page's own fetch,
so they carry the live session's cookies).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from ..constants import SHEKEL_CURRENCY
from ..helpers.debug import get_debug
from ..helpers.elements_interactions import click_button, fill_input, page_eval_all, wait_until_element_found
from ..helpers.fetch import fetch_get_within_page
from ..helpers.navigation import wait_for_navigation
from ..helpers.transactions import get_raw_transaction
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Page

debug = get_debug("leumi")

BASE_URL = "https://hb2.bankleumi.co.il"
LOGIN_URL = "https://www.leumi.co.il/he"
TRANSACTIONS_URL = f"{BASE_URL}/eBanking/SO/SPA.aspx#/ts/BusinessAccountTrx?WidgetPar=1"
FILTERED_TRANSACTIONS_URL = f"{BASE_URL}/ChannelWCF/Broker.svc/ProcessRequest?moduleName=UC_SO_27_GetBusinessAccountTrx"
SAVINGS_URL = f"{BASE_URL}/uiapiproxy/v1/digital-retails/mobile/accounts/1/Deposits?operationList=true"

DATE_FORMAT = "%d.%m.%y"
ACCOUNT_BLOCKED_MSG = "\u05d4\u05de\u05e0\u05d5\u05d9 \u05d7\u05e1\u05d5\u05dd"
INVALID_PASSWORD_MSG = (
    "\u05d0\u05d7\u05d3 \u05d0\u05d5 \u05d9\u05d5\u05ea\u05e8 \u05de\u05e4\u05e8\u05d8\u05d9 \u05d4\u05d4\u05d6\u05d3\u05d4\u05d5\u05ea "
    "\u05e9\u05de\u05e1\u05e8\u05ea \u05e9\u05d2\u05d5\u05d9\u05d9\u05dd. \u05e0\u05d9\u05ea\u05df \u05dc\u05e0\u05e1\u05d5\u05ea \u05e9\u05d5\u05d1"
)
CHANGE_PASSWORD_MODAL_SELECTOR = 'form input[name="newPwd"]'


@dataclass
class LeumiCredentials:
    username: str
    password: str


def _get_possible_login_results() -> dict[str, list[Any]]:
    async def _is_invalid_password(page: "Page") -> bool:
        error_message = await page_eval_all(
            page,
            "svg#Capa_1",
            "",
            "(elements) => elements[0]?.parentElement?.children[1]?.innerText",
        )
        return bool(error_message) and error_message.startswith(INVALID_PASSWORD_MSG)

    async def _is_account_blocked(page: "Page") -> bool:
        # NOTICE - might not be relevant since the Leumi UI redesign (~Sep 2022)
        error_message = await page_eval_all(
            page,
            ".errHeader",
            "",
            "(labels) => labels[0]?.innerText",
        )
        return bool(error_message) and error_message.startswith(ACCOUNT_BLOCKED_MSG)

    async def _is_change_password(page: "Page") -> bool:
        return (await page.query_selector(CHANGE_PASSWORD_MODAL_SELECTOR)) is not None

    return {
        LoginResults.success: [re.compile(r"ebanking/SO/SPA\.aspx", re.I)],
        LoginResults.invalid_password: [_is_invalid_password],
        LoginResults.account_blocked: [_is_account_blocked],
        LoginResults.change_password: [_is_change_password],
    }


def _create_login_fields(credentials: LeumiCredentials) -> list[dict[str, str]]:
    return [
        {"selector": 'input[placeholder="\u05e9\u05dd \u05de\u05e9\u05ea\u05de\u05e9"]', "value": credentials.username},
        {"selector": 'input[placeholder="\u05e1\u05d9\u05e1\u05de\u05d4"]', "value": credentials.password},
    ]


def _extract_transactions_from_page(
    transactions: list[dict] | None,
    status: TransactionStatuses,
    options: ScraperOptions,
) -> list[Transaction]:
    if not transactions:
        return []

    result = []
    for raw in transactions:
        dt = datetime.fromisoformat(raw["DateUTC"].replace("Z", "+00:00")).replace(microsecond=0)
        iso_date = dt.isoformat().replace("+00:00", "Z")
        txn = Transaction(
            status=status,
            type=TransactionTypes.normal,
            date=iso_date,
            processed_date=iso_date,
            description=raw.get("Description") or "",
            identifier=raw.get("ReferenceNumberLong"),
            memo=raw.get("AdditionalData") or "",
            original_currency=SHEKEL_CURRENCY,
            charged_amount=raw["Amount"],
            original_amount=raw["Amount"],
        )
        if options.include_raw_transaction:
            txn.raw_transaction = get_raw_transaction(raw)
        result.append(txn)
    return result


def _remove_special_characters(s: str) -> str:
    return re.sub(r"[^0-9/-]", "", s)


async def _click_by_xpath(page: "Page", xpath: str) -> None:
    locator = page.locator(f"xpath={xpath}")
    await locator.first.wait_for(state="visible", timeout=30000)
    await locator.first.click()


async def _fetch_transactions_for_account(
    page: "Page",
    start_date: date,
    account_id: str,
    options: ScraperOptions,
) -> TransactionsAccount:
    # DEVELOPER NOTICE (kept from upstream): the account number received from the
    # server is altered at runtime for some accounts after 1-2 seconds, so we
    # need to hang the process for a short while.
    await asyncio.sleep(4)

    await wait_until_element_found(page, 'button[title="\u05d7\u05d9\u05e4\u05d5\u05e9 \u05de\u05ea\u05e7\u05d3\u05dd"]', only_visible=True)
    await click_button(page, 'button[title="\u05d7\u05d9\u05e4\u05d5\u05e9 \u05de\u05ea\u05e7\u05d3\u05dd"]')
    await wait_until_element_found(page, "bll-radio-button", only_visible=True)
    await click_button(page, "bll-radio-button:not([checked])")

    await wait_until_element_found(page, 'input[formcontrolname="txtInputFrom"]', only_visible=True)
    await fill_input(page, 'input[formcontrolname="txtInputFrom"]', start_date.strftime(DATE_FORMAT))

    # blur the "from" control, otherwise the search uses the previous value
    await page.focus("button[aria-label='\u05e1\u05e0\u05df']")

    async with page.expect_response(
        lambda r: r.url == FILTERED_TRANSACTIONS_URL and r.request.method == "POST"
    ) as response_info:
        await click_button(page, "button[aria-label='\u05e1\u05e0\u05df']")
    final_response = await response_info.value

    response_json = await final_response.json()
    account_number = _remove_special_characters(account_id.replace("/", "_"))

    import json as _json

    response = _json.loads(response_json["jsonResp"])

    pending_transactions = response.get("TodayTransactionsItems")
    transactions = response.get("HistoryTransactionsItems")
    balance = float(response["BalanceDisplay"]) if response.get("BalanceDisplay") else None

    pending_txns = _extract_transactions_from_page(pending_transactions, TransactionStatuses.pending, options)
    completed_txns = _extract_transactions_from_page(transactions, TransactionStatuses.completed, options)

    return TransactionsAccount(account_number=account_number, balance=balance, txns=[*pending_txns, *completed_txns])


async def _fetch_regular_accounts(
    scraper: "LeumiScraper",
    page: "Page",
    start_date: date,
    options: ScraperOptions,
) -> list[TransactionsAccount]:
    await scraper.navigate_to(TRANSACTIONS_URL)
    return await _fetch_transactions(page, start_date, options)


async def _get_savings_accounts(page: "Page", account_id: str) -> list[TransactionsAccount]:
    debug.debug("========== FETCHING SAVINGS ACCOUNTS ==========")
    debug.debug("Account: %s", account_id)

    accounts: list[TransactionsAccount] = []
    try:
        debug.debug("Trying savings URL: %s", SAVINGS_URL)
        savings_data = await fetch_get_within_page(page, SAVINGS_URL)
        deposits = (savings_data or {}).get("depositsAndSavingsItems") or []
        if not deposits:
            debug.debug("No savings accounts found for account %s", account_id)
            return []
        debug.debug("Found %d savings deposits", len(deposits))

        for deposit in deposits:
            balance = deposit["currentBalance"]
            savings_account_number = f"{account_id}-{deposit['depositId']}"
            accounts.append(
                TransactionsAccount(account_number=savings_account_number, savings_account=True, balance=balance, txns=[])
            )
            debug.debug(
                "Added savings account %s with balance %s (product: %s)",
                savings_account_number,
                balance,
                deposit.get("productName"),
            )
    except Exception as e:
        debug.debug("Error fetching savings accounts: %s", e)

    debug.debug("Returning %d savings accounts", len(accounts))
    return accounts


async def _fetch_transactions(page: "Page", start_date: date, options: ScraperOptions) -> list[TransactionsAccount]:
    accounts: list[TransactionsAccount] = []

    # see DEVELOPER NOTICE above
    await asyncio.sleep(4)

    account_ids: list[str] = await page.evaluate(
        "() => Array.from(document.querySelectorAll('app-masked-number-combo span.display-number-li'), "
        "e => e.textContent)"
    )

    if not account_ids:
        raise Exception("Failed to extract or parse the account number")

    for account_id in account_ids:
        if len(account_ids) > 1:
            await _click_by_xpath(page, '//*[contains(@class, "number") and contains(@class, "combo-inner")]')
            await _click_by_xpath(page, f'//span[contains(text(), "{account_id}")]')

        accounts.append(
            await _fetch_transactions_for_account(page, start_date, _remove_special_characters(account_id), options)
        )

    return accounts


async def _fetch_savings_accounts(
    page: "Page", regular_accounts: list[TransactionsAccount]
) -> list[TransactionsAccount]:
    all_savings: list[TransactionsAccount] = []
    for account in regular_accounts:
        try:
            savings = await _get_savings_accounts(page, account.account_number)
            all_savings.extend(savings)
            debug.debug("Added %d savings accounts to results", len(savings))
        except Exception as e:
            debug.debug("Error fetching savings accounts for %s: %s", account.account_number, e)
    return all_savings


async def _navigate_to_login(page: "Page") -> None:
    debug.debug("navigating directly to login page")
    await page.goto("https://hb2.bankleumi.co.il/authenticate/logon")
    debug.debug("waiting for page to be loaded (networkidle)")
    await wait_for_navigation(page, "networkidle")
    debug.debug("waiting for components of login to enter credentials")
    await asyncio.gather(
        wait_until_element_found(page, 'input[placeholder="\u05e9\u05dd \u05de\u05e9\u05ea\u05de\u05e9"]', only_visible=True),
        wait_until_element_found(page, 'input[placeholder="\u05e1\u05d9\u05e1\u05de\u05d4"]', only_visible=True),
        wait_until_element_found(page, 'button[type="submit"]', only_visible=True),
    )


async def _wait_for_post_login(page: "Page") -> None:
    # Playwright has no built-in Promise.race-of-selectors helper, so we poll:
    # whichever indicator (post-login nav, error text, or the change-password
    # modal) shows up first wins — mirroring Puppeteer's Promise.race here.
    candidates = [
        (wait_until_element_found(page, 'a[title="\u05d3\u05dc\u05d2 \u05dc\u05d7\u05e9\u05d1\u05d5\u05df"]', True, 60), "post_login_link"),
        (wait_until_element_found(page, "div.main-content", False, 60), "main_content"),
        (page.wait_for_selector(f'xpath=//div[contains(string(),"{INVALID_PASSWORD_MSG}")]'), "invalid_password"),
        (wait_until_element_found(page, CHANGE_PASSWORD_MODAL_SELECTOR, True, 60), "change_password"),
    ]
    tasks = [asyncio.ensure_future(c) for c, _ in candidates]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    # surface the first exception, if the winning task actually failed
    for task in done:
        task.exception()  # noqa: consume to avoid "exception never retrieved" warnings


class LeumiScraper(BaseScraperWithBrowser[LeumiCredentials]):
    def get_login_options(self, credentials: LeumiCredentials) -> LoginOptions:
        return LoginOptions(
            login_url=LOGIN_URL,
            fields=_create_login_fields(credentials),
            submit_button_selector="button[type='submit']",
            check_readiness=lambda: _navigate_to_login(self.page),
            post_action=lambda: _wait_for_post_login(self.page),
            possible_results=_get_possible_login_results(),
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        minimum_start = date.today() - timedelta(days=365 * 3 - 1)
        default_start = date.today() - timedelta(days=365 - 1)
        start_date = self.options.start_date or default_start
        start_date = max(minimum_start, start_date)

        accounts = await _fetch_regular_accounts(self, self.page, start_date, self.options)
        savings_accounts = await _fetch_savings_accounts(self.page, accounts)
        accounts.extend(savings_accounts)

        return ScraperScrapingResult(success=True, accounts=accounts)
