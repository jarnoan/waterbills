from datetime import date
from pathlib import Path
from typing import List, Optional

from water_billing.domain.rules import BillingError


def parse_date_prefix(filename: str) -> Optional[date]:
    try:
        return date(int(filename[:4]), int(filename[4:6]), int(filename[6:8]))
    except (ValueError, IndexError):
        return None


def run_folder(data_root: Path, year: int, month: int) -> Path:
    return data_root / str(year) / f"{year}-{month:02d}"


def list_run_folders(data_root: Path, year: int) -> List[Path]:
    year_dir = data_root / str(year)
    if not year_dir.exists():
        return []
    folders = [
        p for p in year_dir.iterdir()
        if p.is_dir() and p.name.startswith(f"{year}-") and len(p.name) == 7
    ]
    return sorted(folders, key=lambda p: p.name, reverse=True)


def _find_in_folder(folder: Path, file_type: str, at_or_before: date) -> Optional[Path]:
    if not folder.exists():
        return None
    candidates = []
    for p in (
        list(folder.glob(f"*-{file_type}-*.csv"))
        + list(folder.glob(f"*-{file_type}.csv"))
    ):
        d = parse_date_prefix(p.name)
        if d is not None and d <= at_or_before:
            candidates.append((d, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def find_with_fallback(
    data_root: Path,
    current_run: Path,
    year: int,
    file_type: str,
    at_or_before: date,
) -> Path:
    result = _find_in_folder(current_run, file_type, at_or_before)
    if result is not None:
        return result

    for folder in list_run_folders(data_root, year):
        if folder == current_run:
            continue
        result = _find_in_folder(folder, file_type, at_or_before)
        if result is not None:
            return result

    for folder in list_run_folders(data_root, year - 1):
        result = _find_in_folder(folder, file_type, at_or_before)
        if result is not None:
            return result

    raise BillingError(f"Tiedostoa tyyppiä '{file_type}' ei löydy")


def find_all_yleiset(
    data_root: Path,
    current_run: Path,
    year: int,
) -> List[Path]:
    result: List[Path] = []
    all_folders = [current_run] + [
        f for f in list_run_folders(data_root, year) if f != current_run
    ] + list_run_folders(data_root, year - 1)

    for folder in all_folders:
        if not folder.exists():
            continue
        candidates = []
        for p in (
            list(folder.glob("*-yleiset-*.csv"))
            + list(folder.glob("*-yleiset.csv"))
        ):
            d = parse_date_prefix(p.name)
            if d is not None:
                candidates.append((d, p))
        candidates.sort(key=lambda x: x[0], reverse=True)
        result.extend(p for _, p in candidates)
    return result


def find_all_laskut(data_root: Path) -> List[Path]:
    result: List[Path] = []
    if not data_root.exists():
        return result
    for year_dir in data_root.iterdir():
        if not year_dir.is_dir():
            continue
        for run_dir in year_dir.iterdir():
            if not run_dir.is_dir():
                continue
            result.extend(run_dir.glob("*-laskut-*.csv"))
            result.extend(run_dir.glob("*-laskut.csv"))
    return result


def find_previous_lukemats(
    data_root: Path,
    current_year: int,
    current_month: int,
    before_date: date,
) -> List[Path]:
    result: List[Path] = []

    all_folders = list_run_folders(data_root, current_year) + list_run_folders(
        data_root, current_year - 1
    )

    for folder in all_folders:
        candidates = []
        for p in (
            list(folder.glob("*-lukemat-*.csv"))
            + list(folder.glob("*-lukemat.csv"))
        ):
            d = parse_date_prefix(p.name)
            if d is not None and d < before_date:
                candidates.append((d, p))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            result.append(candidates[0][1])
        if len(result) == 2:
            break

    if not result:
        raise BillingError("Ei aikaisempia lukematietoja löydy")
    return result


def output_path(
    run_dir: Path,
    cycle_end_date: date,
    file_type: str,
    note: str,
    extension: str,
) -> Path:
    if note:
        filename = f"{cycle_end_date.strftime('%Y%m%d')}-{file_type}-{note}.{extension}"
    else:
        filename = f"{cycle_end_date.strftime('%Y%m%d')}-{file_type}.{extension}"
    return run_dir / filename
