from __future__ import annotations

import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional

import typer

from water_billing.config import AppConfig, require_smtp_config
from water_billing.domain.models import BillLine, BillingSummary, MeterReading
from water_billing.domain.rules import ApplicationRule, BillingError
from water_billing.io.csv_readers import (
    read_bill_lines,
    read_customers,
    read_general_info,
    read_meter_readings,
)
from water_billing.io.csv_writers import write_bill_lines, write_bills
from water_billing.io.file_discovery import (
    find_all_laskut,
    find_all_yleiset,
    find_previous_lukemats,
    find_with_fallback,
    output_path,
    parse_date_prefix,
)
from water_billing.pdf.bill_renderer import format_amount_fi, format_date_fi, render_bill_pdf
from water_billing.pdf.merger import merge_pdfs
from water_billing.pdf.summary_renderer import render_summary_pdf
from water_billing.services.billing import (
    compute_consumptions,
    compute_main_meter_consumption,
    detect_ownership_transfers,
    generate_bills,
    get_next_bill_number,
    next_billing_period,
    split_bills_for_transfer,
)
from water_billing.services.email import email_bill_pdf_paths, send_all_bills, send_summary_email, sort_bill_pdfs_for_print
from water_billing.services.validation import validate_inputs

_YLEISET_KEY_ORDER = [
    "jakso_alkaa", "jakso_loppuu", "laskupäivä",
    "osuuskunnan_nimi", "iban", "bic", "osoite", "www", "y_tunnus",
    "yhteyshenkilö", "puhelin", "sähköposti", "päämittarinro",
    "rahastonhoitajan_sähköposti", "päämittarin_kulutuspiste",
    "päämittarin_perusmaksu", "vesihinta", "aloituslaskunumero",
]
_OPTIONAL_YLEISET_KEYS = {
    "laskupäivä", "bic", "osoite", "www", "päämittarin_kulutuspiste",
    "päämittarin_perusmaksu", "vesihinta", "aloituslaskunumero",
}
_REQUIRED_YLEISET_KEYS = [k for k in _YLEISET_KEY_ORDER if k not in _OPTIONAL_YLEISET_KEYS]
_PERIOD_KEYS = {"jakso_alkaa", "jakso_loppuu"}
# jakso_alkaa/jakso_loppuu are always recomputed fresh for each new cycle
# (see run_cycle_wizard), so they are excluded from the "other settings
# unchanged?" check below.
_OTHER_REQUIRED_KEYS = [k for k in _REQUIRED_YLEISET_KEYS if k not in _PERIOD_KEYS]

_OSAKKAAT_HEADER = (
    "nimi,katuosoite,postinumero,postitoimipaikka,sähköposti,puhelin,"
    "kiinteistötunnus,henkilömäärä,liittynyt,lähtenyt,kulutuspiste,"
    "mittarinro,laskutustapa,tilinumero"
)


def _write_yleiset(run_dir: Path, values: dict, cycle_start_date: date) -> Path:
    filename = f"{cycle_start_date.strftime('%Y%m%d')}-yleiset.csv"
    out = run_dir / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["avain", "arvo"])
        for k, v in values.items():
            writer.writerow([k, v])
    return out


def _write_lukemat_file(run_dir: Path, readings: List[MeterReading], filename: str) -> Path:
    out = run_dir / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["nimi", "päivämäärä", "lukema"])
        for r in readings:
            writer.writerow([r.customer_name, r.reading_date.isoformat(), r.reading])
    return out


def _write_laskurivit(run_dir: Path, cycle_end_date: date, lines: List[BillLine]) -> Path:
    out = output_path(run_dir, cycle_end_date, "laskurivit", "", "csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    write_bill_lines(out, lines, overwrite=True)
    return out


def _prompt_yleiset_key(key: str, jakso_alkaa_default: str, jakso_loppuu_default: str) -> Optional[str]:
    """Prompt user for a single yleiset key value. Returns the value or None if optional and skipped."""
    today_iso = date.today().isoformat()

    if key == "jakso_alkaa":
        val = typer.prompt(f"  Jakso alkaa (oletus: {jakso_alkaa_default})", default="")
        return val.strip() if val.strip() else jakso_alkaa_default
    elif key == "jakso_loppuu":
        val = typer.prompt(f"  Jakso loppuu (oletus: {jakso_loppuu_default})", default="")
        return val.strip() if val.strip() else jakso_loppuu_default
    elif key == "laskupäivä":
        val = typer.prompt(f"  Laskupäivä (oletus: tänään {today_iso})", default="")
        bill_date_str = val.strip() if val.strip() else today_iso
        due = date.fromisoformat(bill_date_str) + timedelta(days=14)
        typer.echo(f"  Eräpäivä: {due.strftime('%d.%m.%Y')}")
        return bill_date_str
    elif key == "bic":
        val = typer.prompt(
            "  Pankin BIC/SWIFT-koodi (valinnainen, tyhjä = ei määritelty)", default=""
        )
        return val.strip() if val.strip() else None
    elif key == "osoite":
        val = typer.prompt(
            "  Osuuskunnan osoite (valinnainen, näytetään laskun alatunnisteessa, tyhjä = ei määritelty)",
            default="",
        )
        return val.strip() if val.strip() else None
    elif key == "www":
        val = typer.prompt(
            "  Osuuskunnan www-osoite (valinnainen, näytetään laskun alatunnisteessa tilinumeron jälkeen, tyhjä = ei määritelty)",
            default="",
        )
        return val.strip() if val.strip() else None
    elif key == "päämittarin_kulutuspiste":
        val = typer.prompt(
            "  Päämittarin kulutuspiste (valinnainen, tyhjä = ei määritelty)", default=""
        )
        return val.strip() if val.strip() else None
    elif key == "päämittarin_perusmaksu":
        val = typer.prompt(
            "  Päämittarin perusmaksu yhteensä (€ alv 0%, valinnainen, tyhjä = ei määritelty)",
            default="",
        )
        if val.strip():
            try:
                Decimal(val.strip())
                return val.strip()
            except InvalidOperation:
                typer.echo("  Varoitus: virheellinen desimaaliluku, ohitetaan.")
        return None
    elif key == "vesihinta":
        val = typer.prompt(
            "  Vesihinta (€/m³ alv 0%, valinnainen, tyhjä = ei määritelty)", default=""
        )
        if val.strip():
            try:
                Decimal(val.strip())
                return val.strip()
            except InvalidOperation:
                typer.echo("  Varoitus: virheellinen desimaaliluku, ohitetaan.")
        return None
    elif key == "aloituslaskunumero":
        val = typer.prompt(
            "  Aloituslaskunumero (valinnainen, tyhjä = käytä automaattista numerointia)",
            default="",
        )
        if val.strip():
            try:
                n = int(val.strip())
                if n > 0:
                    return str(n)
                typer.echo("  Varoitus: aloituslaskunumeron on oltava positiivinen kokonaisluku, ohitetaan.")
            except ValueError:
                typer.echo("  Varoitus: virheellinen kokonaisluku, ohitetaan.")
        return None
    else:
        val = ""
        while not val.strip():
            val = typer.prompt(f"  Anna arvo avaimelle {key}")
        return val.strip()


def run_cycle_wizard(
    config: AppConfig,
    run_dir: Path,
    year: int,
    month: int,
) -> None:
    root = config.data_root
    typer.echo(f"\n=== Laskutusohjaaja: {year}-{month:02d} ===\n")

    # Phase 1 — yleiset
    typer.echo("--- Vaihe 1: Yleiset asetukset ---")
    is_resume = run_dir.exists() and (
        any(run_dir.glob("*-yleiset-*.csv")) or any(run_dir.glob("*-yleiset.csv"))
    )
    yleiset_paths = find_all_yleiset(root, run_dir, year)
    resolved: dict = {}
    for path in yleiset_paths:
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                for row in csv.DictReader(f):
                    k = row.get("avain", "").strip()
                    v = row.get("arvo", "").strip()
                    if k and k not in resolved:
                        resolved[k] = v
        except Exception:
            pass

    if is_resume:
        # This period's own yleiset already exists (resuming an in-progress
        # cycle) — keep its jakso_alkaa/jakso_loppuu like any other setting.
        jakso_alkaa_default = resolved.get("jakso_alkaa", "")
        jakso_loppuu_default = resolved.get("jakso_loppuu", "")
        other_required_keys = _REQUIRED_YLEISET_KEYS
    else:
        # jakso_alkaa/jakso_loppuu/laskupäivä in `resolved` describe the
        # *previous* cycle (each yleiset file is a full snapshot of its own
        # period). They must never be silently carried over unchanged into
        # a new cycle, so they are pulled out here and always recomputed
        # fresh (laskupäivä defaults to today via _prompt_yleiset_key).
        prev_jakso_loppuu = resolved.pop("jakso_loppuu", None)
        resolved.pop("jakso_alkaa", None)
        resolved.pop("laskupäivä", None)

        if prev_jakso_loppuu:
            next_start, next_end = next_billing_period(date.fromisoformat(prev_jakso_loppuu))
            jakso_alkaa_default = next_start.isoformat()
            jakso_loppuu_default = next_end.isoformat()
        elif month == 1:
            jakso_alkaa_default = date(year - 1, 12, 1).isoformat()
            jakso_loppuu_default = date(
                year, month, calendar.monthrange(year, month)[1]
            ).isoformat()
        else:
            jakso_alkaa_default = date(year, month - 1, 1).isoformat()
            jakso_loppuu_default = date(
                year, month, calendar.monthrange(year, month)[1]
            ).isoformat()
        other_required_keys = _OTHER_REQUIRED_KEYS

    typer.echo(f"Laskutusjakso: {jakso_alkaa_default} – {jakso_loppuu_default}\n")

    # Display resolved values
    if resolved:
        typer.echo("Nykyiset yleiset-asetukset:")
        for key in _YLEISET_KEY_ORDER:
            if key in resolved:
                display_val = resolved[key]
                if key in ("päämittarin_perusmaksu", "vesihinta"):
                    display_val += " (alv 0%)"
                typer.echo(f"  {key}: {display_val}")
        typer.echo("")

    # Ask about changes
    all_required_present = all(k in resolved for k in other_required_keys)
    if resolved and all_required_present:
        wants_changes = typer.confirm(
            "Haluatko muuttaa joitain yleiset-asetuksia?", default=False
        )
    else:
        wants_changes = True

    updated: dict = dict(resolved)
    changed = False

    # Change loop — only runs if wants_changes, only for keys that already have values
    if wants_changes:
        for key in _YLEISET_KEY_ORDER:
            if key not in resolved:
                continue
            current_val = resolved[key]
            display_val = current_val
            if key in ("päämittarin_perusmaksu", "vesihinta"):
                display_val += " (alv 0%)"
            new_val = typer.prompt(
                f"  {key} (nykyinen: {display_val!r}, tyhjä = pidä)",
                default="",
            )
            if new_val.strip():
                updated[key] = new_val.strip()
                changed = True
                if key == "laskupäivä":
                    due = date.fromisoformat(new_val.strip()) + timedelta(days=14)
                    typer.echo(f"  Eräpäivä: {due.strftime('%d.%m.%Y')}")

    # Missing-key loop — always runs, for keys absent from the (possibly updated) dict
    for key in _YLEISET_KEY_ORDER:
        if key in updated:
            continue
        if key in _OPTIONAL_YLEISET_KEYS:
            result = _prompt_yleiset_key(key, jakso_alkaa_default, jakso_loppuu_default)
            if result is not None:
                updated[key] = result
                changed = True
        else:
            result = _prompt_yleiset_key(key, jakso_alkaa_default, jakso_loppuu_default)
            if result is not None:
                updated[key] = result
            changed = True

    # Remove optional keys with empty/None values
    for opt_key in _OPTIONAL_YLEISET_KEYS:
        if opt_key in updated and not updated[opt_key]:
            del updated[opt_key]

    cycle_start_date = date.fromisoformat(updated["jakso_alkaa"])
    cycle_end_date = date.fromisoformat(updated["jakso_loppuu"])

    if changed:
        out = _write_yleiset(run_dir, updated, cycle_start_date)
        typer.echo(f"Yleiset-asetukset tallennettu: {out.name}")
    else:
        typer.echo("Yleiset-asetukset muuttumattomia, ei uutta tiedostoa.")

    general_info = read_general_info(find_all_yleiset(root, run_dir, year))
    cycle = general_info.billing_cycle

    # Phase 2 — osakkaat
    typer.echo("\n--- Vaihe 2: Osakkaat ---")
    osakkaat_path: Optional[Path] = None
    try:
        osakkaat_path = find_with_fallback(root, run_dir, year, "osakkaat", cycle.end_date)
    except BillingError:
        pass

    if osakkaat_path is None:
        placeholder = run_dir / f"{cycle.start_date.strftime('%Y%m%d')}-osakkaat.csv"
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        with open(placeholder, "w", encoding="utf-8-sig", newline="") as f:
            f.write(_OSAKKAAT_HEADER + "\n")
        typer.echo(
            f"Osakkaat-tiedosto luotu: {placeholder}. "
            "Täytä asiakastiedot tiedostoon ja käynnistä 'uusi' uudelleen."
        )
        return

    typer.echo(f"Osakkaat: {osakkaat_path.name}")
    if typer.confirm("Onko osakkaat-tiedostossa muutoksia?", default=False):
        typer.echo("Päivitä tiedosto ja käynnistä 'uusi' uudelleen.")
        return

    customers = read_customers(osakkaat_path)
    active = [c for c in customers if c.is_active()]
    typer.echo(f"  {len(active)} aktiivista osakasta.")

    # Phase 3 — lukemat
    typer.echo("\n--- Vaihe 3: Mittarilukemat ---")

    prev_lukemat_paths: List[Path] = []
    try:
        prev_lukemat_paths = find_previous_lukemats(root, year, month, cycle.start_date)
    except BillingError:
        pass

    today = date.today()
    prev_readings: List[MeterReading] = []
    prev_prev_readings: List[MeterReading] = []

    # First-run seed phase
    if not prev_lukemat_paths:
        typer.echo(
            "Ensimmäinen laskutusjakso havaittu. "
            "Syötä alkutilanteen mittarilukemat ennen nykyjakson lukemia."
        )
        seed_date = cycle_start_date - timedelta(days=1)
        seed_collected: List[MeterReading] = []
        for c in active:
            val = typer.prompt(f"  Alkutilanne – {c.name} (m³)", default="")
            if val.strip():
                try:
                    seed_collected.append(
                        MeterReading(
                            customer_name=c.name,
                            reading_date=seed_date,
                            reading=int(val.strip()),
                        )
                    )
                except ValueError:
                    typer.echo(f"  Varoitus: ei kelvollinen lukema '{val}', ohitetaan.")
        seed_main = typer.prompt("  Päämittarin alkutilanne (m³)", default="")
        if seed_main.strip():
            try:
                seed_collected.append(
                    MeterReading(
                        customer_name="päämittari",
                        reading_date=seed_date,
                        reading=int(seed_main.strip()),
                    )
                )
            except ValueError:
                typer.echo("  Varoitus: ei kelvollinen päämittarin lukema, ohitetaan.")
        else:
            typer.echo("Varoitus: päämittarin alkutilanne puuttuu.", err=True)

        seed_filename = f"{seed_date.strftime('%Y%m%d')}-lukemat-alkutilanne.csv"
        seed_path = _write_lukemat_file(run_dir, seed_collected, seed_filename)
        typer.echo(f"Alkutilanne tallennettu: {seed_path.name}")
        prev_readings = seed_collected

    # Check for existing current-period lukemat (exclude seed files)
    existing_lukemat_path: Optional[Path] = None
    candidates = [
        p for p in (
            list(run_dir.glob("*-lukemat-*.csv"))
            + list(run_dir.glob("*-lukemat.csv"))
        )
        if "-alkutilanne" not in p.name
    ]
    if candidates:
        candidates.sort(key=lambda p: (parse_date_prefix(p.name) or date.min), reverse=True)
        existing_lukemat_path = candidates[0]

    if existing_lukemat_path is not None:
        existing_readings = read_meter_readings(existing_lukemat_path)
        existing_by_name = {r.customer_name: r.reading for r in existing_readings}

        typer.echo(f"\nOlemassa olevat lukemat ({existing_lukemat_path.name}):")
        for c in active:
            val = existing_by_name.get(c.name, "–")
            typer.echo(f"  {c.name}: {val} m³")
        main_val = existing_by_name.get("päämittari", "–")
        typer.echo(f"  Päämittari: {main_val} m³")

        wants_reading_changes = typer.confirm(
            "Haluatko muuttaa mittarilukemia?", default=False
        )
        if not wants_reading_changes:
            meter_readings = existing_readings
        else:
            collected: List[MeterReading] = []
            for c in active:
                current_r = existing_by_name.get(c.name)
                hint = f"nykyinen: {current_r}" if current_r is not None else "ei lukemaa"
                val = typer.prompt(f"  Lukema – {c.name} (m³) [{hint}]:", default="")
                if val.strip():
                    try:
                        collected.append(
                            MeterReading(
                                customer_name=c.name,
                                reading_date=today,
                                reading=int(val.strip()),
                            )
                        )
                    except ValueError:
                        typer.echo(f"  Varoitus: ei kelvollinen lukema '{val}', ohitetaan.")
                elif current_r is not None:
                    # Keep existing reading date from existing file
                    orig = next(r for r in existing_readings if r.customer_name == c.name)
                    collected.append(orig)

            current_main = existing_by_name.get("päämittari")
            hint = f"nykyinen: {current_main}" if current_main is not None else "ei lukemaa"
            main_val_input = typer.prompt(f"  Päämittarin lukema (m³) [{hint}]:", default="")
            if main_val_input.strip():
                try:
                    collected.append(
                        MeterReading(
                            customer_name="päämittari",
                            reading_date=today,
                            reading=int(main_val_input.strip()),
                        )
                    )
                except ValueError:
                    typer.echo("  Varoitus: ei kelvollinen päämittarin lukema, ohitetaan.")
            elif current_main is not None:
                orig = next(
                    (r for r in existing_readings if r.customer_name == "päämittari"), None
                )
                if orig:
                    collected.append(orig)
            else:
                typer.echo(
                    "Varoitus: päämittarin lukema puuttuu — vesihäviö jää laskematta yhteenvedossa.",
                    err=True,
                )

            lukemat_filename = f"{today.strftime('%Y%m%d')}-lukemat.csv"
            lukemat_path = _write_lukemat_file(run_dir, collected, lukemat_filename)
            typer.echo(f"Lukemat päivitetty: {lukemat_path.name}")
            meter_readings = collected
    else:
        typer.echo("Syötä mittarilukemat. Paina Enter ohittaaksesi asiakkaan (ei lukemaa tällä jaksolla).")
        collected = []
        for c in active:
            val = typer.prompt(f"  Lukema – {c.name} (m³)", default="")
            if val.strip():
                try:
                    collected.append(
                        MeterReading(
                            customer_name=c.name,
                            reading_date=today,
                            reading=int(val.strip()),
                        )
                    )
                except ValueError:
                    typer.echo(f"  Varoitus: ei kelvollinen lukema '{val}', ohitetaan.")

        main_input = typer.prompt("  Päämittarin lukema (m³)", default="")
        if main_input.strip():
            try:
                collected.append(
                    MeterReading(
                        customer_name="päämittari",
                        reading_date=today,
                        reading=int(main_input.strip()),
                    )
                )
            except ValueError:
                typer.echo("  Varoitus: ei kelvollinen päämittarin lukema, ohitetaan.")
        else:
            typer.echo(
                "Varoitus: päämittarin lukema puuttuu — vesihäviö jää laskematta yhteenvedossa.",
                err=True,
            )

        lukemat_filename = f"{cycle_end_date.strftime('%Y%m%d')}-lukemat.csv"
        lukemat_path = _write_lukemat_file(run_dir, collected, lukemat_filename)
        typer.echo(f"Lukemat tallennettu: {lukemat_path.name}")
        meter_readings = collected

    if prev_lukemat_paths:
        prev_readings = read_meter_readings(prev_lukemat_paths[0])
        prev_prev_readings = (
            read_meter_readings(prev_lukemat_paths[1])
            if len(prev_lukemat_paths) > 1
            else []
        )

    # Phase 4 — laskurivit
    typer.echo("\n--- Vaihe 4: Laskurivit ---")
    laskurivit_path: Optional[Path] = None
    try:
        laskurivit_path = find_with_fallback(root, run_dir, year, "laskurivit", cycle.end_date)
    except BillingError:
        pass

    bill_lines_list: List[BillLine] = []
    bill_lines_changed = False
    ci = general_info.contact_info

    if laskurivit_path is None:
        cycle_months = (
            (cycle_end_date.year * 12 + cycle_end_date.month)
            - (cycle_start_date.year * 12 + cycle_start_date.month)
            + 1
        )

        # Perusmaksu — user provides monthly fee; wizard multiplies by cycle_months
        if ci.main_meter_basic_fee is not None:
            typer.echo(
                f"  Päämittarin perusmaksu yleiset-tiedostosta: "
                f"{ci.main_meter_basic_fee} € (alv 0%, per kuukausi)"
            )
            perusmaksu_monthly_val = typer.prompt(
                "  Muuta? (tyhjä = käytä yleiset-arvoa)", default=""
            )
            monthly_fee = (
                Decimal(perusmaksu_monthly_val.strip())
                if perusmaksu_monthly_val.strip()
                else ci.main_meter_basic_fee
            )
        else:
            monthly_fee_str = ""
            while not monthly_fee_str.strip():
                monthly_fee_str = typer.prompt(
                    "  Päämittarin perusmaksu yhteensä (€ alv 0%, per kuukausi)"
                )
            monthly_fee = Decimal(monthly_fee_str.strip())

        perusmaksu_summa = monthly_fee * cycle_months
        typer.echo(
            f"  Perusmaksun laskutusjakson summa: {perusmaksu_summa} € ({cycle_months} kk)"
        )
        alv_perusmaksu_str = typer.prompt("  ALV-% (perusmaksu)")

        # Vesimaksu
        if ci.water_price is not None:
            typer.echo(f"  Vesihinta yleiset-tiedostosta: {ci.water_price} €/m³ (alv 0%)")
            vesimaksu_val = typer.prompt(
                "  Muuta? (tyhjä = käytä yleiset-arvoa)", default=""
            )
            water_price = (
                Decimal(vesimaksu_val.strip())
                if vesimaksu_val.strip()
                else ci.water_price
            )
        else:
            vesimaksu_str = ""
            while not vesimaksu_str.strip():
                vesimaksu_str = typer.prompt("  Vesimaksu (€/m³ alv 0%)")
            water_price = Decimal(vesimaksu_str.strip())

        alv_vesimaksu_str = typer.prompt("  ALV-% (vesimaksu)")

        bill_lines_list = [
            BillLine(
                title="Perusmaksu",
                count=Decimal(cycle_months),
                unit="kk",
                unit_price=monthly_fee,
                vat_percent=Decimal(alv_perusmaksu_str.strip()),
                application_rule=ApplicationRule.PER_ACTIVE_CUSTOMER,
            ),
            BillLine(
                title="Vesimaksu",
                count=Decimal("1"),
                unit="m³",
                unit_price=water_price,
                vat_percent=Decimal(alv_vesimaksu_str.strip()),
                application_rule=ApplicationRule.PER_CONSUMPTION,
            ),
        ]
        bill_lines_changed = True
    else:
        bill_lines_list = read_bill_lines(laskurivit_path)
        typer.echo("Nykyiset laskurivit:")
        for bl in bill_lines_list:
            typer.echo(
                f"  {bl.title}: {bl.count} {bl.unit} × {bl.unit_price} €/kpl, "
                f"ALV {bl.vat_percent}%, {bl.application_rule.value}"
            )

    # Additional expenses loop (runs in both found and not-found cases)
    valid_values = (
        ApplicationRule.PER_ACTIVE_CUSTOMER.value,
        ApplicationRule.PER_ALL_CUSTOMERS.value,
        ApplicationRule.PER_CONSUMPTION.value,
    )
    initial_count = len(bill_lines_list)
    while typer.confirm("Lisätäänkö lisäkustannusrivi (esim. yhteiskulut)?", default=False):
        nimike = typer.prompt("  Nimike")
        maara_str = typer.prompt("  Määrä")
        yksikko = typer.prompt("  Yksikkö")
        ahinta_str = typer.prompt("  À-hinta (€)")
        alv_pct_str = typer.prompt("  ALV-%")
        soveltamistapa = ""
        while soveltamistapa not in valid_values:
            soveltamistapa = typer.prompt("  Soveltamistapa (aktiiviset/kaikki/kulutus)")
            if soveltamistapa not in valid_values:
                typer.echo(
                    f"  Virhe: soveltamistapa on oltava yksi arvoista: "
                    f"{', '.join(valid_values)}"
                )
        bill_lines_list.append(
            BillLine(
                title=nimike,
                count=Decimal(maara_str.strip()),
                unit=yksikko,
                unit_price=Decimal(ahinta_str.strip()),
                vat_percent=Decimal(alv_pct_str.strip()),
                application_rule=ApplicationRule(soveltamistapa),
            )
        )
        typer.echo("  Rivi lisätty.")

    if bill_lines_changed or len(bill_lines_list) > initial_count:
        laskurivit_path = _write_laskurivit(run_dir, cycle_end_date, bill_lines_list)
        typer.echo(f"Laskurivit tallennettu: {laskurivit_path.name}")

    bill_lines = bill_lines_list

    # Phase 5 — generate laskut and review
    typer.echo("\n--- Vaihe 5: Laskujen laskenta ---")

    warnings = validate_inputs(
        customers, bill_lines, general_info, meter_readings, prev_readings, prev_prev_readings
    )
    for w in warnings:
        typer.echo(w)

    transfers = detect_ownership_transfers(meter_readings, customers)
    transferred_names = {n for t in transfers for n in (t.prev_owner_name, t.new_owner_name)}
    regular_customers = [c for c in customers if c.name not in transferred_names]

    consumptions = compute_consumptions(
        regular_customers, meter_readings, prev_readings, prev_prev_readings, cycle.end_date
    )
    all_laskut = find_all_laskut(root)
    start_number = get_next_bill_number(all_laskut, general_info.contact_info.initial_bill_number)
    bills = list(generate_bills(regular_customers, consumptions, bill_lines, cycle, start_number))

    next_number = start_number + len(bills)
    for transfer in transfers:
        prev_bill, new_bill = split_bills_for_transfer(
            transfer, cycle, bill_lines, customers, next_number
        )
        bills.extend([prev_bill, new_bill])
        next_number += 2

    typer.echo(
        f"\n{'Nimi':<30} {'m³':>6} {'Perus':>8} {'Vesi':>8} {'Yhteisk':>8} {'Yhteensä':>10}"
    )
    typer.echo("-" * 74)
    for b in sorted(bills, key=lambda x: x.customer_name):
        est = " (arvio)" if b.is_estimated else ""
        typer.echo(
            f"{b.customer_name:<30} {b.consumption:>6}{est}"
            f" {format_amount_fi(b.basic_fee_share):>8}"
            f" {format_amount_fi(b.water_cost):>8}"
            f" {format_amount_fi(b.shared_expense_share):>8}"
            f" {format_amount_fi(b.total_due):>10}"
        )
    total = sum(b.total_due for b in bills)
    typer.echo(f"\nLaskuja: {len(bills)}, yhteensä: {format_amount_fi(total)}")

    laskut_out = output_path(run_dir, cycle.end_date, "laskut", "", "csv")
    write_bills(laskut_out, bills, overwrite=True)
    typer.echo(f"Laskut kirjoitettu: {laskut_out.name}")

    if not typer.confirm("\nOvatko laskut oikein?", default=True):
        typer.echo("Tarkista syöttötiedot ja käynnistä 'uusi' uudelleen.")
        return

    # Phase 6 — generate PDFs
    typer.echo("\n--- Vaihe 6: PDF-laskujen luonti ---")
    customer_by_name = {c.name: c for c in customers}
    pdf_count = 0
    for bill in bills:
        customer = customer_by_name.get(bill.customer_name)
        if customer is None:
            continue
        name_parts = bill.customer_name.split()
        if len(name_parts) >= 2:
            note = f"{name_parts[-1].lower()}-{name_parts[0].lower()}"
        else:
            note = bill.customer_name.lower().replace(" ", "-")
        pdf_out = output_path(run_dir, cycle.end_date, "lasku", note, "pdf")
        render_bill_pdf(bill, general_info, customer, pdf_out)
        pdf_count += 1

    customer_total = sum(b.consumption for b in bills)
    prev_path_for_main = prev_lukemat_paths[0] if prev_lukemat_paths else None
    main_consumption = compute_main_meter_consumption(meter_readings, prev_path_for_main)

    water_loss_m3: Optional[int] = None
    water_loss_pct = None
    if main_consumption is not None:
        water_loss_m3 = main_consumption - customer_total
        if main_consumption > 0:
            water_loss_pct = Decimal(water_loss_m3) / Decimal(main_consumption) * 100

    summary = BillingSummary(
        bills=bills,
        main_meter_consumption=main_consumption,
        customer_consumption_total=customer_total,
        water_loss_m3=water_loss_m3,
        water_loss_percent=water_loss_pct,
        billing_cycle=cycle,
        contact_info=general_info.contact_info,
    )
    summary_out = run_dir / f"{cycle.end_date.strftime('%Y%m%d')}-yhteenveto.pdf"
    render_summary_pdf(summary, summary_out)

    typer.echo(f"PDF-laskut generoitu: {pdf_count} laskua + yhteenveto.")
    typer.echo(f"Hakemisto: {run_dir}")

    if not typer.confirm("\nJulkaistaanko laskut nyt?", default=True):
        typer.echo("Laskut on tallennettu. Julkaise myöhemmin komennolla 'julkaise'.")
        return

    # Phase 7 — publish
    typer.echo("\n--- Vaihe 7: Julkaisu ---")
    try:
        require_smtp_config(config)
    except BillingError as exc:
        typer.echo(f"SMTP-virhe: {exc.message}", err=True)
        return

    paper_out = run_dir / f"{cycle.end_date.strftime('%Y%m%d')}-paperilaskut.pdf"
    emailed = email_bill_pdf_paths(bills, customers, run_dir, cycle.end_date)
    paper_pdfs = sort_bill_pdfs_for_print(
        [p for p in run_dir.glob(f"{cycle.end_date.strftime('%Y%m%d')}-lasku-*.pdf")
         if p not in emailed],
        bills, customers, run_dir, cycle.end_date,
    )
    if paper_pdfs:
        merge_pdfs(paper_pdfs, paper_out)
        typer.echo(f"Paperilaskut: {paper_out.name}")

    succeeded, failed = send_all_bills(config, bills, customers, run_dir, general_info)
    typer.echo(f"Sähköpostit lähetetty: {len(succeeded)}")
    if failed:
        typer.echo(f"Epäonnistuneet: {', '.join(failed)}", err=True)

    send_summary_email(config, summary_out, summary)
    recipient = general_info.contact_info.treasurer_email or config.treasurer_email
    typer.echo(f"Yhteenveto lähetetty: {recipient}")
    typer.echo("\nLaskutuskierto valmis.")
