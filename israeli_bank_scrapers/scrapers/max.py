"""Port of src/scrapers/max.ts"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlencode

from ..constants import DOLLAR_CURRENCY, EURO_CURRENCY, SHEKEL_CURRENCY
from ..helpers.dates import get_all_month_moments
from ..helpers.debug import get_debug
from ..helpers.elements_interactions import click_button, element_present_on_page, wait_until_element_found
from ..helpers.fetch import fetch_get_within_page
from ..helpers.navigation import wait_for_redirect
from ..helpers.transactions import filter_old_transactions, fix_installments, get_raw_transaction, sort_transactions_by_date
from ..helpers.waiting import sleep
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import Transaction, TransactionInstallments, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Page

debug = get_debug("max")

BASE_API_ACTIONS_URL = "https://onlinelcapi.max.co.il"
BASE_WELCOME_URL = "https://www.max.co.il"
HOME_PAGE_DATA_URL = f"{BASE_WELCOME_URL}/api/registered/getHomePageData"

LOGIN_URL = f"{BASE_WELCOME_URL}/login"
PASSWORD_EXPIRED_URL = f"{BASE_WELCOME_URL}/renew-password"
SUCCESS_URL = f"{BASE_WELCOME_URL}/homepage/personal"

INVALID_DETAILS_SELECTOR = "#popupWrongDetails"
LOGIN_ERROR_SELECTOR = "#popupCardHoldersLoginError"


@dataclass
class MaxCredentials:
    username: str
    password: str


class _MaxPlanName(str, Enum):
    normal = "\u05e8\u05d2\u05d9\u05dc\u05d4"
    immediate_charge = "\u05d7\u05d9\u05d5\u05d1 \u05e2\u05e1\u05e7\u05d5\u05ea \u05de\u05d9\u05d9\u05d3\u05d9"
    internet_shopping = '\u05d0\u05d9\u05e0\u05d8\u05e8\u05e0\u05d8/\u05d7\u05d5"\u05dc'
    installments = "\u05ea\u05e9\u05dc\u05d5\u05de\u05d9\u05dd"
    monthly_charge = "\u05d7\u05d9\u05d5\u05d1 \u05d7\u05d5\u05d3\u05e9\u05d9"
    one_month_postponed = "\u05d3\u05d7\u05d5\u05d9 \u05d7\u05d5\u05d3\u05e9"
    monthly_postponed = "\u05d3\u05d7\u05d5\u05d9 \u05dc\u05d7\u05d9\u05d5\u05d1 \u05d4\u05d7\u05d5\u05d3\u05e9\u05d9"
    monthly_payment = "\u05ea\u05e9\u05dc\u05d5\u05dd \u05d7\u05d5\u05d3\u05e9\u05d9"
    future_purchase_financing = "\u05de\u05d9\u05de\u05d5\u05df \u05dc\u05e8\u05db\u05d9\u05e9\u05d4 \u05e2\u05ea\u05d9\u05d3\u05d9\u05ea"
    monthly_postponed_installments = "\u05d3\u05d7\u05d5\u05d9 \u05d7\u05d5\u05d3\u05e9 \u05ea\u05e9\u05dc\u05d5\u05de\u05d9\u05dd"
    thirty_days_plus = "\u05e2\u05e1\u05e7\u05ea 30 \u05e4\u05dc\u05d5\u05e1"
    two_months_postponed = "\u05d3\u05d7\u05d5\u05d9 \u05d7\u05d5\u05d3\u05e9\u05d9\u05d9\u05dd"
    two_months_postponed_2 = "\u05d3\u05d7\u05d5\u05d9 2 \u05d7' \u05ea\u05e9\u05dc\u05d5\u05de\u05d9\u05dd"
    monthly_charge_plus_interest = "\u05d7\u05d5\u05d3\u05e9\u05d9 + \u05e8\u05d9\u05d1\u05d9\u05ea"
    credit = "\u05e7\u05e8\u05d3\u05d9\u05d8"
    credit_outside_the_limit = "\u05e7\u05e8\u05d3\u05d9\u05d8-\u05de\u05d7\u05d5\u05e5 \u05dc\u05de\u05e1\u05d2\u05e8\u05ea"
    accumulating_basket = "\u05e1\u05dc \u05de\u05e6\u05d8\u05d1\u05e8"
    postponed_transaction_installments = "\u05e4\u05e8\u05d9\u05e1\u05ea \u05d4\u05e2\u05e1\u05e7\u05d4 \u05d4\u05d3\u05d7\u05d5\u05d9\u05d4"
    replacement_card = "\u05db\u05e8\u05d8\u05d9\u05e1 \u05d7\u05dc\u05d9\u05e4\u05d9"
    early_repayment = "\u05e4\u05e8\u05e2\u05d5\u05df \u05de\u05d5\u05e7\u05d3\u05dd"
    monthly_card_fee = "\u05d3\u05de\u05d9 \u05db\u05e8\u05d8\u05d9\u05e1"
    currency_pocket = '\u05d7\u05d9\u05d5\u05d1 \u05d0\u05e8\u05e0\u05e7 \u05de\u05d8"\u05d7'
    monthly_charge_distribution = "\u05d7\u05dc\u05d5\u05e7\u05ea \u05d7\u05d9\u05d5\u05d1 \u05d7\u05d5\u05d3\u05e9\u05d9"


_NORMAL_PLAN_NAMES = {
    _MaxPlanName.immediate_charge,
    _MaxPlanName.normal,
    _MaxPlanName.monthly_charge,
    _MaxPlanName.one_month_postponed,
    _MaxPlanName.monthly_postponed,
    _MaxPlanName.future_purchase_financing,
    _MaxPlanName.monthly_payment,
    _MaxPlanName.monthly_postponed_installments,
    _MaxPlanName.thirty_days_plus,
    _MaxPlanName.two_months_postponed,
    _MaxPlanName.two_months_postponed_2,
    _MaxPlanName.accumulating_basket,
    _MaxPlanName.internet_shopping,
    _MaxPlanName.monthly_charge_plus_interest,
    _MaxPlanName.postponed_transaction_installments,
    _MaxPlanName.replacement_card,
    _MaxPlanName.early_repayment,
    _MaxPlanName.monthly_card_fee,
    _MaxPlanName.currency_pocket,
    _MaxPlanName.monthly_charge_distribution,
}
_INSTALLMENT_PLAN_NAMES = {_MaxPlanName.installments, _MaxPlanName.credit, _MaxPlanName.credit_outside_the_limit}

_categories: dict[int, str] = {}


async def _redirect_or_dialog(page: "Page") -> None:
    tasks = [
        asyncio.ensure_future(wait_for_redirect(page, 20.0, False, [BASE_WELCOME_URL, f"{BASE_WELCOME_URL}/"])),
        asyncio.ensure_future(wait_until_element_found(page, INVALID_DETAILS_SELECTOR, only_visible=True)),
        asyncio.ensure_future(wait_until_element_found(page, LOGIN_ERROR_SELECTOR, only_visible=True)),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        t.exception()


def _get_transactions_url(month: date) -> str:
    date_str = f"{month.year}-{month.month}-01"
    filter_data = (
        '{"userIndex":-1,"cardIndex":-1,"monthView":true,"date":"%s",'
        '"dates":{"startDate":"0","endDate":"0"},"bankAccount":{"bankAccountIndex":-1,"cards":null}}'
    ) % date_str
    params = urlencode({"filterData": filter_data, "firstCallCardIndex": "-1"})
    return f"{BASE_API_ACTIONS_URL}/api/registered/transactionDetails/getTransactionsAndGraphs?{params}"


async def _load_home_page_data(page: "Page") -> dict[str, dict]:
    debug.debug("Loading home page data for card balances")
    res = await fetch_get_within_page(page, HOME_PAGE_DATA_URL)
    card_map: dict[str, dict] = {}
    for card in (((res or {}).get("Result") or {}).get("UserCards") or {}).get("Cards") or []:
        card_map[card["Last4Digits"]] = card
    return card_map


def _get_card_balance(card: dict) -> Optional[float]:
    if card.get("CreditLimit") is None or card.get("OpenToBuy") is None:
        return None
    balance = -(card["CreditLimit"] - card["OpenToBuy"])
    return round(balance, 2)


def _get_card_balance_date(card: dict) -> Optional[str]:
    for entry in card.get("CycleSummary") or []:
        if "\u20aa" in entry.get("CurrencySymbol", ""):
            return entry.get("Date")
    return None


async def _load_categories(page: "Page") -> None:
    debug.debug("Loading categories")
    res = await fetch_get_within_page(page, f"{BASE_API_ACTIONS_URL}/api/contents/getCategories")
    result = (res or {}).get("result")
    if isinstance(result, list):
        debug.debug("%d categories loaded", len(result))
        for item in result:
            _categories[item["id"]] = item["name"]


def _get_transaction_type(plan_name: str, plan_type_id: int) -> TransactionTypes:
    cleaned = plan_name.replace("\t", " ").strip()
    try:
        plan = _MaxPlanName(cleaned)
    except ValueError:
        plan = None

    if plan in _NORMAL_PLAN_NAMES:
        return TransactionTypes.normal
    if plan in _INSTALLMENT_PLAN_NAMES:
        return TransactionTypes.installments

    if plan_type_id in (2, 3):
        return TransactionTypes.installments
    if plan_type_id == 5:
        return TransactionTypes.normal
    raise Exception(f"Unknown transaction type {cleaned}")


def _get_installments_info(comments: str) -> Optional[TransactionInstallments]:
    if not comments:
        return None
    matches = re.findall(r"\d+", comments)
    if len(matches) < 2:
        return None
    return TransactionInstallments(number=int(matches[0]), total=int(matches[1]))


def _get_charged_currency(currency_id: Optional[int]) -> Optional[str]:
    return {376: SHEKEL_CURRENCY, 840: DOLLAR_CURRENCY, 978: EURO_CURRENCY}.get(currency_id)


def get_memo(comments: str, funds_transfer_receiver_or_transfer: Optional[str], funds_transfer_comment: Optional[str]) -> Optional[str]:
    if funds_transfer_receiver_or_transfer:
        memo = f"{comments} {funds_transfer_receiver_or_transfer}" if comments else funds_transfer_receiver_or_transfer
        return f"{memo}: {funds_transfer_comment}" if funds_transfer_comment else memo
    return comments


def _map_transaction(raw: dict, options: ScraperOptions) -> Transaction:
    is_pending = raw.get("paymentDate") is None
    processed_source = raw["purchaseDate"] if is_pending else raw["paymentDate"]
    processed_date = datetime.fromisoformat(processed_source.replace("Z", "+00:00")).isoformat().replace("+00:00", "Z")
    status = TransactionStatuses.pending if is_pending else TransactionStatuses.completed

    installments = _get_installments_info(raw.get("comments"))
    deal_data = raw.get("dealData") or {}
    identifier = f"{deal_data.get('arn')}_{installments.number}" if installments else deal_data.get("arn")

    purchase_date = datetime.fromisoformat(raw["purchaseDate"].replace("Z", "+00:00")).isoformat().replace("+00:00", "Z")

    t = Transaction(
        type=_get_transaction_type(raw["planName"], raw["planTypeId"]),
        date=purchase_date,
        processed_date=processed_date,
        original_amount=-raw["originalAmount"],
        original_currency=raw["originalCurrency"],
        charged_amount=-raw["actualPaymentAmount"],
        charged_currency=_get_charged_currency(raw.get("paymentCurrency")),
        description=raw["merchantName"].strip(),
        memo=get_memo(raw.get("comments"), raw.get("fundsTransferReceiverOrTransfer"), raw.get("fundsTransferComment")),
        category=_categories.get(raw.get("categoryId")),
        installments=installments,
        identifier=identifier,
        status=status,
    )
    if options.include_raw_transaction:
        t.raw_transaction = get_raw_transaction(raw)
    return t


async def _fetch_transactions_for_month(page: "Page", month: date, options: ScraperOptions) -> dict[str, list[Transaction]]:
    url = _get_transactions_url(month)
    data = await fetch_get_within_page(page, url)
    by_account: dict[str, list[Transaction]] = {}
    if not data or not data.get("result"):
        return by_account

    for txn in data["result"]["transactions"]:
        if not txn.get("planName"):
            continue
        by_account.setdefault(txn["shortCardNumber"], [])
        by_account[txn["shortCardNumber"]].append(_map_transaction(txn, options))
    return by_account


def _add_result(all_results: dict[str, list[Transaction]], result: dict[str, list[Transaction]]) -> dict[str, list[Transaction]]:
    cloned = dict(all_results)
    for account_number, txns in result.items():
        cloned.setdefault(account_number, [])
        cloned[account_number] = [*cloned[account_number], *txns]
    return cloned


def _prepare_transactions(
    txns: list[Transaction], start_date_iso: str, combine_installments: bool, enable_filter_by_date: bool
) -> list[Transaction]:
    cloned = list(txns)
    if not combine_installments:
        cloned = fix_installments(cloned)
    cloned = sort_transactions_by_date(cloned)
    if enable_filter_by_date:
        cloned = filter_old_transactions(cloned, start_date_iso, combine_installments)
    return cloned


async def _fetch_transactions(page: "Page", options: ScraperOptions) -> tuple[dict[str, list[Transaction]], dict[str, dict]]:
    future_months_to_scrape = options.future_months_to_scrape if options.future_months_to_scrape is not None else 1
    default_start = date.today() - timedelta(days=365)
    start_limit = date.today() - timedelta(days=365 * 4)
    start_date = options.start_date or default_start
    start_moment = max(start_limit, start_date)
    all_months = get_all_month_moments(start_moment, future_months_to_scrape)

    await _load_categories(page)
    home_page_cards = await _load_home_page_data(page)

    all_results: dict[str, list[Transaction]] = {}
    for month in all_months:
        result = await _fetch_transactions_for_month(page, month, options)
        all_results = _add_result(all_results, result)

    start_iso = start_moment.isoformat() + "T00:00:00.000Z"
    for account_number in list(all_results.keys()):
        all_results[account_number] = _prepare_transactions(
            all_results[account_number],
            start_iso,
            options.combine_installments,
            options.output_data.enable_transactions_filter_by_date or True,
        )

    return all_results, home_page_cards


def _get_possible_login_results(page: "Page") -> dict[str, list]:
    async def _invalid_details() -> bool:
        return await element_present_on_page(page, INVALID_DETAILS_SELECTOR)

    async def _login_error() -> bool:
        return await element_present_on_page(page, LOGIN_ERROR_SELECTOR)

    return {
        LoginResults.success: [SUCCESS_URL],
        LoginResults.change_password: [PASSWORD_EXPIRED_URL],
        LoginResults.invalid_password: [_invalid_details],
        LoginResults.unknown_error: [_login_error],
    }


def _create_login_fields(credentials: MaxCredentials) -> list[dict[str, str]]:
    return [
        {"selector": "#user-name", "value": credentials.username},
        {"selector": "#password", "value": credentials.password},
    ]


class MaxScraper(BaseScraperWithBrowser[MaxCredentials]):
    def get_login_options(self, credentials: MaxCredentials) -> LoginOptions:
        async def _pre_action() -> None:
            if await element_present_on_page(self.page, "#closePopup"):
                await click_button(self.page, "#closePopup")
            await click_button(self.page, ".personal-area > a.go-to-personal-area")
            if await element_present_on_page(self.page, ".login-link#private"):
                await click_button(self.page, ".login-link#private")
            try:
                await wait_until_element_found(self.page, "#login-password-link", only_visible=True, timeout=10)
            except Exception:
                await sleep(1)
                await wait_until_element_found(self.page, "#login-password-link", only_visible=True, timeout=10)
            await click_button(self.page, "#login-password-link")
            await wait_until_element_found(
                self.page, "#login-password.tab-pane.active app-user-login-form", only_visible=True
            )

        async def _check_readiness() -> None:
            await wait_until_element_found(self.page, ".personal-area > a.go-to-personal-area", only_visible=True)

        return LoginOptions(
            login_url=LOGIN_URL,
            fields=_create_login_fields(credentials),
            submit_button_selector="app-user-login-form .general-button.send-me-code",
            pre_action=_pre_action,
            check_readiness=_check_readiness,
            post_action=lambda: _redirect_or_dialog(self.page),
            possible_results=_get_possible_login_results(self.page),
            wait_until="domcontentloaded",
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        all_results, home_page_cards = await _fetch_transactions(self.page, self.options)
        accounts = []
        for account_number, txns in all_results.items():
            card = home_page_cards.get(account_number)
            accounts.append(
                TransactionsAccount(
                    account_number=account_number,
                    txns=txns,
                    balance=_get_card_balance(card) if card else None,
                    balance_date=_get_card_balance_date(card) if card else None,
                    card_frame=(card or {}).get("CreditLimit"),
                )
            )
        return ScraperScrapingResult(success=True, accounts=accounts)
