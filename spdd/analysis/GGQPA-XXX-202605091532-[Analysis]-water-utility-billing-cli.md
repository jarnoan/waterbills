# SPDD Analysis: Water Utility Billing CLI Tool

## Original Business Requirement

# Water Utility Billing System

Simple command-line tool to help billing in a small Finnish water utility cooperative with ~20 customers.

The tool is typically run once in a bi-monthly billing cycle. 
In some cases the tool could be run mid-cycle, if for example a property changes owner and
we need to split the bills between old and new owner.

The billed items include
- monthly basic fee
- water consumption fee
- shared expenses (insurance, banking fees, other co-op costs)  

The language used in the system is Finnish. This includes the CSV column titles,
file names, bills, emails and even the command line options and help texts of the tool.
The currency used is Euro.

## Data

All the data should be stored in simple CSV files, stored in local filesystem mapped from Google Drive.

There is a set of input files and a set of output files for each billing cycle (or mid-cycle when needed).

The input files are typically created manually, or the tool can provide some helper commands to produce them,
or they can be created with AI.
There is no need to create a new input file for every billing cycle if there are no changes to that billing cycle.
If there is no particular input file for a billing cycle, the tool should use the latest corresponding input file.

The output files are produced by the tool.

Organizing the files:
- There is one folder per year, containing all input and output files for that year.
- The file name pattern is date-type-note.extension, where
    - date is the date when file is produced (other other relevant date) in ISO-like format
    - type is the file type (see below)
    - note is some free-form descriptive note of the file (optional)
    - extension is csv or pdf

The set of input files:
- Customer List CSV (type: `osakkaat`)
    - name, address, email, phone
    - meter ID
    - billing preference (email/paper)
    - when joined, when left (for the record)
    - property id (for the record)
    - number of persons (for authority reporting)
- Bill Lines CSV (type: `laskurivit`)
    - title
    - amount
    - VAT percentage
    - how to apply (shared ones rounded up to next cent):
        - shared by all active customers (main meter basic fee)
        - shared by all customers (insurance, banking fees, other expenses)
        - multiplied by water consumption (water price per cubic meter)
- General Information CSV (type: `yleiset`)
    - billing cycle beginning and end dates
    - due date
    - contact information
- Customer Consumptions CSV (type: `kulutus`)
    - previous meter reading and date, new meter reading and date, consumption

The set of output files:
- Customer Bills CSV (type: `laskut`)
    - reference number, bill total
- Bill PDFs (type: `lasku`, note: `lastname-firstname`)
- Paper Bill PDFs (type: `paperilaskut`)
- Billing Summary
    - Customers names, amount dues, due dates, reference numbers

## Usage

The billing cycle run:
1. Create new Customer List CSV if there are changes.
2. Create new Bill Lines CSV if there are changes.
3. Create new General Information CSV.
4. Create new Customer Consumptions CSV.
5. Run the tool to produce Customer Bills CSV.
    - By default the tool uses the same consumption as in the previous billing cycle.
5. Check that the Customer Bills CSV looks correct, update if needed.
6. Run the tool to produce Bill PDFs.
    - The PDFs should look like standard Finnish bills with bar code and virtual bar code.
7. Check that the Bill PDFs look correct.
8. Run the tool to publish the bills.
    - Produce Paper Bill PDFs file containing the bills for customers who want a paper bill.
    - Send the bills by email for customers who want the bill by email.
        - Emails should include the PDF as an attachment, and the main details (total, due date, bank account, virtual bar code) as plain text.
    - Send a billing summary to the treasurer by email.

## Future development

### AI skill

Produce standard skill description for AI agents so that they can produce the input files,
run the tool and check output files.

### Fetching meter readings from the municipal utility

The water meters are owned and maintained by a municipal utility, who uses them for billing for the waste water.
They don't currently have a web portal where we could get the meter readings, 
but once they do, the tool should fetch the readings from there to produce Customer Consumption CSV.

### Web usage

The tool could be transformed to a function-as-a-service kind of cloud based service
that would provide a web interface.

### Checking the payments

The tool could use some banking API to check if customers have paid their bills
and report the status.

### E-billing

The tool could use some banking API to generate E-bills.

### Authority reporting

The tool could produce a report with data required by authorities annually.

---

## Domain Concept Identification

### Existing Concepts (from codebase)

None — this is a greenfield project with no existing implementation.

### New Concepts Required

- **Customer (Osakas)**: A shareholder/member of the cooperative. Has billing preference (email/paper), a joined date, and optionally a left date (for the record). Customers are tracked in the `osakkaat` CSV. Two sub-populations:
  - **Active customer (aktiivinen osakas)**: Connected to the water network — has a water meter and is actually consuming water. Billed for water-related charges.
  - **Inactive customer**: Member of the co-op but not connected to the water network. Still shares co-op overhead costs (insurance, banking) but is not billed for water consumption or the main meter basic fee.

- **BillingCycle**: A time period with a start date, end date, and payment due date. Determines the scope of billing. Defined in the `yleiset` input file. Mid-cycle runs produce partial bills for a sub-period within the cycle.

- **CustomerConsumption (Kulutus)**: Water usage data for one active customer for a billing cycle. Contains previous meter reading + date, new meter reading + date, and computed consumption in m³. Provided as the `kulutus` input CSV — created manually or by the tool in a future enhancement. Separate from the bills output.

- **MeterReading (Mittarilukema)**: A water meter measurement at a specific date tied to a meter ID. Two readings (previous, new) define a CustomerConsumption. Meter IDs come from the `osakkaat` customer record.

- **BillLine (Laskurivi)**: A single line item contributing to a bill, with a title, amount, VAT percentage, and an application rule. Defined in the `laskurivit` input CSV.

- **ApplicationRule**: How a BillLine is distributed across customers. Three variants:
  1. **PerActiveCustomer** — total amount split equally among all active (water-connected) customers; each share rounded up to the next whole cent (ceiling).
  2. **PerAllCustomers** — total amount split equally among ALL co-op members including non-connected ones; each share rounded up to the next whole cent.
  3. **PerConsumption** — unit price multiplied by individual water consumption in m³ (not rounded up in the same way — full precision then round to cent normally).

- **Bill (Lasku)**: A complete bill for one customer for one billing cycle. Contains the calculated total and a reference number. Output as a row in the `laskut` CSV (reference number + total) and as a PDF. The detailed line items and meter readings appear in the PDF but the `laskut` CSV is a compact summary.

- **ReferenceNumber (Viitenumero)**: A Finnish bank reference number assigned to each bill using a globally incrementing counter. The counter state is carried forward from the previous run (derived from the highest reference number in the previous `laskut` CSV). Uses the Finnish Viitenumero algorithm (modulo 10 with weights 7-3-1) to append a check digit.

- **Barcode (Viivakoodi)**: A traditional 1D barcode printed on the Finnish bill PDF, encoding key payment information (IBAN, amount, reference number, due date). Machine-readable by bank scanners.

- **VirtualBarcode (Virtuaaliviivakoodi)**: A numeric string representation of the same payment data as the barcode, in the Finnish Banking Association's standardised format. Printed in human-readable form on the bill and included as plain text in the email body so the customer can copy-paste it when paying online.

- **ContactInfo**: The cooperative's own details defined in the `yleiset` CSV: cooperative name, IBAN, y-tunnus (Finnish company ID), contact person name, phone, email. Used in bill PDFs and emails.

- **BillingSummary**: An email report sent to the treasurer after publishing, listing customer names, amounts due, due dates, and reference numbers for the current billing cycle.

- **PaperBillsPDF (Paperilaskut)**: A single merged PDF containing all bill PDFs for customers who prefer paper billing. Produced by the publish step. The treasurer prints this file manually.

### Key Business Rules

- **Active customer definition**: "Active" (aktiivinen) means connected to the water network — has a water meter and is billed for water. This is a property of the customer record, not of the billing cycle. Non-connected co-op members still appear in `osakkaat` but have no meter ID and are only billed for co-op overhead ("all customers" bill lines).

- **Bill line application — "all active" vs "all"**: Active customers pay PerActiveCustomer lines (e.g., main meter basic fee) AND PerAllCustomers lines AND PerConsumption lines. Inactive (non-connected) members pay only PerAllCustomers lines.

- **Rounding — shared bill lines**: For PerActiveCustomer and PerAllCustomers bill lines, each individual customer's share is rounded **up** to the next whole cent (ceiling). This means total collected may slightly exceed the original line amount due to rounding, which is intentional.

- **Default consumption**: If no `kulutus` CSV exists for the current billing cycle, the tool falls back to the consumption values from the previous billing cycle's `kulutus` CSV. This is the default; the user can override by providing an explicit `kulutus` file for the current cycle.

- **File fallback**: If no input file of a given type exists for the current billing cycle, the tool uses the most recent previous file of that type (by date prefix in the filename). File discovery is deterministic based on the date prefix and the year folder.

- **Reference number counter**: Reference numbers are assigned sequentially using a global counter. Each new bill run reads the highest reference number from all previous `laskut` CSV files to establish the starting counter, then increments for each new bill. Counter is not reset between cycles.

- **Mid-cycle ownership transfer**: When a property changes owner mid-cycle, two bills are produced. The **basic fee (PerActiveCustomer)** is split between old and new owner proportionally by calendar days each held ownership within the billing cycle. All **other expenses** (PerAllCustomers, PerConsumption) are charged entirely to the new owner. The consumption (m³) is also attributed entirely to the new owner.

- **Finnish bill standard**: PDFs must include both the traditional barcode and the virtual barcode string in the prescribed Finnish bill layout (Finanssiala specification).

- **Finnish reference number**: Viitenumero algorithm — modulo 10 with weights 7-3-1 applied to the base number to produce a check digit. Must validate correctly against Finnish banking systems.

- **Language**: All user-facing text — CLI option names, help strings, CSV column headers, PDF content, email subject and body — must be in Finnish.

---

## Strategic Approach

### Solution Direction

- Python CLI tool with distinct subcommands for each workflow step: generate bills CSV, generate PDFs, publish (email + merged paper PDF).
- Input CSVs (`osakkaat`, `laskurivit`, `yleiset`, `kulutus`) are read-only inputs; `laskut` CSV and PDFs are outputs. Clean separation — `laskut` is no longer an intermediate read/write artifact.
- File discovery uses date-sorted filename scanning within year-named folders to implement the "use latest if no cycle-specific file exists" rule.
- PDF generation implements Finnish bill layout with barcode and virtual barcode as a standalone module.
- Email delivery via Fastmail SMTP (smtp.fastmail.com:465 SSL or :587 STARTTLS) using Python's `smtplib`. Credentials stored in a local config file (e.g., `~/.vesilasku.env` or `.env`) excluded from version control.
- Paper bills: individual bill PDFs are merged into a single `paperilaskut` PDF for manual printing.

### Key Design Decisions

- **Implementation language**: Python. Broad library ecosystem covers all needs: `click` or `typer` for Finnish-language CLI, `reportlab` or `fpdf2` for PDF, `smtplib` for SMTP, `csv` stdlib for CSV, `pypdf` or `PyPDF2` for PDF merging.

- **Email provider**: Fastmail via SMTP. Fastmail supports app-specific passwords for SMTP authentication (smtp.fastmail.com, port 465). Credentials stored in a local `.env` file, never in CSVs or version control.

- **PDF rendering approach**: Hand-implement Finnish bill layout using a PDF library. The barcode and virtual barcode encoding are implemented as isolated, unit-tested modules derived from the Finanssiala specification.

- **Virtual barcode format**: Finnish Banking Association Virtuaaliviivakoodi version 5 — numeric string encoding IBAN (without spaces), amount (euros and cents, 8 digits), reference number (padded), and due date (YYMMDD). Validated against specification test vectors.

- **Reference number counter persistence**: The tool reads all `laskut` CSV files across all year folders to find the current maximum reference number (base, before check digit). New bills start from max+1. No separate state file needed — the `laskut` CSVs are the authoritative counter source.

- **Mid-cycle split**: Basic fee split by day-ratio (old owner days / total cycle days × fee, new owner days / total cycle days × fee), each share rounded up to cent. All other charges assigned to new owner. Meter consumption attributed entirely to new owner.

- **Paper bills**: Individual bill PDFs are generated first, then merged (in customer-name alphabetical order) into a single `paperilaskut` PDF using a PDF merge library. The merged file is saved alongside the individual PDFs in the year folder.

- **Active customer field in `osakkaat`**: Customers connected to the water network are identified by the presence of a non-empty meter ID. Customers without a meter ID are co-op members only (not water users). No separate "active" boolean field needed.

### Alternatives Considered

- **SQLite instead of CSV**: Would simplify querying. Rejected — requirement explicitly mandates CSV for human-editable transparency and Google Drive compatibility.
- **macOS Mail.app integration for sending**: Avoids SMTP credential management. Rejected — unreliable for automation; SMTP is robust and portable.
- **Separate counter state file for reference numbers**: Simple and explicit. Rejected — `laskut` CSVs already contain all reference numbers and scanning them is deterministic; a separate file creates a synchronisation risk.
- **Per-customer stable reference numbers**: Easier for standing orders. Rejected by owner — the system uses an incrementing counter per bill, not per customer.

---

## Risk & Gap Analysis

### Requirement Ambiguities

- **`kulutus` file fallback vs "same consumption as previous"**: The requirement says "by default the tool uses the same consumption as in the previous billing cycle." Does this mean: (a) use the previous `kulutus` CSV file as the fallback, or (b) copy the consumption numbers from the previous `laskut`-era data? Assumed: the previous `kulutus` CSV serves as fallback if no current-cycle `kulutus` exists. Needs confirmation.

- **"All customers" scope for non-connected members**: How many non-connected co-op members exist in practice? Are they tracked in `osakkaat` with empty meter ID, or maintained separately? The current model assumes empty meter ID = non-connected. Needs confirmation.

- **Mid-cycle ownership transfer — consumption attribution**: Consumption goes entirely to the new owner, but this requires a meter reading at the exact transfer date. Who provides this reading, and is it recorded in the `kulutus` CSV as a separate row for each owner?

- **Reference number counter cold start**: On the very first ever run, no previous `laskut` CSV exists. What is the starting counter value? (e.g., 1, 100, or user-specified?)

- **Billing summary format**: Specified as: customer names, amounts due, due dates, reference numbers. Is this an email with a table? A PDF attachment? Plain text list? Format not specified.

- **`kulutus` CSV for mid-cycle runs**: A mid-cycle run involves two customers for one property. Does the `kulutus` CSV have two rows (one per customer) with a shared meter ID but different date ranges?

### Edge Cases

- **First billing cycle ever**: No previous `kulutus` CSV — default consumption fallback fails. Tool must prompt or error explicitly with a clear Finnish-language message.

- **Active customer joins mid-cycle (not ownership transfer)**: A new customer connects to the network during the cycle. Do they get a full-cycle bill or a pro-rata bill? Ownership-transfer rules likely apply but this case is not explicitly described.

- **Customer list spanning year boundary**: A billing cycle spanning December–January spans two year folders. Which folder gets the output files? Assume: the folder of the cycle end year, but must confirm.

- **Multiple ownership transfers in one cycle for same property**: Three partial bills. The `kulutus` CSV would need three rows for the same meter. The tool must handle duplicate meter IDs across rows.

- **Zero consumption**: Meter reading unchanged. Bill still includes basic fee and shared expenses. PerConsumption line results in zero — should it appear on the PDF or be omitted?

- **Rounding residual visibility**: Customers compare bills with each other. If rounding-up causes different totals for otherwise identical customers, this may prompt questions. Acceptable but worth noting in billing summary or tool output.

- **Email sending failure**: If one customer's email bounces or SMTP fails mid-send, the run must not abort. Partial success must be logged and reported.

- **PDF merge order for `paperilaskut`**: Alphabetical by last name assumed; needs confirmation.

### Technical Risks

- **Finnish virtual barcode specification compliance**: The Virtuaaliviivakoodi format (version 5) is a Finnish Banking Association standard. Encoding error means bills cannot be paid electronically. Mitigation: implement as isolated module with test vectors from the official spec.

- **Finnish reference number algorithm**: Modulo-10 with weights 7-3-1. Must match bank validation exactly. Mitigation: unit-test against known-good examples from Finnish banking documentation.

- **PDF layout fidelity**: Finnish bill PDFs have prescribed layout including barcode positioning. No official automated test suite; validation is visual. Mitigation: generate sample bills and review manually before first real run.

- **Google Drive filesystem mapping**: Files accessed via local mount. Network interruptions or sync delays can cause mid-run failures. Mitigation: validate all required input files exist and are readable before starting any computation.

- **Fastmail SMTP credentials management**: App-specific password must be generated in Fastmail settings (not the account password). Stored in local `.env` file; risk of accidental commit. Mitigation: `.env` in `.gitignore`; tool fails with a clear error if credentials not configured.

- **CSV encoding for Finnish characters**: ä, ö, å must be consistently UTF-8 across all read/write paths. Excel on Windows expects UTF-8 with BOM; Python's `csv` module writes without BOM by default. Mitigation: always write UTF-8-BOM when producing CSVs to ensure Excel compatibility on Mac and Windows.

- **PDF merge library compatibility**: `pypdf` / `PyPDF2` must preserve barcode graphics when merging individual bill PDFs into `paperilaskut`. Mitigation: test merge output with a barcode scanner or banking app.

### Acceptance Criteria Coverage

The requirement describes a workflow but does not contain formal Acceptance Criteria. The table below maps each workflow step to addressability.

| Step | Description | Addressable? | Gaps/Notes |
|------|-------------|--------------|------------|
| 1 | Create/update customer list CSV (`osakkaat`) | Partial | Tool validates; creation is manual. Active/inactive via meter ID presence. |
| 2 | Create/update bill lines CSV (`laskurivit`) | Partial | Tool validates; creation is manual. Rounding-up rule for shared lines. |
| 3 | Create general information CSV (`yleiset`) | Partial | Fields specified: name, IBAN, y-tunnus, contact person, phone, email. |
| 4 | Create customer consumptions CSV (`kulutus`) | Partial | Manual or AI-created. Fallback to previous cycle's `kulutus` if absent. Cold-start unresolved. |
| 5 | Produce customer bills CSV (`laskut`) | Yes | Output: reference number + total per customer. Counter starts from max previous. |
| 5b | User checks/edits `laskut` CSV | Out of scope | Manual step. |
| 6 | Produce bill PDFs (Finnish standard, barcode, virtual barcode) | Yes | Finnish barcode spec must be sourced; layout TBD. |
| 7 | User checks PDFs | Out of scope | Manual step. |
| 8a | Produce paper bills PDF (`paperilaskut`) | Yes | Merged PDF of paper-preference customers. User prints manually. |
| 8b | Send bills by email (PDF + plain text) | Yes | Fastmail SMTP. Credential config via `.env`. |
| 8c | Send billing summary to treasurer | Partial | Content specified (names, amounts, due dates, refs) but format not specified. |
| — | Mid-cycle ownership transfer | Yes | Basic fee by day-ratio; other charges to new owner. Consumption to new owner. |
| — | File fallback (use latest if no cycle-specific file) | Yes | Deterministic date-prefix scanning within year folders. |
| — | Authority reporting | Future | Number of persons field captured but report not in scope for current phase. |
