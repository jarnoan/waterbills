from datetime import date
from decimal import Decimal

import pytest

from water_billing.domain.models import Customer, MeterReading
from water_billing.domain.rules import BillingError
from water_billing.services.billing import compute_consumptions


def _customer(name: str, meter_id: str = "M1") -> Customer:
    return Customer(
        name=name,
        street_address="Testikatu 1",
        postal_code="00100",
        city="Helsinki",
        email="",
        phone="",
        meter_id=meter_id,
        billing_preference="sähköposti",
        joined_date=date(2020, 1, 1),
        left_date=None,
        property_id="",
        number_of_persons=1,
        bank_account=None,
        consumption_point=None,
        print_order=None,
    )


def _reading(name: str, reading: int, d: date = date(2025, 6, 30)) -> MeterReading:
    return MeterReading(customer_name=name, reading_date=d, reading=reading)


def test_consumption_from_reading():
    customers = [_customer("Matti Meikäläinen")]
    current = [_reading("Matti Meikäläinen", 350)]
    prev = [_reading("Matti Meikäläinen", 300, date(2024, 12, 31))]
    result = compute_consumptions(customers, current, prev, [], date(2025, 6, 30))
    assert len(result) == 1
    c = result[0]
    assert c.consumption == 50
    assert c.new_reading == 350
    assert not c.is_estimated


def test_estimated_from_prev_prev():
    customers = [_customer("Matti Meikäläinen")]
    prev = [_reading("Matti Meikäläinen", 300, date(2024, 12, 31))]
    prev_prev = [_reading("Matti Meikäläinen", 240, date(2024, 6, 30))]
    result = compute_consumptions(customers, [], prev, prev_prev, date(2025, 6, 30))
    c = result[0]
    assert c.is_estimated
    assert c.consumption == 60
    assert c.new_reading == 360


def test_estimated_zero_when_no_prev_prev():
    customers = [_customer("Matti Meikäläinen")]
    prev = [_reading("Matti Meikäläinen", 300, date(2024, 12, 31))]
    result = compute_consumptions(customers, [], prev, [], date(2025, 6, 30))
    c = result[0]
    assert c.is_estimated
    assert c.consumption == 0
    assert c.new_reading == 300


def test_raises_if_no_prev_reading():
    customers = [_customer("Tuntematon")]
    with pytest.raises(BillingError):
        compute_consumptions(customers, [], [], [], date(2025, 6, 30))


def test_inactive_customer_skipped():
    inactive = Customer(
        name="Lähtijä",
        street_address="",
        postal_code="",
        city="",
        email="",
        phone="",
        meter_id="",
        billing_preference="",
        joined_date=date(2020, 1, 1),
        left_date=date(2024, 1, 1),
        property_id="",
        number_of_persons=1,
        bank_account=None,
        consumption_point=None,
        print_order=None,
    )
    result = compute_consumptions([inactive], [], [], [], date(2025, 6, 30))
    assert result == []


def test_main_meter_excluded():
    customers = [_customer("Asiakas")]
    current = [
        _reading("päämittari", 9999),
        _reading("Asiakas", 200),
    ]
    prev = [_reading("Asiakas", 150, date(2024, 12, 31))]
    result = compute_consumptions(customers, current, prev, [], date(2025, 6, 30))
    assert len(result) == 1
    assert result[0].customer_name == "Asiakas"
    assert result[0].consumption == 50
