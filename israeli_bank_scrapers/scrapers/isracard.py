"""Port of src/scrapers/isracard.ts"""

from __future__ import annotations

from ..interface import ScraperOptions
from .base_isracard_amex import IsracardAmexBaseScraper, IsracardAmexCredentials

BASE_URL = "https://digital.isracard.co.il"
COMPANY_CODE = "11"

IsracardCredentials = IsracardAmexCredentials


class IsracardScraper(IsracardAmexBaseScraper):
    def __init__(self, options: ScraperOptions):
        super().__init__(options, BASE_URL, COMPANY_CODE)
