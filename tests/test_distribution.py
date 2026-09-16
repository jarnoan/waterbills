from decimal import Decimal

import pytest

from water_billing.domain.models import BillLine, Customer
from water_billing.domain.rules import (
    ApplicationRule,
    BillingError,
    ceil_cent,
    distribute_bill_line,
)
from datetime import date


def _customer(name: str, active: bool = True) -> Customer:
    return Customer(
        name=name,
        street_address="",
        postal_code="",
        city="",
        email="",
        phone="",
        meter_id="M1" if active else "",
        billing_preference="sähköposti",
        joined_date=date(2020, 1, 1),
        left_date=None,
        property_id="",
        number_of_persons=1,
        bank_account=None,
        consumption_point=None,
        print_order=None,
    )


def _line(amount: str, rule: ApplicationRule) -> BillLine:
    return BillLine(
        title="Testi",
        count=Decimal("1"),
        unit="kpl",
        unit_price=Decimal(amount),
        vat_percent=Decimal("0"),
        application_rule=rule,
    )


def test_ceil_cent_rounds_up():
    assert ceil_cent(Decimal("1.001")) == Decimal("1.01")
    assert ceil_cent(Decimal("1.005")) == Decimal("1.01")
    assert ceil_cent(Decimal("1.00")) == Decimal("1.00")


def test_per_active_customer_split():
    customers = [_customer("A"), _customer("B"), _customer("C")]
    line = _line("10.00", ApplicationRule.PER_ACTIVE_CUSTOMER)
    result = distribute_bill_line(line, customers, {})
    assert "A" in result and "B" in result and "C" in result
    assert result["A"] == Decimal("3.34")


def test_per_active_customer_excludes_inactive():
    customers = [_customer("A"), _customer("B", active=False)]
    line = _line("10.00", ApplicationRule.PER_ACTIVE_CUSTOMER)
    result = distribute_bill_line(line, customers, {})
    assert "B" not in result
    assert result["A"] == Decimal("10.00")


def test_per_all_customers():
    customers = [_customer("A"), _customer("B", active=False)]
    line = _line("10.00", ApplicationRule.PER_ALL_CUSTOMERS)
    result = distribute_bill_line(line, customers, {})
    assert "A" in result and "B" in result
    assert result["A"] == Decimal("5.00")


def test_per_consumption():
    customers = [_customer("A"), _customer("B")]
    consumptions = {"A": Decimal("10"), "B": Decimal("5")}
    line = _line("2.00", ApplicationRule.PER_CONSUMPTION)
    result = distribute_bill_line(line, customers, consumptions)
    assert result["A"] == Decimal("20.00")
    assert result["B"] == Decimal("10.00")


def test_per_consumption_zero_if_no_reading():
    customers = [_customer("A")]
    line = _line("2.00", ApplicationRule.PER_CONSUMPTION)
    result = distribute_bill_line(line, customers, {})
    assert result["A"] == Decimal("0.00")


def test_per_active_raises_if_no_active():
    customers = [_customer("A", active=False)]
    line = _line("10.00", ApplicationRule.PER_ACTIVE_CUSTOMER)
    with pytest.raises(BillingError):
        distribute_bill_line(line, customers, {})


def test_ceiling_applied_correctly():
    customers = [_customer("A"), _customer("B"), _customer("C")]
    line = _line("100.00", ApplicationRule.PER_ACTIVE_CUSTOMER)
    result = distribute_bill_line(line, customers, {})
    for v in result.values():
        assert v == Decimal("33.34")
