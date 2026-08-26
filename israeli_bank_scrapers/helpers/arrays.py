"""Port of src/helpers/arrays.ts"""

from __future__ import annotations

from typing import TypeVar

T = TypeVar("T")


def chunk(array: list[T], size: int) -> list[list[T]]:
    if size <= 0:
        raise ValueError(f"chunk size must be positive, got {size}")
    return [array[i : i + size] for i in range(0, len(array), size)]
