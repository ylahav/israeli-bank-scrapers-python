"""Version lookup for israeli_bank_scrapers.

The version lives in exactly one place — pyproject.toml's `version` field —
and is read back from the installed package's own metadata here, rather
than duplicated as a separate hardcoded string that could drift out of
sync with what actually got published.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _installed_version

_DISTRIBUTION_NAME = "israeli-bank-scrapers-python"
_FALLBACK_VERSION = "0.0.0+unknown"


def get_version() -> str:
    """Returns the installed package version (from pyproject.toml via
    package metadata). Falls back to a clearly-marked placeholder if the
    package isn't actually installed — e.g. running straight from a source
    checkout without `pip install` or `pip install -e .` — rather than
    raising, since callers (including the CLI's version request) should
    always get a string back.
    """
    try:
        return _installed_version(_DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return _FALLBACK_VERSION
