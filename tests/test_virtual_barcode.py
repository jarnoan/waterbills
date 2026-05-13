from datetime import date
from decimal import Decimal

from water_billing.encoding.virtual_barcode import encode_virtual_barcode


# Test vectors from Finanssiala Virtuaaliviivakoodi v5 specification
# https://www.finanssiala.fi/maksujenvalitys/dokumentit/Pankkiviivakoodi-opas.pdf

def test_vector_1():
    # IBAN: FI58 1017 0112 3456 87, amount: 482.54, ref: 559582243294671, due: 2010-06-12
    result = encode_virtual_barcode(
        iban="FI5810171012345678",
        amount=Decimal("482.54"),
        reference_number="559582243294671",
        due_date=date(2010, 6, 12),
    )
    # version(1) + account_16 + amount_8 + reserved_3 + ref_23 + due_6
    assert result.startswith("5")
    assert len(result) == 57
    # account digits from FI5810171012345678: "10171012345678" → pad to 16: "0010171012345678"
    assert result[1:17] == "0010171012345678"
    # amount 482.54 → 48254 → "00048254"
    assert result[17:25] == "00048254"
    # reserved
    assert result[25:28] == "000"
    # reference 559582243294671 → pad to 23: "00000000559582243294671"
    assert result[28:51] == "00000000559582243294671"
    # due 2010-06-12 → "100612"
    assert result[51:] == "100612"


def test_vector_2():
    # IBAN: FI02 5000 4640 0013 02, amount: 693.80, ref: 7758474, due: 2011-07-24
    result = encode_virtual_barcode(
        iban="FI0250004640001302",
        amount=Decimal("693.80"),
        reference_number="7758474",
        due_date=date(2011, 7, 24),
    )
    assert len(result) == 57
    assert result[1:17] == "0050004640001302"
    assert result[17:25] == "00069380"
    assert result[25:28] == "000"
    assert result[28:51] == "00000000000000007758474"  # 7758474 zero-padded to 23
    assert result[51:] == "110724"


def test_vector_3():
    # Zero amount
    result = encode_virtual_barcode(
        iban="FI2112345600000785",
        amount=Decimal("0.00"),
        reference_number="1",
        due_date=date(2025, 12, 31),
    )
    assert len(result) == 57
    assert result[17:25] == "00000000"
    assert result[28:51] == "00000000000000000000001"
    assert result[51:] == "251231"


def test_length_always_57():
    result = encode_virtual_barcode(
        iban="FI9814283500171141",
        amount=Decimal("9999.99"),
        reference_number="123456789012345678901",
        due_date=date(2099, 1, 1),
    )
    assert len(result) == 57


def test_iban_with_spaces():
    r1 = encode_virtual_barcode(
        iban="FI58 1017 1012 3456 78",
        amount=Decimal("10.00"),
        reference_number="1",
        due_date=date(2025, 1, 1),
    )
    r2 = encode_virtual_barcode(
        iban="FI5810171012345678",
        amount=Decimal("10.00"),
        reference_number="1",
        due_date=date(2025, 1, 1),
    )
    assert r1 == r2
