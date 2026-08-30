"""Tests for version lookup — both the plain Python API (get_version())
and the CLI's lightweight "type": "version" request.
"""

import json

import pytest


class TestGetVersion:
    def test_returns_a_string(self):
        from israeli_bank_scrapers.version import get_version

        version = get_version()
        assert isinstance(version, str)
        assert len(version) > 0

    def test_matches_pyproject_toml(self):
        """The installed package's metadata should reflect pyproject.toml's
        version field — this is the whole point of reading it dynamically
        rather than hardcoding a second copy."""
        import tomllib
        from pathlib import Path
        from israeli_bank_scrapers.version import get_version

        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)

        assert get_version() == pyproject["project"]["version"]

    def test_exposed_on_package_init(self):
        import israeli_bank_scrapers as ibs
        from israeli_bank_scrapers.version import get_version

        assert ibs.get_version is get_version
        assert ibs.__version__ == get_version()

    def test_fallback_does_not_raise_when_package_metadata_missing(self, monkeypatch):
        """Simulates running from source without an install — should return
        a clearly-marked placeholder, never raise."""
        from importlib.metadata import PackageNotFoundError
        import israeli_bank_scrapers.version as version_module

        def raise_not_found(name):
            raise PackageNotFoundError(name)

        monkeypatch.setattr(version_module, "_installed_version", raise_not_found)
        result = version_module.get_version()
        assert result == "0.0.0+unknown"


class TestCliVersionRequest:
    def test_version_request_returns_version_without_scraping(self, monkeypatch):
        import sys
        import io
        from israeli_bank_scrapers import cli as cli_module

        # If this test somehow reached the scrape path, create_scraper would
        # be called with no company_id and blow up loudly — asserting it's
        # never called at all is the real proof this is a fast path.
        monkeypatch.setattr(
            cli_module,
            "create_scraper",
            lambda options: (_ for _ in ()).throw(AssertionError("should not scrape for a version request")),
        )

        class FakeStdin:
            def readline(self):
                return json.dumps({"type": "version"}) + "\n"

        monkeypatch.setattr(sys, "stdin", FakeStdin())
        stdout_capture = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)

        cli_module.main()

        lines = [line for line in stdout_capture.getvalue().strip().split("\n") if line]
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["type"] == "version"
        assert event["schema_version"] == 2
        assert isinstance(event["version"], str)

    def test_version_request_matches_get_version(self, monkeypatch):
        import sys
        import io
        from israeli_bank_scrapers import cli as cli_module
        from israeli_bank_scrapers.version import get_version

        class FakeStdin:
            def readline(self):
                return json.dumps({"type": "version"}) + "\n"

        monkeypatch.setattr(sys, "stdin", FakeStdin())
        stdout_capture = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)

        cli_module.main()

        event = json.loads(stdout_capture.getvalue().strip())
        assert event["version"] == get_version()

    def test_normal_scrape_request_is_unaffected(self, monkeypatch):
        """Regression guard: adding the version fast-path must not change
        behavior for ordinary scrape requests."""
        import sys
        import io
        from israeli_bank_scrapers import cli as cli_module
        from israeli_bank_scrapers.definitions import ScraperProgressTypes
        from israeli_bank_scrapers.interface import ScraperScrapingResult

        class FakeScraper:
            def __init__(self, options):
                self.otp_provider = None
                self._listeners = []

            def on_progress(self, fn):
                self._listeners.append(fn)

            async def scrape(self, credentials):
                return ScraperScrapingResult(success=True, accounts=[])

        monkeypatch.setattr(cli_module, "create_scraper", lambda options: FakeScraper(options))
        monkeypatch.setattr(cli_module, "build_credentials", lambda company_id, fields: fields)

        class FakeStdin:
            def readline(self):
                return json.dumps({"company_id": "leumi", "credentials": {}}) + "\n"

        monkeypatch.setattr(sys, "stdin", FakeStdin())
        stdout_capture = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)

        cli_module.main()

        lines = [line for line in stdout_capture.getvalue().strip().split("\n") if line]
        events = [json.loads(line) for line in lines]
        assert events[-1]["type"] == "result"
        assert events[-1]["success"] is True
