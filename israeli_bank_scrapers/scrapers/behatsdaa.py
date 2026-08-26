"""Port of src/scrapers/behatsdaa.ts"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from ..helpers.debug import get_debug
from ..helpers.elements_interactions import wait_until_element_found
from ..helpers.fetch import fetch_post_within_page
from ..helpers.transactions import get_raw_transaction
from ..helpers.waiting import sleep
from ..interface import ScraperOptions, ScraperScrapingResult
from ..transactions import Transaction, TransactionsAccount, TransactionStatuses, TransactionTypes
from .base_scraper_with_browser import BaseScraperWithBrowser, LoginOptions, LoginResults

if TYPE_CHECKING:
    from playwright.async_api import Page

debug = get_debug("behatsdaa")

BASE_URL = "https://www.behatsdaa.org.il"
LOGIN_URL = f"{BASE_URL}/login"
PURCHASE_HISTORY_URL = "https://back.behatsdaa.org.il/api/purchases/purchaseHistory"


@dataclass
class BehatsdaaCredentials:
    id: str
    password: str


def _variant_to_transaction(variant: dict, options: ScraperOptions) -> Transaction:
    # The price is positive; make it negative since it's an expense.
    original_amount = -variant["customerPrice"]
    order_date = datetime.fromisoformat(variant["orderDate"].replace("Z", "+00:00")).strftime("%Y-%m-%d")
    t = Transaction(
        type=TransactionTypes.normal,
        identifier=variant.get("tTransactionID"),
        date=order_date,
        processed_date=order_date,
        original_amount=original_amount,
        original_currency="ILS",
        charged_amount=original_amount,
        charged_currency="ILS",
        description=variant["name"],
        status=TransactionStatuses.completed,
        memo=variant.get("variantName"),
    )
    if options.include_raw_transaction:
        t.raw_transaction = get_raw_transaction(variant)
    return t


class BehatsdaaScraper(BaseScraperWithBrowser[BehatsdaaCredentials]):
    def get_login_options(self, credentials: BehatsdaaCredentials) -> LoginOptions:
        async def _check_readiness() -> None:
            import asyncio

            await asyncio.gather(
                wait_until_element_found(self.page, "#loginPassword"),
                wait_until_element_found(self.page, "#loginId"),
            )

        async def _submit() -> None:
            await sleep(1.0)
            debug.debug("Trying to find submit button")
            button = await self.page.query_selector('xpath=//button[contains(., "\u05d4\u05ea\u05d7\u05d1\u05e8\u05d5\u05ea")]')
            if button:
                debug.debug("Submit button found")
                await button.click()
            else:
                debug.debug("Submit button not found")

        return LoginOptions(
            login_url=LOGIN_URL,
            fields=[
                {"selector": "#loginId", "value": credentials.id},
                {"selector": "#loginPassword", "value": credentials.password},
            ],
            check_readiness=_check_readiness,
            possible_results={
                LoginResults.success: [f"{BASE_URL}/"],
                LoginResults.invalid_password: [".custom-input-error-label"],
            },
            submit_button_selector=_submit,
        )

    async def fetch_data(self) -> ScraperScrapingResult:
        token = await self.page.evaluate("() => window.localStorage.getItem('userToken')")
        if not token:
            debug.debug("Token not found in local storage")
            return ScraperScrapingResult(success=False, error_message="TokenNotFound")

        from datetime import date as date_cls

        start = self.options.start_date or date_cls.today()
        body = {
            "FromDate": f"{start.isoformat()}T00:00:00",
            "ToDate": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "BenefitStatusId": None,
        }

        debug.debug("Fetching data")
        res = await fetch_post_within_page(
            self.page,
            PURCHASE_HISTORY_URL,
            body,
            {"authorization": f"Bearer {token}", "Content-Type": "application/json", "organizationid": "20"},
        )
        debug.debug("Data fetched")

        error = (res or {}).get("errorDescription") or ((res or {}).get("data") or {}).get("errorDescription")
        if error:
            debug.debug("Error fetching data: %s", error)
            return ScraperScrapingResult(success=False, error_message=error)

        if not res or not res.get("data"):
            debug.debug("No data found")
            return ScraperScrapingResult(success=False, error_message="NoData")

        debug.debug("Data fetched successfully")
        variants = res["data"].get("variants") or []
        account = TransactionsAccount(
            account_number=res["data"]["memberId"],
            txns=[_variant_to_transaction(v, self.options) for v in variants],
        )
        return ScraperScrapingResult(success=True, accounts=[account])
