from __future__ import annotations

import enum
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from water_billing.domain.models import BillLine, Customer


class ApplicationRule(enum.Enum):
    PER_ACTIVE_CUSTOMER = "aktiiviset"
    PER_ALL_CUSTOMERS = "kaikki"
    PER_CONSUMPTION = "kulutus"


class BillingError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def ceil_cent(value: Decimal) -> Decimal:
    return (value * 100).to_integral_value(rounding=ROUND_CEILING) / Decimal("100")


def distribute_bill_line(
    line: "BillLine",
    customers: List["Customer"],
    consumptions: Dict[str, Decimal],
) -> Dict[str, Decimal]:
    rule = line.application_rule

    netto = line.count * line.unit_price

    if rule == ApplicationRule.PER_ACTIVE_CUSTOMER:
        active = [c for c in customers if c.is_active()]
        if not active:
            raise BillingError("Ei aktiivisia asiakkaita laskurivin jakamiseen.")
        per_share = ceil_cent(netto / len(active))
        return {c.name: per_share for c in active}

    if rule == ApplicationRule.PER_ALL_CUSTOMERS:
        per_share = ceil_cent(netto / len(customers))
        return {c.name: per_share for c in customers}

    # PER_CONSUMPTION
    return {
        c.name: (line.unit_price * consumptions.get(c.name, Decimal("0"))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        for c in customers
        if c.is_active()
    }
