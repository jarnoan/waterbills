import csv
import sys
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
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

_REQUIRED_YLEISET_KEYS = [
    "jakso_alkaa", "jakso_loppuu",
    "osuuskunnan_nimi", "iban", "y_tunnus",
    "yhteyshenkilö", "puhelin", "sähköposti", "päämittarinro",
    "rahastonhoitajan_sähköposti",
]


def _open_csv(path: Path):
    return open(path, encoding="utf-8-sig", newline="")


def read_customers(path: Path) -> List[Customer]:
    customers = []
    with _open_csv(path) as f:
        for row in csv.DictReader(f):
            left: Optional[date] = None
            if row.get("lähtenyt", "").strip():
                left = date.fromisoformat(row["lähtenyt"].strip())
            bank_account = row.get("tilinumero", "").strip() or None
            consumption_point = row.get("kulutuspiste", "").strip() or None
            customer_number = (row.get("asiakasnumero") or "").strip() or None
            _print_order_raw = row.get("tulostusjärjestys", "").strip()
            print_order = int(_print_order_raw) if _print_order_raw else None
            customers.append(
                Customer(
                    name=row["nimi"].strip(),
                    street_address=row["katuosoite"].strip(),
                    postal_code=row["postinumero"].strip(),
                    city=row["postitoimipaikka"].strip(),
                    email=row["sähköposti"].strip(),
                    phone=row["puhelin"].strip(),
                    meter_id=row["mittarinro"].strip(),
                    billing_preference=row["laskutustapa"].strip(),
                    joined_date=date.fromisoformat(row["liittynyt"].strip()),
                    left_date=left,
                    property_id=row["kiinteistötunnus"].strip(),
                    number_of_persons=int(row["henkilömäärä"].strip()),
                    bank_account=bank_account,
                    consumption_point=consumption_point,
                    print_order=print_order,
                    customer_number=customer_number,
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
                raise BillingError(f"Tuntematon soveltamistapa: '{rule_val}'")
            count = Decimal(row["määrä"].strip())
            unit_price = Decimal(row["a-hinta"].strip())
            netto_declared = row.get("netto", "").strip()
            if netto_declared:
                try:
                    netto_val = Decimal(netto_declared)
                    expected = (count * unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    if abs(netto_val - expected) > Decimal("0.001"):
                        print(
                            f"Varoitus: laskurivillä '{row['nimike']}' netto {netto_val} "
                            f"poikkeaa laskennallisesta {expected}",
                            file=sys.stderr,
                        )
                except Exception:
                    pass
            raw_start = row.get("jakso_alkaa", "").strip()
            raw_end = row.get("jakso_loppuu", "").strip()
            lines.append(
                BillLine(
                    title=row["nimike"].strip(),
                    count=count,
                    unit=row["yksikkö"].strip(),
                    unit_price=unit_price,
                    vat_percent=Decimal(row["alv-%"].strip()),
                    application_rule=rule,
                    cycle_start=date.fromisoformat(raw_start) if raw_start else None,
                    cycle_end=date.fromisoformat(raw_end) if raw_end else None,
                )
            )
    return lines


def read_general_info(yleiset_paths: List[Path]) -> GeneralInfo:
    if not yleiset_paths:
        raise BillingError("Yleiset-tiedostoa ei löydy")

    merged: dict = {}
    for path in yleiset_paths:
        with _open_csv(path) as f:
            reader = csv.DictReader(f)
            if reader.fieldnames and "avain" not in reader.fieldnames:
                raise BillingError(
                    f"Yleiset-tiedosto '{path.name}' ei ole avain/arvo-muodossa"
                )
            for row in reader:
                key = row.get("avain", "").strip()
                value = row.get("arvo", "").strip()
                if key and key not in merged:
                    merged[key] = value

    missing = [k for k in _REQUIRED_YLEISET_KEYS if k not in merged]
    if missing:
        raise BillingError(
            f"Yleiset-tiedostosta puuttuu avaimet: {', '.join(missing)}"
        )

    bill_date_str = merged.get("laskupäivä", "").strip()
    bill_date = date.fromisoformat(bill_date_str) if bill_date_str else date.today()
    due_date = bill_date + timedelta(days=14)

    cycle = BillingCycle(
        start_date=date.fromisoformat(merged["jakso_alkaa"]),
        end_date=date.fromisoformat(merged["jakso_loppuu"]),
        bill_date=bill_date,
        due_date=due_date,
    )
    raw_basic_fee = merged.get("päämittarin_perusmaksu", "").strip()
    raw_water_price = merged.get("vesihinta", "").strip()
    raw_initial_bill = merged.get("aloituslaskunumero", "").strip()
    raw_bic = merged.get("bic", "").strip()
    raw_street_address = merged.get("osoite", "").strip()
    raw_web_url = merged.get("www", "").strip()
    raw_message = merged.get("viesti", "").strip().replace("\\n", "\n")
    contact = ContactInfo(
        cooperative_name=merged["osuuskunnan_nimi"],
        iban=merged["iban"],
        bic=raw_bic or None,
        y_tunnus=merged["y_tunnus"],
        contact_person=merged["yhteyshenkilö"],
        street_address=raw_street_address or None,
        phone=merged["puhelin"],
        email=merged["sähköposti"],
        web_url=raw_web_url or None,
        main_meter_id=merged["päämittarinro"],
        treasurer_email=merged["rahastonhoitajan_sähköposti"],
        main_meter_consumption_point=merged.get("päämittarin_kulutuspiste") or None,
        main_meter_basic_fee=Decimal(raw_basic_fee) if raw_basic_fee else None,
        water_price=Decimal(raw_water_price) if raw_water_price else None,
        initial_bill_number=int(raw_initial_bill) if raw_initial_bill else None,
        message=raw_message or None,
        main_meter_customer_number=merged.get("päämittarin_asiakasnumero", "").strip() or None,
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


def read_bill_numbers(path: Path) -> List[int]:
    numbers = []
    with _open_csv(path) as f:
        for row in csv.DictReader(f):
            val = row.get("laskunumero", "").strip()
            try:
                numbers.append(int(val))
            except (ValueError, TypeError):
                pass
    return numbers


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in ("kyllä", "1", "true")


def read_bills(path: Path) -> List[Bill]:
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
                    line_items=[],
                )
            )
    return bills
