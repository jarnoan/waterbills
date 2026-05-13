from datetime import date
from pathlib import Path
from typing import Optional

from water_billing.domain.rules import BillingError


def parse_date_prefix(filename: str) -> Optional[date]:
    try:
        return date(int(filename[:4]), int(filename[4:6]), int(filename[6:8]))
    except (ValueError, IndexError):
        return None


def find_latest_file(
    data_root: Path,
    year: int,
    file_type: str,
    at_or_before: date,
) -> Optional[Path]:
    year_dir = data_root / str(year)
    if not year_dir.exists():
        return None
    candidates = []
    for p in year_dir.glob(f"*-{file_type}-*.csv"):
        d = parse_date_prefix(p.name)
        if d is not None and d <= at_or_before:
            candidates.append((d, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def require_file(
    data_root: Path,
    year: int,
    file_type: str,
    at_or_before: date,
) -> Path:
    result = find_latest_file(data_root, year, file_type, at_or_before)
    if result is None:
        raise BillingError(
            f"Tiedostoa tyyppiä '{file_type}' ei löydy vuodelta {year}"
        )
    return result


def find_previous_laskut(
    data_root: Path,
    current_year: int,
    before_date: date,
) -> Path:
    for year in (current_year, current_year - 1):
        year_dir = data_root / str(year)
        if not year_dir.exists():
            continue
        candidates = []
        for p in year_dir.glob("*-laskut-*.csv"):
            d = parse_date_prefix(p.name)
            if d is not None and d < before_date:
                candidates.append((d, p))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
    raise BillingError(
        f"Edellisiä laskuja ei löydy vuosilta {current_year - 1}–{current_year}"
    )


def find_previous_lukemat(
    data_root: Path,
    current_year: int,
    before_date: date,
) -> Optional[Path]:
    for year in (current_year, current_year - 1):
        year_dir = data_root / str(year)
        if not year_dir.exists():
            continue
        candidates = []
        for p in year_dir.glob("*-lukemat-*.csv"):
            d = parse_date_prefix(p.name)
            if d is not None and d < before_date:
                candidates.append((d, p))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]
    return None


def output_path(
    data_root: Path,
    cycle_end_date: date,
    file_type: str,
    note: str,
    extension: str,
) -> Path:
    year_dir = data_root / str(cycle_end_date.year)
    filename = f"{cycle_end_date.strftime('%Y%m%d')}-{file_type}-{note}.{extension}"
    return year_dir / filename
