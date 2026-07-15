from datetime import date
from decimal import Decimal

from water_billing.encoding.virtual_barcode import encode_virtual_barcode


# Test vectors from the Finanssiala Pankkiviivakoodi guide, version 4 examples
# https://www.finanssiala.fi/maksujenvalitys/dokumentit/Pankkiviivakoodi-opas.pdf

def test_spec_example_1():
    # IBAN: FI79 4405 2020 0360 82, amount: 4883.15,
    # ref: 86851 62596 19897, due: 12.6.2010
    result = encode_virtual_barcode(
        iban="FI79 4405 2020 0360 82",
        amount=Decimal("4883.15"),
        reference_number="868516259619897",
        due_date=date(2010, 6, 12),
    )
    assert result == "479440520200360820048831500000000868516259619897100612"


def test_spec_example_2():
    # IBAN: FI58 1017 1000 0001 22, amount: 482.99,
    # ref: 55958 22432 94671, due: 31.1.2012
    result = encode_virtual_barcode(
        iban="FI58 1017 1000 0001 22",
        amount=Decimal("482.99"),
        reference_number="559582243294671",
        due_date=date(2012, 1, 31),
    )
    assert result == "458101710000001220004829900000000559582243294671120131"


def test_spec_example_3():
    # IBAN: FI02 5000 4640 0013 02, amount: 693.80,
    # ref: 69 87567 20834 35364, due: 9.7.2011
    result = encode_virtual_barcode(
        iban="FI02 5000 4640 0013 02",
        amount=Decimal("693.80"),
        reference_number="69875672083435364",
        due_date=date(2011, 7, 9),
    )
    assert result == "402500046400013020006938000000069875672083435364110709"


def test_structure():
    result = encode_virtual_barcode(
        iban="FI2112345600000785",
        amount=Decimal("0.00"),
        reference_number="1",
        due_date=date(2025, 12, 31),
    )
    assert len(result) == 54
    assert result[0] == "4"
    # account: IBAN without the FI country code, check digits included
    assert result[1:17] == "2112345600000785"
    assert result[17:25] == "00000000"
    assert result[25:28] == "000"
    assert result[28:48] == "00000000000000000001"
    assert result[48:] == "251231"


def test_length_always_54():
    result = encode_virtual_barcode(
        iban="FI9814283500171141",
        amount=Decimal("9999.99"),
        reference_number="12345678901234567890",  # max-length 20-digit reference
        due_date=date(2099, 1, 1),
    )
    assert len(result) == 54


def test_iban_with_spaces():
    r1 = encode_virtual_barcode(
        iban="FI58 1017 1000 0001 22",
        amount=Decimal("10.00"),
        reference_number="1",
        due_date=date(2025, 1, 1),
    )
    r2 = encode_virtual_barcode(
        iban="FI5810171000000122",
        amount=Decimal("10.00"),
        reference_number="1",
        due_date=date(2025, 1, 1),
    )
    assert r1 == r2
