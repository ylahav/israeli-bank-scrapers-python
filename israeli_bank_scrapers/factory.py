"""Port of src/scrapers/factory.ts

All banks/card companies from the upstream repo are wired up here.
"""

from __future__ import annotations

from .definitions import CompanyTypes
from .interface import ScraperOptions
from .scrapers.amex import AmexScraper
from .scrapers.base_scraper import BaseScraper
from .scrapers.behatsdaa import BehatsdaaScraper
from .scrapers.beinleumi import BeinleumiScraper
from .scrapers.beyahad_bishvilha import BeyahadBishvilhaScraper
from .scrapers.discount import DiscountScraper
from .scrapers.hapoalim import HapoalimScraper
from .scrapers.isracard import IsracardScraper
from .scrapers.leumi import LeumiScraper
from .scrapers.massad import MassadScraper
from .scrapers.max import MaxScraper
from .scrapers.mercantile import MercantileScraper
from .scrapers.mizrahi import MizrahiScraper
from .scrapers.one_zero import OneZeroScraper
from .scrapers.otsar_hahayal import OtsarHahayalScraper
from .scrapers.pagi import PagiScraper
from .scrapers.union_bank import UnionBankScraper
from .scrapers.visa_cal import VisaCalScraper
from .scrapers.yahav import YahavScraper

_SCRAPER_CLASSES = {
    CompanyTypes.leumi.value: LeumiScraper,
    CompanyTypes.hapoalim.value: HapoalimScraper,
    CompanyTypes.discount.value: DiscountScraper,
    CompanyTypes.mercantile.value: MercantileScraper,
    CompanyTypes.isracard.value: IsracardScraper,
    CompanyTypes.amex.value: AmexScraper,
    CompanyTypes.max.value: MaxScraper,
    CompanyTypes.visa_cal.value: VisaCalScraper,
    CompanyTypes.mizrahi.value: MizrahiScraper,
    CompanyTypes.union.value: UnionBankScraper,
    CompanyTypes.beinleumi.value: BeinleumiScraper,
    CompanyTypes.massad.value: MassadScraper,
    CompanyTypes.yahav.value: YahavScraper,
    CompanyTypes.one_zero.value: OneZeroScraper,
    CompanyTypes.otsar_hahayal.value: OtsarHahayalScraper,
    CompanyTypes.pagi.value: PagiScraper,
    CompanyTypes.behatsdaa.value: BehatsdaaScraper,
    CompanyTypes.beyahad_bishvilha.value: BeyahadBishvilhaScraper,
}


def create_scraper(options: ScraperOptions) -> BaseScraper:
    company_id = options.company_id.value if isinstance(options.company_id, CompanyTypes) else options.company_id
    scraper_class = _SCRAPER_CLASSES.get(company_id)
    if scraper_class is None:
        raise NotImplementedError(
            f"No Python scraper is ported yet for company_id={company_id!r}. "
            "See factory.py's module docstring for how to port one from the original "
            "TypeScript source."
        )
    return scraper_class(options)
