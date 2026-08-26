"""
israeli_bank_scrapers (Python port)

A Python/Playwright port of the core architecture of eshaham/israeli-bank-scrapers
(https://github.com/eshaham/israeli-bank-scrapers), a Node.js/Puppeteer library that
scrapes transaction data from Israeli banks and credit-card companies.

This port currently includes:
  - The full core scraping architecture (BaseScraper / BaseScraperWithBrowser)
  - Shared helpers (waiting, navigation, element interaction, fetch-in-page, transaction utils)
  - One complete scraper (Bank Leumi) as a worked example
  - A factory for wiring up additional scrapers

See README.md in this package for scope notes and how to port additional banks.
"""

from .definitions import CompanyTypes, ScraperProgressTypes, SCRAPERS
from .errors import ScraperErrorTypes
from .factory import create_scraper

__all__ = [
    "CompanyTypes",
    "ScraperProgressTypes",
    "SCRAPERS",
    "ScraperErrorTypes",
    "create_scraper",
]
