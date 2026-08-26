"""Port of src/helpers/storage.ts"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from playwright.async_api import Page


async def get_from_session_storage(page: "Page", key: str) -> Any | None:
    str_data = await page.evaluate("(k) => sessionStorage.getItem(k)", key)
    if not str_data:
        return None
    return json.loads(str_data)
