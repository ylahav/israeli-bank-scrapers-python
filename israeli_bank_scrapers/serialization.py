"""JSON serialization for the CLI boundary (cli.py). Kept separate from the
core dataclasses so the scraping logic itself has no serialization concerns —
this module is the only place that knows about the wire format Flutter/Dart
will parse.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

from .transactions import TransactionsAccount
from .interface import ScraperScrapingResult


def _to_jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {k: _to_jsonable(v) for k, v in dataclasses.asdict(value).items()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    return value


def account_to_dict(account: TransactionsAccount) -> dict:
    return _to_jsonable(account)


def scrape_result_to_dict(result: ScraperScrapingResult) -> dict:
    return _to_jsonable(result)
