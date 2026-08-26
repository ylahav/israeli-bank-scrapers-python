"""Port of src/scrapers/amex.ts"""

from __future__ import annotations

from ..interface import ScraperOptions
from .base_isracard_amex import IsracardAmexBaseScraper, IsracardAmexCredentials

BASE_URL = "https://he.americanexpress.co.il"
COMPANY_CODE = "77"

AmexCredentials = IsracardAmexCredentials


class AmexScraper(IsracardAmexBaseScraper):
    def __init__(self, options: ScraperOptions):
        super().__init__(options, BASE_URL, COMPANY_CODE)
