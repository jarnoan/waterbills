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


def _consumption(name, consumption, estimated, prev_reading=100):
    from water_billing.domain.models import CustomerConsumption

    return CustomerConsumption(
        customer_name=name,
        meter_id="M",
        prev_reading=prev_reading,
        prev_reading_date=date(2026, 8, 31),
        new_reading=prev_reading + consumption,
        new_reading_date=date(2026, 10, 31),
        consumption=consumption,
        is_estimated=estimated,
    )


def test_remaining_main_meter_consumption_split_by_previous_consumption():
    from water_billing.services.billing import distribute_remaining_to_estimates

    consumptions = [
        _consumption("Luettu", 50, False),
        _consumption("A", 10, True),
        _consumption("B", 20, True),
    ]
    # Main meter 150, actual 50 -> 100 m³ split 1:2 -> 33.3 and 66.7, rounded up.
    result = distribute_remaining_to_estimates(consumptions, 150)
    by_name = {c.customer_name: c for c in result}
    assert by_name["Luettu"].consumption == 50
    assert (by_name["A"].consumption, by_name["A"].new_reading) == (34, 134)
    assert (by_name["B"].consumption, by_name["B"].new_reading) == (67, 167)
    assert by_name["A"].is_estimated and by_name["B"].is_estimated


def test_transfer_consumption_counts_as_actual():
    from water_billing.services.billing import distribute_remaining_to_estimates

    result = distribute_remaining_to_estimates([_consumption("A", 5, True)], 100, 40)
    assert result[0].consumption == 60


def test_no_previous_consumption_splits_equally():
    from water_billing.services.billing import distribute_remaining_to_estimates

    result = distribute_remaining_to_estimates(
        [_consumption("A", 0, True), _consumption("B", 0, True)], 9
    )
    assert [c.consumption for c in result] == [5, 5]


def test_actual_over_main_meter_gives_zero_estimates():
    from water_billing.services.billing import distribute_remaining_to_estimates

    result = distribute_remaining_to_estimates(
        [_consumption("Luettu", 120, False), _consumption("A", 10, True)], 100
    )
    assert result[1].consumption == 0
    assert result[1].new_reading == result[1].prev_reading


def test_without_main_meter_estimates_are_kept():
    from water_billing.services.billing import distribute_remaining_to_estimates

    consumptions = [_consumption("A", 10, True)]
    assert distribute_remaining_to_estimates(consumptions, None) == consumptions
