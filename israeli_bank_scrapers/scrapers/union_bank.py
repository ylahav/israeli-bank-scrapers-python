"""Port of src/scrapers/union-bank.ts"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from ..constants import SHEKEL_CURRENCY
from ..helpers.elements_interactions import (
    click_button,
    dropdown_elements,
    dropdown_select,
    element_present_on_page,
    fill_input,
    page_eval_all,
    wait_until_element_found,
)
from ..helpers.navigation import wait_for_navigation
from ..helpers.transactions import get_raw_transaction
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Page

BASE_URL = "https://hb.unionbank.co.il"
TRANSACTIONS_URL = f"{BASE_URL}/eBanking/Accounts/ExtendedActivity.aspx#/"
DATE_FORMAT = "%d/%m/%y"
NO_TRANSACTION_IN_DATE_RANGE_TEXT = "\u05dc\u05d0 \u05e7\u05d9\u05d9\u05de\u05d5\u05ea \u05ea\u05e0\u05d5\u05e2\u05d5\u05ea \u05de\u05ea\u05d0\u05d9\u05de\u05d5\u05ea \u05e2\u05dc \u05e4\u05d9 \u05d4\u05e1\u05d9\u05e0\u05d5\u05df \u05e9\u05d4\u05d5\u05d2\u05d3\u05e8"
DATE_HEADER = "\u05ea\u05d0\u05e8\u05d9\u05da"
DESCRIPTION_HEADER = "\u05ea\u05d9\u05d0\u05d5\u05e8"
REFERENCE_HEADER = "\u05d0\u05e1\u05de\u05db\u05ea\u05d0"
DEBIT_HEADER = "\u05d7\u05d5\u05d1\u05d4"
CREDIT_HEADER = "\u05d6\u05db\u05d5\u05ea"
PENDING_TRANSACTIONS_TABLE_ID = "trTodayActivityNapaTableUpper"
COMPLETED_TRANSACTIONS_TABLE_ID = "ctlActivityTable"
ERROR_MESSAGE_CLASS = "errInfo"
ACCOUNTS_DROPDOWN_SELECTOR = "select#ddlAccounts_m_ddl"


@dataclass
class UnionBankCredentials:
    username: str
    password: str


def _get_possible_login_results() -> dict[str, list]:
    return {
        LoginResults.success: [re.compile(r"eBanking/Accounts", re.I)],
        LoginResults.invalid_password: [re.compile(r"InternalSite/CustomUpdate/leumi/LoginPage\.ASP", re.I)],
    }


def _create_login_fields(credentials: UnionBankCredentials) -> list[dict[str, str]]:
    return [
        {"selector": "#uid", "value": credentials.username},
        {"selector": "#password", "value": credentials.password},
    ]


def _get_amount_data(amount_str: str) -> float:
    return float(amount_str.replace(",", ""))


def _get_txn_amount(txn: dict) -> float:
    try:
        credit = _get_amount_data(txn["credit"])
    except (ValueError, KeyError):
        credit = 0.0
    try:
        debit = _get_amount_data(txn["debit"])
    except (ValueError, KeyError):
        debit = 0.0
    return credit - debit


def _convert_transactions(txns: list[dict], options: ScraperOptions) -> list[Transaction]:
    result = []
    for txn in txns:
        converted_date = datetime.strptime(txn["date"], DATE_FORMAT).isoformat() + "Z"
        converted_amount = _get_txn_amount(txn)
        t = Transaction(
            type=TransactionTypes.normal,
            identifier=int(txn["reference"]) if txn.get("reference") else None,
            date=converted_date,
            processed_date=converted_date,
            original_amount=converted_amount,
            original_currency=SHEKEL_CURRENCY,
            charged_amount=converted_amount,
            status=txn["status"],
            description=txn["description"],
            memo=txn.get("memo"),
        )
        if options.include_raw_transaction:
            t.raw_transaction = get_raw_transaction(txn)
        result.append(t)
    return result


def _extract_transaction_details(tds: list[str], headers: dict[str, int], status: TransactionStatuses) -> dict:
    def get(col: str) -> str:
        idx = headers.get(col)
        return (tds[idx] if idx is not None and idx < len(tds) else "").strip()

    return {
        "status": status,
        "date": get(DATE_HEADER),
        "description": get(DESCRIPTION_HEADER),
        "reference": get(REFERENCE_HEADER),
        "debit": get(DEBIT_HEADER),
        "credit": get(CREDIT_HEADER),
        "memo": "",
    }


def _is_expanded_desc_row(row: dict) -> bool:
    return row.get("id") == "rowAdded"


def _handle_transaction_row(txns: list[dict], headers: dict[str, int], row: dict, status: TransactionStatuses) -> None:
    if _is_expanded_desc_row(row):
        if not txns:
            raise Exception("internal union-bank error")
        last = txns[-1]
        last["description"] = f"{last['description']} {row['innerTds'][0]}"
    else:
        txns.append(_extract_transaction_details(row["innerTds"], headers, status))


async def _get_transactions_table_headers(page: "Page", table_type_id: str) -> dict[str, int]:
    header_objs = await page_eval_all(
        page,
        f"#WorkSpaceBox #{table_type_id} tr[class='header'] th",
        [],
        "(ths) => ths.map((th, index) => ({ text: th.innerText.trim(), index }))",
    )
    result = {}
    for obj in header_objs or []:
        result[obj["text"]] = obj["index"]
    return result


async def _extract_transactions_from_table(page: "Page", table_type_id: str, status: TransactionStatuses) -> list[dict]:
    headers = await _get_transactions_table_headers(page, table_type_id)
    rows = await page_eval_all(
        page,
        f"#WorkSpaceBox #{table_type_id} tr[class]:not([class='header'])",
        [],
        "(trs) => trs.map((tr) => ({ id: tr.getAttribute('id') || '', "
        "innerTds: Array.from(tr.getElementsByTagName('td')).map((td) => td.innerText) }))",
    )
    txns: list[dict] = []
    for row in rows or []:
        _handle_transaction_row(txns, headers, row, status)
    return txns


async def _is_no_transaction_in_date_range_error(page: "Page") -> bool:
    if await element_present_on_page(page, f".{ERROR_MESSAGE_CLASS}"):
        from ..helpers.elements_interactions import page_eval

        error_text = await page_eval(page, f".{ERROR_MESSAGE_CLASS}", "", "(el) => el.innerText")
        return error_text.strip() == NO_TRANSACTION_IN_DATE_RANGE_TEXT
    return False


async def _choose_account(page: "Page", account_id: str) -> None:
    if await element_present_on_page(page, ACCOUNTS_DROPDOWN_SELECTOR):
        await dropdown_select(page, ACCOUNTS_DROPDOWN_SELECTOR, account_id)


async def _search_by_dates(page: "Page", start_date: date) -> None:
    await dropdown_select(page, "select#ddlTransactionPeriod", "004")
    await wait_until_element_found(page, "select#ddlTransactionPeriod")
    await fill_input(page, "input#dtFromDate_textBox", start_date.strftime(DATE_FORMAT))
    await click_button(page, "input#btnDisplayDates")
    await wait_for_navigation(page)


async def _get_account_number(page: "Page") -> str:
    from ..helpers.elements_interactions import page_eval

    text = await page_eval(page, '#ddlAccounts_m_ddl option[selected="selected"]', "", "(el) => el.innerText")
    return text.replace("/", "_")


async def _expand_transactions_table(page: "Page") -> None:
    if await element_present_on_page(page, "a[id*='lnkCtlExpandAll']"):
        await click_button(page, "a[id*='lnkCtlExpandAll']")


async def _scrape_transactions_from_table(page: "Page", options: ScraperOptions) -> list[Transaction]:
    pending_txns = await _extract_transactions_from_table(page, PENDING_TRANSACTIONS_TABLE_ID, TransactionStatuses.pending)
    completed_txns = await _extract_transactions_from_table(
        page, COMPLETED_TRANSACTIONS_TABLE_ID, TransactionStatuses.completed
    )
    return _convert_transactions([*pending_txns, *completed_txns], options)


async def _get_account_transactions(page: "Page", options: ScraperOptions) -> list[Transaction]:
    tasks = [
        asyncio.ensure_future(wait_until_element_found(page, f"#{COMPLETED_TRANSACTIONS_TABLE_ID}", only_visible=False)),
        asyncio.ensure_future(wait_until_element_found(page, f".{ERROR_MESSAGE_CLASS}", only_visible=False)),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        t.exception()

    if await _is_no_transaction_in_date_range_error(page):
        return []

    await _expand_transactions_table(page)
    return await _scrape_transactions_from_table(page, options)


async def _fetch_account_data(page: "Page", start_date: date, account_id: str, options: ScraperOptions) -> TransactionsAccount:
    await _choose_account(page, account_id)
    await _search_by_dates(page, start_date)
    account_number = await _get_account_number(page)
    txns = await _get_account_transactions(page, options)
    return TransactionsAccount(account_number=account_number, txns=txns)


async def _fetch_accounts(page: "Page", start_date: date, options: ScraperOptions) -> list[TransactionsAccount]:
    accounts: list[TransactionsAccount] = []
    accounts_list = await dropdown_elements(page, ACCOUNTS_DROPDOWN_SELECTOR)
    for account in accounts_list:
        if account["value"] != "-1":  # Skip "All accounts" option
            accounts.append(await _fetch_account_data(page, start_date, account["value"], options))
    return accounts


async def _wait_for_post_login(page: "Page") -> None:
    tasks = [
        asyncio.ensure_future(wait_until_element_found(page, "#signoff", only_visible=True)),
        asyncio.ensure_future(wait_until_element_found(page, "#restore", only_visible=True)),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        t.exception()


class UnionBankScraper(BaseScraperWithBrowser[UnionBankCredentials]):
    def get_login_options(self, credentials: UnionBankCredentials) -> LoginOptions:
        return LoginOptions(
            login_url=BASE_URL,
            fields=_create_login_fields(credentials),
            submit_button_selector="#enter",
            post_action=lambda: _wait_for_post_login(self.page),
            possible_results=_get_possible_login_results(),
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        default_start = date.today() - timedelta(days=365 - 1)
        start_date = self.options.start_date or default_start
        start_moment = max(default_start, start_date)

        await self.navigate_to(TRANSACTIONS_URL)
        accounts = await _fetch_accounts(self.page, start_moment, self.options)
        return ScraperScrapingResult(success=True, accounts=accounts)
