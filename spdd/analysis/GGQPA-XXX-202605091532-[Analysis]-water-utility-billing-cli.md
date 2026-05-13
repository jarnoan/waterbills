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

Most customers are **active**, meaning they have a water meter and are actually consuming water.
Some customers are not active; they are members of the co-op but are not connected to the water network.

There is a main water meter that meters the total water consumption of the cooperative.

The language used in the system is Finnish. This includes the CSV column titles,
file names, bills, emails and even the command line options and help texts of the tool.
The source code uses English terms.
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
    - meter ID (for active customers, empty if not active)
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
    - main meter ID
- Meter readings CSV (type: `lukemat`)
    - customer name, date when reading was taken, the reading
    - lists only customers who have provided the real reading + main meter
    - name for main meter is `päämittari`
    - in mid-cycle property owner change case the CSV would have a line only for the previous owner
      (the new owner will be billed at regular cycle, from this reading onwards)

The set of output files:
- Customer Bills CSV (type: `laskut`)
    - previous meter reading and date, new meter reading and date, consumption, 
      whether consumption is based on real reading or estimated (same as previous consumption)
    - basic fee share, water cost, total due
- Bill PDFs (type: `lasku`, note: `lastname-firstname`)
- Paper Bill PDFs (type: `paperilaskut`)
    - Contains Bill PDFs for customers who want a paper bill.
- Summary PDF (type: `yhteenveto`)
    - Customers names, amound dues, due dates, reference numbers.
    - Total water usage as measured by the main water meter.
    - Total water usage as summed from customer consumptions.
    - The difference (loss) in cubic meters and as percentage of main water meter consumption.

## Usage

The billing cycle run:
1. User creates a new Customer List CSV if there are changes.
2. User creates a new Bill Lines CSV if there are changes.
3. User creates a new General Information CSV.
4. User creates new Meter Readings CSV.
5. User runs the tool to produce Customer Bills CSV.
    - If a new reading is present in Meter Readings CSV, the tool uses that.
    - If not, the tool estimates the consumption by using the same consumption as in the previous bill.
5. User checks that the Customer Bills CSV looks correct, updates if needed.
6. User runs the tool to produce Bill PDFs.
    - The PDFs should look like standard Finnish bills with bar code and virtual bar code.
7. User checks that the Bill PDFs look correct.
8. User runs the tool to publish the bills.
    - The tool produces Paper Bill PDFs file containing the bills for customers who want a paper bill.
    - Send the bills by email for customers who want the bill by email.
        - Emails should include the PDF as an attachment, and the main details (total, due date, bank account, virtual bar code) as plain text.
    - Send a billing summary to the treasurer by email.

Before the very first run user creates an initial Customer Bills CSV and Meter Readings CSV to be used as a seed.

SMTP server address and authentication information are provided in .env file.

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

- **Customer (Osakas)**: A shareholder/member of the cooperative. Has billing preference (email/paper), a joined date, and optionally a left date (for the record). Customers are tracked in the `osakkaat` CSV — both active and inactive customers appear in this single file. Two sub-populations:
  - **Active customer (aktiivinen osakas)**: Connected to the water network — has a water meter and is actually consuming water. Billed for water-related charges. Identified by a non-empty meter ID in the `osakkaat` record.
  - **Inactive customer**: Member of the co-op but not connected to the water network. Still shares co-op overhead costs (insurance, banking) but is not billed for water consumption or the main meter basic fee. Currently one inactive customer exists in practice.

- **MainMeter (Päämittari)**: A single cooperative-level water meter that measures total water input to the network. Its meter ID is stored in the `yleiset` CSV. Its reading appears in the `lukemat` CSV under the reserved customer name `päämittari`. Used only for water loss reporting in the `yhteenveto` PDF — not associated with any individual customer bill.

- **BillingCycle**: A time period with a start date, end date, and payment due date. Determines the scope of billing. Defined in the `yleiset` input file. Mid-cycle runs produce partial bills for a sub-period within the cycle.

- **MeterReading (Lukema)**: A water meter measurement taken at a specific date, tied to a customer name. Provided in the `lukemat` input CSV — one row per customer who supplied a real reading for this cycle, plus one row for the main meter (`päämittari`). Customers absent from `lukemat` receive an estimated consumption instead.

- **CustomerConsumption (Kulutus)**: Computed (not input) value: the difference between a customer's current meter reading (from `lukemat`) and their previous meter reading (from the latest `laskut` CSV). If no current reading exists for a customer in `lukemat`, consumption is estimated as equal to the value recorded in the previous `laskut` CSV. Flagged as real or estimated in the output.

- **MainMeterConsumption**: Computed from the main meter's current reading (from the current `lukemat`) minus the main meter's previous reading (from the most recent previous `lukemat` file). The main meter has no entry in `laskut` — its reading history is tracked solely through `lukemat` files. Used only for water loss calculation in `yhteenveto`.

- **BillLine (Laskurivi)**: A single line item contributing to a bill, with a title, amount, VAT percentage, and an application rule. Defined in the `laskurivit` input CSV.

- **ApplicationRule**: How a BillLine is distributed across customers. Three variants:
  1. **PerActiveCustomer** — total amount split equally among all active (water-connected) customers; each share rounded up to the next whole cent (ceiling).
  2. **PerAllCustomers** — total amount split equally among ALL co-op members including non-connected ones; each share rounded up to the next whole cent.
  3. **PerConsumption** — unit price multiplied by individual water consumption in m³ (full precision then round to cent normally).

- **BillNumber (Laskunumero)**: A globally incrementing integer counter assigned to each bill. Stored in the `laskut` CSV. The counter is seeded from the highest bill number in the most recent `laskut` file (the previous cycle's output, or the seed on first run). Never reset. Serves as the base from which the bank reference number is computed.

- **Bill (Lasku)**: A complete bill for one customer for one billing cycle. The `laskut` CSV row stores: bill number, previous meter reading + date, new meter reading + date, consumption, real/estimated flag, basic fee share, water cost, total due, bank reference number. The PDF additionally includes barcode, virtual barcode, and contact info. The `laskut` CSV is the authoritative record of readings for each cycle and serves as the source of "previous readings" in the next cycle.

- **ReferenceNumber (Viitenumero)**: A Finnish bank reference number computed from the bill number using the Viitenumero algorithm (modulo 10 with weights 7-3-1) to append a check digit. Stored in the `laskut` CSV alongside the bill number. The seed `laskut` CSV contains bill numbers (and their corresponding reference numbers) so the counter can be bootstrapped on first real run.

- **Barcode (Viivakoodi)**: A traditional 1D barcode printed on the Finnish bill PDF, encoding key payment information (IBAN, amount, reference number, due date). Machine-readable by bank scanners.

- **VirtualBarcode (Virtuaaliviivakoodi)**: A numeric string representation of the same payment data as the barcode, in the Finnish Banking Association's standardised format. Printed in human-readable form on the bill and included as plain text in the email body.

- **ContactInfo**: The cooperative's own details defined in the `yleiset` CSV: cooperative name, IBAN, y-tunnus (Finnish company ID), contact person name, phone, email. Used in bill PDFs and emails.

- **BillingSummary (Yhteenveto)**: A PDF output (`yhteenveto`) produced during the publish step and emailed to the treasurer as an attachment. Structured as two tables: (1) a billing table with customer names, amounts due, due dates, and reference numbers; (2) a water loss table with total main meter consumption, sum of customer consumptions, the difference in m³, and the difference as a percentage of main meter consumption.

- **PaperBillsPDF (Paperilaskut)**: A single merged PDF containing all bill PDFs for customers who prefer paper billing. Produced by the publish step. The treasurer prints this file manually.

### Key Business Rules

- **Active customer definition**: "Active" (aktiivinen) means connected to the water network — has a water meter and is billed for water. Identified by non-empty meter ID in `osakkaat`. Non-connected co-op members have no meter ID and are only billed for co-op overhead ("all customers" bill lines).

- **Bill line application — "all active" vs "all"**: Active customers pay PerActiveCustomer lines (e.g., main meter basic fee) AND PerAllCustomers lines AND PerConsumption lines. Inactive (non-connected) members pay only PerAllCustomers lines.

- **Rounding — shared bill lines**: For PerActiveCustomer and PerAllCustomers bill lines, each individual customer's share is rounded **up** to the next whole cent (ceiling). Total collected may slightly exceed the original line amount — intentional.

- **Consumption derivation**: For each active customer, the tool looks up their current reading in `lukemat`. If found, consumption = current reading − previous reading (from the latest `laskut` CSV). If not found in `lukemat`, consumption = the consumption value recorded in the previous `laskut` CSV (estimated, same-as-last).

- **Estimation flag**: The `laskut` CSV records for each customer whether their consumption is based on a real reading or an estimate. This flag appears on the output CSV row and may appear on the PDF.

- **Seed files for cold start**: Before the very first run, the user creates an initial `laskut` CSV (seed) and an initial `lukemat` CSV (seed). The seed `laskut` contains previous meter readings and bill numbers (with reference numbers), seeding both the reading ledger and the bill number counter. The seed `lukemat` contains the main meter (`päämittari`) reading, seeding the main meter's baseline for water loss calculation on the first real run.

- **File fallback**: If no input file of a given type exists for the current billing cycle, the tool uses the most recent previous file of that type (by date prefix in the filename). File discovery is deterministic based on the date prefix and the year folder. This applies to `osakkaat`, `laskurivit`, and `yleiset`; `lukemat` is always required (either real or seed).

- **Bill number counter**: Bill numbers are assigned sequentially. Each new bill run reads the highest bill number from the most recent `laskut` CSV file (previous cycle output or seed on first run) to establish the starting counter, then increments for each new bill. Counter is never reset. The Finnish bank reference number (Viitenumero) is computed from the bill number by appending a check digit via the modulo-10 weights-7-3-1 algorithm.

- **Main meter in lukemat**: The `lukemat` CSV includes a row for the main meter under the reserved name `päämittari`. This reading is used only for water loss calculation in `yhteenveto` — it does not correspond to any customer bill.

- **Water loss calculation**: `yhteenveto` shows: (a) total consumption from main meter (current minus previous main meter reading), (b) sum of all customer consumptions, (c) difference (a − b) in m³ and as a percentage of (a). A positive loss indicates unaccounted water (leakage, shared-space use, rounding).

- **Mid-cycle ownership transfer**: When a property changes owner mid-cycle, the `lukemat` CSV contains a reading for the **previous owner** at the transfer date. It may optionally also contain an end-of-cycle reading for the **new owner**. If a new-owner end-of-cycle reading is present, new-owner consumption = end-of-cycle reading − transfer-point reading. If absent, new-owner consumption is estimated using the previous owner's consumption from the prior cycle (same-as-last rule). The **basic fee (PerActiveCustomer)** is split between old and new owner proportionally by calendar days each held ownership within the billing cycle. All **other expenses** (PerAllCustomers, PerConsumption) are charged entirely to the new owner.

- **Finnish bill standard**: PDFs must include both the traditional barcode and the virtual barcode string in the prescribed Finnish bill layout (Finanssiala specification).

- **Finnish reference number**: Viitenumero algorithm — modulo 10 with weights 7-3-1 applied to the base number to produce a check digit. Must validate correctly against Finnish banking systems.

- **Language boundary**: All user-facing text (CLI option names, help strings, CSV column headers, PDF content, email subject and body) must be in Finnish. Source code identifiers (variables, functions, classes) use English.

---

## Strategic Approach

### Solution Direction

- Python CLI tool with distinct subcommands for each workflow step: generate bills CSV, generate PDFs, publish (email + merged paper PDF + yhteenveto PDF to treasurer).
- Input CSVs (`osakkaat`, `laskurivit`, `yleiset`, `lukemat`) are read-only inputs; `laskut` CSV and PDFs are outputs. The `laskut` CSV is also the source of previous meter readings for the next cycle.
- Consumption is computed by the tool: current reading from `lukemat` minus previous reading from the latest `laskut` CSV. Estimated consumption (fallback) uses the consumption value from the previous `laskut` row directly.
- File discovery uses date-sorted filename scanning within year-named folders to implement the "use latest if no cycle-specific file exists" rule.
- PDF generation implements Finnish bill layout with barcode and virtual barcode as a standalone module.
- Email delivery via configurable SMTP using Python's `smtplib`. Server address and credentials stored in a local `.env` file excluded from version control.
- Paper bills: individual bill PDFs are merged into a single `paperilaskut` PDF for manual printing.
- `yhteenveto` PDF produced during publish step and emailed to the treasurer; includes water loss report derived from main meter vs. sum of customer consumptions.

### Key Design Decisions

- **Implementation language**: Python. `click` or `typer` for Finnish-language CLI; `reportlab` or `fpdf2` for PDF; `smtplib` for SMTP; `csv` stdlib for CSV; `pypdf` for PDF merging.

- **Email provider**: Configurable SMTP via `.env` file (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`). No provider hardcoded in the tool. Credentials never in CSVs or version control.

- **PDF rendering approach**: Hand-implement Finnish bill layout using a PDF library. Barcode and virtual barcode encoding are isolated, unit-tested modules derived from the Finanssiala specification. `yhteenveto` PDF uses the same PDF library with a different layout template.

- **Virtual barcode format**: Finnish Banking Association Virtuaaliviivakoodi version 5 — numeric string encoding IBAN (without spaces), amount (euros and cents, 8 digits), reference number (padded), and due date (YYMMDD). Validated against specification test vectors.

- **Consumption computation**: The tool reads the latest `laskut` CSV to obtain previous readings. For each active customer, it looks up their meter ID in `lukemat`; if found, computes difference; if not, copies the previous consumption and sets the estimated flag. This makes `laskut` the single authoritative ledger of per-customer readings across cycles.

- **laskut CSV as reading ledger**: The richer `laskut` CSV (with prev/new readings, dates, consumption, flag, fee breakdown) replaces any need for a separate state file for readings. New cycles always read the latest `laskut` CSV to seed previous readings.

- **Bill number counter persistence**: The tool reads the most recent `laskut` CSV file to find the current maximum bill number. New bills start from max+1. Reference number is computed from bill number on the fly via the Viitenumero algorithm. No separate state file needed.

- **Mid-cycle split**: Basic fee split by day-ratio (old owner days / total cycle days × fee, new owner days / total cycle days × fee), each share rounded up to cent. All other charges assigned to new owner. Consumption attributed entirely to new owner.

- **Paper bills**: Individual bill PDFs generated first, then merged (alphabetical by customer last name) into a single `paperilaskut` PDF using a PDF merge library.

- **Active customer field in `osakkaat`**: Customers connected to the water network are identified by the presence of a non-empty meter ID. Customers without a meter ID are co-op members only. No separate boolean field needed.

### Alternatives Considered

- **SQLite instead of CSV**: Would simplify querying. Rejected — requirement explicitly mandates CSV for human-editable transparency and Google Drive compatibility.
- **macOS Mail.app integration**: Avoids SMTP credential management. Rejected — unreliable for automation; SMTP is robust and portable.
- **Separate counter state file for bill numbers**: Simple and explicit. Rejected — `laskut` CSVs already contain all bill numbers; a separate file creates a synchronisation risk.
- **Per-customer stable reference numbers**: Easier for standing orders. Rejected by owner — the system uses an incrementing counter per bill, not per customer.
- **Storing previous readings separately from laskut**: Cleaner separation. Rejected — `laskut` already contains all per-customer reading data; duplicating it creates synchronisation risk.

---

## Risk & Gap Analysis

### Requirement Ambiguities

All previously identified ambiguities have been resolved by the updated requirements:

- **`yhteenveto` email delivery**: ~~Needs confirmation~~ → Confirmed: `yhteenveto` PDF is emailed to the treasurer as an attachment. No inline text summary required.

- **"All customers" scope**: ~~Needs confirmation~~ → Confirmed: all customers (active and inactive) are in the single `osakkaat` CSV, identified by empty meter ID. Currently one inactive customer exists.

- **Mid-cycle ownership transfer — new owner consumption**: ~~Unclear~~ → Confirmed: `lukemat` may optionally include end-of-cycle reading for the new owner. If present, consumption is computed from it; if absent, estimated from previous owner's prior-cycle consumption. Tool must handle both cases and may have two rows per meter ID in `lukemat` (prev-owner at transfer date + new-owner at cycle end).

- **Bill number counter cold start**: ~~Assumed~~ → Confirmed: the seed `laskut` CSV contains bill numbers and reference numbers. The tool reads the highest bill number from the most recent `laskut` file (seed on first run) to establish the counter.

- **Billing summary format**: ~~Layout not specified~~ → Confirmed: two tables — billing table (customers, amounts, due dates, reference numbers) and water loss table (main meter vs. customer sum, difference in m³ and %).

- **Main meter seed reading**: ~~Format undocumented~~ → Confirmed: the seed `lukemat` CSV contains the `päämittari` row, providing the main meter's baseline reading for the first real run.

### Edge Cases

- **Active customer joins mid-cycle (not ownership transfer)**: A new customer connects to the network during the cycle. Do they get a full-cycle bill or a pro-rata bill? Ownership-transfer rules likely apply but this case is not explicitly described.

- **Customer list spanning year boundary**: A billing cycle spanning December–January spans two year folders. Which folder gets the output files? Assume: the folder of the cycle end year, but must confirm.

- **Multiple ownership transfers in one cycle for same property**: Three partial bills. The `lukemat` CSV would need rows for each owner (at each transfer date) plus optionally a cycle-end reading for the last new owner. The tool must handle multiple rows per meter ID in `lukemat`.

- **Zero consumption**: Meter reading unchanged. Bill still includes basic fee and shared expenses. PerConsumption line results in zero — should it appear on the PDF or be omitted?

- **Missing main meter reading in lukemat**: If `päämittari` row is absent from `lukemat`, water loss calculation in `yhteenveto` cannot be performed. Tool must handle this gracefully — either skip the water loss section with a note, or error with a clear Finnish message.

- **Rounding residual visibility**: Customers compare bills. Rounding-up may cause different totals for otherwise identical customers. Acceptable but worth noting in `yhteenveto` or tool output.

- **Email sending failure**: If one customer's email bounces or SMTP fails mid-send, the run must not abort. Partial success must be logged and reported. `yhteenveto` email to treasurer should be sent last (or separately) to ensure all customer bills are attempted first.

- **PDF merge order for `paperilaskut`**: Alphabetical by last name assumed; needs confirmation.

- **Seed file columns**: The seed `laskut` CSV must contain all columns the tool reads: customer name, meter ID, previous/new readings + dates, consumption, flag, fee breakdown, bill number, reference number. The seed `lukemat` must include the `päämittari` row. Both formats must be documented for the user.

### Technical Risks

- **Finnish virtual barcode specification compliance**: Encoding error means bills cannot be paid electronically. Mitigation: implement as isolated module with test vectors from the official spec.

- **Finnish reference number algorithm**: Modulo-10 with weights 7-3-1. Must match bank validation exactly. Mitigation: unit-test against known-good examples from Finnish banking documentation.

- **PDF layout fidelity**: Finnish bill PDFs have prescribed layout including barcode positioning. No official automated test suite; validation is visual. Mitigation: generate sample bills and review manually before first real run.

- **Google Drive filesystem mapping**: Files accessed via local mount. Network interruptions or sync delays can cause mid-run failures. Mitigation: validate all required input files exist and are readable before starting any computation.

- **SMTP credentials management**: Credentials stored in local `.env` file; risk of accidental commit. Mitigation: `.env` in `.gitignore`; tool fails with a clear error if credentials not configured.

- **CSV encoding for Finnish characters**: ä, ö, å must be consistently UTF-8 across all read/write paths. Excel on Windows expects UTF-8 with BOM. Mitigation: always write UTF-8-BOM when producing CSVs.

- **PDF merge library compatibility**: `pypdf` must preserve barcode graphics when merging individual bill PDFs into `paperilaskut`. Mitigation: test merge output with a barcode scanner or banking app.

- **Consumption derivation correctness**: Finding "previous reading" by scanning the latest `laskut` CSV must be deterministic. If a customer's meter ID changed, or if the `laskut` CSV was manually edited, the lookup could return wrong data. Mitigation: validate meter IDs against `osakkaat` before computing; warn on mismatches.

### Acceptance Criteria Coverage

The requirement describes a workflow but does not contain formal Acceptance Criteria. The table below maps each workflow step to addressability.

| Step | Description | Addressable? | Gaps/Notes |
|------|-------------|--------------|------------|
| 1 | Create/update customer list CSV (`osakkaat`) | Partial | Tool validates; creation is manual. Active/inactive via meter ID presence. |
| 2 | Create/update bill lines CSV (`laskurivit`) | Partial | Tool validates; creation is manual. Rounding-up rule for shared lines. |
| 3 | Create general information CSV (`yleiset`) | Partial | Adds main meter ID field. |
| 4 | Create meter readings CSV (`lukemat`) | Partial | Manual or AI-created. Only real readings included; main meter as `päämittari`. |
| 5 | Produce customer bills CSV (`laskut`) | Yes | Rich output: bill number, readings, consumption, flag, fee breakdown, reference number. Consumption derived from `lukemat` vs previous `laskut`. |
| 5b | User checks/edits `laskut` CSV | Out of scope | Manual step. |
| 6 | Produce bill PDFs (Finnish standard, barcode, virtual barcode) | Yes | Finnish barcode spec must be sourced; layout TBD. |
| 7 | User checks PDFs | Out of scope | Manual step. |
| 8a | Produce paper bills PDF (`paperilaskut`) | Yes | Merged PDF of paper-preference customers. User prints manually. |
| 8b | Send bills by email (PDF + plain text) | Yes | Configurable SMTP via `.env`. |
| 8c | Send `yhteenveto` PDF to treasurer | Yes | PDF output with water loss data; emailed as attachment. |
| — | Seed files for cold start | Yes | User creates initial `laskut` CSV and `lukemat` CSV before first run. |
| — | Mid-cycle ownership transfer | Yes | Basic fee by day-ratio; other charges to new owner; `lukemat` has prev-owner reading at transfer date. |
| — | File fallback (use latest if no cycle-specific file) | Yes | Deterministic date-prefix scanning within year folders. |
| — | Water loss reporting | Yes | Main meter vs. sum of customer consumptions; shown in `yhteenveto`. |
| — | Authority reporting | Future | Number of persons field captured but report not in scope for current phase. |
