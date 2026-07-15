from __future__ import annotations

import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import barcode
from barcode.writer import ImageWriter
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from water_billing.domain.models import Bill, ContactInfo, Customer, GeneralInfo
from water_billing.domain.rules import ApplicationRule
from water_billing.encoding.reference_number import format_reference_number
from water_billing.encoding.virtual_barcode import encode_virtual_barcode


def _build_footer_callback(ci: ContactInfo, page_w: float, margin: float):
    def draw_footer(canvas, doc):
        canvas.saveState()
        rule_y = 25 * mm
        canvas.setStrokeColor(colors.grey)
        canvas.setLineWidth(0.5)
        canvas.line(margin, rule_y, page_w - margin, rule_y)

        line1_y = rule_y - 4 * mm
        line2_y = line1_y - 9
        line3_y = line2_y - 9
        line4_y = line3_y - 9

        # Left column, line 1: cooperative name in small bold
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.drawString(margin, line1_y, ci.cooperative_name)

        # Left column, line 2: contact person [, street address]
        canvas.setFont("Helvetica", 7.5)
        contact_parts = [ci.contact_person]
        if ci.street_address:
            contact_parts.append(ci.street_address)
        canvas.drawString(margin, line2_y, ", ".join(contact_parts))

        # Left column, line 3: phone and email
        canvas.drawString(margin, line3_y, f"{ci.phone}, {ci.email}")

        # Left column, line 4: web_url (if present)
        if ci.web_url:
            canvas.drawString(margin, line4_y, ci.web_url)

        # Right column (right-aligned): Y-tunnus and IBAN [+ BIC]
        right_x = page_w - margin
        ytunnus_str = f"Y-tunnus: {ci.y_tunnus}"
        iban_str = f"Tilinumero: {ci.iban}"
        if ci.bic:
            iban_str += f"  BIC: {ci.bic}"
        canvas.drawRightString(right_x, line1_y, ytunnus_str)
        canvas.drawRightString(right_x, line2_y, iban_str)

        canvas.restoreState()
    return draw_footer


def format_amount_fi(amount: Decimal) -> str:
    return f"{amount:.2f}".replace(".", ",") + " €"


def format_date_fi(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _qty_str(count: Decimal, unit: str) -> str:
    return f"{count:.2f}".replace(".", ",") + f" {unit}"


def _price_str(amount: Decimal) -> str:
    return f"{amount:.2f}".replace(".", ",")


def render_bill_pdf(
    bill: Bill,
    general_info: GeneralInfo,
    customer: Customer,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ci = general_info.contact_info
    cycle = general_info.billing_cycle

    page_w, _ = A4
    margin = 20 * mm
    usable_w = page_w - 2 * margin
    footer_fn = _build_footer_callback(ci, page_w, margin)

    normal = ParagraphStyle("normal", fontSize=9, leading=11)
    right_normal = ParagraphStyle("right_normal", fontSize=9, leading=11, alignment=TA_RIGHT)
    bold = ParagraphStyle("bold", fontSize=9, leading=11, fontName="Helvetica-Bold")
    bold_right = ParagraphStyle(
        "bold_right", fontSize=9, leading=11, fontName="Helvetica-Bold", alignment=TA_RIGHT
    )
    small = ParagraphStyle("small", fontSize=7, leading=9)
    small_grey = ParagraphStyle("small_grey", fontSize=7, leading=9, textColor=colors.grey)
    small_italic = ParagraphStyle(
        "small_italic", fontSize=7, leading=9, fontName="Helvetica-Oblique"
    )
    large_bold = ParagraphStyle("large_bold", fontSize=12, leading=14, fontName="Helvetica-Bold")
    large_bold_right = ParagraphStyle(
        "large_bold_right",
        fontSize=12,
        leading=14,
        fontName="Helvetica-Bold",
        alignment=TA_RIGHT,
    )
    monospace = ParagraphStyle("monospace", fontSize=8, leading=10, fontName="Courier")

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=30 * mm,
    )

    story = []

    # Section 1 — Header
    header = Table(
        [[Paragraph(ci.cooperative_name, large_bold), Paragraph("LASKU", large_bold_right)]],
        colWidths=[usable_w * 0.6, usable_w * 0.4],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(header)
    story.append(Spacer(1, 2 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 3 * mm))

    # Section 2 — Billing info block
    left_cell = [
        Paragraph(customer.name, normal),
        Paragraph(customer.street_address, normal),
        Paragraph(f"{customer.postal_code} {customer.city}", normal),
    ]

    meta_rows = [
        ["Laskun numero", str(bill.bill_number)],
        ["Päivämäärä", format_date_fi(cycle.bill_date)],
        ["Eräpäivä", format_date_fi(cycle.due_date)],
    ]
    if customer.consumption_point:
        meta_rows.append(["Käyttöpaikka", customer.consumption_point])
    meta_rows.append(["Mittarinumero", bill.meter_id])
    meta_rows.append(["Henkilömäärä", str(customer.number_of_persons)])

    meta_data = [
        [Paragraph(lbl, small_grey), Paragraph(val, normal)] for lbl, val in meta_rows
    ]
    meta_grid = Table(meta_data, colWidths=[30 * mm, 35 * mm])
    meta_grid.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
    ]))

    info_table = Table(
        [[left_cell, meta_grid]],
        colWidths=[usable_w - 65 * mm, 65 * mm],
    )
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 3 * mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 3 * mm))

    if ci.message:
        story.append(Paragraph(ci.message.replace("\n", "<br/>"), normal))
        story.append(Spacer(1, 3 * mm))

    # Section 3 — Line items table (outer border only, no INNERGRID)
    num_col_widths = [22 * mm, 18 * mm, 22 * mm, 14 * mm, 18 * mm, 22 * mm]
    title_col_w = usable_w - sum(num_col_widths)
    col_widths = [title_col_w] + num_col_widths

    item_data = [[
        Paragraph("", normal),
        Paragraph("Määrä", right_normal),
        Paragraph("À-hinta", right_normal),
        Paragraph("Netto €", right_normal),
        Paragraph("Alv %", right_normal),
        Paragraph("Alv €", right_normal),
        Paragraph("Yht €", right_normal),
    ]]

    for item in bill.line_items:
        item_data.append([
            Paragraph(item.title, normal),
            Paragraph(_qty_str(item.count, item.unit), right_normal),
            Paragraph(_price_str(item.unit_price), right_normal),
            Paragraph(format_amount_fi(item.netto), right_normal),
            Paragraph(_price_str(item.vat_percent), right_normal),
            Paragraph(format_amount_fi(item.vat), right_normal),
            Paragraph(format_amount_fi(item.total), right_normal),
        ])
        item_start = item.cycle_start or cycle.start_date
        item_end = item.cycle_end or cycle.end_date
        period_text = (
            f"Rivin laskutusjakso: {format_date_fi(item_start)} – "
            f"{format_date_fi(item_end)}"
        )
        if item.application_rule == ApplicationRule.PER_CONSUMPTION:
            readings_text = f"\nLukemat {bill.prev_reading} – {bill.new_reading}"
            if bill.is_estimated:
                readings_text += " (arvio)"
            period_text += readings_text
        item_data.append([Paragraph(period_text, small_italic), "", "", "", "", "", ""])

    vat_rates = sorted({i.vat_percent for i in bill.line_items})
    for idx, rate in enumerate(vat_rates):
        rate_items = [i for i in bill.line_items if i.vat_percent == rate]
        rate_netto = sum(i.netto for i in rate_items)
        rate_vat = sum(i.vat for i in rate_items)
        label = "Alv-erittely" if idx == 0 else ""
        item_data.append([
            Paragraph("", normal), Paragraph("", normal),
            Paragraph(label, small),
            Paragraph(format_amount_fi(rate_netto), right_normal),
            Paragraph(_price_str(rate), right_normal),
            Paragraph(format_amount_fi(rate_vat), right_normal),
            Paragraph("", normal),
        ])

    n_items = len(bill.line_items)
    sub_cmds = []
    for idx in range(n_items):
        sub_row = 2 + idx * 2
        sub_cmds.append(("SPAN", (0, sub_row), (6, sub_row)))

    items_table = Table(item_data, colWidths=col_widths)
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
    ] + sub_cmds))
    story.append(items_table)
    story.append(Spacer(1, 3 * mm))

    # Grand total row
    total_row = Table(
        [[
            Paragraph("LASKU YHTEENSÄ:", large_bold),
            Paragraph(format_amount_fi(bill.total_due), large_bold_right),
        ]],
        colWidths=[usable_w * 0.6, usable_w * 0.4],
    )
    total_row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(total_row)
    story.append(Spacer(1, 5 * mm))

    # Section 4 — Payment information
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.black))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Maksutiedot", bold))
    story.append(Spacer(1, 2 * mm))

    iban_val = ci.iban
    if ci.bic:
        iban_val += f"  BIC: {ci.bic}"

    virtual_bc = encode_virtual_barcode(
        iban=ci.iban,
        amount=bill.total_due,
        reference_number=bill.reference_number,
        due_date=cycle.due_date,
    )

    payment_data = [
        [Paragraph("Saaja", small_grey), Paragraph(ci.cooperative_name, normal)],
        [Paragraph("Tilinumero (IBAN)", small_grey), Paragraph(iban_val, normal)],
        [Paragraph("Viitenumero", small_grey), Paragraph(format_reference_number(bill.reference_number), normal)],
        [Paragraph("Eräpäivä", small_grey), Paragraph(format_date_fi(cycle.due_date), normal)],
        [Paragraph("Summa", small_grey), Paragraph(format_amount_fi(bill.total_due), bold)],
        [Paragraph("Virtuaaliviivakoodi", small_grey), Paragraph(virtual_bc, monospace)],
    ]
    payment_table = Table(payment_data, colWidths=[40 * mm, usable_w - 40 * mm])
    payment_table.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(payment_table)
    story.append(Spacer(1, 4 * mm))

    # Section 5 — Barcode (full page width, ~20 mm tall, no caption)
    barcode_buf = io.BytesIO()
    code128 = barcode.get("code128", virtual_bc, writer=ImageWriter())
    code128.write(barcode_buf, options={"write_text": False})
    barcode_buf.seek(0)
    story.append(Image(barcode_buf, width=usable_w, height=20 * mm))

    doc.build(story, onFirstPage=footer_fn, onLaterPages=footer_fn)
