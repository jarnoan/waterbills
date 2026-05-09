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
    - name, address, email, meter ID, billing preference (email/paper), when joined, when left, property id, number of persons
- Bill Lines CSV (type: `laskurivit`)
    - title
    - amount
    - VAT percentage
    - how to apply:
        - shared by all active customers (main meter basic fee)
        - shared by all customers (insurance, banking fees, other expenses)
        - multiplied by water consumption (water price per cubic meter)
- General Information CSV (type: `yleiset`)
    - billing cycle beginning and end dates
    - due date
    - contact information

The set of output files:
- Customer Bills CSV (type: `laskut`)
    - previous meter reading and date, new meter reading and date, consumption, reference number, bill total
- Bill PDFs (type: `lasku`, note: `lastname-firstname`)

## Usage

A billing cycle run:
1. Create new customer list CSV if there are changes.
2. Create new bill lines CSV if there are changes.
3. Create new general information CSV.
4. Run the tool to produce customer bills CSV.
    - By default the tool uses the same consumption as in the previous billing cycle.
5. Check that the customer bills CSV looks correct, update if needed.
6. Run the tool to produce bill PDFs.
    - The PDFs should look like standard Finnish bills with bar code and virtual bar code.
7. Check that the bill PDFs look correct.
8. Run the tool to publish the bills.
    - Print the bills for customers who want a paper bill.
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
but once they do, the tool should fetch the readings from there.

### Web usage

The tool could be transformed to a function-as-a-service kind of cloud based service
that would provide a web interface.

### Checking the payments

The tool could use some banking API to check if customers have paid their bills
and report the status.

### E-billing

The tool could use some banking API to generate E-bills.

