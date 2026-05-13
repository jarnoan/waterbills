from pathlib import Path
from typing import List

from pypdf import PdfWriter


def merge_pdfs(input_paths: List[Path], output_path: Path) -> None:
    writer = PdfWriter()
    for p in input_paths:
        writer.append(str(p))
    with open(output_path, "wb") as f:
        writer.write(f)


def sort_bill_pdfs_alphabetically(pdf_paths: List[Path]) -> List[Path]:
    def _key(p: Path):
        parts = p.stem.split("-")
        if len(parts) >= 4:
            return (parts[3], parts[2])
        return (p.stem, "")

    return sorted(pdf_paths, key=_key)
