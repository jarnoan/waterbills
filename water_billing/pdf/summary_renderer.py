from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from water_billing.domain.models import BillingSummary
from water_billing.encoding.reference_number import format_reference_number
from water_billing.pdf.bill_renderer import format_amount_fi, format_date_fi


def render_summary_pdf(summary: BillingSummary, output_path: Path) -> None:
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

    cycle = summary.billing_cycle
    period = (
        f"{format_date_fi(cycle.start_date)} – {format_date_fi(cycle.end_date)}"
    )

    story = []
    story.append(Paragraph("Laskutusyhteenveto", styles["Heading1"]))
    story.append(Paragraph(f"Laskutusjakso: {period}", normal))
    story.append(Spacer(1, 6 * mm))

    sorted_bills = sorted(summary.bills, key=lambda b: b.customer_name)
    total_sum = sum(b.total_due for b in sorted_bills)

    bill_data = [["Nimi", "Summa (€)", "Eräpäivä", "Viitenumero"]]
    for b in sorted_bills:
        bill_data.append(
            [
                b.customer_name,
                format_amount_fi(b.total_due),
                format_date_fi(cycle.due_date),
                format_reference_number(b.reference_number),
            ]
        )
    bill_data.append(["Yhteensä", format_amount_fi(total_sum), "", ""])

    bill_table = Table(
        bill_data, colWidths=[70 * mm, 35 * mm, 35 * mm, 35 * mm]
    )
    bill_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    story.append(Paragraph("Laskut", heading))
    story.append(bill_table)
    story.append(Spacer(1, 8 * mm))

    def _val(v, fmt=str):
        return fmt(v) if v is not None else "N/A"

    water_data = [
        ["Mittaus", "Arvo"],
        ["Päämittari (m³)", _val(summary.main_meter_consumption)],
        [
            "Asiakkaiden yhteiskulutus (m³)",
            str(summary.customer_consumption_total),
        ],
        ["Häviö (m³)", _val(summary.water_loss_m3)],
        [
            "Häviö (%)",
            _val(
                summary.water_loss_percent,
                lambda v: f"{v:.1f}".replace(".", ",") + " %",
            ),
        ],
    ]
    water_table = Table(water_data, colWidths=[110 * mm, 60 * mm])
    water_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]
        )
    )
    story.append(Paragraph("Vesimittaritiedot", heading))
    story.append(water_table)

    doc.build(story)
