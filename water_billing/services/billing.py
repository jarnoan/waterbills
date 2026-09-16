from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import typer

from water_billing.domain.models import (
    Bill,
    BillingCycle,
    BillLine,
    BillLineItem,
    Customer,
    CustomerConsumption,
    MeterReading,
    OwnershipTransfer,
)
from water_billing.domain.rules import (
    ApplicationRule,
    BillingError,
    ceil_cent,
    distribute_bill_line,
)
from water_billing.encoding.reference_number import compute_reference_number
from water_billing.io.csv_readers import read_bill_numbers, read_meter_readings


def next_billing_period(prev_end_date: date) -> Tuple[date, date]:
    """Compute the next two-month billing period following prev_end_date.

    The period starts the day after prev_end_date and runs to the end of
    the following calendar month.
    """
    start = prev_end_date + timedelta(days=1)
    end_month = start.month + 1
    end_year = start.year
    if end_month > 12:
        end_month -= 12
        end_year += 1
    end = date(end_year, end_month, calendar.monthrange(end_year, end_month)[1])
    return start, end


def compute_consumptions(
    customers: List[Customer],
    current_readings: List[MeterReading],
    prev_readings: List[MeterReading],
    prev_prev_readings: List[MeterReading],
    cycle_end_date: date,
) -> List[CustomerConsumption]:
    current_by_name = {
        r.customer_name: r
        for r in current_readings
        if r.customer_name != "päämittari"
    }
    prev_by_name = {
        r.customer_name: r
        for r in prev_readings
        if r.customer_name != "päämittari"
    }
    prev_prev_by_name = {
        r.customer_name: r
        for r in prev_prev_readings
        if r.customer_name != "päämittari"
    }

    result = []
    for c in customers:
        if not c.is_active():
            continue
        prev_r = prev_by_name.get(c.name)
        if prev_r is None:
            raise BillingError(f"Ei edellisiä lukemia asiakkaalle: {c.name}")

        if c.name in current_by_name:
            new_r = current_by_name[c.name]
            is_estimated = False
            consumption = new_r.reading - prev_r.reading
            new_reading = new_r.reading
            new_date = new_r.reading_date
        else:
            is_estimated = True
            new_date = cycle_end_date
            if c.name in prev_prev_by_name:
                consumption = prev_r.reading - prev_prev_by_name[c.name].reading
            else:
                consumption = 0
                typer.echo(
                    f"Varoitus: ei kahta edellistä lukemaa, kulutus arvioidaan"
                    f" nollaksi: {c.name}",
                    err=True,
                )
            new_reading = prev_r.reading + consumption

        result.append(
            CustomerConsumption(
                customer_name=c.name,
                meter_id=c.meter_id,
                prev_reading=prev_r.reading,
                prev_reading_date=prev_r.reading_date,
                new_reading=new_reading,
                new_reading_date=new_date,
                consumption=consumption,
                is_estimated=is_estimated,
            )
        )
    return result


def compute_main_meter_consumption(
    current_readings: List[MeterReading],
    prev_lukemat_path: Optional[Path],
) -> Optional[int]:
    current_main = next(
        (r for r in current_readings if r.customer_name == "päämittari"), None
    )
    if current_main is None:
        return None
    if prev_lukemat_path is None:
        return None
    prev_readings = read_meter_readings(prev_lukemat_path)
    prev_main = next(
        (r for r in prev_readings if r.customer_name == "päämittari"), None
    )
    if prev_main is None:
        return None
    return current_main.reading - prev_main.reading


def get_next_bill_number(
    all_laskut_paths: List[Path],
    initial_bill_number: Optional[int] = None,
) -> int:
    if initial_bill_number is not None:
        return initial_bill_number
    if all_laskut_paths:
        all_numbers = []
        for path in all_laskut_paths:
            all_numbers.extend(read_bill_numbers(path))
        if all_numbers:
            return max(all_numbers) + 1
    return 1


def generate_bills(
    customers: List[Customer],
    consumptions: List[CustomerConsumption],
    bill_lines: List[BillLine],
    billing_cycle: BillingCycle,
    start_bill_number: int,
) -> List[Bill]:
    consumption_by_name: Dict[str, Decimal] = {
        c.customer_name: Decimal(c.consumption) for c in consumptions
    }

    distributions: List[Dict[str, Decimal]] = [
        distribute_bill_line(line, customers, consumption_by_name) for line in bill_lines
    ]

    basic_fee: Dict[str, Decimal] = {}
    water_cost: Dict[str, Decimal] = {}
    shared_expense: Dict[str, Decimal] = {}

    for line, dist in zip(bill_lines, distributions):
        if line.application_rule == ApplicationRule.PER_ACTIVE_CUSTOMER:
            for name, amt in dist.items():
                basic_fee[name] = basic_fee.get(name, Decimal("0")) + amt
        elif line.application_rule == ApplicationRule.PER_ALL_CUSTOMERS:
            for name, amt in dist.items():
                shared_expense[name] = shared_expense.get(name, Decimal("0")) + amt
        else:
            for name, amt in dist.items():
                water_cost[name] = water_cost.get(name, Decimal("0")) + amt

    consumption_by_customer = {c.customer_name: c for c in consumptions}
    active_in_order = [c for c in customers if c.is_active()]

    bills = []
    for i, customer in enumerate(active_in_order):
        bill_number = start_bill_number + i
        name = customer.name
        cons = consumption_by_customer[name]
        bf = basic_fee.get(name, Decimal("0"))
        wc = water_cost.get(name, Decimal("0"))
        se = shared_expense.get(name, Decimal("0"))

        line_items = []
        for line, dist in zip(bill_lines, distributions):
            customer_amount = dist.get(name, Decimal("0"))
            if line.application_rule == ApplicationRule.PER_CONSUMPTION:
                item_count = consumption_by_name.get(name, Decimal("0"))
                effective_unit_price = line.unit_price
            else:
                item_count = line.count
                effective_unit_price = (
                    (customer_amount / item_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    if item_count
                    else Decimal("0")
                )
            vat = (customer_amount * line.vat_percent / 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            line_items.append(
                BillLineItem(
                    title=line.title,
                    count=item_count,
                    unit=line.unit,
                    unit_price=effective_unit_price,
                    netto=customer_amount,
                    vat_percent=line.vat_percent,
                    vat=vat,
                    total=customer_amount + vat,
                    application_rule=line.application_rule,
                    cycle_start=line.cycle_start,
                    cycle_end=line.cycle_end,
                )
            )

        total_due = sum(item.total for item in line_items)
        bills.append(
            Bill(
                bill_number=bill_number,
                customer_name=name,
                meter_id=customer.meter_id,
                prev_reading=cons.prev_reading,
                prev_reading_date=cons.prev_reading_date,
                new_reading=cons.new_reading,
                new_reading_date=cons.new_reading_date,
                consumption=cons.consumption,
                is_estimated=cons.is_estimated,
                basic_fee_share=bf,
                water_cost=wc,
                shared_expense_share=se,
                total_due=total_due,
                reference_number=compute_reference_number(bill_number),
                line_items=line_items,
            )
        )
    return bills


def detect_ownership_transfers(
    current_readings: List[MeterReading],
    customers: List[Customer],
) -> List[OwnershipTransfer]:
    name_to_meter = {c.name: c.meter_id for c in customers if c.is_active()}
    meter_readings_by_meter: Dict[str, List[MeterReading]] = {}
    for r in current_readings:
        if r.customer_name == "päämittari":
            continue
        mid = name_to_meter.get(r.customer_name)
        if mid:
            meter_readings_by_meter.setdefault(mid, []).append(r)

    transfers = []
    for meter_id, readings in meter_readings_by_meter.items():
        if len(readings) < 2:
            continue
        sorted_readings = sorted(readings, key=lambda r: r.reading_date)
        prev_owner_reading = sorted_readings[0]
        new_owner_reading = sorted_readings[1]
        prev_customer = next(
            (c for c in customers if c.name == prev_owner_reading.customer_name), None
        )
        new_customer = next(
            (c for c in customers if c.name == new_owner_reading.customer_name), None
        )
        if prev_customer is None or new_customer is None:
            continue
        transfers.append(
            OwnershipTransfer(
                meter_id=meter_id,
                prev_owner_name=prev_owner_reading.customer_name,
                new_owner_name=new_owner_reading.customer_name,
                transfer_date=prev_owner_reading.reading_date,
                transfer_reading=prev_owner_reading.reading,
                new_owner_end_reading=new_owner_reading.reading,
            )
        )
    return transfers


def split_bills_for_transfer(
    transfer: OwnershipTransfer,
    billing_cycle: BillingCycle,
    bill_lines: List[BillLine],
    all_customers: List[Customer],
    start_bill_number: int,
) -> Tuple[Bill, Bill]:
    total_days = Decimal((billing_cycle.end_date - billing_cycle.start_date).days)
    prev_days = Decimal((transfer.transfer_date - billing_cycle.start_date).days)
    new_days = total_days - prev_days

    per_customer_basic = Decimal("0")
    for line in bill_lines:
        if line.application_rule == ApplicationRule.PER_ACTIVE_CUSTOMER:
            active_count = sum(1 for c in all_customers if c.is_active())
            if active_count:
                per_customer_basic += ceil_cent((line.count * line.unit_price) / active_count)

    prev_basic = ceil_cent(per_customer_basic * (prev_days / total_days))
    new_basic = ceil_cent(per_customer_basic * (new_days / total_days))

    shared_all = Decimal("0")
    for line in bill_lines:
        if line.application_rule == ApplicationRule.PER_ALL_CUSTOMERS:
            count = len(all_customers)
            if count:
                shared_all += ceil_cent((line.count * line.unit_price) / count)

    if transfer.new_owner_end_reading is not None:
        new_consumption = transfer.new_owner_end_reading - transfer.transfer_reading
    else:
        new_consumption = 0

    water_unit_price = Decimal("0")
    for line in bill_lines:
        if line.application_rule == ApplicationRule.PER_CONSUMPTION:
            water_unit_price += line.unit_price

    new_water = (water_unit_price * Decimal(new_consumption)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    prev_total = prev_basic
    new_total = new_basic + new_water + shared_all

    prev_bill = Bill(
        bill_number=start_bill_number,
        customer_name=transfer.prev_owner_name,
        meter_id=transfer.meter_id,
        prev_reading=0,
        prev_reading_date=billing_cycle.start_date,
        new_reading=transfer.transfer_reading,
        new_reading_date=transfer.transfer_date,
        consumption=0,
        is_estimated=False,
        basic_fee_share=prev_basic,
        water_cost=Decimal("0"),
        shared_expense_share=Decimal("0"),
        total_due=prev_total,
        reference_number=compute_reference_number(start_bill_number),
        line_items=[],
    )
    new_bill = Bill(
        bill_number=start_bill_number + 1,
        customer_name=transfer.new_owner_name,
        meter_id=transfer.meter_id,
        prev_reading=transfer.transfer_reading,
        prev_reading_date=transfer.transfer_date,
        new_reading=transfer.new_owner_end_reading or transfer.transfer_reading,
        new_reading_date=billing_cycle.end_date,
        consumption=new_consumption,
        is_estimated=False,
        basic_fee_share=new_basic,
        water_cost=new_water,
        shared_expense_share=shared_all,
        total_due=new_total,
        reference_number=compute_reference_number(start_bill_number + 1),
        line_items=[],
    )
    return prev_bill, new_bill
