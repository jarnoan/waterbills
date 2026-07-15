from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import List, Optional


@dataclass(frozen=True)
class Customer:
    name: str
    street_address: str
    postal_code: str
    city: str
    email: str
    phone: str
    meter_id: str
    billing_preference: str
    joined_date: date
    left_date: Optional[date]
    property_id: str
    number_of_persons: int
    bank_account: Optional[str]
    consumption_point: Optional[str]

    def is_active(self) -> bool:
        return bool(self.meter_id.strip())


@dataclass(frozen=True)
class BillingCycle:
    start_date: date
    end_date: date
    bill_date: date
    due_date: date


@dataclass(frozen=True)
class ContactInfo:
    cooperative_name: str
    iban: str
    bic: Optional[str]
    y_tunnus: str
    contact_person: str
    street_address: Optional[str]
    phone: str
    email: str
    web_url: Optional[str]
    main_meter_id: str
    treasurer_email: str
    main_meter_consumption_point: Optional[str]
    main_meter_basic_fee: Optional[Decimal]
    water_price: Optional[Decimal]
    initial_bill_number: Optional[int]


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
    count: Decimal
    unit: str
    unit_price: Decimal
    vat_percent: Decimal
    application_rule: "ApplicationRule"


@dataclass(frozen=True)
class BillLineItem:
    title: str
    count: Decimal
    unit: str
    unit_price: Decimal
    netto: Decimal
    vat_percent: Decimal
    vat: Decimal
    total: Decimal
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
    line_items: List["BillLineItem"]


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
