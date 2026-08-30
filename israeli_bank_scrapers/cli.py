"""CLI entrypoint for host processes (e.g. a Flutter desktop app) to drive a
scrape without importing this package as a Python library.

Protocol (all on stdin/stdout — never mix app logs into stdout; use stderr
or Python's `logging` for anything that isn't part of the protocol):

  Version request (ONE LINE of JSON on stdin) — a lightweight alternative to
  a scrape request, for a host process to check which build of this
  executable it's running against without needing credentials or launching
  a browser at all:
    stdin  -> {"type": "version"}
    stdout <- {"schema_version": 2, "type": "version", "version": "0.1.0"}
  The process exits immediately after this one line — no further protocol
  activity, no OTP round-trip possible for this request type.

  Scrape request (ONE LINE of JSON on stdin, newline-terminated — do not
  pretty-print this across multiple lines, and do not close stdin right
  after writing it; see the OTP round-trip below for why):
    {
      "company_id": "leumi",
      "start_date": "2026-01-01",             // ISO date, optional (defaults ~90 days back)
      "credentials": {"username": "...", "password": "..."},
      "options": {                              // all optional
        "show_browser": false,
        "future_months_to_scrape": 1,
        "combine_installments": false,
        "additional_transaction_information": false,
        "include_raw_transaction": false
      }
    }

  Response (newline-delimited JSON on stdout, one object per line):
    {"schema_version": 2, "type": "progress", "company_id": "leumi", "progress": "LOGGING_IN"}
    {"schema_version": 2, "type": "progress", "company_id": "leumi", "progress": "LOGIN_SUCCESS"}
    {"schema_version": 2, "type": "result", "success": true, "accounts": [...], "error_type": null, "error_message": null}

  One-time-code (OTP) round-trip — used by scrapers whose login texts/emails
  a code mid-flow (e.g. insurance companies). If the scraper hits this step,
  it emits a request and then BLOCKS waiting for a response line on stdin —
  the host process must keep stdin open across this exchange, not close it
  after the initial request:
    stdout <- {"schema_version": 2, "type": "otp_required", "context": {"company_id": "...", ...}}
    stdin  -> {"type": "otp_code", "code": "123456"}\n
  `context` always includes company_id and may include scraper-specific
  hints (e.g. a phone number suffix) worth showing the end user. This can
  happen zero or more times before the final "result" line, in principle —
  most scrapers that need it only need it once per run.

  On any failure before a scrape result can be produced (bad JSON, unknown
  company, missing credential fields, unexpected exception), exactly one line
  is still emitted on stdout so the host process only ever has to parse JSON
  lines from stdout:
    {"schema_version": 2, "type": "fatal_error", "message": "..."}

  The process exit code is 0 if a "result" or "fatal_error" line was emitted
  (the host inspects the JSON to know success/failure), non-zero only for a
  truly unexpected crash that prevented emitting any line at all.

Everything that is NOT part of this protocol (tracebacks, warnings, debug
logs) goes to stderr, so a host process that only reads stdout never sees
malformed lines.

SCHEMA_VERSION 2 note: version 1 read the entirety of stdin in one blocking
call and closed the door on any further input — fine for scrapers with no
mid-flow interaction, but incompatible with the OTP round-trip above. A
host built against v1 (single request line, then close stdin) still works
unchanged for every scraper that never needs an OTP step; it will simply
never see an "otp_required" line. Only a host that wants to support
OTP-requiring scrapers needs to keep stdin open and handle that message.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from datetime import date, timedelta
from typing import Any

SCHEMA_VERSION = 2


def _configure_bundled_browser_path() -> None:
    """When running as a PyInstaller-frozen executable (see build/cli.spec),
    point Playwright at the Chromium bundled next to this executable instead
    of the default `~/.cache/ms-playwright` (or equivalent) — which won't
    exist on an end user's machine and would otherwise trigger a failed
    attempt to download ~150MB on first run.

    Must run before anything imports `playwright.async_api` — this module's
    other imports are deliberately placed after this call for that reason.
    """
    if not getattr(sys, "frozen", False):
        return

    # PyInstaller >=6's onedir layout nests bundled data under `_internal/`
    # (sys._MEIPASS points there); older layouts and --onefile put data
    # directly beside the executable. Check both so this doesn't silently
    # break on a PyInstaller version bump.
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "ms-playwright"))
    candidates.append(os.path.join(os.path.dirname(sys.executable), "ms-playwright"))
    candidates.append(os.path.join(os.path.dirname(sys.executable), "_internal", "ms-playwright"))

    for bundled_dir in candidates:
        if os.path.isdir(bundled_dir):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled_dir
            return


_configure_bundled_browser_path()

from israeli_bank_scrapers.credentials import build_credentials
from israeli_bank_scrapers.factory import create_scraper
from israeli_bank_scrapers.interface import OutputDataOptions, ScraperOptions
from israeli_bank_scrapers.serialization import scrape_result_to_dict
from israeli_bank_scrapers.version import get_version

# ScraperOptions fields a request's "options" object is allowed to set.
# Deliberately a fixed allowlist rather than **kwargs — an unrecognized key
# in the request should be a clear error, not silently ignored or crash on
# an unexpected dataclass field.
_ALLOWED_OPTION_FIELDS = {
    "show_browser",
    "future_months_to_scrape",
    "combine_installments",
    "additional_transaction_information",
    "include_raw_transaction",
    "navigation_retry_count",
    "default_timeout",
    "timeout",
}


def _emit(obj: dict) -> None:
    obj = {"schema_version": SCHEMA_VERSION, **obj}
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


async def _read_stdin_line() -> str:
    """Blocking stdin reads must not block the event loop — run them in the
    default executor. Used only for the OTP round-trip; the initial request
    line is read synchronously before the loop starts (see main())."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sys.stdin.readline)


async def _otp_provider(context: dict) -> str:
    _emit({"type": "otp_required", "context": context})
    line = await _read_stdin_line()
    if not line:
        raise Exception("stdin closed while waiting for the OTP code — host must keep stdin open after the request")
    try:
        response = json.loads(line)
    except json.JSONDecodeError as e:
        raise Exception(f"invalid JSON in OTP response: {e}") from e
    if response.get("type") != "otp_code" or not response.get("code"):
        raise Exception(f"expected {{'type': 'otp_code', 'code': ...}}, got: {line.strip()!r}")
    return str(response["code"])


def _parse_options(request: dict) -> ScraperOptions:
    company_id = request["company_id"]

    start_date_str = request.get("start_date")
    if start_date_str:
        start_date = date.fromisoformat(start_date_str)
    else:
        start_date = date.today() - timedelta(days=90)

    raw_options: dict[str, Any] = request.get("options") or {}
    unknown = set(raw_options) - _ALLOWED_OPTION_FIELDS
    if unknown:
        raise ValueError(f"Unknown option field(s): {', '.join(sorted(unknown))}")

    output_data = OutputDataOptions()
    return ScraperOptions(company_id=company_id, start_date=start_date, output_data=output_data, **raw_options)


async def _run(request: dict) -> None:
    company_id = request["company_id"]
    options = _parse_options(request)
    credentials = build_credentials(company_id, request.get("credentials") or {})

    scraper = create_scraper(options)
    scraper.otp_provider = _otp_provider
    scraper.on_progress(
        lambda cid, progress: _emit({"type": "progress", "company_id": cid, "progress": progress.value})
    )

    result = await scraper.scrape(credentials)
    _emit({"type": "result", **scrape_result_to_dict(result)})


def main() -> None:
    # Read exactly the first line synchronously, before the event loop
    # starts — the request must be a single line of JSON (see module
    # docstring). Any further stdin reads (the OTP round-trip) happen from
    # inside the running loop via _read_stdin_line()'s executor call.
    first_line = sys.stdin.readline()

    try:
        request = json.loads(first_line)
    except json.JSONDecodeError as e:
        _emit({"type": "fatal_error", "message": f"invalid JSON request: {e}"})
        return

    if request.get("type") == "version":
        # Lightweight fast path — no company_id/credentials needed, no
        # browser launched, no event loop even started. Lets a host process
        # (e.g. the Flutter app) sanity-check which build of the bundled
        # executable it's actually running against, independent of any scrape.
        _emit({"type": "version", "version": get_version()})
        return

    try:
        asyncio.run(_run(request))
    except Exception as e:  # noqa: BLE001 — this boundary must never leak a raw traceback to stdout
        print(traceback.format_exc(), file=sys.stderr)
        _emit({"type": "fatal_error", "message": str(e)})


if __name__ == "__main__":
    main()
