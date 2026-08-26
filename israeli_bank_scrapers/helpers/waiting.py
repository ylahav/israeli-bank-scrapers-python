"""Port of src/helpers/waiting.ts"""

from __future__ import annotations

import asyncio
import random
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")

SECOND = 1.0
"""In this port, durations are seconds (asyncio-native) rather than ms like the JS lib."""


class TimeoutError(Exception):
    pass


async def wait_until(
    async_test: Callable[[], Awaitable[T]],
    description: str = "",
    timeout: float = 10 * SECOND,
    interval: float = 0.1,
) -> T:
    """Poll `async_test` until it returns a truthy value, or raise TimeoutError.

    Mirrors the JS `waitUntil`: on each interval, calls async_test(); a truthy
    result resolves immediately, an exception propagates immediately, and a
    falsy result triggers another poll after `interval` until `timeout` elapses.
    """

    async def _poll() -> T:
        while True:
            value = await async_test()
            if value:
                return value
            await asyncio.sleep(interval)

    try:
        return await asyncio.wait_for(_poll(), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise TimeoutError(description) from e


async def race_timeout(seconds: float, awaitable: Awaitable[T]) -> T | None:
    try:
        return await asyncio.wait_for(awaitable, timeout=seconds)
    except asyncio.TimeoutError:
        return None


async def run_serial(actions: list[Callable[[], Awaitable[T]]]) -> list[T]:
    results: list[T] = []
    for action in actions:
        results.append(await action())
    return results


async def sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def random_delay(min_seconds: float = 0.5, max_seconds: float = 2.0) -> None:
    await asyncio.sleep(random.uniform(min_seconds, max_seconds))
