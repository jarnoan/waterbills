import csv
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional

from water_billing.domain.models import (
    Bill,
    BillingCycle,
    BillLine,
    ContactInfo,
    Customer,
    GeneralInfo,
    MeterReading,
)
from water_billing.domain.rules import ApplicationRule, BillingError


def _open_csv(path: Path):
    return open(path, encoding="utf-8-sig", newline="")


def read_customers(path: Path) -> List[Customer]:
    customers = []
    with _open_csv(path) as f:
        for row in csv.DictReader(f):
            left: Optional[date] = None
            if row["lähtenyt"].strip():
                left = date.fromisoformat(row["lähtenyt"].strip())
            customers.append(
                Customer(
                    name=row["nimi"].strip(),
                    address=row["osoite"].strip(),
                    email=row["sähköposti"].strip(),
                    phone=row["puhelin"].strip(),
                    meter_id=row["mittarinro"].strip(),
                    billing_preference=row["laskutustapa"].strip(),
                    joined_date=date.fromisoformat(row["liittynyt"].strip()),
                    left_date=left,
                    property_id=row["kiinteistötunnus"].strip(),
                    number_of_persons=int(row["henkilömäärä"].strip()),
                )
            )
    return customers


def read_bill_lines(path: Path) -> List[BillLine]:
    lines = []
    with _open_csv(path) as f:
        for row in csv.DictReader(f):
            rule_val = row["soveltamistapa"].strip()
            try:
                rule = ApplicationRule(rule_val)
            except ValueError:
                raise BillingError(
                    f"Tuntematon soveltamistapa: '{rule_val}'"
                )
            lines.append(
                BillLine(
                    title=row["nimike"].strip(),
                    amount=Decimal(row["summa"].strip()),
                    vat_percent=Decimal(row["alv_prosentti"].strip()),
                    application_rule=rule,
                )
            )
    return lines


def read_general_info(path: Path) -> GeneralInfo:
    with _open_csv(path) as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise BillingError("Yleiset-tiedosto on tyhjä.")
    row = rows[0]
    cycle = BillingCycle(
        start_date=date.fromisoformat(row["jakso_alkaa"].strip()),
        end_date=date.fromisoformat(row["jakso_loppuu"].strip()),
        due_date=date.fromisoformat(row["eräpäivä"].strip()),
    )
    contact = ContactInfo(
        cooperative_name=row["osuuskunnan_nimi"].strip(),
        iban=row["iban"].strip(),
        y_tunnus=row["y_tunnus"].strip(),
        contact_person=row["yhteyshenkilö"].strip(),
        phone=row["puhelin"].strip(),
        email=row["sähköposti"].strip(),
        main_meter_id=row["päämittarinro"].strip(),
    )
    return GeneralInfo(billing_cycle=cycle, contact_info=contact)


def read_meter_readings(path: Path) -> List[MeterReading]:
    readings = []
    with _open_csv(path) as f:
        for row in csv.DictReader(f):
            readings.append(
                MeterReading(
                    customer_name=row["nimi"].strip(),
                    reading_date=date.fromisoformat(row["päivämäärä"].strip()),
                    reading=int(row["lukema"].strip()),
                )
            )
    return readings


def _parse_bool(value: str) -> bool:
    v = value.strip().lower()
    if v in ("kyllä", "1", "true"):
        return True
    return False


def read_previous_bills(path: Path) -> List[Bill]:
    bills = []
    with _open_csv(path) as f:
        for row in csv.DictReader(f):
            bills.append(
                Bill(
                    bill_number=int(row["laskunumero"].strip()),
                    customer_name=row["nimi"].strip(),
                    meter_id=row["mittarinro"].strip(),
                    prev_reading=int(row["ed_lukema"].strip()),
                    prev_reading_date=date.fromisoformat(row["ed_lukema_pvm"].strip()),
                    new_reading=int(row["uusi_lukema"].strip()),
                    new_reading_date=date.fromisoformat(row["uusi_lukema_pvm"].strip()),
                    consumption=int(row["kulutus"].strip()),
                    is_estimated=_parse_bool(row["arvio"]),
                    basic_fee_share=Decimal(row["perusmaksu_osuus"].strip()),
                    water_cost=Decimal(row["vesimaksu"].strip()),
                    shared_expense_share=Decimal(row["yhteiskustannukset"].strip()),
                    total_due=Decimal(row["yhteensä"].strip()),
                    reference_number=row["viitenumero"].strip(),
                )
            )
    return bills
