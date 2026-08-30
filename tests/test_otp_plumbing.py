"""Tests for the OTP (one-time code) plumbing added for scrapers whose login
needs a mid-flow code (e.g. insurance companies) — the generic hook in
BaseScraper, and the CLI's otp_required/otp_code NDJSON round-trip.
No real insurance scraper exists yet; these test the reusable plumbing with
fakes, the same pattern used for the rest of the CLI protocol tests.
"""

import json
from datetime import date

import pytest

from israeli_bank_scrapers.interface import ScraperOptions


class TestBaseScraperOtpHook:
    @pytest.mark.asyncio
    async def test_raises_clear_error_without_provider(self):
        from israeli_bank_scrapers.scrapers.base_scraper import BaseScraper

        scraper = BaseScraper(ScraperOptions(company_id="test_co", start_date=date.today()))
        with pytest.raises(Exception, match="no otp_provider was configured"):
            await scraper.request_otp_code({"hint": "x"})

    @pytest.mark.asyncio
    async def test_calls_provider_with_company_id_merged_in(self):
        from israeli_bank_scrapers.scrapers.base_scraper import BaseScraper

        scraper = BaseScraper(ScraperOptions(company_id="test_co", start_date=date.today()))

        received = {}

        async def fake_provider(context):
            received.update(context)
            return "654321"

        scraper.otp_provider = fake_provider
        code = await scraper.request_otp_code({"hint": "sent to phone"})

        assert code == "654321"
        assert received == {"company_id": "test_co", "hint": "sent to phone"}

    @pytest.mark.asyncio
    async def test_context_defaults_to_empty_dict(self):
        from israeli_bank_scrapers.scrapers.base_scraper import BaseScraper

        scraper = BaseScraper(ScraperOptions(company_id="test_co", start_date=date.today()))
        received = {}

        async def fake_provider(context):
            received.update(context)
            return "1"

        scraper.otp_provider = fake_provider
        await scraper.request_otp_code()  # no context at all
        assert received == {"company_id": "test_co"}


class TestOtpStep:
    def test_stores_all_fields(self):
        from israeli_bank_scrapers.scrapers.base_scraper_with_browser import OtpStep

        step = OtpStep(
            detect_selector="#otp-input",
            input_selector="#otp-code",
            submit_selector="#otp-submit",
            detect_timeout=20.0,
            context={"hint": "sms"},
        )
        assert step.detect_selector == "#otp-input"
        assert step.input_selector == "#otp-code"
        assert step.submit_selector == "#otp-submit"
        assert step.detect_timeout == 20.0
        assert step.context == {"hint": "sms"}

    def test_defaults(self):
        from israeli_bank_scrapers.scrapers.base_scraper_with_browser import OtpStep

        step = OtpStep(detect_selector="#a", input_selector="#b", submit_selector="#c")
        assert step.detect_timeout == 15.0
        assert step.context is None

    def test_login_options_accepts_otp_step(self):
        from israeli_bank_scrapers.scrapers.base_scraper_with_browser import LoginOptions, OtpStep, LoginResults

        step = OtpStep(detect_selector="#a", input_selector="#b", submit_selector="#c")
        options = LoginOptions(
            login_url="https://example.com",
            fields=[],
            submit_button_selector="#submit",
            possible_results={LoginResults.success: ["https://example.com/home"]},
            otp_step=step,
        )
        assert options.otp_step is step

    def test_login_options_otp_step_defaults_to_none(self):
        from israeli_bank_scrapers.scrapers.base_scraper_with_browser import LoginOptions, LoginResults

        options = LoginOptions(
            login_url="https://example.com",
            fields=[],
            submit_button_selector="#submit",
            possible_results={LoginResults.success: ["https://example.com/home"]},
        )
        assert options.otp_step is None


class FakeStdin:
    """Simulates a line-based stdin for cli.main() tests — each call to
    readline() pops the next queued line, returning '' (EOF) once exhausted."""

    def __init__(self, lines):
        self._lines = list(lines)

    def readline(self):
        return self._lines.pop(0) if self._lines else ""


class TestCliOtpRoundTrip:
    def test_full_round_trip(self, monkeypatch):
        import sys
        import io
        from israeli_bank_scrapers import cli as cli_module
        from israeli_bank_scrapers.definitions import ScraperProgressTypes
        from israeli_bank_scrapers.interface import ScraperScrapingResult
        from israeli_bank_scrapers.transactions import TransactionsAccount

        class FakeOtpScraper:
            def __init__(self, options):
                self.options = options
                self.otp_provider = None
                self._listeners = []

            def on_progress(self, fn):
                self._listeners.append(fn)

            async def scrape(self, credentials):
                for fn in self._listeners:
                    fn("phoenix", ScraperProgressTypes.logging_in)
                code = await self.otp_provider({"company_id": "phoenix", "hint": "sent to phone ending 1234"})
                assert code == "999888"
                for fn in self._listeners:
                    fn("phoenix", ScraperProgressTypes.login_success)
                return ScraperScrapingResult(
                    success=True, accounts=[TransactionsAccount(account_number="1", txns=[])]
                )

        monkeypatch.setattr(cli_module, "create_scraper", lambda options: FakeOtpScraper(options))
        monkeypatch.setattr(cli_module, "build_credentials", lambda company_id, fields: fields)

        request_line = json.dumps({"company_id": "phoenix", "credentials": {"id": "x", "password": "y"}}) + "\n"
        otp_response_line = json.dumps({"type": "otp_code", "code": "999888"}) + "\n"

        monkeypatch.setattr(sys, "stdin", FakeStdin([request_line, otp_response_line]))

        stdout_capture = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)
        cli_module.main()

        lines = [line for line in stdout_capture.getvalue().strip().split("\n") if line]
        events = [json.loads(line) for line in lines]

        assert any(e["type"] == "otp_required" for e in events)
        otp_event = next(e for e in events if e["type"] == "otp_required")
        assert otp_event["context"]["company_id"] == "phoenix"
        assert otp_event["context"]["hint"] == "sent to phone ending 1234"

        final = events[-1]
        assert final["type"] == "result"
        assert final["success"] is True

    def test_stdin_closed_during_otp_wait_raises_cleanly(self, monkeypatch):
        import sys
        import io
        from israeli_bank_scrapers import cli as cli_module

        class FakeOtpScraper:
            def __init__(self, options):
                self.options = options
                self.otp_provider = None

            def on_progress(self, fn):
                pass

            async def scrape(self, credentials):
                # stdin will return '' (EOF) with no otp_code line queued
                await self.otp_provider({})
                raise AssertionError("should not reach here")

        monkeypatch.setattr(cli_module, "create_scraper", lambda options: FakeOtpScraper(options))
        monkeypatch.setattr(cli_module, "build_credentials", lambda company_id, fields: fields)

        request_line = json.dumps({"company_id": "phoenix", "credentials": {}}) + "\n"
        monkeypatch.setattr(sys, "stdin", FakeStdin([request_line]))  # no OTP response queued

        stdout_capture = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)
        cli_module.main()

        lines = [line for line in stdout_capture.getvalue().strip().split("\n") if line]
        events = [json.loads(line) for line in lines]
        final = events[-1]
        assert final["type"] == "fatal_error"
        assert "stdin closed" in final["message"]

    def test_malformed_otp_response_raises_cleanly(self, monkeypatch):
        import sys
        import io
        from israeli_bank_scrapers import cli as cli_module

        class FakeOtpScraper:
            def __init__(self, options):
                self.options = options
                self.otp_provider = None

            def on_progress(self, fn):
                pass

            async def scrape(self, credentials):
                await self.otp_provider({})
                raise AssertionError("should not reach here")

        monkeypatch.setattr(cli_module, "create_scraper", lambda options: FakeOtpScraper(options))
        monkeypatch.setattr(cli_module, "build_credentials", lambda company_id, fields: fields)

        request_line = json.dumps({"company_id": "phoenix", "credentials": {}}) + "\n"
        bad_response_line = json.dumps({"type": "not_otp_code", "foo": "bar"}) + "\n"
        monkeypatch.setattr(sys, "stdin", FakeStdin([request_line, bad_response_line]))

        stdout_capture = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)
        cli_module.main()

        lines = [line for line in stdout_capture.getvalue().strip().split("\n") if line]
        events = [json.loads(line) for line in lines]
        final = events[-1]
        assert final["type"] == "fatal_error"
        assert "otp_code" in final["message"]

    def test_schema_version_is_2(self, monkeypatch):
        import sys
        import io
        from israeli_bank_scrapers import cli as cli_module

        monkeypatch.setattr(cli_module, "build_credentials", lambda company_id, fields: (_ for _ in ()).throw(ValueError("stop early")))

        request_line = json.dumps({"company_id": "leumi", "credentials": {}}) + "\n"
        monkeypatch.setattr(sys, "stdin", FakeStdin([request_line]))

        stdout_capture = io.StringIO()
        monkeypatch.setattr(sys, "stdout", stdout_capture)
        cli_module.main()

        lines = [line for line in stdout_capture.getvalue().strip().split("\n") if line]
        event = json.loads(lines[0])
        assert event["schema_version"] == 2
