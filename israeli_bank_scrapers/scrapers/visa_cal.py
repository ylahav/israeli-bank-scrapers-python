"""Port of src/scrapers/visa-cal.ts

The trickiest scraper in this port: login happens in an iframe, and the
scraper needs to intercept an outgoing SSO request to read its Authorization
header (rather than the header being handed to it directly) before it can
call the card API out-of-page via plain HTTP (helpers/fetch.py's
`fetch_post`, not the in-page variant).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace as dc_replace
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional

from ..helpers.debug import get_debug
from ..helpers.elements_interactions import click_button, element_present_on_page, page_eval, wait_until_element_found
from ..helpers.fetch import fetch_post
from ..helpers.navigation import get_current_url, wait_for_redirect
from ..helpers.storage import get_from_session_storage
from ..helpers.transactions import filter_old_transactions, get_raw_transaction
from ..helpers.waiting import wait_until
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import CardType, Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Frame, Page

debug = get_debug("visa-cal")

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    "Origin": "https://digital-web.cal-online.co.il",
    "Referer": "https://digital-web.cal-online.co.il",
    "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
}
LOGIN_URL = "https://www.cal-online.co.il/"
TRANSACTIONS_REQUEST_ENDPOINT = "https://api.cal-online.co.il/Transactions/api/transactionsDetails/getCardTransactionsDetails"
FRAMES_REQUEST_ENDPOINT = "https://api.cal-online.co.il/Frames/api/Frames/GetFrameStatus"
PENDING_TRANSACTIONS_REQUEST_ENDPOINT = "https://api.cal-online.co.il/Transactions/api/approvals/getClearanceRequests"
SSO_AUTHORIZATION_REQUEST_ENDPOINT = "https://connect.cal-online.co.il/col-rest/calconnect/authentication/SSO"

INVALID_PASSWORD_MESSAGE = "\u05e9\u05dd \u05d4\u05de\u05e9\u05ea\u05de\u05e9 \u05d0\u05d5 \u05d4\u05e1\u05d9\u05e1\u05de\u05d4 \u05e9\u05d4\u05d5\u05d6\u05e0\u05d5 \u05e9\u05d2\u05d5\u05d9\u05d9\u05dd"
CHANGE_PASSWORD_MESSAGE = "\u05dc\u05d4\u05d7\u05dc\u05d9\u05e3 \u05e1\u05d9\u05e1\u05de\u05d4"
CHANGE_PASSWORD_SUBTITLE = "\u05d4\u05d2\u05d9\u05e2 \u05d4\u05d6\u05de\u05df \u05dc\u05e1\u05d9\u05e1\u05de\u05d4 \u05d7\u05d3\u05e9\u05d4"
CHANGE_PASSWORD_URL = "/change-password"

TRN_TYPE_REGULAR = "5"
TRN_TYPE_CREDIT = "6"
TRN_TYPE_INSTALLMENTS = "8"
TRN_TYPE_STANDING_ORDER = "9"


@dataclass
class VisaCalCredentials:
    username: str
    password: str


async def _get_login_frame(page: "Page") -> "Frame":
    debug.debug("wait until login frame found")
    found = {}

    async def check() -> bool:
        candidates = [f.url for f in page.frames if "connect" in f.url]
        if candidates:
            debug.debug("candidate frame(s) matching 'connect': %s", candidates)
        frame = next((f for f in page.frames if "connect" in f.url), None)
        if frame:
            found["frame"] = frame
        return frame is not None

    await wait_until(check, "wait for iframe with login form", timeout=10, interval=1.0)
    if "frame" not in found:
        debug.debug("failed to find login frame for 10 seconds. all frame urls: %s", [f.url for f in page.frames])
        raise Exception("failed to extract login iframe")
    debug.debug("using login frame: %s", found["frame"].url)
    return found["frame"]


async def _has_invalid_password_error(page: "Page") -> bool:
    frame = await _get_login_frame(page)
    error_found = await element_present_on_page(frame, "div.general-error > div")
    error_message = ""
    if error_found:
        error_message = await page_eval(frame, "div.general-error > div", "", "(item) => item.innerText")
    return error_message == INVALID_PASSWORD_MESSAGE


async def _has_change_password_form(page: "Page") -> bool:
    change_password_frame = next(
        (f for f in page.frames if "connect.cal-online.co.il" in f.url and CHANGE_PASSWORD_URL in f.url), None
    )
    if change_password_frame:
        return True

    try:
        frame = await _get_login_frame(page)

        if await element_present_on_page(frame, "change-password"):
            return True
        if await element_present_on_page(frame, ".change-password-title"):
            return True
        if await element_present_on_page(frame, ".change-password-subtitle"):
            subtitle = await page_eval(frame, ".change-password-subtitle", "", "(item) => item.innerText.trim()")
            if CHANGE_PASSWORD_SUBTITLE in subtitle:
                return True

        error_found = await element_present_on_page(frame, ".err-desc")
        if error_found:
            err_text = await page_eval(frame, ".err-desc", "", "(item) => item.innerText.trim()")
            return CHANGE_PASSWORD_MESSAGE in err_text
    except Exception as e:
        debug.debug("failed to check change password form in login frame: %s", e)
    return False


def _get_possible_login_results() -> dict[str, list]:
    import re as _re

    async def _invalid(page: "Page") -> bool:
        return await _has_invalid_password_error(page)

    async def _change_pw(page: "Page") -> bool:
        return await _has_change_password_form(page)

    return {
        LoginResults.success: [_re.compile(r"dashboard", _re.I)],
        LoginResults.invalid_password: [_invalid],
        LoginResults.change_password: [_change_pw],
    }


def _create_login_fields(credentials: VisaCalCredentials) -> list[dict[str, str]]:
    return [
        {"selector": '[formcontrolname="userName"]', "value": credentials.username},
        {"selector": '[formcontrolname="password"]', "value": credentials.password},
    ]


def _is_pending(transaction: dict) -> bool:
    return "debCrdDate" not in transaction


def _convert_parsed_data_to_transactions(
    data: list[dict], pending_data: Optional[dict], options: ScraperOptions
) -> list[Transaction]:
    pending_transactions: list[dict] = []
    if pending_data and pending_data.get("result"):
        for card in pending_data["result"]["cardsList"]:
            pending_transactions.extend(card.get("authDetalisList") or [])

    bank_accounts = [ba for month_data in data for ba in month_data["result"]["bankAccounts"]]
    regular_debit_days = [d for acc in bank_accounts for d in acc["debitDates"]]
    immediate_debit_days = [d for acc in bank_accounts for d in acc["immidiateDebits"]["debitDays"]]
    completed_transactions = [t for d in (regular_debit_days + immediate_debit_days) for t in d["transactions"]]

    all_txns = [*pending_transactions, *completed_transactions]

    result = []
    for transaction in all_txns:
        pending = _is_pending(transaction)
        num_of_payments = transaction.get("numberOfPayments") if pending else transaction.get("numOfPayments")
        installments = None
        if num_of_payments:
            from ..transactions import TransactionInstallments

            installments = TransactionInstallments(
                number=1 if pending else transaction["curPaymentNum"], total=num_of_payments
            )

        txn_date = datetime.fromisoformat(transaction["trnPurchaseDate"].replace("Z", "+00:00"))

        charged_amount = -(transaction["trnAmt"] if pending else transaction["amtBeforeConvAndIndex"])
        original_amount = transaction["trnAmt"] * (1 if transaction["trnTypeCode"] == TRN_TYPE_CREDIT else -1)

        if installments:
            date_iso = _add_months_iso(txn_date, installments.number - 1)
        else:
            date_iso = txn_date.isoformat().replace("+00:00", "Z")

        if pending:
            processed_date = txn_date.isoformat().replace("+00:00", "Z")
        else:
            processed_date = datetime.fromisoformat(transaction["debCrdDate"].replace("Z", "+00:00")).isoformat().replace("+00:00", "Z")

        t = Transaction(
            identifier=transaction.get("trnIntId") if not pending else None,
            type=(
                TransactionTypes.normal
                if transaction["trnTypeCode"] in (TRN_TYPE_REGULAR, TRN_TYPE_STANDING_ORDER)
                else TransactionTypes.installments
            ),
            status=TransactionStatuses.pending if pending else TransactionStatuses.completed,
            date=date_iso,
            processed_date=processed_date,
            original_amount=original_amount,
            original_currency=transaction["trnCurrencySymbol"],
            charged_amount=charged_amount,
            charged_currency=transaction.get("debCrdCurrencySymbol") if not pending else None,
            description=transaction["merchantName"],
            memo=str(transaction.get("transTypeCommentDetails") or ""),
            category=transaction.get("branchCodeDesc"),
            installments=installments,
        )
        if options.include_raw_transaction:
            t.raw_transaction = get_raw_transaction(transaction)
        result.append(t)
    return result


def _add_months_iso(dt: datetime, months: int) -> str:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    day = min(dt.day, 28)
    shifted = dt.replace(year=year, month=month, day=day)
    return shifted.isoformat().replace("+00:00", "Z")


class VisaCalScraper(BaseScraperWithBrowser[VisaCalCredentials]):
    def __init__(self, options: ScraperOptions):
        super().__init__(options)
        self._authorization: Optional[str] = None
        self._auth_request_task: Optional[asyncio.Task] = None

    async def _open_login_popup(self) -> "Frame":
        debug.debug("open login popup, wait until login button available")
        await wait_until_element_found(self.page, "#ccLoginDesktopBtn", only_visible=True)
        debug.debug("click on the login button")
        await click_button(self.page, "#ccLoginDesktopBtn")
        debug.debug("current page url right after click: %s", get_current_url(self.page))
        debug.debug("get the frame that holds the login")
        frame = await _get_login_frame(self.page)
        debug.debug("wait until the password login tab header is available")
        await wait_until_element_found(frame, "#regular-login")
        debug.debug("navigate to the password login tab")
        await click_button(frame, "#regular-login")
        debug.debug("wait until the password login tab is active")
        await wait_until_element_found(frame, "regular-login")
        return frame

    async def get_cards(self) -> list[dict]:
        async def fetch_init():
            return await get_from_session_storage(self.page, "init")

        init_data = await wait_until(fetch_init, "get init data in session storage", timeout=10, interval=1.0)
        if not init_data:
            raise Exception('could not find "init" data in session storage')
        return [{"cardUniqueId": c["cardUniqueId"], "last4Digits": c["last4Digits"]} for c in init_data["result"]["cards"]]

    async def get_authorization_header(self) -> str:
        if not self._authorization:
            debug.debug("fetching authorization header")

            async def fetch_auth():
                data = await get_from_session_storage(self.page, "auth-module")
                token = ((data or {}).get("auth") or {}).get("calConnectToken")
                return data if token and str(token).strip() else None

            auth_module = await wait_until(
                fetch_auth, "get authorization header with valid token in session storage", timeout=10, interval=0.05
            )
            return f"CALAuthScheme {auth_module['auth']['calConnectToken']}"
        return self._authorization

    async def get_x_site_id(self) -> str:
        return "09031987-273E-2311-906C-8AF85B17C8D9"

    def get_login_options(self, credentials: VisaCalCredentials) -> LoginOptions:
        # Python's Playwright API has no plain `wait_for_request()` (unlike Node's
        # Playwright/Puppeteer) — only `expect_request()` as a context manager, which
        # doesn't fit this "start listening now, resolve later" shape. Use a raw
        # request-event listener + future instead.
        auth_future: asyncio.Future = asyncio.get_event_loop().create_future()

        def _on_request(request):
            if not auth_future.done() and request.url == SSO_AUTHORIZATION_REQUEST_ENDPOINT:
                auth_future.set_result(request)

        self.page.on("request", _on_request)

        async def _wait_for_auth_request():
            try:
                return await asyncio.wait_for(auth_future, timeout=10.0)
            except asyncio.TimeoutError:
                debug.debug("timed out waiting for the SSO token request")
                return None
            except Exception as e:
                debug.debug("error while waiting for the token request: %s", e)
                return None

        self._auth_request_task = asyncio.ensure_future(_wait_for_auth_request())

        async def _post_action():
            try:
                debug.debug(
                    "waiting for the SPA to redirect after login (URL change from %s)", get_current_url(self.page)
                )
                await wait_for_redirect(self.page, timeout=20.0)
                current_url = get_current_url(self.page)
                debug.debug("post-login url: %s", current_url)
                if current_url.endswith("site-tutorial"):
                    await click_button(self.page, "button.btn-close")
                request = await self._auth_request_task
                self._authorization = str((request.headers.get("authorization") if request else "") or "").strip()
                debug.debug("authorization header captured: %s", bool(self._authorization))
            except Exception as e:
                current_url = get_current_url(self.page)
                debug.debug("post_action exception with current url %s: %s", current_url, e)
                if current_url.endswith("dashboard"):
                    return
                if await _has_change_password_form(self.page):
                    return
                raise e

        return LoginOptions(
            login_url=LOGIN_URL,
            fields=_create_login_fields(credentials),
            submit_button_selector='button[type="submit"]',
            possible_results=_get_possible_login_results(),
            check_readiness=lambda: wait_until_element_found(self.page, "#ccLoginDesktopBtn"),
            pre_action=self._open_login_popup,
            post_action=_post_action,
            user_agent=API_HEADERS["User-Agent"],
        )

    async def _fetch_card_data(
        self,
        card: dict,
        start_moment: date,
        start_date: date,
        future_months_to_scrape: int,
        authorization: str,
        x_site_id: str,
    ) -> TransactionsAccount:
        debug.debug("fetch frames (misgarot) for card %s", card["cardUniqueId"])
        headers = {"Authorization": authorization, "X-Site-Id": x_site_id, "Content-Type": "application/json", **API_HEADERS}
        frames = await fetch_post(
            FRAMES_REQUEST_ENDPOINT, {"cardsForFrameData": [{"cardUniqueId": card["cardUniqueId"]}]}, headers
        )

        result = frames.get("result") or {}
        bank_issued_frame = next(
            (f for f in (result.get("bankIssuedCards") or {}).get("cardLevelFrames") or [] if f["cardUniqueId"] == card["cardUniqueId"]),
            None,
        )
        cal_issued_frame = next(
            (f for f in (result.get("calIssuedCards") or {}).get("cardLevelFrames") or [] if f["cardUniqueId"] == card["cardUniqueId"]),
            None,
        )

        if bank_issued_frame:
            frame = bank_issued_frame
            card_type = CardType.bank_issued
            account_group = result.get("bankIssuedCards")
        else:
            frame = cal_issued_frame
            card_type = CardType.company_issued
            account_group = result.get("calIssuedCards")

        balance_date = (frame or {}).get("nextDebitDate") or (account_group or {}).get("nextTotalDebitDateForAccount")

        final_month = date.today().replace(day=1)
        final_month = _add_months(final_month, future_months_to_scrape)
        months_diff = (final_month.year - start_moment.year) * 12 + (final_month.month - start_moment.month)

        debug.debug("fetch pending transactions for card %s", card["cardUniqueId"])
        pending_data = await fetch_post(
            PENDING_TRANSACTIONS_REQUEST_ENDPOINT, {"cardUniqueIDArray": [card["cardUniqueId"]]}, headers
        )

        debug.debug("fetch completed transactions for card %s", card["cardUniqueId"])
        all_months_data = []
        for i in range(months_diff + 1):
            month = _add_months(final_month, -i)
            month_data = await fetch_post(
                TRANSACTIONS_REQUEST_ENDPOINT,
                {"cardUniqueId": card["cardUniqueId"], "month": str(month.month), "year": str(month.year)},
                headers,
            )
            if month_data.get("statusCode") != 1:
                raise Exception(f"failed to fetch transactions for card {card['last4Digits']}. Message: {month_data.get('title', '')}")
            all_months_data.append(month_data)

        if pending_data.get("statusCode") not in (1, 96):
            debug.debug(
                "failed to fetch pending transactions for card %s. Message: %s",
                card["last4Digits"],
                pending_data.get("title", ""),
            )
            pending_data = None

        transactions = _convert_parsed_data_to_transactions(all_months_data, pending_data, self.options)

        debug.debug("filter out old transactions")
        if self.options.output_data.enable_transactions_filter_by_date or True:
            start_iso = start_date.isoformat() + "T00:00:00.000Z"
            txns = filter_old_transactions(transactions, start_iso, self.options.combine_installments)
        else:
            txns = transactions

        balance_amount = (frame or {}).get("nextTotalDebit")
        if balance_amount is None:
            balance_amount = (account_group or {}).get("nextTotalDebitForAccount")

        return TransactionsAccount(
            txns=txns,
            balance=-balance_amount if balance_amount is not None else None,
            balance_date=balance_date,
            account_number=card["last4Digits"],
            card_type=card_type,
            card_frame=(account_group or {}).get("frameLimitForCardAmount"),
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        default_start = date.today() - timedelta(days=365 + 30 * 6 - 1)
        start_date = self.options.start_date or default_start
        start_moment = max(default_start, start_date)
        debug.debug("fetch transactions starting %s", start_moment.isoformat())

        cards, x_site_id, authorization = await asyncio.gather(
            self.get_cards(), self.get_x_site_id(), self.get_authorization_header()
        )

        future_months_to_scrape = self.options.future_months_to_scrape if self.options.future_months_to_scrape is not None else 1

        accounts = await asyncio.gather(
            *[
                self._fetch_card_data(card, start_moment, start_date, future_months_to_scrape, authorization, x_site_id)
                for card in cards
            ]
        )

        debug.debug("return the scraped accounts")
        return ScraperScrapingResult(success=True, accounts=list(accounts))


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return d.replace(year=year, month=month, day=1)
