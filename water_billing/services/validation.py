from typing import List

from water_billing.domain.models import (
    Bill,
    BillLine,
    Customer,
    GeneralInfo,
    MeterReading,
)
from water_billing.domain.rules import BillingError


def validate_iban(iban: str) -> bool:
    clean = iban.replace(" ", "")
    return (
        clean.startswith("FI")
        and len(clean) == 18
        and clean[2:].isdigit()
    )


def validate_inputs(
    customers: List[Customer],
    bill_lines: List[BillLine],
    general_info: GeneralInfo,
    meter_readings: List[MeterReading],
    prev_bills: List[Bill],
) -> List[str]:
    messages: List[str] = []
    errors: List[str] = []

    active = [c for c in customers if c.is_active()]
    if not active:
        errors.append("Ei aktiivisia asiakkaita.")

    if not bill_lines:
        errors.append("Laskurivit-tiedosto on tyhjä.")

    cycle = general_info.billing_cycle
    if cycle.start_date >= cycle.end_date:
        errors.append("Laskutusjakson alkupäivä on jakson loppupäivän jälkeen tai sama.")

    if not validate_iban(general_info.contact_info.iban):
        errors.append(
            f"IBAN-numero ei ole kelvollinen suomalainen muoto: "
            f"'{general_info.contact_info.iban}'"
        )

    if errors:
        raise BillingError("\n".join(errors))

    prev_names = {b.customer_name for b in prev_bills}
    for c in active:
        if c.name not in prev_names:
            messages.append(
                f"Varoitus: asiakkaalla '{c.name}' ei ole edellisiä laskutietoja "
                "(uusi asiakas tai puuttuva siemenlaskut-tiedosto)."
            )

    reading_names = {r.customer_name for r in meter_readings}
    if "päämittari" not in reading_names:
        messages.append(
            "Varoitus: päämittarin lukema puuttuu — vesihäviötietoja ei lasketa."
        )

    return messages
