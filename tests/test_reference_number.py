from water_billing.encoding.reference_number import (
    compute_reference_number,
    format_reference_number,
)


def test_known_vector_1234():
    # weights [7,3,1] from right: 4*7+3*3+2*1+1*7=46, check=(10-6)%10=4
    assert compute_reference_number(1234) == "12344"


def test_known_vector_13579():
    # 9*7 + 7*3 + 5*1 + 3*7 + 1*3 = 63+21+5+21+3 = 113; check = (10 - 113%10)%10 = (10-3)%10 = 7
    result = compute_reference_number(13579)
    assert result == "135797"


def test_check_digit_zero():
    # find a number where total % 10 == 0 → check digit 0
    # 10 → digits reversed [0,1], weights [7,3]: 0*7+1*3=3; check=(10-3)%10=7 → nope
    # Try 37: reversed [7,3], 7*7+3*3=49+9=58; (10-8)%10=2 → nope
    # Try 100: reversed [0,0,1], 0*7+0*3+1*1=1; (10-1)%10=9
    # Try 5: [5], 5*7=35; (10-5)%10=5
    # Try 1230: reversed [0,3,2,1], 0*7+3*3+2*1+1*7=0+9+2+7=18; (10-8)%10=2
    # Try 1240: reversed [0,4,2,1], 0*7+4*3+2*1+1*7=0+12+2+7=21; (10-1)%10=9
    # Try 1250: 0*7+5*3+2*1+1*7=0+15+2+7=24; (10-4)%10=6
    # Try 1260: 0*7+6*3+2*1+1*7=0+18+2+7=27; (10-7)%10=3
    # Try 1290: 0+9*3+2+7=0+27+2+7=36; (10-6)%10=4
    # Try 1300: 0+0+3*1+1*7=0+0+3+7=10; (10-0)%10=0 ✓
    result = compute_reference_number(1300)
    assert result.endswith("0")
    assert compute_reference_number(1300) == "13000"


def test_format_groups_from_right():
    assert format_reference_number("12345678") == "123 45678"


def test_format_exact_5():
    assert format_reference_number("12345") == "12345"


def test_format_6_chars():
    assert format_reference_number("123456") == "1 23456"


def test_format_single_digit():
    assert format_reference_number("5") == "5"
