"""
israeli_bank_scrapers (Python port)

A Python/Playwright port of eshaham/israeli-bank-scrapers
(https://github.com/eshaham/israeli-bank-scrapers), a Node.js/Puppeteer library
that scrapes transaction data from Israeli banks and credit-card companies.
See README.md for the full company list and how to port an additional company.
"""

from .definitions import CompanyTypes, ScraperProgressTypes, SCRAPERS
from .errors import ScraperErrorTypes
from .factory import create_scraper
from .version import get_version

__version__ = get_version()

__all__ = [
    "CompanyTypes",
    "ScraperProgressTypes",
    "SCRAPERS",
    "ScraperErrorTypes",
    "create_scraper",
    "get_version",
    "__version__",
]
