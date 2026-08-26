"""Layer 2: real-browser smoke test, run against a local HTML fixture instead of
a live bank site. This is what actually proves the Puppeteer -> Playwright
translation of the DOM-interaction helpers behaves correctly — the riskiest
part of this port to get subtly wrong.

Requires: `playwright install chromium` (one-time).
Run: pytest tests/test_browser_smoke.py -v
"""

from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from israeli_bank_scrapers.helpers.elements_interactions import (
    click_button,
    dropdown_select,
    fill_input,
    wait_until_element_found,
    element_present_on_page,
)

FIXTURE_URL = f"file://{Path(__file__).parent / 'fixtures' / 'fake_login_page.html'}"


@pytest.fixture
async def page():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        pg = await browser.new_page()
        await pg.goto(FIXTURE_URL)
        yield pg
        await browser.close()


class TestElementInteractionsAgainstRealBrowser:
    @pytest.mark.asyncio
    async def test_wait_until_element_found(self, page):
        await wait_until_element_found(page, 'input[placeholder="שם משתמש"]', only_visible=True)
        # no exception raised = pass

    @pytest.mark.asyncio
    async def test_fill_input_sets_value(self, page):
        await fill_input(page, 'input[placeholder="שם משתמש"]', "my_username")
        value = await page.eval_on_selector('input[placeholder="שם משתמש"]', "el => el.value")
        assert value == "my_username"

    @pytest.mark.asyncio
    async def test_fill_input_clears_previous_value_first(self, page):
        await fill_input(page, 'input[placeholder="סיסמה"]', "first")
        await fill_input(page, 'input[placeholder="סיסמה"]', "second")
        value = await page.eval_on_selector('input[placeholder="סיסמה"]', "el => el.value")
        assert value == "second"  # not "firstsecond"

    @pytest.mark.asyncio
    async def test_click_button_submits_form(self, page):
        assert not await element_present_on_page(page, "#result:visible")
        await click_button(page, 'button[type="submit"]')
        await wait_until_element_found(page, "#result", only_visible=True, timeout=5)
        text = await page.eval_on_selector("#result", "el => el.textContent")
        assert text == "SUCCESS"

    @pytest.mark.asyncio
    async def test_dropdown_select(self, page):
        await dropdown_select(page, "#account-picker", "acc2")
        value = await page.eval_on_selector("#account-picker", "el => el.value")
        assert value == "acc2"

    @pytest.mark.asyncio
    async def test_full_login_style_flow(self, page):
        """End-to-end shape of what LeumiScraper.login() does internally:
        fill fields in order, click submit, wait for a post-submit indicator.
        """
        await fill_input(page, 'input[placeholder="שם משתמש"]', "demo_user")
        await fill_input(page, 'input[placeholder="סיסמה"]', "demo_pass")
        await click_button(page, 'button[type="submit"]')
        await wait_until_element_found(page, "#result", only_visible=True, timeout=5)
        assert await element_present_on_page(page, "#result")
