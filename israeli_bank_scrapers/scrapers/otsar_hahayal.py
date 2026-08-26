"""Port of src/scrapers/otsar-hahayal.ts"""

from __future__ import annotations

from .base_beinleumi_group import BeinleumiGroupBaseScraper, BeinleumiGroupCredentials

OtsarHahayalCredentials = BeinleumiGroupCredentials


class OtsarHahayalScraper(BeinleumiGroupBaseScraper):
    BASE_URL = "https://online.bankotsar.co.il"
    LOGIN_URL = f"{BASE_URL}/MatafLoginService/MatafLoginServlet?bankId=OTSARPRTAL&site=Private&KODSAFA=HE"
    TRANSACTIONS_URL = f"{BASE_URL}/wps/myportal/FibiMenu/Online/OnAccountMngment/OnBalanceTrans/PrivateAccountFlow"
