from datetime import date
from decimal import Decimal

import pytest

from water_billing.domain.models import Bill, Customer, MeterReading
from water_billing.domain.rules import BillingError
from water_billing.services.billing import compute_consumptions


def _customer(name: str, meter_id: str = "M1") -> Customer:
    return Customer(
        name=name,
        address="",
        email="",
        phone="",
        meter_id=meter_id,
        billing_preference="sähköposti",
        joined_date=date(2020, 1, 1),
        left_date=None,
        property_id="",
        number_of_persons=1,
    )


def _bill(name: str, new_reading: int, consumption: int) -> Bill:
    return Bill(
        bill_number=1,
        customer_name=name,
        meter_id="M1",
        prev_reading=0,
        prev_reading_date=date(2024, 6, 30),
        new_reading=new_reading,
        new_reading_date=date(2024, 12, 31),
        consumption=consumption,
        is_estimated=False,
        basic_fee_share=Decimal("0"),
        water_cost=Decimal("0"),
        shared_expense_share=Decimal("0"),
        total_due=Decimal("0"),
        reference_number="1",
    )


def test_consumption_from_reading():
    customers = [_customer("Matti Meikäläinen")]
    readings = [
        MeterReading("Matti Meikäläinen", date(2025, 6, 30), 350)
    ]
    prev = [_bill("Matti Meikäläinen", new_reading=300, consumption=50)]
    result = compute_consumptions(customers, readings, prev, date(2025, 6, 30))
    assert len(result) == 1
    c = result[0]
    assert c.consumption == 50
    assert c.new_reading == 350
    assert not c.is_estimated


def test_estimated_consumption_when_no_reading():
    customers = [_customer("Matti Meikäläinen")]
    readings: list = []
    prev = [_bill("Matti Meikäläinen", new_reading=300, consumption=60)]
    result = compute_consumptions(customers, readings, prev, date(2025, 6, 30))
    c = result[0]
    assert c.is_estimated
    assert c.new_reading == 360
    assert c.consumption == 60


def test_raises_if_no_prev_bill():
    customers = [_customer("Tuntematon")]
    readings = []
    with pytest.raises(BillingError):
        compute_consumptions(customers, readings, [], date(2025, 6, 30))


def test_inactive_customer_skipped():
    inactive = Customer(
        name="Lähtijä",
        address="",
        email="",
        phone="",
        meter_id="",
        billing_preference="",
        joined_date=date(2020, 1, 1),
        left_date=date(2024, 1, 1),
        property_id="",
        number_of_persons=1,
    )
    result = compute_consumptions([inactive], [], [], date(2025, 6, 30))
    assert result == []


def test_main_meter_excluded():
    customers = [_customer("Asiakas")]
    readings = [
        MeterReading("päämittari", date(2025, 6, 30), 9999),
        MeterReading("Asiakas", date(2025, 6, 30), 200),
    ]
    prev = [_bill("Asiakas", new_reading=150, consumption=30)]
    result = compute_consumptions(customers, readings, prev, date(2025, 6, 30))
    assert len(result) == 1
    assert result[0].customer_name == "Asiakas"
