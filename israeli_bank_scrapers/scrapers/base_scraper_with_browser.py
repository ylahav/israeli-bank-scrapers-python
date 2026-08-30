"""Port of src/scrapers/base-scraper-with-browser.ts to Playwright's async API.

Puppeteer -> Playwright translation notes:
  - `puppeteer.launch()` -> `playwright.chromium.launch()`. This class owns
    (starts/stops) its own `async_playwright()` instance when it launches its
    own browser, mirroring the JS lib's default "launch and close" behavior.
  - `page.setUserAgent()` has no direct Playwright `Page` equivalent (UA is
    normally set at `browser.new_context()` time). We approximate it with a
    CDP session override, which works on Chromium (the only engine this port
    targets, matching the original Puppeteer-only library).
  - `page.setCacheEnabled(false)` has no direct Playwright equivalent either;
    we approximate via a CDP `Network.setCacheDisabled` call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional, TypeVar

from ..definitions import ScraperProgressTypes
from ..errors import ScraperErrorTypes
from ..helpers.debug import get_debug
from ..helpers.elements_interactions import wait_until_element_found
from ..helpers.navigation import get_current_url_client_side
from ..interface import ScraperLoginResult, ScraperOptions, ScraperScrapingResult
from .base_scraper import BaseScraper

if TYPE_CHECKING:
    from playwright.async_api import Frame, Page

debug = get_debug("base-scraper-with-browser")

TCredentials = TypeVar("TCredentials")

PossibleResultCondition = "str | Callable[[dict], Awaitable[bool]]"
# possible_results: dict[LoginResults, list[str-substring | regex-pattern | async predicate]]


class LoginResults:
    success = "SUCCESS"
    unknown_error = "UNKNOWN_ERROR"
    two_factor_retriever_missing = ScraperErrorTypes.two_factor_retriever_missing
    invalid_password = ScraperErrorTypes.invalid_password
    change_password = ScraperErrorTypes.change_password
    account_blocked = ScraperErrorTypes.account_blocked


class LoginOptions:
    """Declarative description of a login flow, mirroring the JS `LoginOptions`.

    Attributes:
        login_url: URL to navigate to before login.
        fields: [{"selector": ..., "value": ...}, ...] filled in order.
        submit_button_selector: CSS selector to click, OR a zero-arg async
            callable to invoke instead (for logins that submit via JS/keyboard).
        check_readiness: optional async callable run instead of the default
            "wait for submit button" readiness check (e.g. when login needs a
            multi-step navigation before the form even exists).
        pre_action: optional async callable run before filling fields; may
            return a Frame to fill inputs into instead of the top-level page
            (e.g. when the login form lives in an iframe).
        post_action: optional async callable run instead of the default
            "wait for navigation" step after submitting.
        possible_results: dict mapping a LoginResults value to a list of
            match conditions, each either a substring, a compiled regex, or
            an async predicate `(page) -> bool`. Checked against the
            post-submit URL (or via the predicate, given the page).
        user_agent: optional UA override (see CDP note above).
        wait_until: Playwright navigation wait state for `login_url`.
        otp_step: optional OtpStep — set this for sites that text/email a
            one-time code mid-login (common for insurance companies; some
            banks too). Checked right after the initial credentials submit,
            before post_action.
    """

    def __init__(
        self,
        *,
        login_url: str,
        fields: list[dict[str, str]],
        submit_button_selector: "str | Callable[[], Awaitable[None]]",
        possible_results: dict[str, list[Any]],
        check_readiness: Optional[Callable[[], Awaitable[None]]] = None,
        pre_action: Optional[Callable[[], Awaitable["Frame | None"]]] = None,
        post_action: Optional[Callable[[], Awaitable[None]]] = None,
        user_agent: Optional[str] = None,
        wait_until: str = "load",
        otp_step: Optional["OtpStep"] = None,
    ):
        self.login_url = login_url
        self.fields = fields
        self.submit_button_selector = submit_button_selector
        self.possible_results = possible_results
        self.check_readiness = check_readiness
        self.pre_action = pre_action
        self.post_action = post_action
        self.user_agent = user_agent
        self.wait_until = wait_until
        self.otp_step = otp_step


class OtpStep:
    """Describes a "type in the code we texted/emailed you" step that shows
    up mid-login, after credentials are submitted but before the site
    considers you logged in.

    Attributes:
        detect_selector: element whose appearance means "the site wants a
            code now". Checked with a short timeout right after the initial
            submit — if it never appears, login proceeds normally (the site
            may skip OTP for a remembered device/session).
        input_selector: where to type the code once BaseScraper.request_otp_code()
            returns it. Use this for a single combined code field.
        input_selectors: alternative to input_selector, for sites that split
            the code across N separate single-digit boxes (not universal).
            Pass exactly one selector per box, in order; the
            code is zipped across them one character each. Provide exactly
            one of input_selector / input_selectors, not both.
        submit_selector: CSS selector to click, or a zero-arg async callable,
            same shape as LoginOptions.submit_button_selector.
        detect_timeout: seconds to wait for detect_selector before giving up
            and assuming OTP wasn't required this time.
        context: extra info passed through to request_otp_code() /
            otp_provider — e.g. {"hint": "sent to the phone on file"}. The
            company_id is always included automatically; this is for
            anything scraper-specific worth showing the end user.
    """

    def __init__(
        self,
        *,
        detect_selector: str,
        submit_selector: "str | Callable[[], Awaitable[None]]",
        input_selector: Optional[str] = None,
        input_selectors: Optional[list[str]] = None,
        detect_timeout: float = 15.0,
        context: Optional[dict] = None,
    ):
        if bool(input_selector) == bool(input_selectors):
            raise ValueError("OtpStep needs exactly one of input_selector or input_selectors, not both/neither")
        self.detect_selector = detect_selector
        self.input_selector = input_selector
        self.input_selectors = input_selectors
        self.submit_selector = submit_selector
        self.detect_timeout = detect_timeout
        self.context = context


async def _get_key_by_value(possible_results: dict[str, list[Any]], value: str, page: "Page") -> str:
    import re

    for key, conditions in possible_results.items():
        for condition in conditions:
            if isinstance(condition, re.Pattern):
                if condition.search(value):
                    return key
            elif callable(condition):
                if await condition(page):
                    return key
            else:
                if value.lower() == str(condition).lower():
                    return key
    debug.debug("no login result matched. final url was: %s", value)
    return LoginResults.unknown_error


def _create_general_error() -> ScraperScrapingResult:
    return ScraperScrapingResult(success=False, error_type=ScraperErrorTypes.general)


async def _safe_cleanup(cleanup: Callable[[], Awaitable[None]]) -> None:
    try:
        await cleanup()
    except Exception as e:
        debug.debug("Cleanup function failed: %s", e)


class BaseScraperWithBrowser(BaseScraper[TCredentials]):
    DEFAULT_VIEWPORT = {"width": 1024, "height": 768}
    DEFAULT_BROWSER_ENGINE = "chromium"

    def __init__(self, options: ScraperOptions):
        super().__init__(options)
        self._cleanups: list[Callable[[], Awaitable[None]]] = []
        self.page: "Page" = None  # type: ignore[assignment]
        self._playwright = None  # owned playwright instance, if we launched our own browser

    def get_viewport(self) -> dict[str, int]:
        return self.options.viewport_size or self.DEFAULT_VIEWPORT

    def get_browser_engine(self) -> str:
        return self.options.browser_engine or self.DEFAULT_BROWSER_ENGINE

    async def initialize(self) -> None:
        await super().initialize()
        debug.debug("initialize scraper")
        self._emit_progress(ScraperProgressTypes.initializing)

        page = await self._initialize_page()
        if not page:
            debug.debug("failed to initiate a browser page, exit")
            return

        self.page = page
        self._cleanups.append(page.close)

        try:
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
        except Exception as e:
            debug.debug("could not disable cache via CDP: %s", e)

        if self.options.default_timeout:
            self.page.set_default_timeout(self.options.default_timeout)

        if self.options.prepare_page:
            debug.debug("execute 'prepare_page' interceptor provided in options")
            await self.options.prepare_page(self.page)

        viewport = self.get_viewport()
        debug.debug("set viewport to width %s, height %s", viewport["width"], viewport["height"])
        await self.page.set_viewport_size(viewport)

        def _on_request_failed(request):
            failure = request.failure
            debug.debug("Request failed: %s %s", failure, request.url)

        self.page.on("requestfailed", _on_request_failed)

    async def _initialize_page(self) -> "Page":
        debug.debug("initialize browser page")

        if self.options.browser_context is not None:
            debug.debug("Using the browser context provided in options")
            return await self.options.browser_context.new_page()

        if self.options.browser is not None:
            debug.debug("Using the browser instance provided in options")
            browser = self.options.browser
            if not self.options.skip_close_browser:

                async def _close_provided_browser():
                    debug.debug("closing the browser")
                    await browser.close()

                self._cleanups.append(_close_provided_browser)
            return await browser.new_page()

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        headless = not self.options.show_browser
        engine = self.get_browser_engine()
        debug.debug("launch a %s browser with headless mode = %s", engine, headless)

        if engine == "camoufox":
            browser = await self._launch_camoufox_browser(headless)
        else:
            browser = await self._playwright.chromium.launch(
                headless=headless,
                executable_path=self.options.executable_path,
                args=self.options.args,
                timeout=self.options.timeout,
            )

        async def _close_own_browser():
            debug.debug("closing the browser")
            await browser.close()
            if self._playwright:
                await self._playwright.stop()

        self._cleanups.append(_close_own_browser)

        if self.options.prepare_browser:
            debug.debug("execute 'prepare_browser' interceptor provided in options")
            await self.options.prepare_browser(browser)

        debug.debug("create a new browser page")
        return await browser.new_page()

    async def _launch_camoufox_browser(self, headless: bool):
        """Camoufox (https://camoufox.com/) is a hardened Firefox build with
        built-in fingerprint spoofing — needed for scrapers facing bot
        detection tiers (Cloudflare Bot Management) that vanilla Chromium
        automation can't get past. Requires the optional `camoufox` package
        (see requirements-camoufox.txt) and its own Firefox binary, fetched
        once via `python -m camoufox fetch`.
        """
        try:
            from camoufox.async_api import AsyncNewBrowser
        except ImportError as e:
            raise Exception(
                "browser_engine='camoufox' requires the optional 'camoufox' package. "
                "Install it with `pip install -r requirements-camoufox.txt`, then run "
                "`python -m camoufox fetch` once to download its Firefox binary."
            ) from e

        return await AsyncNewBrowser(self._playwright, headless=headless, humanize=True)

    async def navigate_to(self, url: str, wait_until: str = "load", retries: Optional[int] = None) -> None:
        if retries is None:
            retries = self.options.navigation_retry_count or 0

        response = await self.page.goto(url, wait_until=wait_until)
        if response is None:
            # response is None when navigating to the same URL but only the hash changes.
            return

        if not response.ok:
            status = response.status
            if retries > 0:
                debug.debug("Failed to navigate to url %s, status code: %s, retrying %s more times", url, status, retries)
                await self.navigate_to(url, wait_until, retries - 1)
            else:
                raise Exception(f"Failed to navigate to url {url}, status code: {status}")

    def get_login_options(self, credentials: TCredentials) -> LoginOptions:
        raise NotImplementedError(f"get_login_options() is not implemented in {self.options.company_id}")

    async def fill_inputs(self, page_or_frame: "Page | Frame", fields: list[dict[str, str]]) -> None:
        from ..helpers.elements_interactions import fill_input

        for field in fields:
            await fill_input(page_or_frame, field["selector"], field["value"])

    async def _handle_otp_step(self, otp_step: "OtpStep", login_frame_or_page: "Page | Frame") -> None:
        debug.debug("checking whether an OTP step is required")
        try:
            await wait_until_element_found(login_frame_or_page, otp_step.detect_selector, timeout=otp_step.detect_timeout)
        except Exception:
            debug.debug("OTP indicator never appeared within %ss — assuming not required this time", otp_step.detect_timeout)
            return

        debug.debug("OTP required — requesting code from otp_provider")
        code = await self.request_otp_code(otp_step.context)

        from ..helpers.elements_interactions import fill_input

        if otp_step.input_selectors:
            if len(code) != len(otp_step.input_selectors):
                debug.debug(
                    "OTP code length (%d) doesn't match the number of input boxes (%d) — filling what overlaps",
                    len(code),
                    len(otp_step.input_selectors),
                )
            for selector, digit in zip(otp_step.input_selectors, code):
                await fill_input(login_frame_or_page, selector, digit)
        else:
            await fill_input(login_frame_or_page, otp_step.input_selector, code)

        debug.debug("submitting OTP code")
        if isinstance(otp_step.submit_selector, str):
            from ..helpers.elements_interactions import click_button

            await click_button(login_frame_or_page, otp_step.submit_selector)
        else:
            await otp_step.submit_selector()

    async def login(self, credentials: TCredentials) -> ScraperScrapingResult | ScraperLoginResult:
        if not credentials or self.page is None:
            return _create_general_error()

        debug.debug("execute login process")
        login_options = self.get_login_options(credentials)

        if login_options.user_agent:
            debug.debug("set custom user agent provided in options")
            try:
                cdp = await self.page.context.new_cdp_session(self.page)
                await cdp.send("Network.setUserAgentOverride", {"userAgent": login_options.user_agent})
            except Exception as e:
                debug.debug("could not override user agent via CDP: %s", e)

        debug.debug("navigate to login url")
        await self.navigate_to(login_options.login_url, login_options.wait_until)

        if login_options.check_readiness:
            debug.debug("execute 'check_readiness' interceptor provided in login options")
            await login_options.check_readiness()
        elif isinstance(login_options.submit_button_selector, str):
            debug.debug("wait until submit button is available")
            await wait_until_element_found(self.page, login_options.submit_button_selector)

        login_frame_or_page: "Page | Frame" = self.page
        if login_options.pre_action:
            debug.debug("execute 'pre_action' interceptor provided in login options")
            login_frame_or_page = (await login_options.pre_action()) or self.page

        debug.debug("fill login components input with relevant values")
        await self.fill_inputs(login_frame_or_page, login_options.fields)

        debug.debug("click on login submit button")
        if isinstance(login_options.submit_button_selector, str):
            from ..helpers.elements_interactions import click_button

            await click_button(login_frame_or_page, login_options.submit_button_selector)
        else:
            await login_options.submit_button_selector()

        self._emit_progress(ScraperProgressTypes.logging_in)

        if login_options.otp_step:
            await self._handle_otp_step(login_options.otp_step, login_frame_or_page)

        if login_options.post_action:
            debug.debug("execute 'post_action' interceptor provided in login options")
            await login_options.post_action()
        else:
            debug.debug("wait for page navigation")
            from ..helpers.navigation import wait_for_navigation

            await wait_for_navigation(self.page)

        debug.debug("check login result")
        current = await get_current_url_client_side(self.page)
        login_result = await _get_key_by_value(login_options.possible_results, current, self.page)
        debug.debug("handle login results %s", login_result)
        return self._handle_login_result(login_result)

    async def terminate(self, success: bool) -> None:
        debug.debug("terminating browser with success = %s", success)
        self._emit_progress(ScraperProgressTypes.terminating)

        if not success and self.options.store_failure_screenshot_path:
            debug.debug("create a snapshot before terminated in %s", self.options.store_failure_screenshot_path)
            await self.page.screenshot(path=self.options.store_failure_screenshot_path, full_page=True)

        for cleanup in reversed(self._cleanups):
            await _safe_cleanup(cleanup)
        self._cleanups = []

    def _handle_login_result(self, login_result: str) -> ScraperLoginResult:
        if login_result == LoginResults.success:
            self._emit_progress(ScraperProgressTypes.login_success)
            return ScraperLoginResult(success=True)
        if login_result in (LoginResults.invalid_password, LoginResults.unknown_error):
            self._emit_progress(ScraperProgressTypes.login_failed)
            return ScraperLoginResult(
                success=False,
                error_type=(
                    ScraperErrorTypes.invalid_password
                    if login_result == LoginResults.invalid_password
                    else ScraperErrorTypes.general
                ),
                error_message=f"Login failed with {login_result} error",
            )
        if login_result == LoginResults.change_password:
            self._emit_progress(ScraperProgressTypes.change_password)
            return ScraperLoginResult(success=False, error_type=ScraperErrorTypes.change_password)
        raise Exception(f'unexpected login result "{login_result}"')
