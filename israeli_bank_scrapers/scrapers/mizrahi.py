"""Port of src/scrapers/mizrahi.ts

Like Visa Cal, this scraper needs to intercept a live network request (here,
the transactions API call the page itself makes) to read its POST body and a
custom XSRF header before replaying it via `fetch_post_within_page`. Uses the
same request-listener + future pattern as Visa Cal's auth capture, since
Python's Playwright has no direct `page.waitForRequest()` (see
base_scraper_with_browser.py's module docstring, and visa_cal.py's
get_login_options for the same fix applied there).
"""

from __future__ import annotations

import asyncio
import json as json_module
import re
from dataclasses import dataclass, replace as dc_replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Callable, Optional

from ..constants import SHEKEL_CURRENCY
from ..helpers.debug import get_debug
from ..helpers.elements_interactions import page_eval_all, wait_until_element_disappear, wait_until_element_found
from ..helpers.fetch import fetch_post_within_page
from ..helpers.navigation import wait_for_url
from ..helpers.transactions import get_raw_transaction
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Frame, Page, Request

debug = get_debug("mizrahi")

BASE_WEBSITE_URL = "https://www.mizrahi-tefahot.co.il"
LOGIN_URL = f"{BASE_WEBSITE_URL}/login/index.html#/auth-page-he"
BASE_APP_URL = "https://mto.mizrahi-tefahot.co.il"
AFTER_LOGIN_BASE_URL = re.compile(r"https://mto\.mizrahi-tefahot\.co\.il/OnlineApp/.*")
OSH_PAGE = "/osh/legacy/legacy-Osh-Main"
TRANSACTIONS_PAGE = "/osh/legacy/root-main-osh-p428New"
TRANSACTIONS_REQUEST_URLS = [
    f"{BASE_APP_URL}/OnlinePilot/api/SkyOSH/get428Index",
    f"{BASE_APP_URL}/Online/api/SkyOSH/get428Index",
]
PENDING_TRANSACTIONS_PAGE = "/osh/legacy/legacy-Osh-p420"
PENDING_TRANSACTIONS_IFRAME = "p420.aspx"
MORE_DETAILS_URL = f"{BASE_APP_URL}/Online/api/OSH/getMaherBerurimSMF"
CHANGE_PASSWORD_URL = re.compile(r"https://www\.mizrahi-tefahot\.co\.il/login/index\.html#/change-pass")
DATE_FORMAT = "%d/%m/%Y"
MAX_ROWS_PER_REQUEST = 10000000000

USERNAME_SELECTOR = "#userNumberDesktopHeb"
PASSWORD_SELECTOR = "#passwordDesktopHeb"
SUBMIT_BUTTON_SELECTOR = "button.btn.btn-primary"
INVALID_PASSWORD_SELECTOR = 'a[href*="https://sc.mizrahi-tefahot.co.il/SCServices/SC/P010.aspx"]'
AFTER_LOGIN_SELECTOR = "#dropdownBasic"
LOGIN_SPINNER_SELECTOR = "div.ngx-overlay.loading-foreground"
ACCOUNT_DROPDOWN_ITEM_SELECTOR = "#AccountPicker .item"
PENDING_TRX_IDENTIFIER_ID = "#ctl00_ContentPlaceHolder2_panel1"
CHECKING_ACCOUNT_TAB_HEBREW = "\u05e2\u05d5\u05d1\u05e8 \u05d5\u05e9\u05d1"
CHECKING_ACCOUNT_TAB_ENGLISH = "Checking Account"
GENERIC_DESCRIPTIONS = ["\u05d4\u05e2\u05d1\u05e8\u05ea \u05d9\u05d5\u05de\u05df \u05dc\u05d1\u05e0\u05e7 \u05d6\u05e8 \u05de\u05e1\u05e0\u05d9\u05e3 \u05d6\u05e8"]


@dataclass
class MizrahiCredentials:
    username: str
    password: str


def _create_login_fields(credentials: MizrahiCredentials) -> list[dict[str, str]]:
    return [
        {"selector": USERNAME_SELECTOR, "value": credentials.username},
        {"selector": PASSWORD_SELECTOR, "value": credentials.password},
    ]


async def _is_logged_in(page: "Page") -> bool:
    xpath = (
        f'//a//span[contains(., "{CHECKING_ACCOUNT_TAB_HEBREW}") or contains(., "{CHECKING_ACCOUNT_TAB_ENGLISH}")]'
    )
    matches = await page.query_selector_all(f"xpath={xpath}")
    return len(matches) > 0


def _get_possible_login_results(page: "Page") -> dict[str, list]:
    async def _invalid(p: "Page") -> bool:
        return (await p.query_selector(INVALID_PASSWORD_SELECTOR)) is not None

    return {
        LoginResults.success: [AFTER_LOGIN_BASE_URL, _is_logged_in],
        LoginResults.invalid_password: [_invalid],
        LoginResults.change_password: [CHANGE_PASSWORD_URL],
    }


def _get_start_moment(options_start_date: Optional[date]) -> date:
    default_start = date.today() - timedelta(days=365)
    start_date = options_start_date or default_start
    return max(default_start, start_date)


async def _get_extra_transaction_details(page: "Page", item: dict, api_headers: dict) -> dict:
    try:
        debug.debug("getExtraTransactionDetails for item: %s", item)
        if item.get("MC02ShowDetailsEZ") == "1":
            tar_peula = datetime.fromisoformat(item["MC02PeulaTaaEZ"].replace("Z", "+00:00"))
            tar_erech_raw = item.get("MC02ErehTaaEZ")
            tar_erech = datetime.fromisoformat(tar_erech_raw.replace("Z", "+00:00")) if tar_erech_raw else tar_peula

            params = {
                "inKodGorem": item.get("MC02KodGoremEZ"),
                "inAsmachta": item.get("MC02AsmahtaMekoritEZ"),
                "inSchum": item.get("MC02SchumEZ"),
                "inNakvanit": item.get("MC02KodGoremEZ"),
                "inSugTnua": item.get("MC02SugTnuaKaspitEZ"),
                "inAgid": item.get("MC02AgidEZ"),
                "inTarPeulaFormatted": tar_peula.strftime(DATE_FORMAT),
                "inTarErechFormatted": (tar_erech if tar_erech.year > 2000 else tar_peula).strftime(DATE_FORMAT),
                "inKodNose": item.get("MC02SeifMaralEZ"),
                "inKodTatNose": item.get("MC02NoseMaralEZ"),
                "inTransactionNumber": item.get("TransactionNumber"),
            }

            response = await fetch_post_within_page(page, MORE_DETAILS_URL, params, api_headers)
            records = (((response or {}).get("body") or {}).get("fields") or [[]])
            details = None
            if records and records[0] and records[0][0].get("Records"):
                details = records[0][0]["Records"][0].get("Fields")
            debug.debug("fetch details for %s details: %s", params, details)
            if details:
                entries = [(d["Label"].strip(), d["Value"].strip()) for d in details]
                memo = ", ".join(
                    f"{label} {value}"
                    for label, value in entries
                    if any(label.startswith(key) for key in ("\u05e9\u05dd", "\u05de\u05d4\u05d5\u05ea", "\u05d7\u05e9\u05d1\u05d5\u05df"))
                )
                return {"entries": dict(entries), "memo": memo}
    except Exception as e:
        debug.debug("Error fetching extra transaction details: %s", e)

    return {"entries": {}, "memo": None}


def _get_transaction_identifier(row: dict):
    if not row.get("MC02AsmahtaMekoritEZ"):
        return None
    if row.get("TransactionNumber") and str(row["TransactionNumber"]) != "1":
        return f"{row['MC02AsmahtaMekoritEZ']}-{row['TransactionNumber']}"
    return int(row["MC02AsmahtaMekoritEZ"])


async def _convert_transactions(
    txns: list[dict],
    get_more_details: Callable[[dict], "asyncio.Future"],
    pending_if_today_transaction: bool,
    options: ScraperOptions,
) -> list[Transaction]:
    async def _convert_one(row: dict) -> Transaction:
        more_details = await get_more_details(row)
        txn_date = datetime.strptime(str(row["MC02PeulaTaaEZ"]), "%Y-%m-%dT%H:%M:%S").isoformat() + "Z"

        t = Transaction(
            type=TransactionTypes.normal,
            identifier=_get_transaction_identifier(row),
            date=txn_date,
            processed_date=txn_date,
            original_amount=row["MC02SchumEZ"],
            original_currency=SHEKEL_CURRENCY,
            charged_amount=row["MC02SchumEZ"],
            description=row["MC02TnuaTeurEZ"],
            memo=more_details.get("memo"),
            status=(
                TransactionStatuses.pending
                if pending_if_today_transaction and row.get("IsTodayTransaction")
                else TransactionStatuses.completed
            ),
        )
        if options.include_raw_transaction:
            t.raw_transaction = get_raw_transaction({**row, "additionalInformation": more_details.get("entries")})
        return t

    return list(await asyncio.gather(*[_convert_one(row) for row in txns]))


async def _extract_pending_transactions(frame: "Frame") -> list[Transaction]:
    rows = await page_eval_all(
        frame,
        "tr.rgRow, tr.rgAltRow",
        [],
        "(trs) => trs.map((tr) => Array.from(tr.querySelectorAll('td'), (td) => td.textContent || ''))",
    )
    result = []
    for row in rows or []:
        if len(row) < 4:
            continue
        date_str, description, _income_amount_str, amount_str = row[0], row[1], row[2], row[3]
        try:
            txn_date = datetime.strptime(date_str, "%d/%m/%y").isoformat() + "Z"
        except ValueError:
            continue
        amount = float(amount_str.replace(",", ""))
        result.append(
            Transaction(
                type=TransactionTypes.normal,
                date=txn_date,
                processed_date=txn_date,
                original_amount=amount,
                original_currency=SHEKEL_CURRENCY,
                charged_amount=amount,
                description=description,
                status=TransactionStatuses.pending,
            )
        )
    return result


async def _post_login(page: "Page") -> None:
    tasks = [
        asyncio.ensure_future(wait_until_element_found(page, AFTER_LOGIN_SELECTOR)),
        asyncio.ensure_future(wait_until_element_found(page, INVALID_PASSWORD_SELECTOR)),
        asyncio.ensure_future(wait_for_url(page, CHANGE_PASSWORD_URL.pattern, is_regex=True)),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    for t in done:
        t.exception()


class MizrahiScraper(BaseScraperWithBrowser[MizrahiCredentials]):
    def get_login_options(self, credentials: MizrahiCredentials) -> LoginOptions:
        return LoginOptions(
            login_url=LOGIN_URL,
            fields=_create_login_fields(credentials),
            submit_button_selector=SUBMIT_BUTTON_SELECTOR,
            check_readiness=lambda: wait_until_element_disappear(self.page, LOGIN_SPINNER_SELECTOR),
            post_action=lambda: _post_login(self.page),
            possible_results=_get_possible_login_results(self.page),
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        await self.page.eval_on_selector("#dropdownBasic, .item", "(el) => el.click()")

        num_of_accounts = len(await self.page.query_selector_all(ACCOUNT_DROPDOWN_ITEM_SELECTOR))

        try:
            results: list[TransactionsAccount] = []
            for i in range(num_of_accounts):
                if i > 0:
                    await self.page.eval_on_selector("#dropdownBasic, .item", "(el) => el.click()")
                await self.page.eval_on_selector(f"{ACCOUNT_DROPDOWN_ITEM_SELECTOR}:nth-child({i + 1})", "(el) => el.click()")
                results.append(await self._fetch_account())

            return ScraperScrapingResult(success=True, accounts=results)
        except Exception as e:
            from ..errors import ScraperErrorTypes

            return ScraperScrapingResult(success=False, error_type=ScraperErrorTypes.generic, error_message=str(e))

    async def _get_pending_transactions(self) -> list[Transaction]:
        await self.page.eval_on_selector(f'a[href*="{PENDING_TRANSACTIONS_PAGE}"]', "(el) => el.click()")

        from ..helpers.elements_interactions import wait_until_iframe_found

        frame = await wait_until_iframe_found(self.page, lambda f: PENDING_TRANSACTIONS_IFRAME in f.url)
        try:
            await wait_until_element_found(frame, PENDING_TRX_IDENTIFIER_ID)
            is_pending = True
        except Exception:
            is_pending = False

        if not is_pending:
            return []

        return await _extract_pending_transactions(frame)

    async def _fetch_account(self) -> TransactionsAccount:
        await self.page.wait_for_selector(f'a[href*="{OSH_PAGE}"]')
        await self.page.eval_on_selector(f'a[href*="{OSH_PAGE}"]', "(el) => el.click()")
        await wait_until_element_found(self.page, f'a[href*="{TRANSACTIONS_PAGE}"]')
        await self.page.eval_on_selector(f'a[href*="{TRANSACTIONS_PAGE}"]', "(el) => el.click()")

        account_number_el = await self.page.query_selector("#dropdownBasic b span")
        account_number = await account_number_el.get_attribute("title") if account_number_el else None
        if not account_number:
            raise Exception("Account number not found")

        # Python's Playwright has no page.waitForRequest() (see module docstring) —
        # listen for the request event instead, racing across both candidate URLs.
        result_future: asyncio.Future = asyncio.get_event_loop().create_future()

        def _on_request(request: "Request"):
            if result_future.done():
                return
            if request.url in TRANSACTIONS_REQUEST_URLS:
                result_future.set_result(request)

        self.page.on("request", _on_request)
        try:
            request = await asyncio.wait_for(result_future, timeout=30.0)
        finally:
            self.page.remove_listener("request", _on_request)

        data = json_module.loads(request.post_data or "{}")
        default_start = date.today() - timedelta(days=365)
        options_start = self.options.start_date or default_start
        data["inFromDate"] = _get_start_moment(self.options.start_date).strftime(DATE_FORMAT)
        data["inToDate"] = date.today().strftime(DATE_FORMAT)
        if "table" in data:
            data["table"]["maxRow"] = MAX_ROWS_PER_REQUEST

        headers = {
            "mizrahixsrftoken": request.headers.get("mizrahixsrftoken"),
            "Content-Type": request.headers.get("content-type"),
        }

        response = await fetch_post_within_page(self.page, request.url, data, headers)

        if not response or response.get("header", {}).get("success") is False:
            messages = (response or {}).get("header", {}).get("messages") or []
            msg = messages[0]["text"] if messages else ""
            raise Exception(f"Error fetching transaction. Response message: {msg}")

        relevant_rows = [r for r in response["body"]["table"]["rows"] if r.get("RecTypeSpecified")]

        async def _get_more_details(row: dict) -> dict:
            if self.options.additional_transaction_information:
                return await _get_extra_transaction_details(self.page, row, headers)
            return {"entries": {}, "memo": None}

        opt_in = self.options.opt_in_features or []
        osh_txn = await _convert_transactions(
            relevant_rows, _get_more_details, "mizrahi:pendingIfTodayTransaction" in opt_in, self.options
        )

        for i, txn in enumerate(osh_txn):
            if self._should_mark_as_pending(txn, opt_in):
                osh_txn[i] = dc_replace(txn, status=TransactionStatuses.pending)

        start_moment = _get_start_moment(self.options.start_date)
        osh_txn_after_start = [t for t in osh_txn if t.date[:10] >= start_moment.isoformat()]

        pending_txn = await self._get_pending_transactions()
        all_txn = [*osh_txn_after_start, *pending_txn]

        balance_raw = response["body"].get("fields", {}).get("Yitra")
        return TransactionsAccount(
            account_number=account_number,
            txns=all_txn,
            balance=float(balance_raw) if balance_raw is not None else None,
        )

    def _should_mark_as_pending(self, txn: Transaction, opt_in: list[str]) -> bool:
        if "mizrahi:pendingIfNoIdentifier" in opt_in and not txn.identifier:
            debug.debug("Marking transaction '%s' as pending due to no identifier.", txn.description)
            return True
        if "mizrahi:pendingIfHasGenericDescription" in opt_in and txn.description in GENERIC_DESCRIPTIONS:
            debug.debug("Marking transaction '%s' as pending due to generic description.", txn.description)
            return True
        return False
