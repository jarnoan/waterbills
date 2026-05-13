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
Some customers are not active (currently only one); they are members of the co-op but are not connected to the water network.

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
    - This includes both active and inactive customers.
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
    - bill number (global increasing counter), bank reference number computed from bill number
- Bill PDFs (type: `lasku`, note: `lastname-firstname`)
- Paper Bill PDFs (type: `paperilaskut`)
    - Contains Bill PDFs for customers who want a paper bill.
- Summary PDF (type: `yhteenveto`)
    - Customers names, amound dues, due dates, reference numbers as a table.
    - Total water usage data as a table:
        - As measured by the main water meter.
        - As summed from customer consumptions.
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
    - The tool sends the bills by email for customers who want the bill by email.
        - Emails should include the PDF as an attachment, and the main details (total, due date, bank account, virtual bar code) as plain text.
    - The tool sends the Summary PDF to the treasurer by email as an attachment.

### Property owner changing mid-cycle

Meter Readings CSV contains mid-cycle reading for the old owner.
It can also contain end-of-cycle reading for the new owner.
If it does not contain end-of-cycle reading for the new owner, 
the consumption of the old owner from the previous cycle is used as an estimate.

### Initial seeding

Before the very first run user creates an initial Customer Bills CSV and Meter Readings CSV to be used as a seed.

The initial Meter Readings CSV contains the main meter reading.

The initial Customer Bills CSV contains also bill numbers and bank reference numbers, 
so that the tool can use the largest bill number as a base for the first run.

### Configuration

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
