"""Port of src/helpers/elements-interactions.ts to Playwright's async API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from .debug import get_debug
from .waiting import wait_until

if TYPE_CHECKING:
    from playwright.async_api import Frame, Page

debug = get_debug("elements-interactions")


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

    # Verify the value actually stuck — some frameworks' reactive forms
    # (Angular in particular) can overwrite a programmatically-typed value on
    # their own change-detection cycle if they don't recognize it as "real"
    # input in the way they expect. Confirmed live on a real Angular
    # reactive form (type="number" ID field) — .type()'s per-keystroke
    # events got silently wiped back to empty.
    actual_value = await _get_input_value(page_or_frame, input_selector)
    if actual_value == input_value:
        return

    # Second attempt: retype at a realistic human pace. Playwright's default
    # .type() fires keystrokes essentially instantly, with uniform timing —
    # a pattern some frameworks' validation (or bot-detection heuristics)
    # can reject even though the events themselves look correct. A real,
    # actively-maintained sibling project (israeli-pension-scrapers) uses an
    # explicit ~45ms per-character delay for exactly this reason, on a
    # comparable Angular reactive-form field. Worth trying before the more
    # mechanical fallbacks below.
    debug.debug(
        "fill_input: value did not stick for selector %r via type() — expected %r, DOM shows %r. "
        "Retrying with a realistic per-keystroke delay (45ms) before falling back to atomic-set "
        "strategies — some frameworks' validation is sensitive to unnaturally fast/uniform typing.",
        input_selector,
        input_value,
        actual_value,
    )
    try:
        await page_or_frame.eval_on_selector(input_selector, "(input) => { input.value = ''; }")
        await page_or_frame.type(input_selector, input_value, delay=45)
    except Exception as e:
        debug.debug("fill_input: slow-retype attempt raised an exception for selector %r: %s", input_selector, e)

    actual_value = await _get_input_value(page_or_frame, input_selector)
    if actual_value == input_value:
        debug.debug("fill_input: slow-retype (45ms delay) succeeded for selector %r", input_selector)
        return

    debug.debug(
        "fill_input: value still did not stick for selector %r after the slow retype — expected %r, "
        "DOM shows %r. Retrying with page.fill(), which inserts the value as one atomic operation "
        "instead of per-keystroke events — this handles frameworks with mid-typing validation/reset "
        "logic (e.g. Angular reactive forms) more reliably.",
        input_selector,
        input_value,
        actual_value,
    )
    try:
        await page_or_frame.fill(input_selector, input_value)
    except Exception as e:
        debug.debug("fill_input: page.fill() fallback raised an exception for selector %r: %s", input_selector, e)

    retry_value = await _get_input_value(page_or_frame, input_selector)
    if retry_value == input_value:
        debug.debug("fill_input: page.fill() fallback succeeded for selector %r", input_selector)
        return

    debug.debug(
        "fill_input: page.fill() fallback ALSO failed for selector %r — DOM shows %r. Trying a third "
        "approach: setting the value via the native HTMLInputElement property setter (bypassing any "
        "framework-level property interception) and manually dispatching input/change/blur events — "
        "the standard workaround for React/Angular components that intercept the native value setter "
        "so even a properly-dispatched event doesn't update their internal model.",
        input_selector,
        retry_value,
    )
    try:
        await page_or_frame.eval_on_selector(
            input_selector,
            """(input, value) => {
                const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                nativeSetter.call(input, value);
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.dispatchEvent(new Event('blur', { bubbles: true }));
            }""",
            input_value,
        )
    except Exception as e:
        debug.debug("fill_input: native-setter fallback raised an exception for selector %r: %s", input_selector, e)
        return

    final_value = await _get_input_value(page_or_frame, input_selector)
    if final_value == input_value:
        debug.debug("fill_input: native-setter fallback succeeded for selector %r", input_selector)
    else:
        debug.debug(
            "fill_input: native-setter fallback ALSO failed for selector %r — DOM shows %r. All three "
            "fill strategies exhausted; this needs a scraper-specific investigation (the selector may be "
            "matching a stale/duplicate element, e.g. from an SSR-hydration mismatch).",
            input_selector,
            final_value,
        )


async def _get_input_value(page_or_frame: "Page | Frame", input_selector: str) -> Any:
    try:
        return await page_or_frame.eval_on_selector(input_selector, "(input) => input.value")
    except Exception as e:
        debug.debug("fill_input: could not read back value for selector %r: %s", input_selector, e)
        return None


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
