from datetime import date
from decimal import Decimal


def encode_virtual_barcode(
    iban: str,
    amount: Decimal,
    reference_number: str,
    due_date: date,
) -> str:
    clean_iban = iban.replace(" ", "")
    account_digits = clean_iban[4:]
    account_16 = account_digits.zfill(16)

    total_cents = int((amount * 100).to_integral_value())
    amount_8 = str(total_cents).zfill(8)

    clean_ref = reference_number.replace(" ", "")
    reference_23 = clean_ref.zfill(23)

    due_yymmdd = due_date.strftime("%y%m%d")

    return "5" + account_16 + amount_8 + "000" + reference_23 + due_yymmdd
