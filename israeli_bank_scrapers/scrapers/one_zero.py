"""Port of src/scrapers/one-zero.ts

Unlike every other scraper in this port, One Zero never launches a browser —
it's a pure API client (GraphQL + REST), so it subclasses `BaseScraper`
directly rather than `BaseScraperWithBrowser`. Supports two credential
shapes: a one-time OTP flow (phone number + a caller-supplied code retriever)
or a previously-obtained long-term OTP token, mirroring the union type in
the original TypeScript.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Awaitable, Callable, Optional

from ..definitions import ScraperProgressTypes
from ..errors import ScraperErrorTypes, create_generic_error
from ..helpers.debug import get_debug
from ..helpers.fetch import fetch_graphql, fetch_post
from ..helpers.transactions import get_raw_transaction
from ..interface import (
    ScraperGetLongTermTwoFactorTokenResult,
    ScraperLoginResult,
    ScraperOptions,
    ScraperScrapingResult,
    ScraperTwoFactorAuthTriggerResult,
)
from ..transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper import BaseScraper
from .one_zero_queries import GET_CUSTOMER, GET_MOVEMENTS

debug = get_debug("one-zero")

HEBREW_WORDS_REGEX = re.compile(r"[\u0590-\u05FF][\u0590-\u05FF\"'\-_ /\\]*[\u0590-\u05FF]")

IDENTITY_SERVER_URL = "https://identity.tfd-bank.com/v1/"
GRAPHQL_API_URL = "https://mobile.tfd-bank.com/mobile-graph/graphql"


def _is_success(result) -> bool:
    """login()/OTP helpers return either an ErrorResult dataclass or a plain
    success dict (mirrors the TS union return type) — normalize access to
    both shapes rather than assuming one."""
    if isinstance(result, dict):
        return bool(result.get("success"))
    return bool(getattr(result, "success", False))


def _err_type(result):
    if isinstance(result, dict):
        return result.get("error_type")
    return getattr(result, "error_type", None)


def _err_msg(result):
    if isinstance(result, dict):
        return result.get("error_message")
    return getattr(result, "error_message", None)


def _field(result, key, default=None):
    if isinstance(result, dict):
        return result.get(key, default)
    return getattr(result, key, default)


@dataclass
class OneZeroCredentials:
    email: str
    password: str
    # exactly one of these two groups should be provided, mirroring the
    # TypeScript union type — validated at use time in resolve_otp_token()
    otpCodeRetriever: Optional[Callable[[], Awaitable[str]]] = None  # noqa: N815
    phoneNumber: Optional[str] = None  # noqa: N815
    otpLongTermToken: Optional[str] = None  # noqa: N815


class OneZeroScraper(BaseScraper[OneZeroCredentials]):
    def __init__(self, options: ScraperOptions):
        super().__init__(options)
        self._otp_context: Optional[str] = None
        self._access_token: Optional[str] = None

    async def initialize(self) -> None:
        # BaseScraper.initialize() only emits a progress event — no browser to set up.
        await super().initialize()

    async def trigger_two_factor_auth(self, phone_number: str) -> ScraperTwoFactorAuthTriggerResult:
        if not phone_number.startswith("+"):
            return create_generic_error(
                "A full international phone number starting with + and a three digit country code is required"
            )
        debug.debug("Fetching device token")
        device_token_response = await fetch_post(f"{IDENTITY_SERVER_URL}/devices/token", {"extClientId": "mobile", "os": "Android"})
        device_token = device_token_response["resultData"]["deviceToken"]

        debug.debug("Sending OTP to phone number %s", phone_number)
        otp_prepare_response = await fetch_post(
            f"{IDENTITY_SERVER_URL}/otp/prepare",
            {"factorValue": phone_number, "deviceToken": device_token, "otpChannel": "SMS_OTP"},
        )
        otp_context = otp_prepare_response["resultData"]["otpContext"]
        self._otp_context = otp_context

        return {"success": True}

    async def get_long_term_two_factor_token(self, otp_code: str) -> ScraperGetLongTermTwoFactorTokenResult:
        if not self._otp_context:
            return create_generic_error("triggerOtp was not called before calling getPermenantOtpToken()")

        debug.debug("Requesting OTP token")
        otp_verify_response = await fetch_post(
            f"{IDENTITY_SERVER_URL}/otp/verify", {"otpContext": self._otp_context, "otpCode": otp_code}
        )
        otp_token = otp_verify_response["resultData"]["otpToken"]
        return {"success": True, "long_term_two_factor_auth_token": otp_token}

    async def _resolve_otp_token(self, credentials: OneZeroCredentials) -> ScraperGetLongTermTwoFactorTokenResult:
        if credentials.otpLongTermToken:
            return {"success": True, "long_term_two_factor_auth_token": credentials.otpLongTermToken}

        if credentials.otpLongTermToken is not None and not credentials.otpLongTermToken:
            return create_generic_error("Invalid otpLongTermToken")

        if not credentials.otpCodeRetriever:
            return ScraperLoginResult(
                success=False,
                error_type=ScraperErrorTypes.two_factor_retriever_missing,
                error_message="otpCodeRetriever is required when otpPermanentToken is not provided",
            )

        if not credentials.phoneNumber:
            return create_generic_error("phoneNumber is required when providing a otpCodeRetriever callback")

        debug.debug("Triggering user supplied otpCodeRetriever callback")
        trigger_result = await self.trigger_two_factor_auth(credentials.phoneNumber)
        if not _is_success(trigger_result):
            return trigger_result

        otp_code = await credentials.otpCodeRetriever()

        otp_token_result = await self.get_long_term_two_factor_token(otp_code)
        if not _is_success(otp_token_result):
            return otp_token_result

        return {"success": True, "long_term_two_factor_auth_token": _field(otp_token_result, "long_term_two_factor_auth_token")}

    async def login(self, credentials: OneZeroCredentials) -> ScraperLoginResult:
        otp_token_result = await self._resolve_otp_token(credentials)
        if not _is_success(otp_token_result):
            return ScraperLoginResult(
                success=False,
                error_type=_err_type(otp_token_result) or ScraperErrorTypes.general,
                error_message=_err_msg(otp_token_result),
            )

        long_term_token = _field(otp_token_result, "long_term_two_factor_auth_token")

        debug.debug("Requesting id token")
        get_id_token_response = await fetch_post(
            f"{IDENTITY_SERVER_URL}/getIdToken",
            {"otpSmsToken": long_term_token, "email": credentials.email, "pass": credentials.password, "pinCode": ""},
        )
        id_token = get_id_token_response["resultData"]["idToken"]

        debug.debug("Requesting session token")
        get_session_token_response = await fetch_post(
            f"{IDENTITY_SERVER_URL}/sessions/token", {"idToken": id_token, "pass": credentials.password}
        )
        access_token = get_session_token_response["resultData"]["accessToken"]

        self._access_token = access_token
        self._emit_progress(ScraperProgressTypes.login_success)

        return ScraperLoginResult(success=True, persistent_otp_token=long_term_token)

    def _sanitize_hebrew(self, text: str) -> str:
        """One Zero hebrew strings are reversed with a unicode control character
        that forces LTR display order. Strip that control character, then
        reverse the hebrew substrings back to correct reading order."""
        if "\u202d" not in text:
            return text.strip()

        plain = text.replace("\u202d", "").strip()
        out: list[str] = []
        index = 0
        for match in HEBREW_WORDS_REGEX.finditer(plain):
            start, end = match.start(), match.end()
            out.append(plain[index:start])
            out.append("".join(reversed(plain[start:end])))
            index = end
        out.append(plain[index:])
        return "".join(out)

    async def _fetch_portfolio_movements(self, portfolio: dict, start_date: date) -> TransactionsAccount:
        account = portfolio["accounts"][0]
        cursor = None
        movements: list[dict] = []

        while True:
            debug.debug("Fetching transactions for account %s...", portfolio["portfolioNum"])
            result = await fetch_graphql(
                GRAPHQL_API_URL,
                GET_MOVEMENTS,
                {
                    "portfolioId": portfolio["portfolioId"],
                    "accountId": account["accountId"],
                    "language": "HEBREW",
                    "pagination": {"cursor": cursor, "limit": 50},
                },
                {"authorization": f"Bearer {self._access_token}"},
            )
            new_movements = result["movements"]["movements"]
            pagination = result["movements"]["pagination"]

            movements[:0] = new_movements  # prepend, matching upstream's unshift
            cursor = pagination["cursor"]

            if movements and datetime.fromisoformat(movements[0]["movementTimestamp"].replace("Z", "+00:00")).date() < start_date:
                break
            if not pagination["hasMore"]:
                break

        movements.sort(key=lambda m: m["movementTimestamp"])

        matching = [
            m for m in movements if datetime.fromisoformat(m["movementTimestamp"].replace("Z", "+00:00")).date() >= start_date
        ]

        txns = []
        for movement in matching:
            enrichment = (movement.get("transaction") or {}).get("enrichment") or {}
            recurrences = enrichment.get("recurrences") or []
            has_installments = any(r.get("isRecurrent") for r in recurrences)
            modifier = -1 if movement["creditDebit"] == "DEBIT" else 1

            t = Transaction(
                identifier=movement["movementId"],
                date=movement["valueDate"],
                charged_amount=float(movement["movementAmount"]) * modifier,
                charged_currency=movement["movementCurrency"],
                original_amount=float(movement["movementAmount"]) * modifier,
                original_currency=movement["movementCurrency"],
                description=self._sanitize_hebrew(movement["description"]),
                processed_date=movement["movementTimestamp"],
                status=TransactionStatuses.completed,
                type=TransactionTypes.installments if has_installments else TransactionTypes.normal,
            )
            if self.options.include_raw_transaction:
                t.raw_transaction = get_raw_transaction(movement)
            txns.append(t)

        balance = 0.0 if not movements else float(movements[-1]["runningBalance"])
        return TransactionsAccount(account_number=portfolio["portfolioNum"], balance=balance, txns=txns)

    async def fetch_data(self) -> ScraperScrapingResult:
        if not self._access_token:
            return create_generic_error("login() was not called")

        default_start = date.today() - timedelta(days=365 - 1)
        start_date = self.options.start_date or default_start
        start_moment = max(default_start, start_date)

        debug.debug("Fetching account list")
        result = await fetch_graphql(
            GRAPHQL_API_URL, GET_CUSTOMER, {}, {"authorization": f"Bearer {self._access_token}"}
        )
        portfolios = [p for customer in result["customer"] for p in (customer.get("portfolios") or [])]

        import asyncio

        accounts = await asyncio.gather(*[self._fetch_portfolio_movements(p, start_moment) for p in portfolios])
        return ScraperScrapingResult(success=True, accounts=list(accounts))
