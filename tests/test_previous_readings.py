from datetime import date

import pytest

from water_billing.domain.rules import BillingError
from water_billing.services.billing import find_previous_readings

_LASKUT_HEADER = (
    "laskunumero,nimi,mittarinro,ed_lukema,ed_lukema_pvm,uusi_lukema,uusi_lukema_pvm,"
    "kulutus,arvio,perusmaksu_osuus,vesimaksu,yhteiskustannukset,yhteensä,viitenumero\n"
)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_estimated_reading_from_previous_bill_is_used(tmp_path):
    june = tmp_path / "2026" / "2026-06"
    august = tmp_path / "2026" / "2026-08"
    _write(june / "20260630-lukemat.csv",
           "nimi,päivämäärä,lukema\nRead,2026-06-30,100\nEstimated,2026-06-30,500\n"
           "päämittari,2026-06-30,9000\n")
    # In August only "Read" and the main meter were read; "Estimated" was billed
    # up to an estimated reading that exists only in the laskut file.
    _write(august / "20260831-lukemat.csv",
           "nimi,päivämäärä,lukema\nRead,2026-09-16,120\npäämittari,2026-09-16,9100\n")
    _write(august / "20260831-laskut.csv", _LASKUT_HEADER
           + "1,Read,M1,100,2026-06-30,120,2026-09-16,20,ei,1,1,0,2,1\n"
           + "2,Estimated,M2,500,2026-06-30,530,2026-08-31,30,kyllä,1,1,0,2,2\n")

    prev, prev_prev = find_previous_readings(tmp_path, 2026, date(2026, 9, 1))
    prev_by = {r.customer_name: (r.reading_date, r.reading) for r in prev}
    prev_prev_by = {r.customer_name: (r.reading_date, r.reading) for r in prev_prev}

    assert prev_by["Read"] == (date(2026, 9, 16), 120)
    assert prev_by["Estimated"] == (date(2026, 8, 31), 530)
    assert prev_by["päämittari"] == (date(2026, 9, 16), 9100)
    assert prev_prev_by["Read"] == (date(2026, 6, 30), 100)
    assert prev_prev_by["Estimated"] == (date(2026, 6, 30), 500)


def test_current_cycle_files_are_ignored(tmp_path):
    october = tmp_path / "2026" / "2026-10"
    _write(tmp_path / "2026" / "2026-08" / "20260831-lukemat.csv",
           "nimi,päivämäärä,lukema\nA,2026-08-31,10\n")
    _write(october / "20261031-lukemat.csv", "nimi,päivämäärä,lukema\nA,2026-10-31,20\n")
    _write(october / "20261031-laskut.csv", _LASKUT_HEADER
           + "3,A,M1,10,2026-08-31,20,2026-10-31,10,ei,1,1,0,2,3\n")

    prev, _ = find_previous_readings(tmp_path, 2026, date(2026, 9, 1))
    assert [(r.customer_name, r.reading) for r in prev] == [("A", 10)]


def test_no_history_raises(tmp_path):
    with pytest.raises(BillingError):
        find_previous_readings(tmp_path, 2026, date(2026, 9, 1))
