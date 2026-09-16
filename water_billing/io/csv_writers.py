import csv
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import List

from water_billing.domain.models import Bill, BillLine
from water_billing.domain.rules import ApplicationRule, BillingError

_LASKURIVIT_HEADERS = [
    "nimike", "määrä", "yksikkö", "a-hinta", "netto",
    "alv-%", "alv", "yhteensä", "soveltamistapa",
]

_HEADERS = [
    "laskunumero", "nimi", "mittarinro",
    "ed_lukema", "ed_lukema_pvm",
    "uusi_lukema", "uusi_lukema_pvm",
    "kulutus", "arvio",
    "perusmaksu_osuus", "vesimaksu", "yhteiskustannukset",
    "yhteensä", "viitenumero",
]


def write_bills(path: Path, bills: List[Bill], overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise BillingError(
            f"Tulostiedosto on jo olemassa: {path}. "
            "Käytä --ylikirjoita ylikirjoittaaksesi."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_HEADERS)
        writer.writeheader()
        for b in sorted(bills, key=lambda b: b.bill_number):
            perusmaksu = sum(
                i.total for i in b.line_items
                if i.application_rule == ApplicationRule.PER_ACTIVE_CUSTOMER
            )
            vesimaksu = sum(
                i.total for i in b.line_items
                if i.application_rule == ApplicationRule.PER_CONSUMPTION
            )
            yhteiskustannukset = sum(
                i.total for i in b.line_items
                if i.application_rule == ApplicationRule.PER_ALL_CUSTOMERS
            )
            writer.writerow(
                {
                    "laskunumero": b.bill_number,
                    "nimi": b.customer_name,
                    "mittarinro": b.meter_id,
                    "ed_lukema": b.prev_reading,
                    "ed_lukema_pvm": b.prev_reading_date.isoformat(),
                    "uusi_lukema": b.new_reading,
                    "uusi_lukema_pvm": b.new_reading_date.isoformat(),
                    "kulutus": b.consumption,
                    "arvio": "kyllä" if b.is_estimated else "ei",
                    "perusmaksu_osuus": f"{perusmaksu:.2f}",
                    "vesimaksu": f"{vesimaksu:.2f}",
                    "yhteiskustannukset": f"{yhteiskustannukset:.2f}",
                    "yhteensä": f"{b.total_due:.2f}",
                    "viitenumero": b.reference_number,
                }
            )


def write_bill_lines(path: Path, bill_lines: List[BillLine], overwrite: bool = False) -> None:
    if path.exists() and not overwrite:
        raise BillingError(
            f"Tulostiedosto on jo olemassa: {path}. "
            "Käytä --ylikirjoita ylikirjoittaaksesi."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_LASKURIVIT_HEADERS)
        writer.writeheader()
        for bl in bill_lines:
            netto = (bl.count * bl.unit_price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            alv = (netto * bl.vat_percent / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            yhteensa = netto + alv
            writer.writerow({
                "nimike": bl.title,
                "määrä": f"{bl.count:.2f}",
                "yksikkö": bl.unit,
                "a-hinta": f"{bl.unit_price:.2f}",
                "netto": f"{netto:.2f}",
                "alv-%": f"{bl.vat_percent:.2f}",
                "alv": f"{alv:.2f}",
                "yhteensä": f"{yhteensa:.2f}",
                "soveltamistapa": bl.application_rule.value,
            })
