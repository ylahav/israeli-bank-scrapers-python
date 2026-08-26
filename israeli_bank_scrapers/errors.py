"""Port of src/scrapers/errors.ts"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal


class ScraperErrorTypes(str, Enum):
    two_factor_retriever_missing = "TWO_FACTOR_RETRIEVER_MISSING"
    invalid_password = "INVALID_PASSWORD"
    change_password = "CHANGE_PASSWORD"
    timeout = "TIMEOUT"
    account_blocked = "ACCOUNT_BLOCKED"
    generic = "GENERIC"
    general = "GENERAL_ERROR"


@dataclass
class ErrorResult:
    error_type: ScraperErrorTypes
    error_message: str
    success: Literal[False] = False


def create_error_result(error_type: ScraperErrorTypes, error_message: str) -> ErrorResult:
    return ErrorResult(error_type=error_type, error_message=error_message)


def create_timeout_error(error_message: str) -> ErrorResult:
    return create_error_result(ScraperErrorTypes.timeout, error_message)


def create_generic_error(error_message: str) -> ErrorResult:
    return create_error_result(ScraperErrorTypes.generic, error_message)
