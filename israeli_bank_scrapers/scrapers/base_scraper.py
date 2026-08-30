"""Port of src/scrapers/base-scraper.ts

Notes on translation:
  - JS's EventEmitter-based `onProgress` becomes a plain list of callbacks.
  - `moment.tz.setDefault('Asia/Jerusalem')` (a process-global default timezone
    for date formatting) has no direct equivalent here — this port formats
    dates explicitly wherever it matters (see helpers/transactions.py), so
    there's nothing to set globally. If you need it, set the `TZ` env var
    before your process starts, or attach `zoneinfo.ZoneInfo("Asia/Jerusalem")`
    to your own datetime objects.
"""

from __future__ import annotations

from typing import Awaitable, Callable, Generic, Optional, TypeVar

from ..definitions import ScraperProgressTypes
from ..errors import create_generic_error, create_timeout_error
from ..helpers.waiting import TimeoutError as ScraperTimeoutError
from ..interface import ScraperLoginResult, ScraperOptions, ScraperScrapingResult

TCredentials = TypeVar("TCredentials")

ProgressCallback = Callable[[str, ScraperProgressTypes], None]

# Called when a scraper hits a "type in the code we texted/emailed you" step
# mid-login. Receives a small context dict (at minimum {"company_id": ...},
# scrapers may add more — e.g. a phone number hint) and must return the code
# as a string. Set by whatever is driving the scraper: cli.py wires this to
# the NDJSON otp_required/otp_code round-trip over stdio; a direct Python
# caller can set scraper.otp_provider to any async function, e.g. one that
# prompts on a console or a GUI.
OtpProvider = Callable[[dict], Awaitable[str]]


class BaseScraper(Generic[TCredentials]):
    def __init__(self, options: ScraperOptions):
        self.options = options
        self._progress_listeners: list[ProgressCallback] = []
        self.otp_provider: Optional[OtpProvider] = None

    async def request_otp_code(self, context: Optional[dict] = None) -> str:
        """Called by a scraper's login flow when the site requires a code
        sent via SMS/email/etc. Blocks until whatever set `otp_provider`
        supplies one. Raises if nothing configured it — a scraper hitting
        this with no provider set is a caller error, not a scraper bug: the
        caller needs a way to actually get the code to the end user."""
        if not self.otp_provider:
            raise Exception(
                f"{self.options.company_id} requires a one-time code mid-login, but no otp_provider was "
                "configured. Set scraper.otp_provider to an async function that returns the code (a console "
                "prompt, a GUI dialog, or — when driven via cli.py — this is already wired to the "
                "otp_required/otp_code NDJSON round-trip automatically)."
            )
        full_context = {"company_id": self.options.company_id, **(context or {})}
        return await self.otp_provider(full_context)

    async def initialize(self) -> None:
        self._emit_progress(ScraperProgressTypes.initializing)

    async def scrape(self, credentials: TCredentials) -> ScraperScrapingResult:
        self._emit_progress(ScraperProgressTypes.start_scraping)
        await self.initialize()

        try:
            login_result = await self.login(credentials)
        except Exception as e:
            login_result = (
                create_timeout_error(str(e)) if isinstance(e, ScraperTimeoutError) else create_generic_error(str(e))
            )

        scrape_result: ScraperScrapingResult
        if login_result.success:
            try:
                scrape_result = await self.fetch_data()
            except Exception as e:
                scrape_result = ScraperScrapingResult(
                    success=False,
                    error_type=(create_timeout_error(str(e)) if isinstance(e, ScraperTimeoutError) else create_generic_error(str(e))).error_type,
                    error_message=str(e),
                )
        else:
            scrape_result = ScraperScrapingResult(
                success=False,
                error_type=login_result.error_type,
                error_message=login_result.error_message,
            )

        try:
            success = bool(scrape_result and scrape_result.success is True)
            await self.terminate(success)
        except Exception as e:
            scrape_result = ScraperScrapingResult(
                success=False,
                error_type=create_generic_error(str(e)).error_type,
                error_message=str(e),
            )

        self._emit_progress(ScraperProgressTypes.end_scraping)
        return scrape_result

    async def trigger_two_factor_auth(self, phone_number: str):
        raise NotImplementedError(f"trigger_two_factor_auth() is not implemented in {self.options.company_id}")

    async def get_long_term_two_factor_token(self, otp_code: str):
        raise NotImplementedError(f"get_long_term_two_factor_token() is not implemented in {self.options.company_id}")

    async def login(self, credentials: TCredentials) -> ScraperLoginResult:
        raise NotImplementedError(f"login() is not implemented in {self.options.company_id}")

    async def fetch_data(self) -> ScraperScrapingResult:
        raise NotImplementedError(f"fetch_data() is not implemented in {self.options.company_id}")

    async def terminate(self, success: bool) -> None:
        self._emit_progress(ScraperProgressTypes.terminating)

    def _emit_progress(self, progress_type: ScraperProgressTypes) -> None:
        for listener in self._progress_listeners:
            listener(self.options.company_id, progress_type)

    def on_progress(self, func: ProgressCallback) -> None:
        self._progress_listeners.append(func)
