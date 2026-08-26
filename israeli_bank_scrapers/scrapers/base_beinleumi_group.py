"""Port of src/scrapers/base-beinleumi-group.ts

Shared by Beinleumi, Massad, Otsar Hahayal, and Pagi (see their thin
subclass files) — same DOM/table-scraping flow across the FIBI banking
group's shared platform, differing only in base URL. Supports both an "old"
and a "new" UI, since the bank has been mid-migration for a while upstream.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional

from ..constants import SHEKEL_CURRENCY, SHEKEL_CURRENCY_SYMBOL
from ..helpers.elements_interactions import (
    click_button,
    element_present_on_page,
    fill_input,
    page_eval_all,
    wait_until_element_found,
)
from ..helpers.navigation import wait_for_navigation
from ..helpers.transactions import get_raw_transaction
from ..helpers.waiting import sleep
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Frame, Page

DATE_FORMAT = "%d/%m/%Y"
NO_TRANSACTION_IN_DATE_RANGE_TEXT = "\u05dc\u05d0 \u05e0\u05de\u05e6\u05d0\u05d5 \u05e0\u05ea\u05d5\u05e0\u05d9\u05dd \u05d1\u05e0\u05d5\u05e9\u05d0 \u05d4\u05de\u05d1\u05d5\u05e7\u05e9"
ACCOUNTS_NUMBER = "div.fibi_account span.acc_num"
CLOSE_SEARCH_BY_DATES_BUTTON_CLASS = "ui-datepicker-close"
SHOW_SEARCH_BY_DATES_BUTTON_VALUE = "\u05d4\u05e6\u05d2"
COMPLETED_TRANSACTIONS_TABLE = "table#dataTable077"
PENDING_TRANSACTIONS_TABLE = "table#dataTable023"
NEXT_PAGE_LINK = "a#Npage.paging"
CURRENT_BALANCE = ".main_balance"
IFRAME_NAME = "iframe-old-pages"
ELEMENT_RENDER_TIMEOUT = 10.0
ERROR_MESSAGE_CLASS = "NO_DATA"


@dataclass
class BeinleumiGroupCredentials:
    username: str
    password: str


def _get_possible_login_results() -> dict[str, list]:
    return {
        LoginResults.success: [
            re.compile(r"fibi.*accountSummary", re.I),  # New UI pattern
            re.compile(r"Resources/PortalNG/shell", re.I),  # New UI pattern
            re.compile(r"FibiMenu/Online", re.I),  # Old UI pattern
        ],
        LoginResults.invalid_password: [re.compile(r"FibiMenu/Marketing/Private/Home", re.I)],
    }


def _create_login_fields(credentials: BeinleumiGroupCredentials) -> list[dict[str, str]]:
    return [
        {"selector": "#username", "value": credentials.username},
        {"selector": "#password", "value": credentials.password},
    ]


def _get_amount_data(amount_str: str) -> float:
    cleaned = amount_str.replace(SHEKEL_CURRENCY_SYMBOL, "").replace(",", "")
    return float(cleaned)


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


def _extract_transaction_details(tds: list[str], status: TransactionStatuses, cols: dict[str, int]) -> dict:
    def get(col: str) -> str:
        idx = cols.get(col)
        return (tds[idx] if idx is not None and idx < len(tds) else "").strip()

    if status == TransactionStatuses.completed:
        date_val = get("date first")
        desc_val = get("reference wrap_normal")
    else:
        date_val = get("first date")
        desc_val = get("details wrap_normal")

    return {
        "status": status,
        "date": date_val,
        "description": desc_val,
        "reference": get("details"),
        "debit": get("debit"),
        "credit": get("credit"),
    }


async def _get_transactions_cols_type_classes(page: "Page | Frame", table_locator: str) -> dict[str, int]:
    type_classes = await page_eval_all(
        page,
        f"{table_locator} tbody tr:first-of-type td",
        [],
        "(tds) => tds.map((td, index) => ({ colClass: td.getAttribute('class'), index }))",
    )
    result = {}
    for obj in type_classes or []:
        if obj.get("colClass"):
            result[obj["colClass"]] = obj["index"]
    return result


async def _extract_transactions(page: "Page | Frame", table_locator: str, status: TransactionStatuses) -> list[dict]:
    cols = await _get_transactions_cols_type_classes(page, table_locator)
    rows = await page_eval_all(
        page,
        f"{table_locator} tbody tr",
        [],
        "(trs) => trs.map((tr) => ({ innerTds: Array.from(tr.getElementsByTagName('td')).map((td) => td.innerText) }))",
    )
    txns = []
    for row in rows or []:
        txn = _extract_transaction_details(row["innerTds"], status, cols)
        if txn["date"] != "":
            txns.append(txn)
    return txns


async def _is_no_transaction_in_date_range_error(page: "Page | Frame") -> bool:
    if await element_present_on_page(page, f".{ERROR_MESSAGE_CLASS}"):
        from ..helpers.elements_interactions import page_eval

        error_text = await page_eval(page, f".{ERROR_MESSAGE_CLASS}", "", "(el) => el.innerText")
        return error_text.strip() == NO_TRANSACTION_IN_DATE_RANGE_TEXT
    return False


async def _search_by_dates(page: "Page | Frame", start_date: date) -> None:
    await click_button(page, "a#tabHeader4")
    await wait_until_element_found(page, "div#fibi_dates")
    await fill_input(page, "input#fromDate", start_date.strftime(DATE_FORMAT))
    await click_button(page, f"button[class*={CLOSE_SEARCH_BY_DATES_BUTTON_CLASS}]")
    await click_button(page, f"input[value={SHOW_SEARCH_BY_DATES_BUTTON_VALUE}]")
    await wait_for_navigation(page)


async def _get_account_number(page: "Page | Frame") -> str:
    from ..helpers.elements_interactions import page_eval

    await wait_until_element_found(page, ACCOUNTS_NUMBER, only_visible=True, timeout=ELEMENT_RENDER_TIMEOUT)
    text = await page_eval(page, ACCOUNTS_NUMBER, "", "(el) => el.innerText")
    return text.replace("/", "_").strip()


async def _check_if_has_next_page(page: "Page | Frame") -> bool:
    return await element_present_on_page(page, NEXT_PAGE_LINK)


async def _navigate_to_next_page(page: "Page | Frame") -> None:
    await click_button(page, NEXT_PAGE_LINK)
    await wait_for_navigation(page)


async def _scrape_transactions(
    page: "Page | Frame",
    table_locator: str,
    status: TransactionStatuses,
    need_to_paginate: bool,
    options: ScraperOptions,
) -> list[Transaction]:
    txns: list[dict] = []
    has_next_page = True
    while has_next_page:
        current_page_txns = await _extract_transactions(page, table_locator, status)
        txns.extend(current_page_txns)
        has_next_page = False
        if need_to_paginate:
            has_next_page = await _check_if_has_next_page(page)
            if has_next_page:
                await _navigate_to_next_page(page)
    return _convert_transactions(txns, options)


async def _get_account_transactions(page: "Page | Frame", options: ScraperOptions) -> list[Transaction]:
    tasks = [
        asyncio.ensure_future(wait_until_element_found(page, "div[id*='divTable']", only_visible=False)),
        asyncio.ensure_future(wait_until_element_found(page, f".{ERROR_MESSAGE_CLASS}", only_visible=False)),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        t.exception()

    if await _is_no_transaction_in_date_range_error(page):
        return []

    pending_txns = await _scrape_transactions(page, PENDING_TRANSACTIONS_TABLE, TransactionStatuses.pending, False, options)
    completed_txns = await _scrape_transactions(
        page, COMPLETED_TRANSACTIONS_TABLE, TransactionStatuses.completed, True, options
    )
    return [*pending_txns, *completed_txns]


async def _get_current_balance(page: "Page | Frame") -> float:
    from ..helpers.elements_interactions import page_eval

    await wait_until_element_found(page, CURRENT_BALANCE, only_visible=True, timeout=ELEMENT_RENDER_TIMEOUT)
    text = await page_eval(page, CURRENT_BALANCE, "", "(el) => el.innerText")
    return _get_amount_data(text)


async def wait_for_post_login(page: "Page") -> None:
    tasks = [
        asyncio.ensure_future(wait_until_element_found(page, "#card-header", only_visible=False)),  # New UI
        asyncio.ensure_future(wait_until_element_found(page, "#account_num", only_visible=True)),  # New UI
        asyncio.ensure_future(wait_until_element_found(page, "#matafLogoutLink", only_visible=True)),  # Old UI
        asyncio.ensure_future(wait_until_element_found(page, "#validationMsg", only_visible=True)),  # Old UI
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        t.exception()


async def _fetch_account_data(page: "Page | Frame", start_date: date, options: ScraperOptions) -> dict:
    account_number = await _get_account_number(page)
    balance = await _get_current_balance(page)
    await _search_by_dates(page, start_date)
    txns = await _get_account_transactions(page, options)
    return {"account_number": account_number, "txns": txns, "balance": balance}


async def _get_account_ids_old_ui(page: "Page") -> list[str]:
    return await page.evaluate(
        "() => { const el = document.getElementById('account_num_select'); "
        "const options = el ? el.querySelectorAll('option') : []; "
        "return Array.from(options, (o) => o.value); }"
    )


async def click_account_selector_get_account_ids(page: "Page") -> list[str]:
    try:
        account_selector = "div.current-account"
        dropdown_panel_selector = "div.mat-mdc-autocomplete-panel.account-select-dd"
        option_selector = "mat-option .mdc-list-item__primary-text"

        dropdown_visible = False
        try:
            dropdown_visible = await page.eval_on_selector(
                dropdown_panel_selector,
                "(el) => !!el && window.getComputedStyle(el).display !== 'none' && el.offsetParent !== null",
            )
        except Exception:
            dropdown_visible = False

        if not dropdown_visible:
            await wait_until_element_found(page, account_selector, only_visible=True, timeout=ELEMENT_RENDER_TIMEOUT)
            await click_button(page, account_selector)
            await wait_until_element_found(
                page, dropdown_panel_selector, only_visible=True, timeout=ELEMENT_RENDER_TIMEOUT
            )

        labels = await page.eval_on_selector_all(
            option_selector,
            "(options) => options.map((o) => (o.textContent || '').trim()).filter((l) => l !== '')",
        )
        return labels
    except Exception:
        return []


async def _get_account_ids_both_uis(page: "Page") -> list[str]:
    account_ids = await click_account_selector_get_account_ids(page)
    if not account_ids:
        account_ids = await _get_account_ids_old_ui(page)
    return account_ids


async def select_account_from_dropdown(page: "Page", account_label: str) -> bool:
    available = await click_account_selector_get_account_ids(page)
    if account_label not in available:
        return False

    option_selector = "mat-option .mdc-list-item__primary-text"
    await wait_until_element_found(page, option_selector, only_visible=True, timeout=ELEMENT_RENDER_TIMEOUT)
    return await page.eval_on_selector_all(
        option_selector,
        "(options, label) => { const target = options.find((o) => (o.textContent || '').trim() === label); "
        "if (!target) return false; target.click(); return true; }",
        account_label,
    )


async def _get_transactions_frame(page: "Page") -> Optional["Frame"]:
    for _ in range(3):
        await sleep(2.0)
        target = next((f for f in page.frames if f.name == IFRAME_NAME), None)
        if target:
            return target
    return None


async def _select_account_both_uis(page: "Page", account_id: str) -> None:
    selected = await select_account_from_dropdown(page, account_id)
    if not selected:
        await page.select_option("#account_num_select", account_id)
        await wait_until_element_found(page, "#account_num_select", only_visible=True)


async def _fetch_account_data_both_uis(page: "Page", start_date: date, options: ScraperOptions) -> dict:
    frame = await _get_transactions_frame(page)
    target = frame or page
    return await _fetch_account_data(target, start_date, options)


async def _fetch_accounts(page: "Page", start_date: date, options: ScraperOptions) -> list[TransactionsAccount]:
    account_ids = await _get_account_ids_both_uis(page)

    if not account_ids:
        data = await _fetch_account_data_both_uis(page, start_date, options)
        return [TransactionsAccount(account_number=data["account_number"], balance=data["balance"], txns=data["txns"])]

    accounts = []
    for account_id in account_ids:
        await _select_account_both_uis(page, account_id)
        data = await _fetch_account_data_both_uis(page, start_date, options)
        accounts.append(
            TransactionsAccount(account_number=data["account_number"], balance=data["balance"], txns=data["txns"])
        )
    return accounts


class BeinleumiGroupBaseScraper(BaseScraperWithBrowser[BeinleumiGroupCredentials]):
    BASE_URL = ""
    LOGIN_URL = ""
    TRANSACTIONS_URL = ""

    def get_login_options(self, credentials: BeinleumiGroupCredentials) -> LoginOptions:
        async def _pre_action() -> None:
            # HACK (kept from upstream): though the login button (#continueBtn) is
            # present and visible, clicking immediately doesn't register. A short
            # delay first fixes it.
            await sleep(1.0)

        return LoginOptions(
            login_url=self.LOGIN_URL,
            fields=_create_login_fields(credentials),
            submit_button_selector="#continueBtn",
            post_action=lambda: wait_for_post_login(self.page),
            possible_results=_get_possible_login_results(),
            pre_action=_pre_action,
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        default_start = date.today() - timedelta(days=365 - 1)
        start_limit = date(1600, 1, 1)
        start_date = self.options.start_date or default_start
        start_moment = max(start_limit, start_date)

        await self.navigate_to(self.TRANSACTIONS_URL)
        accounts = await _fetch_accounts(self.page, start_moment, self.options)
        return ScraperScrapingResult(success=True, accounts=accounts)
