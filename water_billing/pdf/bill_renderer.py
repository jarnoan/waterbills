from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import barcode
from barcode.writer import ImageWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from water_billing.domain.models import Bill, Customer, GeneralInfo
from water_billing.encoding.reference_number import format_reference_number
from water_billing.encoding.virtual_barcode import encode_virtual_barcode


def format_amount_fi(amount: Decimal) -> str:
    return f"{amount:.2f}".replace(".", ",") + " €"


def format_date_fi(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def render_bill_pdf(
    bill: Bill,
    general_info: GeneralInfo,
    customer: Customer,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    heading = styles["Heading2"]
    mono = styles["Code"]

    ci = general_info.contact_info
    cycle = general_info.billing_cycle

    formatted_ref = format_reference_number(bill.reference_number)
    virtual_barcode_str = encode_virtual_barcode(
        iban=ci.iban,
        amount=bill.total_due,
        reference_number=bill.reference_number,
        due_date=cycle.due_date,
    )

    story = []

    story.append(Paragraph(ci.cooperative_name, heading))
    story.append(Paragraph(f"Yhteyshenkilö: {ci.contact_person}", normal))
    story.append(Paragraph(f"Puhelin: {ci.phone}", normal))
    story.append(Paragraph(f"Sähköposti: {ci.email}", normal))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(f"<b>Lasku nro {bill.bill_number}</b>", heading))
    story.append(Paragraph(f"Asiakas: {bill.customer_name}", normal))
    story.append(Paragraph(f"Osoite: {customer.address}", normal))
    story.append(
        Paragraph(
            f"Laskutusjakso: {format_date_fi(cycle.start_date)} – "
            f"{format_date_fi(cycle.end_date)}",
            normal,
        )
    )
    story.append(Paragraph(f"Eräpäivä: {format_date_fi(cycle.due_date)}", normal))
    story.append(
        Paragraph(
            f"Edellinen lukema: {bill.prev_reading} m³ "
            f"({format_date_fi(bill.prev_reading_date)})",
            normal,
        )
    )
    story.append(
        Paragraph(
            f"Uusi lukema: {bill.new_reading} m³ "
            f"({format_date_fi(bill.new_reading_date)})"
            + (" (ARVIO)" if bill.is_estimated else ""),
            normal,
        )
    )
    story.append(Paragraph(f"Kulutus: {bill.consumption} m³", normal))
    story.append(Spacer(1, 6 * mm))

    line_data = [
        ["Nimike", "Summa (€)", "ALV %"],
        ["Perusmaksu-osuus", format_amount_fi(bill.basic_fee_share), ""],
        ["Vesimaksu", format_amount_fi(bill.water_cost), ""],
        ["Yhteiskustannukset", format_amount_fi(bill.shared_expense_share), ""],
        ["Yhteensä", format_amount_fi(bill.total_due), ""],
    ]
    table = Table(line_data, colWidths=[90 * mm, 50 * mm, 30 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("<b>Maksutiedot</b>", heading))
    story.append(Paragraph(f"Yhteensä: {format_amount_fi(bill.total_due)}", normal))
    story.append(Paragraph(f"Eräpäivä: {format_date_fi(cycle.due_date)}", normal))
    story.append(Paragraph(f"Tilinumero (IBAN): {ci.iban}", normal))
    story.append(Paragraph(f"Viitenumero: {formatted_ref}", normal))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Virtuaaliviivakoodi:", normal))
    story.append(Paragraph(virtual_barcode_str, mono))
    story.append(Spacer(1, 6 * mm))

    barcode_buf = io.BytesIO()
    code128 = barcode.get("code128", virtual_barcode_str, writer=ImageWriter())
    code128.write(barcode_buf, options={"write_text": False})
    barcode_buf.seek(0)
    story.append(Image(barcode_buf, width=140 * mm, height=25 * mm))

    doc.build(story)
