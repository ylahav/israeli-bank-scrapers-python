"""Registry of company_id -> credentials dataclass, so callers that receive
credential fields as a plain dict (the CLI, eventually any other host process)
can build the right dataclass without hardcoding a big if/elif chain.
"""

from __future__ import annotations

import dataclasses
from typing import Type

from .scrapers.amex import AmexCredentials
from .scrapers.behatsdaa import BehatsdaaCredentials
from .scrapers.beinleumi import BeinleumiCredentials
from .scrapers.beyahad_bishvilha import BeyahadBishvilhaCredentials
from .scrapers.discount import DiscountCredentials
from .scrapers.hapoalim import HapoalimCredentials
from .scrapers.isracard import IsracardCredentials
from .scrapers.leumi import LeumiCredentials
from .scrapers.massad import MassadCredentials
from .scrapers.max import MaxCredentials
from .scrapers.mercantile import MercantileCredentials
from .scrapers.mizrahi import MizrahiCredentials
from .scrapers.one_zero import OneZeroCredentials
from .scrapers.otsar_hahayal import OtsarHahayalCredentials
from .scrapers.pagi import PagiCredentials
from .scrapers.union_bank import UnionBankCredentials
from .scrapers.visa_cal import VisaCalCredentials
from .scrapers.yahav import YahavCredentials

CREDENTIALS_CLASSES: dict[str, Type] = {
    "leumi": LeumiCredentials,
    "hapoalim": HapoalimCredentials,
    "discount": DiscountCredentials,
    "mercantile": MercantileCredentials,
    "isracard": IsracardCredentials,
    "amex": AmexCredentials,
    "max": MaxCredentials,
    "visaCal": VisaCalCredentials,
    "mizrahi": MizrahiCredentials,
    "union": UnionBankCredentials,
    "beinleumi": BeinleumiCredentials,
    "massad": MassadCredentials,
    "yahav": YahavCredentials,
    "oneZero": OneZeroCredentials,
    "otsarHahayal": OtsarHahayalCredentials,
    "pagi": PagiCredentials,
    "behatsdaa": BehatsdaaCredentials,
    "beyahadBishvilha": BeyahadBishvilhaCredentials,
}


def credential_fields(company_id: str) -> list[str]:
    cls = CREDENTIALS_CLASSES[company_id]
    return [f.name for f in dataclasses.fields(cls)]


def _required_credential_fields(company_id: str) -> list[str]:
    """Fields with no dataclass default are required; fields with a default
    (e.g. OneZeroCredentials' OTP-callback fields, which can't travel over a
    plain JSON/string protocol anyway) are optional."""
    cls = CREDENTIALS_CLASSES[company_id]
    return [
        f.name
        for f in dataclasses.fields(cls)
        if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING  # type: ignore[misc]
    ]


def build_credentials(company_id: str, fields: dict[str, str]):
    if company_id not in CREDENTIALS_CLASSES:
        raise ValueError(f"Unknown company_id: {company_id!r}. Known: {', '.join(CREDENTIALS_CLASSES)}")

    cls = CREDENTIALS_CLASSES[company_id]
    all_fields = credential_fields(company_id)
    required = _required_credential_fields(company_id)
    missing = [f for f in required if f not in fields or fields[f] in (None, "")]
    if missing:
        raise ValueError(f"Missing required credential field(s) for {company_id}: {', '.join(missing)}")

    provided = {f: fields[f] for f in all_fields if f in fields and fields[f] not in (None, "")}
    return cls(**provided)
