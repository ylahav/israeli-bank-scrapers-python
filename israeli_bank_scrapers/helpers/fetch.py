"""Port of src/helpers/fetch.ts

`fetch_get_within_page` / `fetch_post_within_page` run `fetch()` inside the
page's own JS context (via `page.evaluate`) so requests carry the site's
cookies/session exactly like the original — this is what leumi.py uses to
pull the savings-accounts JSON. `fetch_get` / `fetch_post` are plain
out-of-page HTTP calls (via `httpx`), included for parity with the JS API
surface; most scrapers in this codebase only need the within-page variants.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Page

JSON_CONTENT_TYPE = "application/json"


def _json_headers() -> dict[str, str]:
    return {"Accept": JSON_CONTENT_TYPE, "Content-Type": JSON_CONTENT_TYPE}


def _assert_automation_not_blocked(status: int, response_text: str | None, url: str) -> None:
    import re

    if status == 429 or (response_text and re.search(r"block automation|bot detection", response_text, re.I)):
        raise Exception(
            f"Automation detected and blocked by server. Status: {status}, URL: {url}. "
            "The site is actively blocking automated access. Consider: 1) Using show_browser=True, "
            "2) Adding longer delays, 3) Using residential proxies, 4) Running at different times of day"
        )


async def fetch_get(url: str, extra_headers: dict[str, Any] | None = None) -> Any:
    import httpx

    headers = {**_json_headers(), **(extra_headers or {})}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
    if response.status_code != 200:
        raise Exception(f"sending a request to the institute server returned with status code {response.status_code}")
    return response.json()


async def fetch_post(url: str, data: dict[str, Any], extra_headers: dict[str, Any] | None = None) -> Any:
    import httpx

    headers = {**_json_headers(), **(extra_headers or {})}
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, content=json.dumps(data))
    return response.json()


async def fetch_graphql(
    url: str,
    query: str,
    variables: dict[str, Any] | None = None,
    extra_headers: dict[str, Any] | None = None,
) -> Any:
    result = await fetch_post(
        url,
        {"operationName": None, "query": query, "variables": variables or {}},
        extra_headers,
    )
    if result.get("errors"):
        raise Exception(result["errors"][0]["message"])
    return result.get("data")


async def fetch_get_within_page(page: "Page", url: str, ignore_errors: bool = False) -> Any | None:
    result, status = await page.evaluate(
        """async (innerUrl) => {
            let response;
            try {
                response = await fetch(innerUrl, { credentials: 'include' });
                if (response.status === 204) {
                    return [null, response.status];
                }
                return [await response.text(), response.status];
            } catch (e) {
                throw new Error(`fetchGetWithinPage error: ${e.message}, url: ${innerUrl}, status: ${response && response.status}`);
            }
        }""",
        url,
    )

    if not ignore_errors:
        _assert_automation_not_blocked(status, result, url)

    if result is not None:
        try:
            return json.loads(result)
        except json.JSONDecodeError as e:
            if not ignore_errors:
                raise Exception(
                    f"fetchGetWithinPage parse error: {e}, url: {url}, result: {result}, status: {status}"
                ) from e
    return None


async def fetch_post_within_page(
    page: "Page",
    url: str,
    data: dict[str, Any],
    extra_headers: dict[str, Any] | None = None,
    ignore_errors: bool = False,
) -> Any | None:
    result_text, status = await page.evaluate(
        """async (args) => {
            const [innerUrl, innerData, innerExtraHeaders] = args;
            const response = await fetch(innerUrl, {
                method: 'POST',
                body: JSON.stringify(innerData),
                credentials: 'include',
                headers: Object.assign(
                    { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
                    innerExtraHeaders,
                ),
            });
            if (response.status === 204) {
                return [null, response.status];
            }
            return [await response.text(), response.status];
        }""",
        [url, data, extra_headers or {}],
    )

    if not ignore_errors:
        _assert_automation_not_blocked(status, result_text, url)

    try:
        if result_text is not None:
            return json.loads(result_text)
    except json.JSONDecodeError as e:
        if not ignore_errors:
            raise Exception(
                f"fetchPostWithinPage parse error: {e}, url: {url}, data: {data}, "
                f"extra_headers: {extra_headers}, result: {result_text}"
            ) from e
    return None
