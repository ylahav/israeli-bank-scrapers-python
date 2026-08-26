"""Port of src/scrapers/pagi.ts"""

from __future__ import annotations

from .base_beinleumi_group import BeinleumiGroupBaseScraper, BeinleumiGroupCredentials

PagiCredentials = BeinleumiGroupCredentials


class PagiScraper(BeinleumiGroupBaseScraper):
    BASE_URL = "https://online.pagi.co.il/"
    LOGIN_URL = f"{BASE_URL}/MatafLoginService/MatafLoginServlet?bankId=PAGIPORTAL&site=Private&KODSAFA=HE"
    TRANSACTIONS_URL = f"{BASE_URL}/wps/myportal/FibiMenu/Online/OnAccountMngment/OnBalanceTrans/PrivateAccountFlow"
