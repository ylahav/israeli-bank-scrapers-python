"""Port of src/scrapers/yahav.ts"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from ..constants import SHEKEL_CURRENCY
from ..helpers.elements_interactions import (
    click_button,
    element_present_on_page,
    page_eval_all,
    wait_until_element_disappear,
    wait_until_element_found,
)
from ..helpers.navigation import wait_for_navigation
from ..helpers.transactions import get_raw_transaction
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Page

LOGIN_URL = "https://login.yahav.co.il/login/"
BASE_URL = "https://digital.yahav.co.il/BaNCSDigitalUI/app/index.html#/"
INVALID_DETAILS_SELECTOR = ".ui-dialog-buttons"
CHANGE_PASSWORD_OLD_PASS = "input#ef_req_parameter_old_credential"
BASE_WELCOME_URL = f"{BASE_URL}main/home"

PORTFOLIO_FORM = 'form[name="formPortfolioSelect"]'
ACCOUNT_ID_SELECTOR_SINGLE = "span.portfolio-value"
ACCOUNT_ID_SELECTOR_MULTI = f"{PORTFOLIO_FORM} .selected-item-top"
PORTFOLIO_OPTION_SELECTOR = f"{PORTFOLIO_FORM} .drop-down-item-list li.drop-down-item"
ACCOUNT_DETAILS_SELECTOR = ".account-details"
DATE_FORMAT = "%d/%m/%Y"

USER_ELEM = "#username"
PASSWD_ELEM = "#password"
NATIONALID_ELEM = "#pinno"
SUBMIT_LOGIN_SELECTOR = ".btn"

FROM_PICKER = 'date-picker-access[btn-label="from"]'


@dataclass
class YahavCredentials:
    username: str
    password: str
    nationalID: str  # noqa: N815 (matches SCRAPERS metadata field name)


def _get_possible_login_results() -> dict[str, list]:
    async def _invalid(page: "Page") -> bool:
        return await element_present_on_page(page, INVALID_DETAILS_SELECTOR)

    async def _change_pw(page: "Page") -> bool:
        return await element_present_on_page(page, CHANGE_PASSWORD_OLD_PASS)

    return {
        LoginResults.success: [BASE_WELCOME_URL],
        LoginResults.invalid_password: [_invalid],
        LoginResults.change_password: [_change_pw],
    }


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


def _handle_transaction_row(txns: list[dict], row: dict) -> None:
    div = row["innerDivs"]
    import re

    tx = {
        "date": div[1],
        "reference": re.sub(r"\D+", "", div[2]),
        "memo": "",
        "description": div[3],
        "debit": div[4],
        "credit": div[5],
        "status": TransactionStatuses.completed,
    }
    txns.append(tx)


async def _get_account_transactions(page: "Page", options: ScraperOptions) -> list[Transaction]:
    await wait_until_element_found(page, ".under-line-txn-table-header", only_visible=True)

    txns: list[dict] = []
    rows = await page_eval_all(
        page,
        ".list-item-holder .entire-content-ctr",
        [],
        "(divs) => divs.map((div) => ({ id: div.getAttribute('id') || '', "
        "innerDivs: Array.from(div.getElementsByTagName('div')).map((el) => el.innerText) }))",
    )
    for row in rows or []:
        _handle_transaction_row(txns, row)

    return _convert_transactions(txns, options)


async def _search_by_dates(page: "Page", start_date: date) -> None:
    await wait_until_element_found(page, f"{FROM_PICKER} a.datepicker-button", only_visible=True)
    await click_button(page, f"{FROM_PICKER} a.datepicker-button")
    await wait_until_element_found(page, f"{FROM_PICKER} .datepicker-calendar", only_visible=True)

    input_value = await page.eval_on_selector(f"{FROM_PICKER} .date-picker-input", "(el) => el.value")
    displayed = datetime.strptime(input_value, DATE_FORMAT)
    months_to_go_back = (displayed.year - start_date.year) * 12 + (displayed.month - start_date.month)
    for _ in range(max(0, months_to_go_back)):
        prev_month_selector = f"{FROM_PICKER} .datepicker-month-prev.enabled"
        await wait_until_element_found(page, prev_month_selector, only_visible=True)
        await click_button(page, prev_month_selector)

    day_selector = (
        f'{FROM_PICKER} .datepicker-calendar td.day.selectable:not(.other-month)[data-value="{start_date.day}"]'
    )
    await wait_until_element_found(page, day_selector, only_visible=True)
    await click_button(page, day_selector)


async def _fetch_account_data(page: "Page", start_date: date, account_id: str, options: ScraperOptions) -> TransactionsAccount:
    await wait_until_element_disappear(page, ".loading-bar-spinner")
    await _search_by_dates(page, start_date)
    await wait_until_element_disappear(page, ".loading-bar-spinner")
    txns = await _get_account_transactions(page, options)
    return TransactionsAccount(account_number=account_id, txns=txns)


async def _get_portfolio_ids(page: "Page") -> list[str]:
    tasks = [
        asyncio.ensure_future(page.wait_for_selector(ACCOUNT_ID_SELECTOR_MULTI, timeout=10000)),
        asyncio.ensure_future(page.wait_for_selector(ACCOUNT_ID_SELECTOR_SINGLE, timeout=10000)),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        t.exception()

    return await page.evaluate(
        """(multiSelector, optionSelector, singleSelector) => {
            const selected = document.querySelector(multiSelector)?.textContent?.trim();
            if (selected) {
                const others = Array.from(document.querySelectorAll(optionSelector)).map((li) => li.textContent?.trim() ?? '');
                return [selected, ...others].filter(Boolean);
            }
            const single = document.querySelector(singleSelector)?.textContent?.trim();
            return single ? [single] : [];
        }""",
        [ACCOUNT_ID_SELECTOR_MULTI, PORTFOLIO_OPTION_SELECTOR, ACCOUNT_ID_SELECTOR_SINGLE],
    )


async def _select_portfolio(page: "Page", target_id: str) -> None:
    clicked = await page.eval_on_selector_all(
        PORTFOLIO_OPTION_SELECTOR,
        "(lis, id) => { const target = lis.find((li) => (li.textContent || '').trim() === id); "
        "if (!target) return false; target.click(); return true; }",
        target_id,
    )
    if not clicked:
        raise Exception(f"Portfolio option not found for ID: {target_id}")
    await wait_until_element_disappear(page, ".loading-bar-spinner")


async def _fetch_accounts(page: "Page", start_date: date, options: ScraperOptions) -> list[TransactionsAccount]:
    portfolio_ids = await _get_portfolio_ids(page)
    if not portfolio_ids:
        raise Exception("No portfolios found on /main/home — Yahav DOM likely changed")

    accounts = []
    for i, portfolio_id in enumerate(portfolio_ids):
        if i > 0:
            await _select_portfolio(page, portfolio_id)
        await wait_until_element_found(page, ACCOUNT_DETAILS_SELECTOR, only_visible=True)
        await click_button(page, ACCOUNT_DETAILS_SELECTOR)
        await wait_until_element_found(page, ".statement-options .selected-item-top", only_visible=True)
        accounts.append(await _fetch_account_data(page, start_date, portfolio_id, options))

    return accounts


async def _wait_readiness_for_all(page: "Page") -> None:
    await wait_until_element_found(page, USER_ELEM, only_visible=True)
    await wait_until_element_found(page, PASSWD_ELEM, only_visible=True)
    await wait_until_element_found(page, NATIONALID_ELEM, only_visible=True)
    await wait_until_element_found(page, SUBMIT_LOGIN_SELECTOR, only_visible=True)


async def _redirect_or_dialog(page: "Page") -> None:
    await wait_for_navigation(page)
    await wait_until_element_disappear(page, ".loading-bar-spinner")
    if await element_present_on_page(page, ".messaging-links-container"):
        await click_button(page, ".link-1")

    tasks = [
        asyncio.ensure_future(page.wait_for_selector(ACCOUNT_DETAILS_SELECTOR, timeout=30000)),
        asyncio.ensure_future(page.wait_for_selector(CHANGE_PASSWORD_OLD_PASS, timeout=30000)),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        t.exception()
    await wait_until_element_disappear(page, ".loading-bar-spinner")


class YahavScraper(BaseScraperWithBrowser[YahavCredentials]):
    def get_login_options(self, credentials: YahavCredentials) -> LoginOptions:
        return LoginOptions(
            login_url=LOGIN_URL,
            fields=[
                {"selector": USER_ELEM, "value": credentials.username},
                {"selector": PASSWD_ELEM, "value": credentials.password},
                {"selector": NATIONALID_ELEM, "value": credentials.nationalID},
            ],
            submit_button_selector=SUBMIT_LOGIN_SELECTOR,
            check_readiness=lambda: _wait_readiness_for_all(self.page),
            post_action=lambda: _redirect_or_dialog(self.page),
            possible_results=_get_possible_login_results(),
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        await wait_until_element_found(self.page, ACCOUNT_DETAILS_SELECTOR, only_visible=True)

        default_start = date.today() - timedelta(days=90 - 1)
        start_date = self.options.start_date or default_start
        start_moment = min(max(default_start, start_date), date.today())

        accounts = await _fetch_accounts(self.page, start_moment, self.options)
        return ScraperScrapingResult(success=True, accounts=accounts)
