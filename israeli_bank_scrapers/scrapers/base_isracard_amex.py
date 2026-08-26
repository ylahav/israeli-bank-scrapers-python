"""Port of src/scrapers/base-isracard-amex.ts

Shared by Isracard and Amex (see isracard.py / amex.py) — same API-driven
login/scrape flow, different base URL + company code. No DOM scraping here;
everything goes through in-page `fetch()` calls against the card company's
JSON API.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

from ..constants import ALT_SHEKEL_CURRENCY, SHEKEL_CURRENCY, SHEKEL_CURRENCY_KEYWORD
from ..definitions import ScraperProgressTypes
from ..errors import ScraperErrorTypes
from ..helpers.arrays import chunk
from ..helpers.browser import mask_headless_user_agent
from ..helpers.dates import get_all_month_moments
from ..helpers.debug import get_debug
from ..helpers.fetch import fetch_get_within_page, fetch_post_within_page
from ..helpers.transactions import filter_old_transactions, fix_installments, get_raw_transaction
from ..helpers.waiting import random_delay, sleep
from ..interface import ScraperOptions, ScraperLoginResult, ScraperScrapingResult
from ..transactions import Transaction, TransactionInstallments, TransactionStatuses, TransactionTypes, TransactionsAccount
from .base_scraper_with_browser import BaseScraperWithBrowser

if TYPE_CHECKING:
    from playwright.async_api import Page

RATE_LIMIT_SLEEP_BETWEEN = 2.5  # seconds; sweet spot per upstream comment (randomized up to +0.5s)
RATE_LIMIT_TRANSACTIONS_BATCH_SIZE = 10

COUNTRY_CODE = "212"
ID_TYPE = "1"
INSTALLMENTS_KEYWORD = "\u05ea\u05e9\u05dc\u05d5\u05dd"  # "תשלום"

DATE_FORMAT = "%d/%m/%Y"

debug = get_debug("base-isracard-amex")


@dataclass
class IsracardAmexCredentials:
    id: str
    password: str
    card6Digits: str  # noqa: N815 (kept camelCase to match SCRAPERS metadata / upstream field name)


def _set_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    existing = dict(parse_qsl(parsed.query))
    existing.update(params)
    return urlunparse(parsed._replace(query=urlencode(existing)))


def _get_accounts_url(services_url: str, month: date) -> str:
    return _set_query_params(
        services_url,
        {
            "reqName": "DashboardMonth",
            "actionCode": "0",
            "billingDate": month.strftime("%Y-%m-%d"),
            "format": "Json",
        },
    )


@dataclass
class _ScrapedAccount:
    index: int
    account_number: str
    processed_date: str


async def _fetch_accounts(page: "Page", services_url: str, month: date) -> list[_ScrapedAccount]:
    data_url = _get_accounts_url(services_url, month)
    debug.debug("fetching accounts for %s from %s", month.strftime("%Y-%m"), data_url)
    await random_delay(RATE_LIMIT_SLEEP_BETWEEN, RATE_LIMIT_SLEEP_BETWEEN + 0.5)
    data_result = await fetch_get_within_page(page, data_url)

    if data_result and (data_result.get("Header") or {}).get("Status") == "1" and data_result.get("DashboardMonthBean"):
        cards_charges = data_result["DashboardMonthBean"].get("cardsCharges") or []
        result = []
        for cc in cards_charges:
            # Card-company APIs (like Hapoalim's) have been observed returning
            # numeric date fields rather than strings — coerce defensively.
            processed = datetime.strptime(str(cc["billingDate"]), DATE_FORMAT)
            result.append(
                _ScrapedAccount(
                    index=int(cc["cardIndex"]),
                    account_number=cc["cardNumber"],
                    processed_date=processed.isoformat() + "Z",
                )
            )
        return result
    return []


def _get_transactions_url(services_url: str, month: date) -> str:
    return _set_query_params(
        services_url,
        {
            "reqName": "CardsTransactionsList",
            "month": f"{month.month:02d}",
            "year": str(month.year),
            "requiredDate": "N",
        },
    )


def _convert_currency(currency_str: str) -> str:
    if currency_str in (SHEKEL_CURRENCY_KEYWORD, ALT_SHEKEL_CURRENCY):
        return SHEKEL_CURRENCY
    return currency_str


def _get_installments_info(txn: dict) -> Optional[TransactionInstallments]:
    more_info = txn.get("moreInfo")
    if not more_info or INSTALLMENTS_KEYWORD not in more_info:
        return None
    matches = re.findall(r"\d+", more_info)
    if len(matches) < 2:
        return None
    return TransactionInstallments(number=int(matches[0]), total=int(matches[1]))


def _get_transaction_type(txn: dict) -> TransactionTypes:
    return TransactionTypes.installments if _get_installments_info(txn) else TransactionTypes.normal


def _convert_transactions(txns: list[dict], processed_date: str, options: ScraperOptions) -> list[Transaction]:
    filtered = [
        t
        for t in txns
        if t.get("dealSumType") != "1"
        and t.get("voucherNumberRatz") != "000000000"
        and t.get("voucherNumberRatzOutbound") != "000000000"
    ]

    result = []
    for txn in filtered:
        # dealSumOutbound is typed as `boolean` in the upstream TS interface but
        # is actually used as a number (0 = domestic, nonzero = outbound amount)
        # — the type annotation is misleading. Coerce to float and derive
        # is_outbound from *that*, not from Python's raw bool() on whatever the
        # API sent (a string "0" is truthy to Python's bool() despite meaning
        # "domestic" numerically).
        deal_sum_outbound_raw = txn.get("dealSumOutbound")
        deal_sum_outbound = float(deal_sum_outbound_raw) if deal_sum_outbound_raw else 0.0
        is_outbound = bool(deal_sum_outbound)

        txn_date_str = txn.get("fullPurchaseDateOutbound") if is_outbound else txn.get("fullPurchaseDate")
        txn_date = datetime.strptime(str(txn_date_str), DATE_FORMAT) if txn_date_str else None

        if txn.get("fullPaymentDate"):
            current_processed = datetime.strptime(str(txn["fullPaymentDate"]), DATE_FORMAT).isoformat() + "Z"
        else:
            current_processed = processed_date

        installments = _get_installments_info(txn)
        # dealSum/paymentSum have been observed as strings from Amex's API
        # rather than numbers (same JS-vs-Python looseness issue as the
        # integer-date bug fixed elsewhere) — coerce before negating, since
        # Python's unary `-` (unlike JS) can't operate on a string.
        deal_sum = float(txn["dealSum"])
        payment_sum = float(txn["paymentSum"])
        payment_sum_outbound_raw = txn.get("paymentSumOutbound")
        payment_sum_outbound = float(payment_sum_outbound_raw) if payment_sum_outbound_raw else 0.0

        t = Transaction(
            type=_get_transaction_type(txn),
            identifier=int(txn["voucherNumberRatzOutbound"] if is_outbound else txn["voucherNumberRatz"]),
            date=(txn_date.isoformat() + "Z") if txn_date else "",
            processed_date=current_processed,
            original_amount=-deal_sum_outbound if is_outbound else -deal_sum,
            original_currency=_convert_currency(txn.get("currentPaymentCurrency") or txn.get("currencyId")),
            charged_amount=-payment_sum_outbound if is_outbound else -payment_sum,
            charged_currency=_convert_currency(txn.get("currencyId")),
            description=txn.get("fullSupplierNameOutbound") if is_outbound else txn.get("fullSupplierNameHeb"),
            memo=txn.get("moreInfo") or "",
            installments=installments,
            status=TransactionStatuses.completed,
        )
        if options.include_raw_transaction:
            t.raw_transaction = get_raw_transaction(txn)
        result.append(t)
    return result


async def _fetch_transactions_for_month(
    page: "Page",
    options: ScraperOptions,
    services_url: str,
    start_moment: date,
    month: date,
) -> dict[str, dict]:
    accounts = await _fetch_accounts(page, services_url, month)
    data_url = _get_transactions_url(services_url, month)

    debug.debug("fetching transactions for %s from %s", month.strftime("%Y-%m"), data_url)
    await random_delay(RATE_LIMIT_SLEEP_BETWEEN, RATE_LIMIT_SLEEP_BETWEEN + 0.5)
    data_result = await fetch_get_within_page(page, data_url)

    account_txns: dict[str, dict] = {}
    if data_result and (data_result.get("Header") or {}).get("Status") == "1" and data_result.get("CardsTransactionsListBean"):
        bean = data_result["CardsTransactionsListBean"]
        for account in accounts:
            txn_groups = (bean.get(f"Index{account.index}") or {}).get("CurrentCardTransactions")
            if not txn_groups:
                continue
            all_txns: list[Transaction] = []
            for group in txn_groups:
                if group.get("txnIsrael"):
                    all_txns.extend(_convert_transactions(group["txnIsrael"], account.processed_date, options))
                if group.get("txnAbroad"):
                    all_txns.extend(_convert_transactions(group["txnAbroad"], account.processed_date, options))

            if not options.combine_installments:
                all_txns = fix_installments(all_txns)
            if options.output_data.enable_transactions_filter_by_date or True:
                start_iso = start_moment.isoformat() + "T00:00:00.000Z"
                all_txns = filter_old_transactions(all_txns, start_iso, options.combine_installments)

            account_txns[account.account_number] = {
                "account_number": account.account_number,
                "index": account.index,
                "txns": all_txns,
            }
    return account_txns


async def _get_extra_scrap_transaction(
    page: "Page", services_url: str, month: date, account_index: int, transaction: Transaction
) -> Transaction:
    url = _set_query_params(
        services_url,
        {
            "reqName": "PirteyIska_204",
            "CardIndex": str(account_index),
            "shovarRatz": str(transaction.identifier),
            "moedChiuv": month.strftime("%m%Y"),
        },
    )
    debug.debug("fetching extra scrap for transaction %s for month %s", transaction.identifier, month.strftime("%Y-%m"))
    data = await fetch_get_within_page(page, url)
    if not data:
        return transaction

    raw_category = (data.get("PirteyIska_204Bean") or {}).get("sector") or ""
    import dataclasses as _dc

    updated = _dc.replace(transaction, category=raw_category.strip())
    updated.raw_transaction = get_raw_transaction(data, transaction)
    return updated


async def _get_extra_scrap_account(page: "Page", services_url: str, account: dict, month: date) -> dict:
    debug.debug(
        "get extra scrap for %s with %d transactions %s", account["account_number"], len(account["txns"]), month.strftime("%Y-%m")
    )
    txns: list[Transaction] = []
    for txns_chunk in chunk(account["txns"], RATE_LIMIT_TRANSACTIONS_BATCH_SIZE):
        updated = await asyncio.gather(
            *[_get_extra_scrap_transaction(page, services_url, month, account["index"], t) for t in txns_chunk]
        )
        await sleep(RATE_LIMIT_SLEEP_BETWEEN)
        txns.extend(updated)
    return {**account, "txns": txns}


async def _get_additional_transaction_information(
    scraper_options: ScraperOptions,
    accounts_with_index: list[dict[str, dict]],
    page: "Page",
    services_url: str,
    all_months: list[date],
) -> list[dict[str, dict]]:
    if not scraper_options.additional_transaction_information or (
        "isracard-amex:skipAdditionalTransactionInformation" in (scraper_options.opt_in_features or [])
    ):
        return accounts_with_index

    result = []
    for i, accounts in enumerate(accounts_with_index):
        updated = {}
        for account_number, account in accounts.items():
            updated[account_number] = await _get_extra_scrap_account(page, services_url, account, all_months[i])
        result.append(updated)
    return result


async def _fetch_all_transactions(
    page: "Page", options: ScraperOptions, services_url: str, start_moment: date
) -> ScraperScrapingResult:
    future_months_to_scrape = options.future_months_to_scrape if options.future_months_to_scrape is not None else 1
    all_months = get_all_month_moments(start_moment, future_months_to_scrape)
    debug.debug("Fetching transactions for %d months", len(all_months))

    results = []
    for month in all_months:
        results.append(await _fetch_transactions_for_month(page, options, services_url, start_moment, month))

    final_result = await _get_additional_transaction_information(options, results, page, services_url, all_months)

    combined_txns: dict[str, list[Transaction]] = {}
    for result in final_result:
        for account_number, account in result.items():
            combined_txns.setdefault(account_number, [])
            combined_txns[account_number].extend(account["txns"])

    accounts = [TransactionsAccount(account_number=num, txns=txns) for num, txns in combined_txns.items()]
    return ScraperScrapingResult(success=True, accounts=accounts)


class IsracardAmexBaseScraper(BaseScraperWithBrowser[IsracardAmexCredentials]):
    # Both card companies sit behind Cloudflare Bot Management, which has
    # blocked vanilla Chromium automation (Puppeteer or Playwright, masked
    # user-agent or not) since early 2026 — see README's Verification status
    # notes. Camoufox's built-in fingerprint spoofing is the current known
    # working approach; explicitly pass browser_engine="chromium" in
    # ScraperOptions to opt back out if you have another reason to.
    DEFAULT_BROWSER_ENGINE = "camoufox"


    def __init__(self, options: ScraperOptions, base_url: str, company_code: str):
        super().__init__(options)
        self._base_url = base_url
        self._company_code = company_code
        self._services_url = f"{base_url}/services/ProxyRequestHandler.ashx"

    async def login(self, credentials: IsracardAmexCredentials):
        async def _route_handler(route):
            if "detector-dom.min.js" in route.request.url:
                debug.debug("force abort for request to download detector-dom.min.js resource")
                await route.abort()
            else:
                await route.continue_()

        await self.page.route("**/*", _route_handler)
        await mask_headless_user_agent(self.page)

        await self.navigate_to(f"{self._base_url}/personalarea/Login")
        self._emit_progress(ScraperProgressTypes.logging_in)

        validate_url = f"{self._services_url}?reqName=ValidateIdData"
        validate_request = {
            "id": credentials.id,
            "cardSuffix": credentials.card6Digits,
            "countryCode": COUNTRY_CODE,
            "idType": ID_TYPE,
            "checkLevel": "1",
            "companyCode": self._company_code,
        }
        debug.debug("logging in with validate request")
        validate_result = await fetch_post_within_page(self.page, validate_url, validate_request)
        if (
            not validate_result
            or not validate_result.get("Header")
            or validate_result["Header"].get("Status") != "1"
            or not validate_result.get("ValidateIdDataBean")
        ):
            raise Exception("unknown error during login")

        validate_return_code = validate_result["ValidateIdDataBean"]["returnCode"]
        debug.debug("user validate with return code '%s'", validate_return_code)

        if validate_return_code == "1":
            user_name = validate_result["ValidateIdDataBean"].get("userName")

            login_url = f"{self._services_url}?reqName=performLogonI"
            request = {
                "KodMishtamesh": user_name,
                "MisparZihuy": credentials.id,
                "Sisma": credentials.password,
                "cardSuffix": credentials.card6Digits,
                "countryCode": COUNTRY_CODE,
                "idType": ID_TYPE,
            }
            debug.debug("user login started")
            login_result = await fetch_post_within_page(self.page, login_url, request)
            debug.debug("user login with status '%s'", (login_result or {}).get("status"))

            if login_result and login_result.get("status") == "1":
                self._emit_progress(ScraperProgressTypes.login_success)
                return ScraperLoginResult(success=True)

            if login_result and login_result.get("status") == "3":
                self._emit_progress(ScraperProgressTypes.change_password)
                return ScraperLoginResult(success=False, error_type=ScraperErrorTypes.change_password)

            self._emit_progress(ScraperProgressTypes.login_failed)
            return ScraperLoginResult(success=False, error_type=ScraperErrorTypes.invalid_password)

        if validate_return_code == "4":
            self._emit_progress(ScraperProgressTypes.change_password)
            return ScraperLoginResult(success=False, error_type=ScraperErrorTypes.change_password)

        self._emit_progress(ScraperProgressTypes.login_failed)
        return ScraperLoginResult(success=False, error_type=ScraperErrorTypes.invalid_password)

    async def fetch_data(self) -> ScraperScrapingResult:
        default_start = date.today() - timedelta(days=365)
        start_date = self.options.start_date or default_start
        start_moment = max(default_start, start_date)
        return await _fetch_all_transactions(self.page, self.options, self._services_url, start_moment)
