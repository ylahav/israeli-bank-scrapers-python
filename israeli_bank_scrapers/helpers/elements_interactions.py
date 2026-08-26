"""Port of src/helpers/elements-interactions.ts to Playwright's async API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .waiting import wait_until

if TYPE_CHECKING:
    from playwright.async_api import Frame, Page


async def wait_until_element_found(
    page: "Page | Frame",
    element_selector: str,
    only_visible: bool = False,
    timeout: float | None = None,
) -> None:
    timeout_ms = timeout * 1000 if timeout is not None else None
    await page.wait_for_selector(
        element_selector,
        state="visible" if only_visible else "attached",
        timeout=timeout_ms,
    )


async def wait_until_element_disappear(page: "Page", element_selector: str, timeout: float | None = None) -> None:
    timeout_ms = timeout * 1000 if timeout is not None else None
    await page.wait_for_selector(element_selector, state="hidden", timeout=timeout_ms)


async def wait_until_iframe_found(
    page: "Page",
    frame_predicate: Callable[["Frame"], bool],
    description: str = "",
    timeout: float = 30.0,
) -> "Frame":
    found: dict[str, Any] = {}

    async def check() -> bool:
        frame = next((f for f in page.frames if frame_predicate(f)), None)
        if frame:
            found["frame"] = frame
        return frame is not None

    await wait_until(check, description, timeout=timeout, interval=1.0)
    if "frame" not in found:
        raise Exception("failed to find iframe")
    return found["frame"]


async def fill_input(page_or_frame: "Page | Frame", input_selector: str, input_value: str) -> None:
    await page_or_frame.eval_on_selector(input_selector, "(input) => { input.value = ''; }")
    await page_or_frame.type(input_selector, input_value)


async def set_value(page_or_frame: "Page | Frame", input_selector: str, input_value: str) -> None:
    await page_or_frame.eval_on_selector(
        input_selector,
        "(input, value) => { input.value = value; }",
        input_value,
    )


async def click_button(page: "Page | Frame", button_selector: str) -> None:
    await page.eval_on_selector(button_selector, "(el) => el.click()")


async def click_link(page: "Page", a_selector: str) -> None:
    await page.eval_on_selector(
        a_selector,
        "(el) => { if (el && typeof el.click !== 'undefined') { el.click(); } }",
    )


async def page_eval_all(
    page: "Page | Frame",
    selector: str,
    default_result: Any,
    expression: str,
    arg: Any = None,
) -> Any:
    """`expression` is a JS function source, e.g. "(elements) => elements.map(e => e.textContent)".

    Mirrors the original's swallow-if-no-elements-matched behavior (Puppeteer's
    older $$eval threw when nothing matched a selector; Playwright's
    eval_on_selector_all instead just calls the callback with an empty array,
    so in practice this rarely needs the fallback — kept for parity).
    """
    try:
        await page.wait_for_function("() => document.readyState === 'complete'")
        if arg is not None:
            return await page.eval_on_selector_all(selector, expression, arg)
        return await page.eval_on_selector_all(selector, expression)
    except Exception:
        return default_result


async def page_eval(
    page_or_frame: "Page | Frame",
    selector: str,
    default_result: Any,
    expression: str,
    arg: Any = None,
) -> Any:
    try:
        await page_or_frame.wait_for_function("() => document.readyState === 'complete'")
        if arg is not None:
            return await page_or_frame.eval_on_selector(selector, expression, arg)
        return await page_or_frame.eval_on_selector(selector, expression)
    except Exception:
        return default_result


async def element_present_on_page(page_or_frame: "Page | Frame", selector: str) -> bool:
    return (await page_or_frame.query_selector(selector)) is not None


async def dropdown_select(page: "Page", select_selector: str, value: str) -> None:
    await page.select_option(select_selector, value)


async def dropdown_elements(page: "Page", selector: str) -> list[dict[str, str]]:
    return await page.evaluate(
        """(optionSelector) => Array.from(document.querySelectorAll(optionSelector))
            .filter(o => o.value)
            .map(o => ({ name: o.text, value: o.value }))""",
        f"{selector} > option",
    )
