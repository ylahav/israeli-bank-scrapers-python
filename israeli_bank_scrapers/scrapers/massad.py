"""Port of src/scrapers/massad.ts"""

from __future__ import annotations

from .base_beinleumi_group import BeinleumiGroupBaseScraper, BeinleumiGroupCredentials

MassadCredentials = BeinleumiGroupCredentials


class MassadScraper(BeinleumiGroupBaseScraper):
    BASE_URL = "https://online.bankmassad.co.il"
    LOGIN_URL = f"{BASE_URL}/MatafLoginService/MatafLoginServlet?bankId=MASADPRTAL&site=Private&KODSAFA=HE"
    TRANSACTIONS_URL = f"{BASE_URL}/wps/myportal/FibiMenu/Online/OnAccountMngment/OnBalanceTrans/PrivateAccountFlow"
