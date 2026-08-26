"""Port of src/transactions.ts"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class CardType(str, Enum):
    bank_issued = "bankIssued"
    company_issued = "companyIssued"


class TransactionTypes(str, Enum):
    normal = "normal"
    installments = "installments"


class TransactionStatuses(str, Enum):
    completed = "completed"
    pending = "pending"


@dataclass
class TransactionInstallments:
    number: int
    """The current installment number."""
    total: int
    """The total number of installments."""


@dataclass
class Transaction:
    type: TransactionTypes
    date: str
    """ISO date string."""
    processed_date: str
    """ISO date string."""
    original_amount: float
    original_currency: str
    charged_amount: float
    description: str
    status: TransactionStatuses
    identifier: Optional[Any] = None
    """Sometimes called Asmachta."""
    charged_currency: Optional[str] = None
    memo: Optional[str] = None
    installments: Optional[TransactionInstallments] = None
    category: Optional[str] = None
    raw_transaction: Optional[Any] = None


@dataclass
class TransactionsAccount:
    account_number: str
    balance: Optional[float] = None
    balance_date: Optional[str] = None
    card_frame: Optional[float] = None
    card_type: Optional[CardType] = None
    currency: Optional[str] = None
    savings_account: Optional[bool] = None
    txns: list[Transaction] = field(default_factory=list)
