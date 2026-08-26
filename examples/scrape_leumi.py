"""Example: scrape Bank Leumi transactions.

Usage:
    pip install -r requirements.txt
    playwright install chromium
    LEUMI_USERNAME=... LEUMI_PASSWORD=... python examples/scrape_leumi.py
"""

import asyncio
import logging
import os
from datetime import date, timedelta

from israeli_bank_scrapers.definitions import CompanyTypes
from israeli_bank_scrapers.factory import create_scraper
from israeli_bank_scrapers.interface import ScraperOptions
from israeli_bank_scrapers.scrapers.leumi import LeumiCredentials


async def main() -> None:
    logging.basicConfig(level=logging.INFO)  # switch to DEBUG for verbose scraper logs

    options = ScraperOptions(
        company_id=CompanyTypes.leumi.value,
        start_date=date.today() - timedelta(days=90),
        show_browser=False,  # set True while developing/debugging a new scraper
    )
    scraper = create_scraper(options)

    scraper.on_progress(lambda company_id, progress: print(f"[{company_id}] {progress.value}"))

    credentials = LeumiCredentials(
        username=os.environ["LEUMI_USERNAME"],
        password=os.environ["LEUMI_PASSWORD"],
    )

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
