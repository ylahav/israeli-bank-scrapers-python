"""Port of src/scrapers/beinleumi.ts"""

from __future__ import annotations

from .base_beinleumi_group import BeinleumiGroupBaseScraper, BeinleumiGroupCredentials

BeinleumiCredentials = BeinleumiGroupCredentials


class BeinleumiScraper(BeinleumiGroupBaseScraper):
    BASE_URL = "https://online.fibi.co.il"
    LOGIN_URL = f"{BASE_URL}/MatafLoginService/MatafLoginServlet?bankId=FIBIPORTAL&site=Private&KODSAFA=HE"
    TRANSACTIONS_URL = f"{BASE_URL}/wps/myportal/FibiMenu/Online/OnAccountMngment/OnBalanceTrans/PrivateAccountFlow"
