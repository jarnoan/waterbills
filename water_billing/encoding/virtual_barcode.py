from datetime import date
from decimal import Decimal


def encode_virtual_barcode(
    iban: str,
    amount: Decimal,
    reference_number: str,
    due_date: date,
) -> str:
    # Pankkiviivakoodi version 4 (national reference number), 54 characters:
    # "4" + account(16) + amount(8) + reserve "000" + reference(20) + due date(6)
    clean_iban = iban.replace(" ", "")
    account_16 = clean_iban[2:]

    total_cents = int((amount * 100).to_integral_value())
    amount_8 = str(total_cents).zfill(8)

    clean_ref = reference_number.replace(" ", "")
    reference_20 = clean_ref.zfill(20)

    due_yymmdd = due_date.strftime("%y%m%d")

    return "4" + account_16 + amount_8 + "000" + reference_20 + due_yymmdd
