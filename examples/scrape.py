"""Generic example: scrape any ported bank/card company by name.

Usage (PowerShell):
    $env:IBS_COMPANY = "hapoalim"          # any company_id from credentials.py's
                                            # CREDENTIALS_CLASSES registry — leumi,
                                            # hapoalim, discount, mercantile, isracard,
                                            # amex, max, visaCal, mizrahi, union,
                                            # beinleumi, massad, yahav, oneZero,
                                            # otsarHahayal, pagi, behatsdaa,
                                            # beyahadBishvilha
    $env:IBS_START_DATE_DAYS_AGO = "90"    # optional, default 90
    $env:IBS_SHOW_BROWSER = "1"            # optional, default off — watch it run instead of headless
    $env:IBS_LOG_LEVEL = "DEBUG"           # optional, default INFO — verbose step-by-step scraper logs

    # credential env vars are the company's dataclass field names, upper-cased
    # and prefixed with the company id — e.g. for hapoalim (fields: userCode,
    # password):
    $env:HAPOALIM_USERCODE = "..."
    $env:HAPOALIM_PASSWORD = "..."

    python -m examples.scrape

Usage (bash):
    IBS_COMPANY=leumi LEUMI_USERNAME=... LEUMI_PASSWORD=... python -m examples.scrape

Credential env var names for every company: run this once to print them all —
    python -c "from israeli_bank_scrapers.credentials import CREDENTIALS_CLASSES, credential_fields; \
        [print(c, [f'{c.upper()}_{f.upper()}' for f in credential_fields(c)]) for c in CREDENTIALS_CLASSES]"
"""

import asyncio
import logging
import os
from datetime import date, timedelta

from israeli_bank_scrapers.credentials import CREDENTIALS_CLASSES, build_credentials, credential_fields
from israeli_bank_scrapers.factory import create_scraper
from israeli_bank_scrapers.interface import ScraperOptions


def _build_credentials_from_env(company_id: str):
    env_prefix = company_id.upper()
    fields = {}
    missing = []
    for field_name in credential_fields(company_id):
        env_var = f"{env_prefix}_{field_name.upper()}"
        value = os.environ.get(env_var)
        if value is not None:
            fields[field_name] = value
        else:
            missing.append(env_var)

    try:
        return build_credentials(company_id, fields)
    except ValueError as e:
        raise SystemExit(f"{e} (checked env vars: {', '.join(missing) or 'none missing'})")


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


async def _console_otp_provider(context: dict) -> str:
    """Prompts for a one-time code on the console — for scrapers whose login
    texts/emails a code mid-flow. Harmless to wire up unconditionally:
    scrapers that never need it never call this."""
    hint = context.get("hint")
    prompt = f"\n[{context.get('company_id')}] One-time code required"
    if hint:
        prompt += f" ({hint})"
    prompt += ": "

    loop = asyncio.get_event_loop()
    # input() is blocking — run it off the event loop so the scraper's other
    # async work (browser automation) isn't frozen while waiting for you to type.
    return await loop.run_in_executor(None, input, prompt)


async def main() -> None:
    log_level = os.environ.get("IBS_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.INFO))

    company_id = os.environ.get("IBS_COMPANY", "leumi")
    if company_id not in CREDENTIALS_CLASSES:
        raise SystemExit(f"Unknown IBS_COMPANY={company_id!r}. Known: {', '.join(CREDENTIALS_CLASSES)}")

    days_ago = int(os.environ.get("IBS_START_DATE_DAYS_AGO", "90"))
    show_browser = _env_bool("IBS_SHOW_BROWSER", default=False)

    options = ScraperOptions(
        company_id=company_id,
        start_date=date.today() - timedelta(days=days_ago),
        show_browser=show_browser,  # $env:IBS_SHOW_BROWSER = "1" to watch it run
        store_failure_screenshot_path="failure_screenshot.png",  # saved next to this script on any failure
    )
    scraper = create_scraper(options)
    scraper.otp_provider = _console_otp_provider
    scraper.on_progress(lambda cid, progress: print(f"[{cid}] {progress.value}"))

    credentials = _build_credentials_from_env(company_id)
    result = await scraper.scrape(credentials)

    if not result.success:
        print(f"Scrape failed: {result.error_type} - {result.error_message}")
        return

    for account in result.accounts or []:
        print(f"\nAccount {account.account_number} — balance: {account.balance}")
        for txn in account.txns:
            print(f"  {txn.date[:10]}  {txn.charged_amount:>10.2f}  {txn.description}")


if __name__ == "__main__":
    asyncio.run(main())
