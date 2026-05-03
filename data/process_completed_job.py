"""
process_completed_job.py - Drop a completed job folder, get it in the database.

Put these files in the folder before running:
  - invoice*.pdf or estimate*.pdf   (the paid invoice)
  - *.txt                           (time/site-visit data - see format below)
  - *.png / *.jpg                   (Maps screenshot - logged but not parsed yet)

Txt format (flexible - as long as these pieces appear somewhere):
  Judy Ester
  101 Bayview Dr. Mountain Home, AR 72653

  20260502    clocked  in: 10:30am
              clocked out: 11:30am

  (Multiple date blocks are supported.)

Usage:
  cd data
  python process_completed_job.py                              # use default folder
  python process_completed_job.py "C:\\path\\to\\folder"      # specify folder
  python process_completed_job.py --dry-run                   # preview, no DB writes
"""

import os
import re
import sys
import shutil
import sqlite3
import pdfplumber
import requests
from datetime import datetime, timedelta

# If set, jobs are posted to Railway instead of the local DB
RAILWAY_URL = os.environ.get('RAILWAY_URL', '').rstrip('/')
ADMIN_KEY = os.environ.get('ADMIN_KEY', '')

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), 'beard_business.db')
APP_INVOICES_DIR = os.path.join(os.path.dirname(__file__), '..', 'Invoices')
DEFAULT_FOLDER = r'C:\Users\bbria\OneDrive\Desktop\BHS Job Complete to be Processed'

# CDT offset (May–Oct in Mountain Home AR); CST is -06:00 (Nov–Mar)
TZ_OFFSET = '-05:00'

# ---------------------------------------------------------------------------
# Service standardization
# ---------------------------------------------------------------------------
# Each entry: ([keywords_any_match], standardized_name, category, service_type)
# Listed most-specific first; first match wins (case-insensitive).

SERVICE_MAPPING = [
    # --- Materials (always first so they're never mis-labeled labor) ---
    (['material', 'reimbursement', 'lowes', ' hd ', 'hd receipt', 'redimix',
      'allsteel', 'lumber', 'supplies', 'hardware', 'ereceipt', 'concrete:',
      'sealer', 'trailer tires'],
     'Materials', 'Materials', 'materials'),

    # --- Painting ---
    (['paint walls', 'painting walls', 'wall paint'],
     'Interior Painting Walls', 'Painting/Staining Labor', 'labor'),
    (['paint ceiling', 'painting ceiling', 'ceiling paint'],
     'Interior Painting Ceiling', 'Painting/Staining Labor', 'labor'),
    (['paint trim', 'painting trim', 'trim paint', 'trim stain'],
     'Interior Paint Trim', 'Painting/Staining Labor', 'labor'),
    (['exterior paint', 'paint exterior', 'house exterior paint'],
     'House Exterior Paint Labor', 'Painting - Exterior', 'labor'),
    (['paint prep', 'surface prep', 'power wash and surface'],
     'Power Wash and Surface Prep', 'Painting - Surface Prep', 'labor'),
    (['paint', 'painting', 'staining', 'stain'],
     'Interior Painting Labor', 'Painting/Staining Labor', 'labor'),

    # --- Decks ---
    (['deck construction', 'new deck', 'deck installation', 'wood decking'],
     'Deck Construction Labor', 'Deck Construction Labor', 'labor'),
    (['covered pergola', 'pergola installation'],
     'Covered Pergola Installation', 'Deck Construction Labor', 'labor'),
    (['deck repair', 'deck and building repair', 'refinish deck'],
     'Deck Repair and Stain', 'Deck Repair & Restoration Labor', 'labor'),
    (['deck removal', 'deck disassembly', 'deck haul'],
     'Deck Removal / Haul-Away', 'Deck Repair & Restoration Labor', 'labor'),
    (['lattice stain'],
     'Lattice Staining', 'Deck Repair & Restoration Labor', 'labor'),

    # --- Flooring ---
    (['subfloor repair', 'subfoor repair'],
     'Bathroom Subfloor Repair Labor', 'Flooring Installation Labor', 'labor'),
    (['flooring install', 'laminate flooring', 'vinyl flooring', 'flooring installation',
      'kitchen flooring', 'bathroom flooring'],
     'Flooring Installation Labor', 'Flooring Installation Labor', 'labor'),

    # --- Tile ---
    (['caulk replacement', 'caulk tub', 'caulk shower'],
     'Caulk Replacement', 'Tile Installation Labor', 'labor'),
    (['grout repair', 'grout kitchen', 'grout bathroom', 'grout shower'],
     'Grout Repair Shower', 'Tile Installation Labor', 'labor'),
    (['mortar repair'],
     'Mortar Repair', 'Tile Installation Labor', 'labor'),
    (['tile install', 'tile installation'],
     'Tile Installation Labor', 'Tile Installation Labor', 'labor'),
    (['tub and tile', 'tub tile refinish'],
     'Tub and Tile Refinish', 'Tile Installation Labor', 'labor'),

    # --- Bathroom ---
    (['shower conversion', 'shower leak', 'bath - shower'],
     'Bath - Shower Conversion Labor', 'Bathroom Remodel Labor', 'labor'),
    (['bath glass', 'glass sealant'],
     'Bath Glass Sealant', 'Bathroom Remodel Labor', 'labor'),
    (['toilet tank', 'toilet replacement'],
     'Toilet Tank Replacement', 'Bathroom Remodel Labor', 'labor'),
    (['bathroom vanity', 'vanity replacement'],
     'Bathroom Vanity Replacement', 'Bathroom Remodel Labor', 'labor'),
    (['bathroom sink plumb', 'sink plumb'],
     'Bathroom Sink Plumbing', 'Bathroom Remodel Labor', 'labor'),
    (['bathroom', 'bath '],
     'Bathroom / Kitchen Labor', 'Bathroom Remodel Labor', 'labor'),

    # --- Plumbing ---
    (['garbage disposal install', 'garbage disposal'],
     'Garbage Disposal Installation Labor', 'Plumbing Labor', 'labor'),
    (['water heater', 'hot water heater'],
     'Hot Water Heater Replacement Labor', 'Plumbing Labor', 'labor'),
    (['kitchen faucet', 'faucet replacement', 'faucet repair'],
     'Kitchen Faucet Replacement', 'Plumbing Labor', 'labor'),
    (['water shutoff', 'water shutof'],
     'Water Shutoff Valve', 'Plumbing Labor', 'labor'),
    (['dishwasher leak', 'dishwasher repair'],
     'Dishwasher Leak Repair', 'Plumbing Labor', 'labor'),
    (['plumbing', 'leak repair', 'drain water'],
     'Plumbing / Leak Repair Labor', 'Plumbing Labor', 'labor'),

    # --- Gutters / Roofing ---
    (['gutter install', 'gutter labor'],
     'Gutter Install Labor', 'Gutter & Roofing Labor', 'labor'),
    (['gutter leak', 'gutter repair'],
     'Gutter Leak Repair', 'Gutter & Roofing Labor', 'labor'),
    (['downspout'],
     "Downspout's Underground Pipes", 'Gutter & Roofing Labor', 'labor'),
    (['pipe boot', 'roof pipe boot'],
     'Pipe Boot Installation Labor', 'Roofing - Metal Roof', 'labor'),
    (['shingle roof'],
     'Shingle Roof Repair Labor', 'Roofing - Shingle', 'labor'),
    (['shed roof'],
     'Shed Roof Labor', 'General Handyman Labor', 'labor'),

    # --- Fence ---
    (['privacy fence', 'fence labor', 'fence construction'],
     'Privacy Fence labor', 'Fence Construction Labor', 'labor'),

    # --- Screen ---
    (['patio screen', 'screen replacement', 'rescreening'],
     'Patio Screen Replacement', 'Screen & Enclosure Labor', 'labor'),

    # --- Landscaping ---
    (['flower bed', 'lawn edging', 'lawn reclaim', 'limb removal',
      'rock bed', 'landscaping', 'lawn'],
     "Flower Bed's Labor", 'Landscaping Labor', 'labor'),

    # --- Concrete ---
    (['concrete pad', 'concrete steps', 'concrete labor', 'concrete finishing'],
     'Concrete Pad Installation Labor', 'Concrete Pad Installation Labor', 'labor'),
    (['culvert labor'],
     'Culvert Labor', 'Concrete Pad Installation Labor', 'labor'),

    # --- Kitchen ---
    (['countertop', 'counter top'],
     'Countertop Replacement', 'Kitchen Remodel Labor', 'labor'),
    (['cabinet sink', 'cabinet spacer'],
     'Cabinet Sink Base Repair', 'Kitchen Remodel Labor', 'labor'),
    (['kitchen sink refinish', 'kitchen sink replacement'],
     'Kitchen Sink Replacement', 'Kitchen Remodel Labor', 'labor'),

    # --- Doors / Windows / Trim ---
    (['exterior door', 'door replacement'],
     'Exterior Door Replacement', 'Door/Window Installation Labor', 'labor'),
    (['crawlspace door'],
     'Crawlspace Door', 'Door/Window Installation Labor', 'labor'),
    (['hang door', 'door install'],
     'Hang Door', 'Door/Window Installation Labor', 'labor'),
    (['baseboard', 'casing', 'molding', 'trim install'],
     'Trim Install', 'Door/Window Installation Labor', 'labor'),
    (['door seal'],
     'Door Seal (front door)', 'Door/Window Installation Labor', 'labor'),

    # --- Appliances ---
    (['electric fireplace'],
     'Electric Fireplace Installation', 'Appliance Installation Labor', 'labor'),
    (['floating mantle', 'mantle'],
     'Floating Mantle Installation', 'Appliance Installation Labor', 'labor'),
    (['microwave', 'range hood'],
     'Over the Range Microwave Installation Labor', 'Appliance Installation Labor', 'labor'),
    (['tv wall mount', 'wall mount'],
     'TV Wall Mount', 'Appliance Installation Labor', 'labor'),
    (['dishwasher install'],
     'Garbage Disposal Installation Labor', 'Appliance Installation Labor', 'labor'),

    # --- Drywall ---
    (['drywall repair', 'drywall patch'],
     'Drywall Repair and Paint', 'Drywall - Repair & Paint', 'labor'),

    # --- Demolition ---
    (['haul away', 'debris', 'demolition', 'antenna removal'],
     'Demolition / Debris Haulaway', 'Demolition & Hauling Labor', 'labor'),

    # --- Asphalt ---
    (['asphalt', 'driveway repair'],
     'Asphalt Repair Labor', 'Asphalt & Paving Labor', 'labor'),

    # --- Insulation ---
    (['insulation', 'crawlspace insul'],
     'Crawlspace Insulation Reinstall', 'Insulation - Crawlspace', 'labor'),

    # --- General handyman (catch-all last) ---
    ([],
     'General Handyman Labor', 'General Handyman Labor', 'labor'),
]

TYPO_FIXES = {
    'bathtoom': 'Bathroom',
    'subfoor': 'Subfloor',
    'refnish': 'Refinish',
    'troubleshoor': 'Troubleshoot',
    'shutof': 'Shutoff',
    'preperation': 'Preparation',
    'fnish': 'Finish',
}


def fix_typos(text):
    result = text
    for typo, fix in TYPO_FIXES.items():
        result = re.sub(typo, fix, result, flags=re.IGNORECASE)
    return result


def standardize_service(raw_description):
    """Return (standardized_name, category, service_type) for a raw service description."""
    desc = raw_description.lower()
    for keywords, std_name, category, stype in SERVICE_MAPPING:
        if not keywords:
            return std_name, category, stype
        for kw in keywords:
            if kw in desc:
                return std_name, category, stype
    return 'General Handyman Labor', 'General Handyman Labor', 'labor'


# ---------------------------------------------------------------------------
# Invoice PDF parser (same logic as import_pdf_invoices.py)
# ---------------------------------------------------------------------------

SERVICE_LINE_RE = re.compile(
    r'^(.+?)\s+(\d+(?:\.\d+)?)\s+\$[\d,]+\.\d{2}(?:\s+\$[\d,]+\.\d{2})?\s+\*?\$?([\d,]+\.\d{2}|null)\s*$'
)
PRICES_ONLY_RE = re.compile(
    r'^(\d+(?:\.\d+)?)\s+\$[\d,]+\.\d{2}(?:\s+\$[\d,]+\.\d{2})?\s+\*?\$?([\d,]+\.\d{2}|null)\s*$'
)
TOTAL_RE = re.compile(r'^(?:Grand\s+)?Total\s+\$([\d,]+\.\d{2})\s*$')
PAID_DATE_RE = re.compile(r'Paid\s+on\s+(\d{4}/\d{2}/\d{2})')
PHONE_RE = re.compile(r'(\+?1?[\s\-.]?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4})')
ADDRESS_RE = re.compile(
    r'(\d+\s+[\w\s]+(?:Dr|Ave|St|Rd|Way|Blvd|Ln|Ct|Hwy|Circle|Cir)\b[.,]?\s+[\w\s]+,\s*(?:AR|TN|MO|OK|TX|MS|AL|GA|FL|LA)\s+\d{5})',
    re.IGNORECASE
)


def parse_pdf_invoice(fpath):
    with pdfplumber.open(fpath) as pdf:
        text = pdf.pages[0].extract_text() or ''

    lines = [l.strip() for l in text.strip().splitlines()]
    result = {
        'customer_name': None,
        'invoice_number': None,
        'invoice_date': None,
        'paid_date': None,
        'phone': None,
        'address': None,
        'services': [],
        'total': 0.0,
        'status': 'paid',
    }

    for i, line in enumerate(lines):
        if re.match(r'^To:\s+(?:Customer\s+\S+|Project Quote\s+\S+)', line):
            if i + 1 < len(lines):
                name_line = lines[i + 1]
                name_line = re.sub(r'\s+Agreement\s*#\s*$', '', name_line).strip()
                name_line = re.sub(r'\s+#\s*$', '', name_line).strip()
                result['customer_name'] = name_line
            break

    for line in lines:
        m = re.search(r'^Project\s+#\s+(\w+)\s*$', line)
        if m:
            result['invoice_number'] = m.group(1)
            break

    for line in lines:
        m = re.search(r'Date\s+(\d{4}/\d{2}/\d{2})', line)
        if m:
            result['invoice_date'] = m.group(1).replace('/', '-')
            break

    for line in lines:
        m = PAID_DATE_RE.search(line)
        if m:
            result['paid_date'] = m.group(1).replace('/', '-')
            break

    full_text = '\n'.join(lines)
    phone_m = PHONE_RE.search(full_text)
    if phone_m:
        result['phone'] = phone_m.group(1).strip()

    addr_m = ADDRESS_RE.search(full_text)
    if addr_m:
        result['address'] = addr_m.group(1).strip()

    in_services = False
    service_lines = []
    for line in lines:
        if 'Service Type' in line and 'Quantity' in line:
            in_services = True
            continue
        if in_services:
            if line.startswith('*Indicates') or line.startswith('Subtotal') or TOTAL_RE.match(line):
                break
            if line:
                service_lines.append(line)

    pending = []
    for line in service_lines:
        fm = SERVICE_LINE_RE.match(line)
        pm = PRICES_ONLY_RE.match(line)
        if fm:
            desc = fm.group(1).strip()
            raw_amt = fm.group(3)
            amt = 0.0 if raw_amt == 'null' else float(raw_amt.replace(',', ''))
            std_name, cat, stype = standardize_service(desc)
            result['services'].append({
                'original': desc,
                'standardized': fix_typos(std_name),
                'category': cat,
                'type': stype,
                'amount': amt,
            })
            pending = []
        elif pm:
            raw_amt = pm.group(2)
            amt = 0.0 if raw_amt == 'null' else float(raw_amt.replace(',', ''))
            desc = ' '.join(pending[-2:]).strip() or 'Service'
            std_name, cat, stype = standardize_service(desc)
            result['services'].append({
                'original': desc,
                'standardized': fix_typos(std_name),
                'category': cat,
                'type': stype,
                'amount': amt,
            })
            pending = []
        else:
            pending.append(line)

    for line in lines:
        m = TOTAL_RE.match(line)
        if m:
            result['total'] = float(m.group(1).replace(',', ''))
            break

    return result


# ---------------------------------------------------------------------------
# Time / site-visit txt parser
# ---------------------------------------------------------------------------

TIME_RE = re.compile(r'(\d{1,2}:\d{2})\s*(am|pm)', re.IGNORECASE)
DATE_BLOCK_RE = re.compile(r'(\d{8})\s+clocked\s+in\s*:\s*(\d{1,2}:\d{2}\s*(?:am|pm))', re.IGNORECASE)
OUT_RE = re.compile(r'clocked\s+out\s*:\s*(\d{1,2}:\d{2}\s*(?:am|pm))', re.IGNORECASE)


def parse_12h(time_str):
    """Parse '10:30am' or '10:30 am' -> datetime.time"""
    m = re.match(r'(\d{1,2}):(\d{2})\s*(am|pm)', time_str.strip(), re.IGNORECASE)
    if not m:
        return None
    h, mn, meridiem = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if meridiem == 'pm' and h != 12:
        h += 12
    if meridiem == 'am' and h == 12:
        h = 0
    return h, mn


def calc_hours(h_in, m_in, h_out, m_out):
    total_in = h_in * 60 + m_in
    total_out = h_out * 60 + m_out
    if total_out <= total_in:
        total_out += 24 * 60
    return (total_out - total_in) / 60.0


def parse_time_txt(fpath):
    """Return list of {date, start_time, end_time, hours} dicts."""
    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    entries = []
    # Find date blocks: 8-digit date followed by clock-in
    date_sections = re.split(r'(?=\d{8}\s+clocked\s+in)', content, flags=re.IGNORECASE)

    for section in date_sections:
        date_m = re.match(r'(\d{8})', section.strip())
        if not date_m:
            continue
        raw_date = date_m.group(1)
        entry_date = raw_date[:4] + '-' + raw_date[4:6] + '-' + raw_date[6:8]

        in_m = re.search(r'clocked\s+in\s*:\s*(\d{1,2}:\d{2}\s*(?:am|pm))', section, re.IGNORECASE)
        out_m = re.search(r'clocked\s+out\s*:\s*(\d{1,2}:\d{2}\s*(?:am|pm))', section, re.IGNORECASE)

        if not in_m or not out_m:
            continue

        in_parsed = parse_12h(in_m.group(1))
        out_parsed = parse_12h(out_m.group(1))
        if not in_parsed or not out_parsed:
            continue

        h_in, m_in = in_parsed
        h_out, m_out = out_parsed
        hours = calc_hours(h_in, m_in, h_out, m_out)

        start_iso = '{0}T{1:02d}:{2:02d}:00.000{3}'.format(entry_date, h_in, m_in, TZ_OFFSET)
        end_iso = '{0}T{1:02d}:{2:02d}:00.000{3}'.format(entry_date, h_out, m_out, TZ_OFFSET)

        entries.append({
            'date': entry_date,
            'start_time': start_iso,
            'end_time': end_iso,
            'hours': round(hours, 4),
            'arrival_time': '{0} {1:02d}:{2:02d}:00'.format(entry_date, h_in, m_in),
            'departure_time': '{0} {1:02d}:{2:02d}:00'.format(entry_date, h_out, m_out),
        })

    return entries


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_or_create_customer(cur, name, address=None, phone=None):
    cur.execute('SELECT id, address, phone FROM customers WHERE name = ?', (name,))
    row = cur.fetchone()
    if row:
        cust = dict(row)
        updates = {}
        if address and not cust.get('address'):
            updates['address'] = address
        if phone and not cust.get('phone'):
            updates['phone'] = phone
        if updates:
            sets = ', '.join(k + ' = ?' for k in updates)
            cur.execute('UPDATE customers SET ' + sets + ' WHERE id = ?',
                        list(updates.values()) + [cust['id']])
        return cust['id'], False
    cur.execute('INSERT INTO customers (name, address, phone) VALUES (?, ?, ?)',
                (name, address, phone))
    return cur.lastrowid, True


def import_job(cur, parsed, time_entries, pdf_filename, dry_run=False):
    inv_num = parsed['invoice_number']
    if not inv_num:
        return False, 'no invoice number found in PDF'

    cur.execute('SELECT id FROM invoices WHERE invoice_number = ?', (inv_num,))
    if cur.fetchone():
        return False, 'invoice ' + inv_num + ' already in database'

    customer_name = parsed['customer_name'] or 'Unknown'
    invoice_date = parsed['invoice_date']
    services = parsed['services']

    total_labor = sum(s['amount'] for s in services if s['type'] == 'labor')
    total_materials = sum(s['amount'] for s in services if s['type'] == 'materials')
    total_amount = parsed['total'] or (total_labor + total_materials)

    total_hours = sum(e['hours'] for e in time_entries)
    summary = (
        'Customer: ' + customer_name +
        ' | Invoice: ' + inv_num +
        ' | Date: ' + str(invoice_date) +
        ' | Total: $' + str(round(total_amount, 2)) +
        ' | Services: ' + str(len(services)) +
        ' | Time entries: ' + str(len(time_entries)) +
        ' | Total hours: ' + str(round(total_hours, 2))
    )

    if dry_run:
        return True, summary

    cust_id, created = get_or_create_customer(
        cur, customer_name, parsed.get('address'), parsed.get('phone')
    )

    cur.execute('''
        INSERT INTO jobs (customer_id, invoice_id, project_number, start_date, status)
        VALUES (?, ?, ?, ?, 'completed')
    ''', (cust_id, inv_num, inv_num, invoice_date))
    job_id = cur.lastrowid

    cur.execute('''
        INSERT INTO invoices
        (invoice_number, customer_id, job_id, total_labor, total_materials,
         total_amount, invoice_date, status, pdf_filename)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'paid', ?)
    ''', (inv_num, cust_id, job_id, total_labor, total_materials,
          total_amount, invoice_date, pdf_filename))
    invoice_id = cur.lastrowid

    for svc in services:
        cur.execute('''
            INSERT INTO services_performed
            (invoice_id, job_id, original_description, standardized_description,
             category, amount, service_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (invoice_id, job_id,
              svc['original'],
              svc['standardized'],
              svc['category'],
              svc['amount'],
              svc['type']))

    svc_desc = ', '.join(s['standardized'] for s in services)
    for te in time_entries:
        cur.execute('''
            INSERT INTO time_entries
            (customer_id, job_id, entry_date, start_time, end_time, hours,
             description, source, cost_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'manual', 'Billable')
        ''', (cust_id, job_id, te['date'], te['start_time'], te['end_time'],
              te['hours'], svc_desc))

    for te in time_entries:
        customer_address = parsed.get('address') or ''
        cur.execute('''
            INSERT INTO timeline_visits
            (customer_id, job_id, visit_date, arrival_time, departure_time,
             duration_hours, address, source, matched)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'manual', 1)
        ''', (cust_id, job_id, te['date'], te['arrival_time'], te['departure_time'],
              te['hours'], customer_address))

    return True, summary


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def find_files(folder):
    pdf_files, txt_files, img_files = [], [], []
    for fname in os.listdir(folder):
        fpath = os.path.join(folder, fname)
        if not os.path.isfile(fpath):
            continue
        low = fname.lower()
        if low == 'desktop.ini':
            continue
        if low.endswith('.pdf') and (low.startswith('invoice') or low.startswith('estimate')):
            pdf_files.append(fpath)
        elif low.endswith('.txt'):
            txt_files.append(fpath)
        elif low.endswith(('.png', '.jpg', '.jpeg', '.webp')):
            img_files.append(fpath)
    return pdf_files, txt_files, img_files


def archive_files(folder, invoice_number, files):
    """Move processed files into a Processed/<date>_<invoice#> subfolder."""
    stamp = datetime.now().strftime('%Y%m%d')
    archive_dir = os.path.join(folder, 'Processed', stamp + '_' + str(invoice_number))
    os.makedirs(archive_dir, exist_ok=True)
    for fpath in files:
        dest = os.path.join(archive_dir, os.path.basename(fpath))
        shutil.move(fpath, dest)
    return archive_dir


def copy_invoice_to_library(src_path, invoice_number):
    """Copy the invoice PDF to the app's Invoices folder."""
    dest_dir = os.path.abspath(APP_INVOICES_DIR)
    os.makedirs(dest_dir, exist_ok=True)
    fname = 'invoice' + str(invoice_number) + '.pdf'
    dest = os.path.join(dest_dir, fname)
    if not os.path.exists(dest):
        shutil.copy2(src_path, dest)
        return dest
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(folder, dry_run=False):
    print('Processing folder: ' + folder)
    if dry_run:
        print('[DRY RUN] No DB changes will be written.\n')

    if not os.path.isdir(folder):
        print('ERROR: folder not found: ' + folder)
        return 1

    pdf_files, txt_files, img_files = find_files(folder)

    if not pdf_files:
        print('ERROR: No invoice PDF found in folder.')
        print('  Expected a file starting with "invoice" or "estimate" ending in .pdf')
        return 1

    if len(pdf_files) > 1:
        print('WARNING: Multiple PDFs found. Using first one: ' + pdf_files[0])

    pdf_path = pdf_files[0]
    pdf_name = os.path.basename(pdf_path)

    print('\nParsing invoice: ' + pdf_name)
    parsed = parse_pdf_invoice(pdf_path)

    print('  Customer:    ' + str(parsed['customer_name']))
    print('  Invoice #:   ' + str(parsed['invoice_number']))
    print('  Date:        ' + str(parsed['invoice_date']))
    print('  Total:       $' + str(parsed['total']))
    print('  Phone:       ' + str(parsed['phone']))
    print('  Address:     ' + str(parsed['address']))
    print('  Services:')
    for svc in parsed['services']:
        print('    [' + svc['type'] + '] ' + svc['original'] +
              ' -> "' + svc['standardized'] + '" (' + svc['category'] + ') $' + str(svc['amount']))

    time_entries = []
    for txt_path in txt_files:
        print('\nParsing time file: ' + os.path.basename(txt_path))
        entries = parse_time_txt(txt_path)
        if entries:
            for e in entries:
                print('  ' + e['date'] + '  in: ' + e['start_time'][11:16] +
                      '  out: ' + e['end_time'][11:16] +
                      '  hours: ' + str(e['hours']))
            time_entries.extend(entries)
        else:
            print('  (no clock-in/out entries found)')

    if img_files:
        print('\nScreenshot(s) found (logged, not parsed):')
        for f in img_files:
            print('  ' + os.path.basename(f))

    print()

    if dry_run:
        # Dry run: just show the summary, no writes anywhere
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        ok, detail = import_job(cur, parsed, time_entries, pdf_name, dry_run=True)
        conn.close()
        if ok:
            print('[DRY RUN] Would import: ' + detail)
        else:
            print('[!] Skipped: ' + detail)
        return 0 if ok else 1

    if RAILWAY_URL:
        # --- Remote mode: POST to Railway API ---
        print('Sending to Railway: ' + RAILWAY_URL)
        payload = {
            'customer_name': parsed['customer_name'],
            'invoice_number': parsed['invoice_number'],
            'invoice_date': parsed['invoice_date'],
            'paid_date': parsed.get('paid_date'),
            'phone': parsed.get('phone'),
            'address': parsed.get('address'),
            'services': parsed['services'],
            'time_entries': time_entries,
            'total': parsed['total'],
            'pdf_filename': pdf_name,
        }
        try:
            resp = requests.post(
                RAILWAY_URL + '/api/import-job',
                json=payload,
                headers={'X-Admin-Key': ADMIN_KEY},
                timeout=30
            )
            if resp.status_code == 201:
                r = resp.json()
                print('[+] Imported to Railway: ' + str(r))
                dest = copy_invoice_to_library(pdf_path, parsed['invoice_number'])
                if dest:
                    print('[+] Invoice copied to local library: ' + os.path.basename(dest))
                all_files = pdf_files + txt_files + img_files
                archive_dir = archive_files(folder, parsed['invoice_number'], all_files)
                print('[+] Files archived to: ' + archive_dir)
                return 0
            elif resp.status_code == 409:
                print('[!] Already in Railway DB: invoice ' + str(parsed['invoice_number']))
                return 1
            else:
                print('[!] Railway error ' + str(resp.status_code) + ': ' + resp.text)
                return 1
        except Exception as e:
            print('[!] Could not reach Railway: ' + str(e))
            return 1
    else:
        # --- Local mode: write directly to local SQLite ---
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        ok, detail = import_job(cur, parsed, time_entries, pdf_name)
        if ok:
            conn.commit()
            print('[+] Imported locally: ' + detail)
            dest = copy_invoice_to_library(pdf_path, parsed['invoice_number'])
            if dest:
                print('[+] Invoice copied to library: ' + os.path.basename(dest))
            all_files = pdf_files + txt_files + img_files
            archive_dir = archive_files(folder, parsed['invoice_number'], all_files)
            print('[+] Files archived to: ' + archive_dir)
        else:
            print('[!] Skipped: ' + detail)
        conn.close()
        return 0 if ok else 1


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    dry_run = '--dry-run' in sys.argv

    folder = args[0] if args else DEFAULT_FOLDER
    sys.exit(run(folder, dry_run=dry_run))
