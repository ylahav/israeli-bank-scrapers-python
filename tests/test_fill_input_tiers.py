"""Deterministic tests for fill_input's escalating fallback tiers, using
mocks rather than a real browser + simulated adversarial framework. Earlier
attempts at simulating "a framework that rejects fast/uniform typing" via
hand-rolled page JS (timing windows, event counts, reset flags) repeatedly
proved flaky or raced against fill_input's own internal timing — three
separate designs, three separate failure modes, none reliably
reproducible. Testing the actual API calls fill_input makes (via mocks) is
both more reliable and more precisely targeted: it verifies fill_input's
own logic, not a guess at how a real framework behaves, which the browser
smoke tests (test_browser_smoke.py) cover from a different, real-browser
angle for the parts that don't depend on adversarial timing.
"""

from unittest.mock import AsyncMock

import pytest

from israeli_bank_scrapers.helpers.elements_interactions import fill_input


def _make_page(values_after_each_attempt: list) -> AsyncMock:
    """A fake page/frame whose eval_on_selector returns a different "current
    value" each time it's called (after the initial clear), simulating each
    fill attempt either sticking or not."""
    page = AsyncMock()
    call_count = {"n": -1}  # -1 accounts for the initial clear call

    async def eval_on_selector(selector, script, *args):
        if "input.value = ''" in script:
            return None  # the clear call itself
        call_count["n"] += 1
        idx = min(call_count["n"], len(values_after_each_attempt) - 1)
        return values_after_each_attempt[idx]

    page.eval_on_selector = AsyncMock(side_effect=eval_on_selector)
    return page


class TestFillInputTierOrdering:
    @pytest.mark.asyncio
    async def test_first_attempt_uses_plain_type_no_delay(self):
        page = _make_page(["051654929"])  # sticks immediately
        await fill_input(page, "#a", "051654929")

        page.type.assert_awaited_once_with("#a", "051654929")
        page.fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_second_attempt_retypes_with_45ms_delay(self):
        # First check (after plain type()) shows a mismatch; second check
        # (after the slow retype) shows the correct value.
        page = _make_page(["", "051654929"])
        await fill_input(page, "#a", "051654929")

        assert page.type.await_count == 2
        first_call, second_call = page.type.await_args_list
        assert first_call.args == ("#a", "051654929")
        assert first_call.kwargs == {}
        assert second_call.args == ("#a", "051654929")
        assert second_call.kwargs == {"delay": 45}
        page.fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_third_attempt_falls_back_to_page_fill(self):
        # type() (no delay) fails, slow retype fails, page.fill() succeeds.
        page = _make_page(["", "", "051654929"])
        await fill_input(page, "#a", "051654929")

        assert page.type.await_count == 2
        page.fill.assert_awaited_once_with("#a", "051654929")

    @pytest.mark.asyncio
    async def test_fourth_attempt_falls_back_to_native_setter(self):
        # All three prior tiers fail; only the native-setter JS eval succeeds.
        page = _make_page(["", "", "", "051654929"])
        await fill_input(page, "#a", "051654929")

        assert page.type.await_count == 2
        page.fill.assert_awaited_once()
        # The native-setter tier is the only remaining call to eval_on_selector
        # with a script that isn't the clear call — confirm it was attempted.
        scripts = [call.args[1] for call in page.eval_on_selector.await_args_list]
        assert any("getOwnPropertyDescriptor" in s for s in scripts)

    @pytest.mark.asyncio
    async def test_stops_escalating_once_a_tier_succeeds(self):
        """If the plain type() already worked, fill_input must not go on to
        call page.fill() or the native-setter tier at all."""
        page = _make_page(["051654929"])
        await fill_input(page, "#a", "051654929")

        page.fill.assert_not_called()
        scripts = [call.args[1] for call in page.eval_on_selector.await_args_list]
        assert not any("getOwnPropertyDescriptor" in s for s in scripts)
