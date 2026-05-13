from __future__ import annotations

import sys
import traceback
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from water_billing.config import load_config, require_smtp_config
from water_billing.domain.models import BillingSummary
from water_billing.domain.rules import BillingError
from water_billing.io.csv_readers import (
    read_bill_lines,
    read_customers,
    read_general_info,
    read_meter_readings,
    read_previous_bills,
)
from water_billing.io.csv_writers import write_bills
from water_billing.io.file_discovery import (
    find_previous_laskut,
    find_previous_lukemat,
    output_path,
    require_file,
)
from water_billing.pdf.bill_renderer import render_bill_pdf
from water_billing.pdf.merger import merge_pdfs, sort_bill_pdfs_alphabetically
from water_billing.pdf.summary_renderer import render_summary_pdf
from water_billing.services.billing import (
    compute_consumptions,
    compute_main_meter_consumption,
    generate_bills,
    get_next_bill_number,
)
from water_billing.services.email import send_all_bills, send_summary_email
from water_billing.services.validation import validate_inputs

app = typer.Typer(name="laskutus", help="Vesiosuuskunnan laskutustyökalu")


def _handle_unexpected(exc: Exception) -> None:
    typer.echo(
        "Odottamaton virhe. Ole hyvä ja ota yhteyttä järjestelmänvalvojaan.",
        err=True,
    )
    traceback.print_exc(file=sys.stderr)
    raise typer.Exit(2)


@app.command("lasku")
def lasku(
    vuosi: int = typer.Option(date.today().year, "--vuosi", help="Laskutusvuosi"),
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

        yleiset_path = require_file(root, vuosi, "yleiset", date(vuosi, 12, 31))
        general_info = read_general_info(yleiset_path)
        cycle = general_info.billing_cycle

        osakkaat_path = require_file(root, vuosi, "osakkaat", cycle.end_date)
        customers = read_customers(osakkaat_path)

        laskurivit_path = require_file(root, vuosi, "laskurivit", cycle.end_date)
        bill_lines = read_bill_lines(laskurivit_path)

        lukemat_path = require_file(root, vuosi, "lukemat", cycle.end_date)
        meter_readings = read_meter_readings(lukemat_path)

        prev_laskut_path = find_previous_laskut(root, vuosi, cycle.start_date)
        previous_bills = read_previous_bills(prev_laskut_path)

        warnings = validate_inputs(
            customers, bill_lines, general_info, meter_readings, previous_bills
        )
        for w in warnings:
            typer.echo(w)

        consumptions = compute_consumptions(
            customers, meter_readings, previous_bills, cycle.end_date
        )
        start_number = get_next_bill_number(previous_bills)
        bills = generate_bills(
            customers, consumptions, bill_lines, cycle, start_number
        )

        out = output_path(root, cycle.end_date, "laskut", "uudet", "csv")
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
    data_hakemisto: Optional[Path] = typer.Option(
        None, "--data-hakemisto", help="Datatiedostojen juurihakemisto"
    ),
) -> None:
    """Luo laskuista PDF-tiedostot."""
    try:
        config = load_config(data_hakemisto)
        root = config.data_root

        yleiset_path = require_file(root, vuosi, "yleiset", date(vuosi, 12, 31))
        general_info = read_general_info(yleiset_path)
        cycle = general_info.billing_cycle

        osakkaat_path = require_file(root, vuosi, "osakkaat", cycle.end_date)
        customers = read_customers(osakkaat_path)
        customer_by_name = {c.name: c for c in customers}

        laskut_path = require_file(root, vuosi, "laskut", cycle.end_date)
        bills = read_previous_bills(laskut_path)

        year_dir = root / str(vuosi)
        count = 0
        for bill in bills:
            customer = customer_by_name.get(bill.customer_name)
            if customer is None:
                continue
            name_parts = bill.customer_name.split()
            if len(name_parts) >= 2:
                note = f"{name_parts[-1].lower()}-{name_parts[0].lower()}"
            else:
                note = bill.customer_name.lower().replace(" ", "-")
            pdf_out = output_path(root, cycle.end_date, "lasku", note, "pdf")
            render_bill_pdf(bill, general_info, customer, pdf_out)
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

        yleiset_path = require_file(root, vuosi, "yleiset", date(vuosi, 12, 31))
        general_info = read_general_info(yleiset_path)
        cycle = general_info.billing_cycle

        osakkaat_path = require_file(root, vuosi, "osakkaat", cycle.end_date)
        customers = read_customers(osakkaat_path)

        laskut_path = require_file(root, vuosi, "laskut", cycle.end_date)
        bills = read_previous_bills(laskut_path)

        lukemat_path = require_file(root, vuosi, "lukemat", cycle.end_date)
        meter_readings = read_meter_readings(lukemat_path)

        prev_lukemat_path = find_previous_lukemat(root, vuosi, cycle.start_date)
        main_consumption = compute_main_meter_consumption(
            meter_readings, prev_lukemat_path
        )
        customer_total = sum(
            b.consumption for b in bills if not b.is_estimated or True
        )

        from decimal import Decimal

        water_loss_m3: Optional[int] = None
        water_loss_pct: Optional[Decimal] = None
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

        paper_out = output_path(root, cycle.end_date, "paperilaskut", "", "pdf")
        paper_out = paper_out.parent / f"{cycle.end_date.strftime('%Y%m%d')}-paperilaskut.pdf"

        if paper_out.exists() and not ylikirjoita:
            raise BillingError(
                f"Tulostiedosto on jo olemassa: {paper_out}. "
                "Käytä --ylikirjoita ylikirjoittaaksesi."
            )

        year_dir = root / str(vuosi)
        paper_pdfs = sorted(year_dir.glob(f"{cycle.end_date.strftime('%Y%m%d')}-lasku-*.pdf"))
        paper_pdfs = sort_bill_pdfs_alphabetically(list(paper_pdfs))
        merge_pdfs(paper_pdfs, paper_out)
        typer.echo(f"Paperilaskut: {paper_out}")

        summary_out = year_dir / f"{cycle.end_date.strftime('%Y%m%d')}-yhteenveto.pdf"
        if summary_out.exists() and not ylikirjoita:
            raise BillingError(
                f"Tulostiedosto on jo olemassa: {summary_out}. "
                "Käytä --ylikirjoita ylikirjoittaaksesi."
            )
        render_summary_pdf(summary, summary_out)
        typer.echo(f"Yhteenveto: {summary_out}")

        succeeded, failed = send_all_bills(
            config, bills, customers, year_dir, general_info
        )
        typer.echo(f"Sähköpostit lähetetty: {len(succeeded)}")
        if failed:
            typer.echo(f"Epäonnistuneet: {', '.join(failed)}", err=True)

        send_summary_email(config, summary_out, summary)
        typer.echo(f"Yhteenveto lähetetty: {config.treasurer_email}")

    except BillingError as exc:
        typer.echo(exc.message, err=True)
        raise typer.Exit(1)
    except Exception as exc:
        _handle_unexpected(exc)


def main() -> None:
    app()
