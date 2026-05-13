from itertools import cycle


def compute_reference_number(bill_number: int) -> str:
    digits = [int(d) for d in reversed(str(bill_number))]
    weights = cycle([7, 3, 1])
    total = sum(d * w for d, w in zip(digits, weights))
    check = (10 - total % 10) % 10
    return f"{bill_number}{check}"


def format_reference_number(reference: str) -> str:
    digits = reference.replace(" ", "")
    groups = []
    while digits:
        groups.append(digits[-5:])
        digits = digits[:-5]
    return " ".join(reversed(groups))
