"""Port of src/helpers/browser.ts

Puppeteer -> Playwright note: `page.setUserAgent()` has no direct Playwright
equivalent (see base_scraper_with_browser.py's module docstring); this uses
the same CDP-session workaround.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import Page


async def mask_headless_user_agent(page: "Page") -> None:
    user_agent = await page.evaluate("() => navigator.userAgent")
    masked = user_agent.replace("HeadlessChrome/", "Chrome/")
    try:
        cdp = await page.context.new_cdp_session(page)
        await cdp.send("Network.setUserAgentOverride", {"userAgent": masked})
    except Exception:
        pass  # best-effort, same spirit as the rest of this port's CDP workarounds


# Priorities for request interception. Playwright's page.route() doesn't have
# a numeric priority system like Puppeteer's setRequestInterception did — the
# first matching route handler wins, evaluated in registration order — so
# these constants are kept only for parity/documentation, not enforced.
interception_priorities = {"abort": 1000, "continue": 10}
