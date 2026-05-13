import csv
from pathlib import Path
from typing import List

from water_billing.domain.models import Bill
from water_billing.domain.rules import BillingError

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
        for b in bills:
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
                    "perusmaksu_osuus": f"{b.basic_fee_share:.2f}",
                    "vesimaksu": f"{b.water_cost:.2f}",
                    "yhteiskustannukset": f"{b.shared_expense_share:.2f}",
                    "yhteensä": f"{b.total_due:.2f}",
                    "viitenumero": b.reference_number,
                }
            )
