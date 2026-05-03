"""
Import new-format invoice PDFs into the database.

New format (Oct 2025+): actual PDF files from new invoicing software.
Different from old InvoiceBee ZIP format (invoiceBHS*.pdf).

Files: Invoices/Not-processed-Invoices/invoice*.pdf
Invoice number: from "Project # XXXXXXXX" line
Customer name:  line after "To: Customer XXXXXXXX", strip " Agreement #" suffix

Idempotent - safe to run multiple times. Skips invoices already in DB.

Usage:
  cd data
  python import_pdf_invoices.py
  python import_pdf_invoices.py --dry-run
"""

import sqlite3
import os
import re
import glob
import sys

import pdfplumber

DB_PATH = os.path.join(os.path.dirname(__file__), 'beard_business.db')
INVOICE_DIR = os.path.join(os.path.dirname(__file__), '..', 'Invoices', 'Not-processed-Invoices')


# ---------------------------------------------------------------------------
# Category + type classification (same rules as import_invoices.py)
# ---------------------------------------------------------------------------

CATEGORY_RULES = [
    (['material', 'sealer', 'reimbursement', 'lowes purchase', 'hd ', 'redimix',
      'allsteel', 'column materials', 'deck materials', 'deck replacement materials',
      'gutter install materials', 'flower beds materials', 'lawn edging materials',
      'tile installation materials', 'bathtoom subfoor repair materials',
      'pergola materials', 'new border materials', 'trailer tires',
      'materials ereceipt', 'materials: concrete', 'hd receipt', 'lowes receipt',
      'culvert materials', 'redimix concrete materials',
      ], 'Materials'),

    (['deck construction', 'deck installation labor', 'wood decking installation',
      'new deck', 'covered pergola installation', 'pergola installation'],
     'Deck Construction Labor'),

    (['deck repair', 'deck and building repairs', 'refnish deck', 'refinish deck',
      'existing deck disassembly', 'deck removal', 'lattice staining',
      'deck stain', 'deck repair and stain'],
     'Deck Repair & Restoration Labor'),

    (['asphalt', 'driveway repair'],
     'Asphalt & Paving Labor'),

    (['painting', 'staining', 'paint ', 'paint\t', 'interior paint', 'exterior paint',
      'siding repair', 'paint prep', 'organizing, cleaning, floor, paint prep'],
     'Painting/Staining Labor'),

    (['flooring installation', 'flooring, vinyl', 'laminate flooring',
      'vinyl bathroom flooring', 'kitchen flooring', 'replace subfoor',
      'bathtoom subfoor repair labor', 'subfoor repair labor',
      'flooring install'],
     'Flooring Installation Labor'),

    (['tile installation labor', 'tile install', 'grout repair', 'mortar repair',
      'tub and tile', 'caulk replacement'],
     'Tile Installation Labor'),

    (['bathroom', 'bath - shower', 'bath glass', 'bathtoom', 'shower conversion',
      'shower leak', 'tub and tile', 'toilet', 'bathroom sink'],
     'Bathroom Remodel Labor'),

    (['plumbing', 'faucet', 'water heater', 'dishwasher', 'water shutof',
      'water shutoff', 'garbage disposal', 'drain water', 'sink plumb',
      'leak repair labor', 'plumbing / leak'],
     'Plumbing Labor'),

    (['gutter', 'downspout', 'roofing'],
     'Gutter & Roofing Labor'),

    (['privacy fence', 'fence labor', 'fence construction'],
     'Fence Construction Labor'),

    (['screen replacement', 'patio screen', 'rescreening'],
     'Screen & Enclosure Labor'),

    (['lawn', 'flower bed', 'limb removal', 'rock bed', 'lawn edging',
      'lawn reclaim', 'landscaping'],
     'Landscaping Labor'),

    (['covered pergola', 'pergola'],
     'Outdoor Structure Labor'),

    (['concrete finishing', 'concrete steps', 'concrete pad',
      'additional labor (concrete)', 'concrete labor', 'culvert labor'],
     'Concrete Pad Installation Labor'),

    (['kitchen remodel', 'countertop', 'cabinet sink', 'cabinet spacer',
      'kitchen sink refnish', 'kitchen sink replacement'],
     'Kitchen Remodel Labor'),

    (['door', 'window', 'trim install', 'baseboard', 'casing', 'molding',
      'crawlspace door', 'door seal', 'exterior door', 'hang door'],
     'Door/Window Installation Labor'),

    (['haul away', 'demolition', 'debris', 'deck removal / haul',
      'antenna removal'],
     'Demolition & Hauling Labor'),

    (['microwave', 'range hood', 'appliance', 'electric fireplace',
      'floating mantle', 'tv wall mount', 'dishwasher install'],
     'Appliance Installation Labor'),

    (['ac return', 'insulation', 'shed roof', 'shed'],
     'General Handyman Labor'),
]


def categorize_service(description):
    desc = description.lower()
    for keywords, category in CATEGORY_RULES:
        for kw in keywords:
            if kw in desc:
                return category
    return 'General Handyman Labor'


def classify_type(description):
    desc = description.lower()
    material_kw = [
        'material', 'sealer', 'reimbursement', 'lowes', ' hd ', 'hd receipt',
        'lowes receipt', 'redimix', 'allsteel', 'trailer tires', 'concrete:',
        'lumber', 'supplies', 'hardware', 'ereceipt', 'culvert material',
        'redimix concrete',
    ]
    for kw in material_kw:
        if kw in desc:
            return 'materials'
    if categorize_service(description) == 'Materials':
        return 'materials'
    return 'labor'


STANDARDIZE = {
    'bathtoom': 'Bathroom',
    'subfoor': 'Subfloor',
    'refnish': 'Refinish',
    'troubleshoor': 'Troubleshoot',
    'shutof': 'Shutoff',
    'fow': 'Flow',
    'preperation': 'Preparation',
    'fnish': 'Finish',
    'oerings': 'Orings',
}


def standardize_description(description):
    result = description
    for typo, fix in STANDARDIZE.items():
        result = re.sub(typo, fix, result, flags=re.IGNORECASE)
    return result


# ---------------------------------------------------------------------------
# PDF parser
# ---------------------------------------------------------------------------

# Service line: Description  Qty  $Price  *?$Amount
# New format always uses *$Amount (non-taxable) - same regex as old format
SERVICE_RE = re.compile(
    r'^(.+?)\s+(\d+(?:\.\d+)?)\s+\$[\d,]+\.\d{2}(?:\s+\$[\d,]+\.\d{2})?\s+\*?\$?([\d,]+\.\d{2}|null)\s*$'
)
PRICES_ONLY_RE = re.compile(
    r'^(\d+(?:\.\d+)?)\s+\$[\d,]+\.\d{2}(?:\s+\$[\d,]+\.\d{2})?\s+\*?\$?([\d,]+\.\d{2}|null)\s*$'
)
TOTAL_RE = re.compile(r'^(?:Grand\s+)?Total\s+\$([\d,]+\.\d{2})\s*$')


def extract_text_from_pdf(fpath):
    """Extract all text from PDF, page 1 is main invoice content."""
    with pdfplumber.open(fpath) as pdf:
        # Page 1 has all invoice data; page 2+ are payment receipts
        return pdf.pages[0].extract_text() or ''


def parse_invoice_text(text):
    """Parse extracted PDF text and return structured invoice data."""
    lines = [l.strip() for l in text.strip().splitlines()]

    result = {
        'customer_name': None,
        'invoice_number': None,
        'invoice_date': None,
        'services': [],
        'total': 0.0,
    }

    # --- Customer name ---
    # The PDF layout merges the name line with "Agreement #":
    #   "Mike Lenz Agreement #"
    # We look for the line after "To: Customer XXXXXXXX"
    for i, line in enumerate(lines):
        # Matches: "To: Customer 20251010", "To: Customer BHS20230527", or "To: Project Quote EST..."
        if re.match(r'^To:\s+(?:Customer\s+\S+|Project Quote\s+\S+)', line):
            if i + 1 < len(lines):
                name_line = lines[i + 1]
                # Strip trailing " Agreement #" or " #" from PDF column merge
                name_line = re.sub(r'\s+Agreement\s*#\s*$', '', name_line).strip()
                name_line = re.sub(r'\s+#\s*$', '', name_line).strip()
                result['customer_name'] = name_line
            break

    # --- Invoice number from "Project # XXXXXXXX" ---
    for line in lines:
        match = re.search(r'^Project\s+#\s+(\d+)\s*$', line)
        if match:
            result['invoice_number'] = match.group(1)
            break

    # --- Invoice date ---
    for line in lines:
        match = re.search(r'Date\s+(\d{4}/\d{2}/\d{2})', line)
        if match:
            result['invoice_date'] = match.group(1).replace('/', '-')
            break

    # --- Services section ---
    service_section = []
    in_services = False
    for line in lines:
        if 'Service Type' in line and 'Quantity' in line and 'Price' in line:
            in_services = True
            continue
        if in_services:
            if line.startswith('*Indicates') or line.startswith('Subtotal') or TOTAL_RE.match(line):
                break
            if line:
                service_section.append(line)

    pending_parts = []
    for line in service_section:
        full_match = SERVICE_RE.match(line)
        prices_match = PRICES_ONLY_RE.match(line)

        if full_match:
            desc = full_match.group(1).strip()
            raw_amount = full_match.group(3)
            amount = 0.0 if raw_amount == 'null' else float(raw_amount.replace(',', ''))
            _add_service(result['services'], desc, amount)
            pending_parts = []

        elif prices_match:
            raw_amount = prices_match.group(2)
            amount = 0.0 if raw_amount == 'null' else float(raw_amount.replace(',', ''))
            desc_parts = pending_parts[-2:] if len(pending_parts) > 2 else pending_parts
            desc = ' '.join(desc_parts).strip() or 'Service'
            _add_service(result['services'], desc, amount)
            pending_parts = []

        else:
            pending_parts.append(line)

    # --- Total ---
    for line in lines:
        match = TOTAL_RE.match(line)
        if match:
            result['total'] = float(match.group(1).replace(',', ''))
            break

    return result


def _add_service(services_list, description, amount):
    std_desc = standardize_description(description)
    services_list.append({
        'description': description,
        'standardized_description': std_desc,
        'amount': amount,
        'type': classify_type(description),
        'category': categorize_service(description),
    })


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_or_create_customer(cursor, name):
    cursor.execute('SELECT id FROM customers WHERE name = ?', (name,))
    row = cursor.fetchone()
    if row:
        return row['id']
    cursor.execute('INSERT INTO customers (name) VALUES (?)', (name,))
    return cursor.lastrowid


def import_invoice(cursor, parsed, pdf_filename, dry_run=False):
    inv_num = parsed['invoice_number']
    if not inv_num:
        return False, 'no invoice number'

    cursor.execute('SELECT id FROM invoices WHERE invoice_number = ?', (inv_num,))
    if cursor.fetchone():
        return False, 'already in DB'

    customer_name = parsed['customer_name'] or 'Unknown'
    invoice_date = parsed['invoice_date']
    services = parsed['services']

    total_labor = sum(s['amount'] for s in services if s['type'] == 'labor')
    total_materials = sum(s['amount'] for s in services if s['type'] == 'materials')
    total_amount = parsed['total'] or (total_labor + total_materials)

    summary = (customer_name + ' | ' + str(invoice_date) +
               ' | $' + str(round(total_amount, 2)) +
               ' | ' + str(len(services)) + ' services')

    if dry_run:
        return True, summary

    customer_id = get_or_create_customer(cursor, customer_name)

    cursor.execute('''
        INSERT INTO jobs (customer_id, invoice_id, project_number, start_date, status)
        VALUES (?, ?, ?, ?, 'completed')
    ''', (customer_id, inv_num, inv_num, invoice_date))
    job_id = cursor.lastrowid

    cursor.execute('''
        INSERT INTO invoices
        (invoice_number, customer_id, job_id, total_labor, total_materials,
         total_amount, invoice_date, status, pdf_filename)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'paid', ?)
    ''', (inv_num, customer_id, job_id, total_labor, total_materials,
          total_amount, invoice_date, pdf_filename))
    invoice_id = cursor.lastrowid

    for svc in services:
        cursor.execute('''
            INSERT INTO services_performed
            (invoice_id, job_id, original_description, standardized_description,
             category, amount, service_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (invoice_id, job_id,
              svc['description'],
              svc['standardized_description'],
              svc['category'],
              svc['amount'],
              svc['type']))

    return True, summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(dry_run=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # invoice2*.pdf = new date-only format (invoice20251010.pdf etc.)
    # invoiceBHS*.pdf = old InvoiceBee PDF format (not ZIP)
    # estimate*.pdf = estimates treated as invoices
    invoice_files = sorted(set(
        glob.glob(os.path.join(INVOICE_DIR, 'invoice2*.pdf')) +
        glob.glob(os.path.join(INVOICE_DIR, 'invoiceBHS*.pdf')) +
        glob.glob(os.path.join(INVOICE_DIR, 'estimate*.pdf'))
    ))
    print('Found ' + str(len(invoice_files)) + ' invoice file(s) in ' + os.path.abspath(INVOICE_DIR))
    if dry_run:
        print('[DRY RUN] No changes will be written.\n')

    imported = 0
    skipped = 0
    errors = []

    for fpath in invoice_files:
        fname = os.path.basename(fpath)
        try:
            text = extract_text_from_pdf(fpath)
            parsed = parse_invoice_text(text)

            if not parsed['invoice_number']:
                errors.append(fname + ': could not parse invoice number')
                continue

            ok, detail = import_invoice(cursor, parsed, fname, dry_run=dry_run)

            if ok:
                print('  [+] ' + fname + ': ' + detail)
                imported += 1
            else:
                print('  [=] ' + fname + ': ' + detail)
                skipped += 1

        except Exception as e:
            errors.append(fname + ': ' + str(e))

    if not dry_run:
        conn.commit()

    conn.close()

    print()
    print('=' * 60)
    if dry_run:
        print('  Would import: ' + str(imported))
        print('  Would skip:   ' + str(skipped))
    else:
        print('  Imported:  ' + str(imported))
        print('  Skipped:   ' + str(skipped) + ' (already in DB)')
    if errors:
        print('  Errors:    ' + str(len(errors)))
        for e in errors:
            print('    - ' + e)
    print('=' * 60)

    return imported


if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    run(dry_run=dry_run)
