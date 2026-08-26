"""Port of src/scrapers/mercantile.ts — same as Discount, different login URL."""

from __future__ import annotations

from .base_scraper_with_browser import LoginOptions
from .discount import DiscountCredentials, DiscountScraper

MercantileCredentials = DiscountCredentials


class MercantileScraper(DiscountScraper):
    LOGIN_URL = "https://start.telebank.co.il/login/?bank=m"

    def get_login_options(self, credentials: DiscountCredentials) -> LoginOptions:
        options = super().get_login_options(credentials)
        options.login_url = self.LOGIN_URL
        return options
