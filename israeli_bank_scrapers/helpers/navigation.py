"""Port of src/helpers/navigation.ts

Puppeteer -> Playwright note: Puppeteer's `page.waitForNavigation()` (call it
right after triggering an action) is discouraged in Playwright in favor of
`page.expect_navigation()` as a context manager wrapped *around* the
triggering action, since events can otherwise be missed. We keep a
function-shaped `wait_for_navigation` for call-site parity with the original
library (most call sites in this codebase call it as a distinct "settle"
step after already awaiting a click), but where you're porting a new scraper
and you control both the click and the wait, prefer:

    async with page.expect_navigation():
        await page.click(selector)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .waiting import wait_until

if TYPE_CHECKING:
    from playwright.async_api import Frame, Page

WaitUntilState = Literal["load", "domcontentloaded", "networkidle"]


async def wait_for_navigation(page_or_frame: "Page | Frame", wait_until_state: WaitUntilState = "load") -> None:
    page = getattr(page_or_frame, "page", page_or_frame)  # Frame.page -> owning Page
    await page.wait_for_load_state(wait_until_state)


async def wait_for_navigation_and_dom_load(page: "Page") -> None:
    await wait_for_navigation(page, "domcontentloaded")


def get_current_url(page_or_frame: "Page | Frame") -> str:
    return page_or_frame.url


async def get_current_url_client_side(page_or_frame: "Page | Frame") -> str:
    return await page_or_frame.evaluate("() => window.location.href")


async def wait_for_redirect(
    page_or_frame: "Page | Frame",
    timeout: float = 20.0,
    client_side: bool = False,
    ignore_list: list[str] | None = None,
) -> None:
    ignore_list = ignore_list or []
    initial = await get_current_url_client_side(page_or_frame) if client_side else get_current_url(page_or_frame)

    async def check() -> bool:
        current = await get_current_url_client_side(page_or_frame) if client_side else get_current_url(page_or_frame)
        return current != initial and current not in ignore_list

    await wait_until(check, f"waiting for redirect from {initial}", timeout=timeout, interval=1.0)


async def wait_for_url(
    page_or_frame: "Page | Frame",
    url: str,
    timeout: float = 20.0,
    client_side: bool = False,
    is_regex: bool = False,
) -> None:
    import re

    pattern = re.compile(url) if is_regex else None

    async def check() -> bool:
        current = await get_current_url_client_side(page_or_frame) if client_side else get_current_url(page_or_frame)
        return bool(pattern.search(current)) if pattern else current == url

    await wait_until(check, f"waiting for url to be {url}", timeout=timeout, interval=1.0)
