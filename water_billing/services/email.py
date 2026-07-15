from __future__ import annotations

import smtplib
from contextlib import contextmanager
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Generator, List, Set, Tuple

from water_billing.config import AppConfig
from water_billing.domain.models import Bill, BillingSummary, Customer, GeneralInfo
from water_billing.encoding.reference_number import format_reference_number
from water_billing.encoding.virtual_barcode import encode_virtual_barcode
from water_billing.pdf.bill_renderer import format_amount_fi, format_date_fi


@contextmanager
def _smtp_connection(config: AppConfig) -> Generator[smtplib.SMTP, None, None]:
    if config.use_tls:
        server = smtplib.SMTP(config.smtp_host, config.smtp_port)
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port)
    server.login(config.smtp_user, config.smtp_password)
    try:
        yield server
    finally:
        server.quit()


def _attach_pdf(msg: MIMEMultipart, pdf_path: Path) -> None:
    with open(pdf_path, "rb") as f:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header(
        "Content-Disposition", f"attachment; filename={pdf_path.name}"
    )
    msg.attach(part)


def send_bill_email(
    config: AppConfig,
    bill: Bill,
    pdf_path: Path,
    general_info: GeneralInfo,
    customer: Customer,
    server: smtplib.SMTP,
) -> None:
    ci = general_info.contact_info
    cycle = general_info.billing_cycle

    virtual_bc = encode_virtual_barcode(
        iban=ci.iban,
        amount=bill.total_due,
        reference_number=bill.reference_number,
        due_date=cycle.due_date,
    )
    body = (
        f"Hei!\n\n"
        f"Liitteenä laskutusjakson {format_date_fi(cycle.start_date)}–"
        f"{format_date_fi(cycle.end_date)} lasku.\n\n"
        f"Maksettava yhteensä: {format_amount_fi(bill.total_due)}\n"
        f"Eräpäivä: {format_date_fi(cycle.due_date)}\n"
        f"Tilinumero (IBAN): {ci.iban}\n"
        f"Viitenumero: {format_reference_number(bill.reference_number)}\n"
        f"Virtuaaliviivakoodi: {virtual_bc}\n\n"
        f"Terveisin,\n{ci.cooperative_name}\n{ci.contact_person}\n{ci.phone}\n{ci.email}\n\n"
    )

    subject = (
        f"Lasku {bill.bill_number} — {ci.cooperative_name}"
    )

    msg = MIMEMultipart()
    msg["From"] = formataddr((str(Header(ci.cooperative_name, "utf-8")), ci.email))
    msg["To"] = customer.email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    _attach_pdf(msg, pdf_path)

    server.sendmail(ci.email, customer.email, msg.as_string())


def send_summary_email(
    config: AppConfig,
    summary_pdf_path: Path,
    summary: BillingSummary,
) -> None:
    from water_billing.domain.rules import BillingError

    recipient = summary.contact_info.treasurer_email or config.treasurer_email
    if not recipient:
        raise BillingError(
            "Rahastonhoitajan sähköposti puuttuu sekä yleiset-tiedostosta"
            " että .env-tiedostosta"
        )

    cycle = summary.billing_cycle
    period = (
        f"{format_date_fi(cycle.start_date)}–{format_date_fi(cycle.end_date)}"
    )
    subject = f"Laskutusyhteenveto {period}"
    body = f"Liitteenä laskutusyhteenveto kaudelle {period}."

    ci = summary.contact_info
    msg = MIMEMultipart()
    msg["From"] = formataddr((str(Header(ci.cooperative_name, "utf-8")), ci.email))
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    _attach_pdf(msg, summary_pdf_path)

    with _smtp_connection(config) as server:
        server.sendmail(ci.email, recipient, msg.as_string())


def send_all_bills(
    config: AppConfig,
    bills: List[Bill],
    customers: List[Customer],
    pdf_dir: Path,
    general_info: GeneralInfo,
) -> Tuple[List[str], List[str]]:
    customer_by_name = {c.name: c for c in customers}
    succeeded: List[str] = []
    failed: List[str] = []

    with _smtp_connection(config) as server:
        for bill in bills:
            customer = customer_by_name.get(bill.customer_name)
            if customer is None or customer.billing_preference.lower() != "sähköposti":
                continue
            name_parts = bill.customer_name.split()
            if len(name_parts) >= 2:
                filename_stem = (
                    f"{general_info.billing_cycle.end_date.strftime('%Y%m%d')}"
                    f"-lasku-{name_parts[-1].lower()}-{name_parts[0].lower()}"
                )
            else:
                filename_stem = (
                    f"{general_info.billing_cycle.end_date.strftime('%Y%m%d')}"
                    f"-lasku-{bill.customer_name.lower().replace(' ', '-')}"
                )
            pdf_path = pdf_dir / f"{filename_stem}.pdf"
            try:
                send_bill_email(
                    config, bill, pdf_path, general_info, customer, server
                )
                succeeded.append(customer.email)
            except Exception as exc:
                failed.append(f"{bill.customer_name}: {exc}")

    return succeeded, failed


def email_bill_pdf_paths(
    bills: List[Bill],
    customers: List[Customer],
    pdf_dir: Path,
    cycle_end_date,
) -> Set[Path]:
    """Return PDF paths for bills that will be delivered by email (not paper)."""
    customer_by_name = {c.name: c for c in customers}
    paths: Set[Path] = set()
    for bill in bills:
        customer = customer_by_name.get(bill.customer_name)
        if customer is None or customer.billing_preference.lower() != "sähköposti":
            continue
        name_parts = bill.customer_name.split()
        if len(name_parts) >= 2:
            stem = (
                f"{cycle_end_date.strftime('%Y%m%d')}"
                f"-lasku-{name_parts[-1].lower()}-{name_parts[0].lower()}"
            )
        else:
            stem = (
                f"{cycle_end_date.strftime('%Y%m%d')}"
                f"-lasku-{bill.customer_name.lower().replace(' ', '-')}"
            )
        paths.add(pdf_dir / f"{stem}.pdf")
    return paths
