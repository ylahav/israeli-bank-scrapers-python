"""Port of src/scrapers/interface.ts

Notes on translation from TypeScript:
  - TS's union-typed `ScraperCredentials` is dropped in favor of each concrete
    scraper defining its own credentials dataclass (e.g. `LeumiCredentials` in
    scrapers/leumi.py). Python has no first-class discriminated unions, and a
    per-scraper dataclass is both simpler and gives you real autocomplete/type
    checking at the call site.
  - `Page`/`Browser`/`BrowserContext` come from Playwright's async API
    (playwright.async_api) rather than Puppeteer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional

from .errors import ErrorResult, ScraperErrorTypes
from .transactions import TransactionsAccount

if TYPE_CHECKING:
    from playwright.async_api import Browser, BrowserContext, Page


@dataclass
class FutureDebit:
    amount: float
    amount_currency: str
    charge_date: Optional[str] = None
    bank_account_number: Optional[str] = None


@dataclass
class OutputDataOptions:
    enable_transactions_filter_by_date: bool = False
    """If true, results are NOT filtered by start date — you get raw scraped data."""


@dataclass
class ScraperOptions:
    """Options shared by every scraper.

    Mirrors the JS library's `ScraperOptions` union of "how to get a browser"
    variants (external browser / external browser context / launch our own),
    flattened into optional fields since Python favors explicit `None` checks
    over structural unions here.
    """

    company_id: str
    start_date: "Any"  # datetime.date | datetime.datetime

    # --- browser acquisition (pick at most one style) ---
    browser: Optional["Browser"] = None
    """An externally created Playwright Browser. Closed after scraping unless skip_close_browser=True."""
    skip_close_browser: bool = False
    browser_context: Optional["BrowserContext"] = None
    """An externally managed BrowserContext (mutually exclusive with `browser`)."""
    show_browser: bool = False
    """Show the browser while scraping — good for debugging. Default headless."""
    browser_engine: Optional[str] = None
    """"chromium" (default) or "camoufox". Camoufox is a hardened, fingerprint-spoofing
    Firefox build (https://camoufox.com/) needed by scrapers facing aggressive bot
    detection (Cloudflare Bot Management) that vanilla Chromium automation can't get
    past — currently Isracard/Amex. Requires the optional `camoufox` package (see
    requirements-camoufox.txt) and its own Firefox binary (`python -m camoufox fetch`).
    If unset, each scraper class's own default (BaseScraperWithBrowser.DEFAULT_BROWSER_ENGINE)
    is used — most scrapers default to "chromium"; IsracardAmexBaseScraper defaults to
    "camoufox". Explicitly setting this overrides that per-scraper default either way."""
    executable_path: Optional[str] = None
    args: Optional[list[str]] = None
    timeout: Optional[float] = None
    """Maximum navigation time in ms."""
    prepare_browser: Optional[Callable[["Browser"], Awaitable[None]]] = None

    # --- general behavior ---
    verbose: bool = False
    future_months_to_scrape: Optional[int] = None
    combine_installments: bool = False
    prepare_page: Optional[Callable[["Page"], Awaitable[None]]] = None
    store_failure_screenshot_path: Optional[str] = None
    default_timeout: Optional[float] = None
    output_data: OutputDataOptions = field(default_factory=OutputDataOptions)
    additional_transaction_information: bool = False
    include_raw_transaction: bool = False
    viewport_size: Optional[dict[str, int]] = None
    """e.g. {"width": 1024, "height": 768}"""
    navigation_retry_count: int = 0
    opt_in_features: list[str] = field(default_factory=list)


@dataclass
class ScraperScrapingResult:
    success: bool
    accounts: Optional[list[TransactionsAccount]] = None
    future_debits: Optional[list[FutureDebit]] = None
    error_type: Optional[ScraperErrorTypes] = None
    error_message: Optional[str] = None
    """Only set when success=False."""


@dataclass
class ScraperLoginResult:
    success: bool
    error_type: Optional[ScraperErrorTypes] = None
    error_message: Optional[str] = None
    persistent_otp_token: Optional[str] = None


ScraperTwoFactorAuthTriggerResult = ErrorResult | dict  # {"success": True}
ScraperGetLongTermTwoFactorTokenResult = ErrorResult | dict  # {"success": True, "long_term_two_factor_auth_token": str}
