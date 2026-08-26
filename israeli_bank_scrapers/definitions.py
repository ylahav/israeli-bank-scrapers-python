"""Port of src/definitions.ts

NOTICE: avoid changing the string values below — they mirror the JS library's
public API/company ids, so data exported from either implementation stays
compatible.
"""

from enum import Enum


PASSWORD_FIELD = "password"


class CompanyTypes(str, Enum):
    hapoalim = "hapoalim"
    beinleumi = "beinleumi"
    union = "union"
    amex = "amex"
    isracard = "isracard"
    visa_cal = "visaCal"
    max = "max"
    otsar_hahayal = "otsarHahayal"
    discount = "discount"
    mercantile = "mercantile"
    mizrahi = "mizrahi"
    leumi = "leumi"
    massad = "massad"
    yahav = "yahav"
    behatsdaa = "behatsdaa"
    beyahad_bishvilha = "beyahadBishvilha"
    one_zero = "oneZero"
    pagi = "pagi"


# Metadata about each supported company: display name + the credential fields
# its login form expects. Only `leumi` has a working scraper in this port so
# far (see scrapers/leumi.py) — the rest are listed for parity with the JS
# library and as a map of what still needs porting.
SCRAPERS = {
    CompanyTypes.hapoalim: {"name": "Bank Hapoalim", "loginFields": ["userCode", PASSWORD_FIELD]},
    CompanyTypes.leumi: {"name": "Bank Leumi", "loginFields": ["username", PASSWORD_FIELD]},
    CompanyTypes.mizrahi: {"name": "Mizrahi Bank", "loginFields": ["username", PASSWORD_FIELD]},
    CompanyTypes.discount: {"name": "Discount Bank", "loginFields": ["id", PASSWORD_FIELD, "num"]},
    CompanyTypes.mercantile: {"name": "Mercantile Bank", "loginFields": ["id", PASSWORD_FIELD, "num"]},
    CompanyTypes.otsar_hahayal: {"name": "Bank Otsar Hahayal", "loginFields": ["username", PASSWORD_FIELD]},
    CompanyTypes.max: {"name": "Max", "loginFields": ["username", PASSWORD_FIELD]},
    CompanyTypes.visa_cal: {"name": "Visa Cal", "loginFields": ["username", PASSWORD_FIELD]},
    CompanyTypes.isracard: {"name": "Isracard", "loginFields": ["id", "card6Digits", PASSWORD_FIELD]},
    CompanyTypes.amex: {"name": "Amex", "loginFields": ["id", "card6Digits", PASSWORD_FIELD]},
    CompanyTypes.union: {"name": "Union", "loginFields": ["username", PASSWORD_FIELD]},
    CompanyTypes.beinleumi: {"name": "Beinleumi", "loginFields": ["username", PASSWORD_FIELD]},
    CompanyTypes.massad: {"name": "Massad", "loginFields": ["username", PASSWORD_FIELD]},
    CompanyTypes.yahav: {"name": "Bank Yahav", "loginFields": ["username", "nationalID", PASSWORD_FIELD]},
    CompanyTypes.beyahad_bishvilha: {"name": "Beyahad Bishvilha", "loginFields": ["id", PASSWORD_FIELD]},
    CompanyTypes.one_zero: {
        "name": "One Zero",
        "loginFields": ["email", PASSWORD_FIELD, "otpCodeRetriever", "phoneNumber", "otpLongTermToken"],
    },
    CompanyTypes.behatsdaa: {"name": "Behatsdaa", "loginFields": ["id", PASSWORD_FIELD]},
    CompanyTypes.pagi: {"name": "Pagi", "loginFields": ["username", PASSWORD_FIELD]},
}


class ScraperProgressTypes(str, Enum):
    initializing = "INITIALIZING"
    start_scraping = "START_SCRAPING"
    logging_in = "LOGGING_IN"
    login_success = "LOGIN_SUCCESS"
    login_failed = "LOGIN_FAILED"
    change_password = "CHANGE_PASSWORD"
    end_scraping = "END_SCRAPING"
    terminating = "TERMINATING"
