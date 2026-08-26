"""Layer 1 (cont.): factory + definitions sanity checks."""

from datetime import date

import pytest

from israeli_bank_scrapers.definitions import CompanyTypes, SCRAPERS
from israeli_bank_scrapers.factory import create_scraper
from israeli_bank_scrapers.interface import ScraperOptions
from israeli_bank_scrapers.scrapers.leumi import LeumiScraper


class TestDefinitions:
    def test_every_company_type_has_scraper_metadata(self):
        for company in CompanyTypes:
            assert company in SCRAPERS
            assert "name" in SCRAPERS[company]
            assert "loginFields" in SCRAPERS[company]


class TestFactory:
    def test_creates_leumi_scraper(self):
        options = ScraperOptions(company_id=CompanyTypes.leumi.value, start_date=date.today())
        scraper = create_scraper(options)
        assert isinstance(scraper, LeumiScraper)

    def test_creates_every_company_type(self):
        """Full parity check: every CompanyTypes member has a working scraper."""
        from israeli_bank_scrapers.scrapers.amex import AmexScraper
        from israeli_bank_scrapers.scrapers.behatsdaa import BehatsdaaScraper
        from israeli_bank_scrapers.scrapers.beinleumi import BeinleumiScraper
        from israeli_bank_scrapers.scrapers.beyahad_bishvilha import BeyahadBishvilhaScraper
        from israeli_bank_scrapers.scrapers.discount import DiscountScraper
        from israeli_bank_scrapers.scrapers.hapoalim import HapoalimScraper
        from israeli_bank_scrapers.scrapers.isracard import IsracardScraper
        from israeli_bank_scrapers.scrapers.massad import MassadScraper
        from israeli_bank_scrapers.scrapers.max import MaxScraper
        from israeli_bank_scrapers.scrapers.mercantile import MercantileScraper
        from israeli_bank_scrapers.scrapers.mizrahi import MizrahiScraper
        from israeli_bank_scrapers.scrapers.one_zero import OneZeroScraper
        from israeli_bank_scrapers.scrapers.otsar_hahayal import OtsarHahayalScraper
        from israeli_bank_scrapers.scrapers.pagi import PagiScraper
        from israeli_bank_scrapers.scrapers.union_bank import UnionBankScraper
        from israeli_bank_scrapers.scrapers.visa_cal import VisaCalScraper
        from israeli_bank_scrapers.scrapers.yahav import YahavScraper

        expected = {
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
        # every CompanyTypes member should be covered — this fails loudly if a
        # future enum addition is forgotten in the factory or this test
        assert set(expected.keys()) == {c.value for c in CompanyTypes}

        for company_id, expected_class in expected.items():
            options = ScraperOptions(company_id=company_id, start_date=date.today())
            assert isinstance(create_scraper(options), expected_class)

    def test_raises_for_unknown_company(self):
        options = ScraperOptions(company_id="not_a_real_bank", start_date=date.today())
        with pytest.raises(NotImplementedError, match="not_a_real_bank"):
            create_scraper(options)


class TestBrowserEngineSelection:
    def test_isracard_defaults_to_camoufox(self):
        options = ScraperOptions(company_id=CompanyTypes.isracard.value, start_date=date.today())
        scraper = create_scraper(options)
        assert scraper.get_browser_engine() == "camoufox"

    def test_amex_defaults_to_camoufox(self):
        options = ScraperOptions(company_id=CompanyTypes.amex.value, start_date=date.today())
        scraper = create_scraper(options)
        assert scraper.get_browser_engine() == "camoufox"

    def test_leumi_defaults_to_chromium(self):
        options = ScraperOptions(company_id=CompanyTypes.leumi.value, start_date=date.today())
        scraper = create_scraper(options)
        assert scraper.get_browser_engine() == "chromium"

    def test_explicit_engine_overrides_default(self):
        options = ScraperOptions(
            company_id=CompanyTypes.isracard.value, start_date=date.today(), browser_engine="chromium"
        )
        scraper = create_scraper(options)
        assert scraper.get_browser_engine() == "chromium"
