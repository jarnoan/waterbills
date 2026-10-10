from __future__ import annotations

import dataclasses
import sys
import traceback
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

import typer

from water_billing.config import load_config, require_smtp_config
from water_billing.domain.models import BillLineItem, BillingSummary
from water_billing.domain.rules import ApplicationRule, BillingError, distribute_bill_line
from water_billing.io.csv_readers import (
    read_bill_lines,
    read_bills,
    read_customers,
    read_general_info,
    read_meter_readings,
)
from water_billing.io.csv_writers import write_bills
from water_billing.io.file_discovery import (
    find_all_laskut,
    find_all_yleiset,
    find_previous_lukemats,
    find_with_fallback,
    output_path,
    run_folder,
)
from water_billing.pdf.bill_renderer import render_bill_pdf
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
from water_billing.services.portal import fetch_portal_readings
from water_billing.services.email import email_bill_pdf_paths, send_all_bills, send_summary_email, sort_bill_pdfs_for_print
from water_billing.services.validation import validate_inputs

app = typer.Typer(name="laskutus", help="Vesiosuuskunnan laskutustyökalu")


def _handle_unexpected(exc: Exception) -> None:
    typer.echo(
        "Odottamaton virhe. Ole hyvä ja ota yhteyttä järjestelmänvalvojaan.",
        err=True,
    )
    traceback.print_exc(file=sys.stderr)
    raise typer.Exit(2)


def _current_cycle_month(root: Path, vuosi: int) -> int:
    """Find the end month of the most recently set-up billing cycle."""
    dummy_run_dir = root / str(vuosi) / f"{vuosi}-00"
    yleiset_paths = find_all_yleiset(root, dummy_run_dir, vuosi)
    if not yleiset_paths:
        raise BillingError(
            "Nykyistä laskutusjaksoa ei löydy. Anna --kuukausi."
        )
    general_info = read_general_info(yleiset_paths)
    return general_info.billing_cycle.end_date.month


@app.command("lasku")
def lasku(
    vuosi: int = typer.Option(date.today().year, "--vuosi", help="Laskutusvuosi"),
    kuukausi: Optional[int] = typer.Option(
        None, "--kuukausi", help="Jakson loppukuukausi (1–12, oletus: nykyinen laskutusjakso)"
    ),
    data_hakemisto: Optional[Path] = typer.Option(
        None, "--data-hakemisto", help="Datatiedostojen juurihakemisto"
    ),
    ylikirjoita: bool = typer.Option(
        False, "--ylikirjoita", help="Ylikirjoita olemassa oleva tulostiedosto"
    ),
) -> None:
    """Laske kulutukset ja luo laskut CSV-tiedostoon."""
    try:
        config = load_config(data_hakemisto)
        root = config.data_root
        if kuukausi is None:
            kuukausi = _current_cycle_month(root, vuosi)
        run_dir = run_folder(root, vuosi, kuukausi)
        run_dir.mkdir(parents=True, exist_ok=True)

        yleiset_paths = find_all_yleiset(root, run_dir, vuosi)
        general_info = read_general_info(yleiset_paths)
        cycle = general_info.billing_cycle

        osakkaat_path = find_with_fallback(root, run_dir, vuosi, "osakkaat", cycle.end_date)
        customers = read_customers(osakkaat_path)

        laskurivit_path = find_with_fallback(root, run_dir, vuosi, "laskurivit", cycle.end_date)
        bill_lines = read_bill_lines(laskurivit_path)

        lukemat_path = find_with_fallback(root, run_dir, vuosi, "lukemat", cycle.end_date)
        meter_readings = read_meter_readings(lukemat_path)

        try:
            prev_lukemat_paths = find_previous_lukemats(root, vuosi, kuukausi, cycle.start_date)
        except BillingError:
            raise BillingError(
                "Ei aikaisempia lukematietoja löydy. Ensimmäisellä laskutuskerralla "
                "tarvitaan siemenlukemat-tiedosto sarakkeilla: nimi, päivämäärä, lukema.\n"
                "Luo tiedosto käsin tai käynnistä 'laskutus uusi', joka ohjaa "
                "alkutietojen syöttämisen läpi."
            )
        prev_readings = read_meter_readings(prev_lukemat_paths[0])
        prev_prev_readings = (
            read_meter_readings(prev_lukemat_paths[1])
            if len(prev_lukemat_paths) > 1
            else []
        )

        warnings = validate_inputs(
            customers, bill_lines, general_info, meter_readings,
            prev_readings, prev_prev_readings,
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

        out = output_path(run_dir, cycle.end_date, "laskut", "", "csv")
        write_bills(out, bills, overwrite=ylikirjoita)
        typer.echo(f"Laskut kirjoitettu: {out} ({len(bills)} laskua)")

    except BillingError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1)
    except Exception as exc:
        _handle_unexpected(exc)


@app.command("pdf")
def pdf(
    vuosi: int = typer.Option(date.today().year, "--vuosi", help="Laskutusvuosi"),
    kuukausi: Optional[int] = typer.Option(
        None, "--kuukausi", help="Jakson loppukuukausi (1–12, oletus: nykyinen laskutusjakso)"
    ),
    data_hakemisto: Optional[Path] = typer.Option(
        None, "--data-hakemisto", help="Datatiedostojen juurihakemisto"
    ),
) -> None:
    """Luo laskuista PDF-tiedostot."""
    try:
        config = load_config(data_hakemisto)
        root = config.data_root
        if kuukausi is None:
            kuukausi = _current_cycle_month(root, vuosi)
        run_dir = run_folder(root, vuosi, kuukausi)

        yleiset_paths = find_all_yleiset(root, run_dir, vuosi)
        general_info = read_general_info(yleiset_paths)
        cycle = general_info.billing_cycle

        osakkaat_path = find_with_fallback(root, run_dir, vuosi, "osakkaat", cycle.end_date)
        customers = read_customers(osakkaat_path)
        customer_by_name = {c.name: c for c in customers}

        laskut_path = find_with_fallback(root, run_dir, vuosi, "laskut", cycle.end_date)
        bills = read_bills(laskut_path)

        laskurivit_path = find_with_fallback(root, run_dir, vuosi, "laskurivit", cycle.end_date)
        bill_lines = read_bill_lines(laskurivit_path)

        consumption_by_name = {b.customer_name: Decimal(b.consumption) for b in bills}
        distributions = [
            distribute_bill_line(line, customers, consumption_by_name) for line in bill_lines
        ]

        count = 0
        for bill in bills:
            customer = customer_by_name.get(bill.customer_name)
            if customer is None:
                continue
            line_items = []
            for line, dist in zip(bill_lines, distributions):
                customer_amount = dist.get(bill.customer_name, Decimal("0"))
                if line.application_rule == ApplicationRule.PER_CONSUMPTION:
                    item_count = consumption_by_name.get(bill.customer_name, Decimal("0"))
                    effective_unit_price = line.unit_price
                else:
                    item_count = line.count
                    effective_unit_price = (
                        (customer_amount / item_count).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        if item_count
                        else Decimal("0")
                    )
                vat = (customer_amount * line.vat_percent / 100).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                line_items.append(
                    BillLineItem(
                        title=line.title,
                        count=item_count,
                        unit=line.unit,
                        unit_price=effective_unit_price,
                        netto=customer_amount,
                        vat_percent=line.vat_percent,
                        vat=vat,
                        total=customer_amount + vat,
                        application_rule=line.application_rule,
                        cycle_start=line.cycle_start,
                        cycle_end=line.cycle_end,
                    )
                )
            bill_with_items = dataclasses.replace(bill, line_items=line_items)
            name_parts = bill.customer_name.split()
            if len(name_parts) >= 2:
                note = f"{name_parts[-1].lower()}-{name_parts[0].lower()}"
            else:
                note = bill.customer_name.lower().replace(" ", "-")
            pdf_out = output_path(run_dir, cycle.end_date, "lasku", note, "pdf")
            render_bill_pdf(bill_with_items, general_info, customer, pdf_out)
            typer.echo(f"  PDF: {pdf_out.name}")
            count += 1
        typer.echo(f"Yhteensä {count} PDF-laskua luotu.")

    except BillingError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1)
    except Exception as exc:
        _handle_unexpected(exc)


@app.command("julkaise")
def julkaise(
    vuosi: int = typer.Option(date.today().year, "--vuosi", help="Laskutusvuosi"),
    kuukausi: Optional[int] = typer.Option(
        None, "--kuukausi", help="Jakson loppukuukausi (1–12, oletus: nykyinen laskutusjakso)"
    ),
    data_hakemisto: Optional[Path] = typer.Option(
        None, "--data-hakemisto", help="Datatiedostojen juurihakemisto"
    ),
    ylikirjoita: bool = typer.Option(
        False, "--ylikirjoita", help="Ylikirjoita olemassa olevat tulostiedostot"
    ),
    laheta_uudelleen: bool = typer.Option(
        False, "--lähetä-uudelleen", help="Lähetä sähköpostit uudelleen jo lähetetyille"
    ),
) -> None:
    """Luo paperilaskut, yhteenveto ja lähetä sähköpostit."""
    try:
        config = load_config(data_hakemisto)
        require_smtp_config(config)
        root = config.data_root
        if kuukausi is None:
            kuukausi = _current_cycle_month(root, vuosi)
        run_dir = run_folder(root, vuosi, kuukausi)

        yleiset_paths = find_all_yleiset(root, run_dir, vuosi)
        general_info = read_general_info(yleiset_paths)
        cycle = general_info.billing_cycle

        osakkaat_path = find_with_fallback(root, run_dir, vuosi, "osakkaat", cycle.end_date)
        customers = read_customers(osakkaat_path)

        laskut_path = find_with_fallback(root, run_dir, vuosi, "laskut", cycle.end_date)
        bills = read_bills(laskut_path)

        lukemat_path = find_with_fallback(root, run_dir, vuosi, "lukemat", cycle.end_date)
        meter_readings = read_meter_readings(lukemat_path)

        prev_lukemat_paths = find_previous_lukemats(root, vuosi, kuukausi, cycle.end_date)
        main_consumption = compute_main_meter_consumption(
            meter_readings, prev_lukemat_paths[0]
        )
        customer_total = sum(b.consumption for b in bills)

        from decimal import Decimal

        water_loss_m3: Optional[int] = None
        water_loss_pct: Optional[Decimal] = None
        if main_consumption is not None:
            water_loss_m3 = main_consumption - customer_total
            if main_consumption > 0:
                water_loss_pct = (
                    Decimal(water_loss_m3) / Decimal(main_consumption) * 100
                )

        summary = BillingSummary(
            bills=bills,
            main_meter_consumption=main_consumption,
            customer_consumption_total=customer_total,
            water_loss_m3=water_loss_m3,
            water_loss_percent=water_loss_pct,
            billing_cycle=cycle,
            contact_info=general_info.contact_info,
        )

        paper_out = run_dir / f"{cycle.end_date.strftime('%Y%m%d')}-paperilaskut.pdf"
        is_rerun = paper_out.exists()
        if is_rerun and not ylikirjoita:
            raise BillingError(
                f"Tulostiedosto on jo olemassa: {paper_out}. "
                "Käytä --ylikirjoita ylikirjoittaaksesi."
            )

        emailed = email_bill_pdf_paths(bills, customers, run_dir, cycle.end_date)
        paper_pdfs = sort_bill_pdfs_for_print(
            [p for p in run_dir.glob(f"{cycle.end_date.strftime('%Y%m%d')}-lasku-*.pdf")
             if p not in emailed],
            bills, customers, run_dir, cycle.end_date,
        )
        merge_pdfs(paper_pdfs, paper_out)
        typer.echo(f"Paperilaskut: {paper_out}")

        summary_out = run_dir / f"{cycle.end_date.strftime('%Y%m%d')}-yhteenveto.pdf"
        if summary_out.exists() and not ylikirjoita:
            raise BillingError(
                f"Tulostiedosto on jo olemassa: {summary_out}. "
                "Käytä --ylikirjoita ylikirjoittaaksesi."
            )
        render_summary_pdf(summary, summary_out)
        typer.echo(f"Yhteenveto: {summary_out}")

        if is_rerun and not laheta_uudelleen:
            typer.echo(
                "Varoitus: laskut on jo julkaistu aiemmin. "
                "Sähköpostit ohitetaan. Käytä --lähetä-uudelleen lähettääksesi uudelleen."
            )
        else:
            succeeded, failed = send_all_bills(config, bills, customers, run_dir, general_info)
            for email in succeeded:
                typer.echo(f"Sähköposti lähetetty: {email}")
            if failed:
                typer.echo(f"Epäonnistuneet: {', '.join(failed)}", err=True)

            send_summary_email(config, summary_out, summary)
            recipient = general_info.contact_info.treasurer_email or config.treasurer_email
            typer.echo(f"Yhteenveto lähetetty: {recipient}")

    except BillingError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1)
    except Exception as exc:
        _handle_unexpected(exc)


@app.command("uusi")
def uusi(
    vuosi: Optional[int] = typer.Option(
        None, "--vuosi", help="Laskutusvuosi (oletus: seuraava jakso edellisen jälkeen)"
    ),
    kuukausi: Optional[int] = typer.Option(
        None,
        "--kuukausi",
        help="Jakson loppukuukausi (1–12, oletus: seuraava jakso edellisen jälkeen)",
    ),
    data_hakemisto: Optional[Path] = typer.Option(
        None, "--data-hakemisto", help="Datatiedostojen juurihakemisto"
    ),
) -> None:
    """Interaktiivinen ohjattu laskutuskierto alusta loppuun."""
    try:
        from water_billing.services.wizard import run_cycle_wizard
        config = load_config(data_hakemisto)
        root = config.data_root
        if kuukausi is None:
            search_year = vuosi if vuosi is not None else date.today().year
            dummy_run_dir = root / str(search_year) / f"{search_year}-00"
            yleiset_paths = find_all_yleiset(root, dummy_run_dir, search_year)
            if not yleiset_paths:
                raise BillingError(
                    "Aiempaa laskutusjaksoa ei löydy. Anna --vuosi ja --kuukausi "
                    "ensimmäistä laskutuskertaa varten."
                )
            latest_path = yleiset_paths[0]
            latest_cycle = read_general_info([latest_path]).billing_cycle
            # A cycle is only "done" once its summary PDF exists (the last
            # artifact the wizard produces) — otherwise re-running 'uusi'
            # without arguments should resume it, not skip past it.
            latest_is_complete = any(latest_path.parent.glob("*-yhteenveto.pdf"))
            if latest_is_complete:
                _, next_end = next_billing_period(latest_cycle.end_date)
                if vuosi is None:
                    vuosi = next_end.year
                kuukausi = next_end.month
            else:
                if vuosi is None:
                    vuosi = latest_cycle.end_date.year
                kuukausi = latest_cycle.end_date.month
        elif vuosi is None:
            vuosi = date.today().year
        run_dir = run_folder(root, vuosi, kuukausi)
        run_dir.mkdir(parents=True, exist_ok=True)
        run_cycle_wizard(config, run_dir, vuosi, kuukausi)
    except BillingError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1)
    except Exception as exc:
        _handle_unexpected(exc)


@app.command("lukemat")
def lukemat(
    vuosi: int = typer.Option(date.today().year, "--vuosi", help="Laskutusvuosi"),
    kuukausi: Optional[int] = typer.Option(
        None, "--kuukausi", help="Jakson loppukuukausi (1–12, oletus: nykyinen laskutusjakso)"
    ),
    data_hakemisto: Optional[Path] = typer.Option(
        None, "--data-hakemisto", help="Datatiedostojen juurihakemisto"
    ),
) -> None:
    """Hae ja näytä viimeisimmät mittarilukemat Vesitili-portaalista (ei tallenna mitään)."""
    try:
        config = load_config(data_hakemisto)
        root = config.data_root
        if kuukausi is None:
            kuukausi = _current_cycle_month(root, vuosi)
        run_dir = run_folder(root, vuosi, kuukausi)

        general_info = read_general_info(find_all_yleiset(root, run_dir, vuosi))
        osakkaat_path = find_with_fallback(
            root, run_dir, vuosi, "osakkaat", general_info.billing_cycle.end_date
        )
        customers = read_customers(osakkaat_path)

        typer.echo(f"Osakkaat: {osakkaat_path.name}")
        readings = fetch_portal_readings(customers, general_info.contact_info, typer.echo)
        if not readings:
            typer.echo(
                "Yhtään lukemaa ei saatu. Tarkista osakkaat-tiedoston sarakkeet "
                "'asiakasnumero' ja 'kulutuspiste'."
            )
    except BillingError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1)
    except Exception as exc:
        _handle_unexpected(exc)


def main() -> None:
    app()
