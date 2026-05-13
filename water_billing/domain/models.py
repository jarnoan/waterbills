from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class Customer:
    name: str
    address: str
    email: str
    phone: str
    meter_id: str
    billing_preference: str
    joined_date: date
    left_date: Optional[date]
    property_id: str
    number_of_persons: int

    def is_active(self) -> bool:
        return bool(self.meter_id.strip())


@dataclass(frozen=True)
class BillingCycle:
    start_date: date
    end_date: date
    due_date: date


@dataclass(frozen=True)
class ContactInfo:
    cooperative_name: str
    iban: str
    y_tunnus: str
    contact_person: str
    phone: str
    email: str
    main_meter_id: str


@dataclass(frozen=True)
class GeneralInfo:
    billing_cycle: BillingCycle
    contact_info: ContactInfo


@dataclass(frozen=True)
class MeterReading:
    customer_name: str
    reading_date: date
    reading: int


@dataclass(frozen=True)
class BillLine:
    title: str
    amount: Decimal
    vat_percent: Decimal
    application_rule: "ApplicationRule"


@dataclass(frozen=True)
class CustomerConsumption:
    customer_name: str
    meter_id: str
    prev_reading: int
    prev_reading_date: date
    new_reading: int
    new_reading_date: date
    consumption: int
    is_estimated: bool


@dataclass(frozen=True)
class Bill:
    bill_number: int
    customer_name: str
    meter_id: str
    prev_reading: int
    prev_reading_date: date
    new_reading: int
    new_reading_date: date
    consumption: int
    is_estimated: bool
    basic_fee_share: Decimal
    water_cost: Decimal
    shared_expense_share: Decimal
    total_due: Decimal
    reference_number: str


@dataclass(frozen=True)
class OwnershipTransfer:
    meter_id: str
    prev_owner_name: str
    new_owner_name: str
    transfer_date: date
    transfer_reading: int
    new_owner_end_reading: Optional[int]


@dataclass(frozen=True)
class BillingSummary:
    bills: List[Bill]
    main_meter_consumption: Optional[int]
    customer_consumption_total: int
    water_loss_m3: Optional[int]
    water_loss_percent: Optional[Decimal]
    billing_cycle: BillingCycle
    contact_info: ContactInfo
