"""
Beard's Home Services API
Flask backend serving data from SQLite database.
"""

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import sqlite3
import os
import re
import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta, timezone
import math
import time as _time
import io
import base64
import hashlib

BRIAN_HOME_ADDRESS = os.environ.get('BRIAN_HOME_ADDRESS', '360 County Road 35, Clarkridge, AR 72623')
BRIAN_HOME_LAT = 36.46519470   # 360 County Rd 35, Clarkridge AR 72623
BRIAN_HOME_LON = -92.31659698


def _init_home_coords():
    global BRIAN_HOME_LAT, BRIAN_HOME_LON
    try:
        encoded = urllib.parse.quote(BRIAN_HOME_ADDRESS + ', USA')
        url = f'https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1'
        req = urllib.request.Request(url, headers={'User-Agent': 'BeardHomeServices/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            geo = json.loads(resp.read())
        if geo:
            BRIAN_HOME_LAT = float(geo[0]['lat'])
            BRIAN_HOME_LON = float(geo[0]['lon'])
    except Exception:
        pass


_init_home_coords()

app = Flask(__name__)
CORS(app)

# Database path — Railway sets DB_PATH env var pointing to a volume
_BUNDLED_DB = os.path.join(os.path.dirname(__file__), '..', 'data', 'beard_business.db')
DB_PATH = os.environ.get('DB_PATH', _BUNDLED_DB)

# If running on Railway with a Volume and the volume DB doesn't exist yet,
# seed it from the bundled copy so existing data carries over.
if os.environ.get('DB_PATH') and not os.path.exists(DB_PATH) and os.path.exists(_BUNDLED_DB):
    import shutil as _shutil
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    _shutil.copy2(_BUNDLED_DB, DB_PATH)

# React build output (served in production)
FRONTEND_DIST = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')


def migrate_db():
    """Run schema migrations at startup — safe to run multiple times."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # trips table
    cursor.execute('''CREATE TABLE IF NOT EXISTS trips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trip_date TEXT NOT NULL,
        trip_type TEXT NOT NULL,
        destination TEXT,
        customer_id INTEGER REFERENCES customers(id),
        job_id INTEGER REFERENCES jobs(id),
        miles REAL,
        drive_time_minutes INTEGER,
        notes TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )''')

    # cya_notes on customers
    try:
        cursor.execute('ALTER TABLE customers ADD COLUMN cya_notes TEXT')
    except Exception:
        pass

    # photos_album_url on jobs
    try:
        cursor.execute('ALTER TABLE jobs ADD COLUMN photos_album_url TEXT')
    except Exception:
        pass

    # data_status on jobs (e.g. 'incomplete' to flag missing time entries)
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN data_status TEXT DEFAULT NULL")
    except:
        pass

    # trip_skip on time_entries (1 = user dismissed the suggested-trip prompt)
    try:
        conn.execute("ALTER TABLE time_entries ADD COLUMN trip_skip INTEGER DEFAULT 0")
    except:
        pass

    # customer_lat / customer_lon — cached geocoords for clock-in GPS matching
    try:
        conn.execute("ALTER TABLE customers ADD COLUMN customer_lat REAL")
    except:
        pass
    try:
        conn.execute("ALTER TABLE customers ADD COLUMN customer_lon REAL")
    except:
        pass

    # source on materials_expenses (tracks how expense was entered)
    try:
        conn.execute("ALTER TABLE materials_expenses ADD COLUMN source TEXT DEFAULT NULL")
    except:
        pass

    # leads table — inbound calls/texts waiting to be actioned
    cursor.execute('''CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT DEFAULT 'sms',
        from_number TEXT,
        contact_name TEXT,
        message TEXT,
        received_at TEXT,
        status TEXT DEFAULT 'new',
        customer_id INTEGER REFERENCES customers(id),
        job_id INTEGER REFERENCES jobs(id),
        notes TEXT,
        metadata TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )''')
    try:
        cursor.execute("ALTER TABLE leads ADD COLUMN metadata TEXT")
    except Exception:
        pass

    # excluded_numbers — personal contacts that should never create leads
    cursor.execute('''CREATE TABLE IF NOT EXISTS excluded_numbers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        label TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )''')

    # payments table
    cursor.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER REFERENCES jobs(id),
        customer_id INTEGER REFERENCES customers(id),
        amount REAL NOT NULL,
        payment_date TEXT,
        payment_method TEXT DEFAULT 'cash',
        memo TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )''')

    # Bulk-mark historical completed jobs as paid (one-time migration)
    try:
        cursor.execute('''
            INSERT INTO payments (job_id, customer_id, amount, payment_date, payment_method, memo)
            SELECT j.id, j.customer_id,
                   COALESCE(i.total_labor, 0) + COALESCE(i.total_materials, 0),
                   COALESCE(i.invoice_date, j.start_date, '2024-01-01'),
                   'Other',
                   'Historical payment (imported)'
            FROM jobs j
            LEFT JOIN invoices i ON j.id = i.job_id
            WHERE j.status = 'completed'
              AND (COALESCE(i.total_labor, 0) + COALESCE(i.total_materials, 0)) > 0
              AND j.id NOT IN (SELECT DISTINCT job_id FROM payments WHERE job_id IS NOT NULL)
        ''')
    except Exception:
        pass

    # ── Jazzlyn Pay ────────────────────────────────────────────────────────────

    # Service items catalog — pre-defined tasks with agreed rates
    cursor.execute('''CREATE TABLE IF NOT EXISTS jazzy_service_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        default_rate REAL NOT NULL,
        category TEXT DEFAULT 'General',
        sort_order INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (datetime('now'))
    )''')

    # Seed default service items (safe to re-run — INSERT OR IGNORE)
    _seed_items = [
        ('Facebook Post (Create & Schedule)', 4.00,  'Social Media',    10),
        ('GMB Business Post',                 4.00,  'Social Media',    20),
        ('Instagram Post',                    4.00,  'Social Media',    30),
        ('Lead Follow-Up (Text/Message)',      3.00,  'Lead Management', 10),
        ('Lead Follow-Up (Phone Call)',        5.00,  'Lead Management', 20),
        ('Review Response (Google/Facebook)',  2.00,  'Lead Management', 30),
        ('Estimate Follow-Up',                4.00,  'Lead Management', 40),
        ('Appointment Scheduled',             8.00,  'Job Conversion',  10),
        ('Job Closed - Small (under $500)',   15.00,  'Job Conversion',  20),
        ('Job Closed - Medium ($500-$2000)', 35.00,  'Job Conversion',  30),
        ('Job Closed - Large ($2000+)',       75.00,  'Job Conversion',  40),
        ('General Admin Task',                5.00,  'Admin',           10),
        ('Research & Pricing',                8.00,  'Admin',           20),
        ('Customer Communication (Email)',    3.00,  'Admin',           30),
        ('Inbox / Message Monitoring (1 hr)', 8.00,  'Admin',           40),
    ]
    for _name, _rate, _cat, _ord in _seed_items:
        try:
            cursor.execute(
                'INSERT OR IGNORE INTO jazzy_service_items (name, default_rate, category, sort_order) VALUES (?, ?, ?, ?)',
                (_name, _rate, _cat, _ord)
            )
        except Exception:
            pass

    # Jazzlyn's invoices to Brian
    cursor.execute('''CREATE TABLE IF NOT EXISTS jazzy_invoices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_number TEXT UNIQUE,
        status TEXT DEFAULT 'draft',
        total_amount REAL DEFAULT 0,
        notes TEXT,
        submitted_at TEXT,
        paid_at TEXT,
        paid_notes TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )''')

    # Line items on each invoice
    cursor.execute('''CREATE TABLE IF NOT EXISTS jazzy_invoice_lines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_id INTEGER NOT NULL REFERENCES jazzy_invoices(id),
        service_item_id INTEGER REFERENCES jazzy_service_items(id),
        description TEXT NOT NULL,
        qty INTEGER DEFAULT 1,
        rate REAL NOT NULL,
        line_total REAL NOT NULL,
        assignment_type TEXT DEFAULT 'business',
        job_ref TEXT,
        notes TEXT,
        is_complete INTEGER DEFAULT 1,
        sort_order INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now'))
    )''')

    # sms_leads — conversation threads from SMS Forwarder, used by the lead extractor
    cursor.execute('''CREATE TABLE IF NOT EXISTS sms_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT NOT NULL UNIQUE,
        first_contact TEXT,
        last_message TEXT,
        thread_json TEXT,
        last_extraction_json TEXT,
        lockbox_code TEXT,
        ntfy_sent_count INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT (datetime('now'))
    )''')

    conn.commit()
    conn.close()


migrate_db()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row):
    return dict(row) if row else None


def rows_to_list(rows):
    return [dict(row) for row in rows]


# ============================================================
# DASHBOARD
# ============================================================

@app.route('/api/dashboard')
def dashboard():
    conn = get_db()
    cursor = conn.cursor()

    # Optional date range filters
    start = request.args.get('start')
    end = request.args.get('end')
    date_range = {'start': start, 'end': end}

    # Build date-filter fragments
    # For invoices: filter on invoice_date (with fallback to jobs.start_date via JOIN)
    if start and end:
        inv_date_filter = "AND COALESCE(i.invoice_date, j.start_date) BETWEEN ? AND ?"
        inv_date_params = [start, end]
        inv_simple_filter = "AND invoice_date BETWEEN ? AND ?"
        inv_simple_params = [start, end]
        te_date_filter = "AND entry_date BETWEEN ? AND ?"
        te_date_params = [start, end]
        job_date_filter = "AND j.start_date BETWEEN ? AND ?"
        job_date_params = [start, end]
        sp_date_filter = "AND j.start_date BETWEEN ? AND ?"
        sp_date_params = [start, end]
    elif start:
        inv_date_filter = "AND COALESCE(i.invoice_date, j.start_date) >= ?"
        inv_date_params = [start]
        inv_simple_filter = "AND invoice_date >= ?"
        inv_simple_params = [start]
        te_date_filter = "AND entry_date >= ?"
        te_date_params = [start]
        job_date_filter = "AND j.start_date >= ?"
        job_date_params = [start]
        sp_date_filter = "AND j.start_date >= ?"
        sp_date_params = [start]
    elif end:
        inv_date_filter = "AND COALESCE(i.invoice_date, j.start_date) <= ?"
        inv_date_params = [end]
        inv_simple_filter = "AND invoice_date <= ?"
        inv_simple_params = [end]
        te_date_filter = "AND entry_date <= ?"
        te_date_params = [end]
        job_date_filter = "AND j.start_date <= ?"
        job_date_params = [end]
        sp_date_filter = "AND j.start_date <= ?"
        sp_date_params = [end]
    else:
        inv_date_filter = ''
        inv_date_params = []
        inv_simple_filter = ''
        inv_simple_params = []
        te_date_filter = ''
        te_date_params = []
        job_date_filter = ''
        job_date_params = []
        sp_date_filter = ''
        sp_date_params = []

    exp_date_filter = te_date_filter.replace('entry_date', 'expense_date')
    exp_date_params = te_date_params

    # Total labor / materials from invoices
    cursor.execute(f'''
        SELECT SUM(i.total_labor) as labor, SUM(i.total_materials) as materials
        FROM invoices i
        LEFT JOIN jobs j ON i.job_id = j.id
        WHERE 1=1 {inv_date_filter}
    ''', inv_date_params)
    revenue = cursor.fetchone()

    # Total hours from time_entries
    cursor.execute(f'''
        SELECT SUM(hours) as total FROM time_entries
        WHERE 1=1 {te_date_filter}
    ''', te_date_params)
    hours = cursor.fetchone()

    cursor.execute(f'''
        SELECT COUNT(DISTINCT j.customer_id) as count
        FROM jobs j
        JOIN customers c ON j.customer_id = c.id
        WHERE c.name != '_UNASSIGNED' AND j.status != 'estimate' {job_date_filter}
    ''', job_date_params)
    customers = cursor.fetchone()

    cursor.execute(f'''
        SELECT COUNT(*) as count FROM jobs j WHERE 1=1 {job_date_filter}
    ''', job_date_params)
    jobs_count = cursor.fetchone()

    cursor.execute(f'''
        SELECT COUNT(*) as count FROM invoices i
        LEFT JOIN jobs j ON i.job_id = j.id
        WHERE 1=1 {inv_date_filter}
    ''', inv_date_params)
    invoice_count = cursor.fetchone()

    # Average days on site per job (distinct calendar days with time entries)
    cursor.execute(f'''
        SELECT AVG(day_count) as avg_days
        FROM (
            SELECT te.job_id, COUNT(DISTINCT te.entry_date) as day_count
            FROM time_entries te
            WHERE te.job_id IS NOT NULL {te_date_filter}
            GROUP BY te.job_id
            HAVING day_count > 0
        )
    ''', te_date_params)
    avg_days_row = cursor.fetchone()

    # Revenue by year (or by month when a date range is active)
    if start or end:
        cursor.execute(f'''
            SELECT SUBSTR(COALESCE(i.invoice_date, j.start_date), 1, 7) as month,
                   SUM(i.total_labor) as total_labor,
                   SUM(i.total_materials) as total_materials,
                   SUM(i.total_amount) as total_revenue
            FROM invoices i
            LEFT JOIN jobs j ON i.job_id = j.id
            WHERE COALESCE(i.invoice_date, j.start_date) IS NOT NULL {inv_date_filter}
            GROUP BY month
            ORDER BY month
        ''', inv_date_params)
        revenue_by_period = rows_to_list(cursor.fetchall())
        period_key = 'revenue_by_month'
    else:
        cursor.execute('''
            SELECT SUBSTR(invoice_date, 1, 4) as year,
                   SUM(total_labor) as total_labor,
                   SUM(total_materials) as total_materials,
                   SUM(total_amount) as total_revenue
            FROM invoices
            WHERE invoice_date IS NOT NULL
            GROUP BY year
            ORDER BY year
        ''')
        revenue_by_period = rows_to_list(cursor.fetchall())
        period_key = 'revenue_by_year'

    # Recent jobs
    cursor.execute(f'''
        SELECT j.id, j.invoice_id, c.name as customer_name, j.start_date, j.status,
               COALESCE(i.total_labor, 0) as total_labor,
               COALESCE(i.total_materials, 0) as total_materials,
               COALESCE(i.total_amount, 0) as total_amount,
               (SELECT COUNT(DISTINCT entry_date) FROM time_entries WHERE job_id = j.id) as actual_days
        FROM jobs j
        JOIN customers c ON j.customer_id = c.id
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE j.status != 'estimate' {job_date_filter}
        ORDER BY j.start_date DESC
        LIMIT 10
    ''', job_date_params)
    recent_jobs = rows_to_list(cursor.fetchall())

    # Top customers by labor revenue
    cursor.execute(f'''
        SELECT c.id, c.name,
               COUNT(DISTINCT j.id) as job_count,
               COALESCE(SUM(i.total_labor), 0) as total_revenue,
               COALESCE(SUM(te_sub.hours), 0) as total_hours
        FROM customers c
        LEFT JOIN jobs j ON c.id = j.customer_id {("AND j.start_date BETWEEN ? AND ?" if (start and end) else ("AND j.start_date >= ?" if start else ("AND j.start_date <= ?" if end else "")))}
        LEFT JOIN invoices i ON j.id = i.job_id
        LEFT JOIN (
            SELECT customer_id, SUM(hours) as hours FROM time_entries
            WHERE 1=1 {te_date_filter}
            GROUP BY customer_id
        ) te_sub ON c.id = te_sub.customer_id
        WHERE c.name != '_UNASSIGNED'
        GROUP BY c.id
        HAVING total_revenue > 0
        ORDER BY total_revenue DESC
        LIMIT 8
    ''', job_date_params + te_date_params)
    top_customers = rows_to_list(cursor.fetchall())

    # Revenue by service category
    cursor.execute(f'''
        SELECT sp.category,
               COUNT(DISTINCT sp.job_id) as job_count,
               SUM(sp.amount) as total_revenue,
               ROUND(AVG(sp.amount), 2) as avg_revenue
        FROM services_performed sp
        JOIN jobs j ON sp.job_id = j.id
        WHERE sp.service_type = 'labor' AND sp.category IS NOT NULL {sp_date_filter}
        GROUP BY sp.category
        ORDER BY total_revenue DESC
        LIMIT 12
    ''', sp_date_params)
    by_category = rows_to_list(cursor.fetchall())

    # Estimation accuracy
    cursor.execute(f'''
        SELECT COUNT(*) as total,
               SUM(CASE WHEN actual_days <= estimated_days THEN 1 ELSE 0 END) as on_time,
               ROUND(AVG(estimated_days), 1) as avg_estimated,
               ROUND(AVG(actual_days), 1) as avg_actual
        FROM (
            SELECT j.estimated_days,
                   COUNT(DISTINCT te.entry_date) as actual_days
            FROM jobs j
            JOIN time_entries te ON te.job_id = j.id
            WHERE j.estimated_days IS NOT NULL AND j.estimated_days > 0 {job_date_filter}
            GROUP BY j.id
        )
    ''', job_date_params)
    est_row = cursor.fetchone()

    # Total expenses in period
    cursor.execute(f'''
        SELECT COALESCE(SUM(cost), 0) as total
        FROM materials_expenses
        WHERE 1=1 {exp_date_filter}
    ''', exp_date_params)
    expenses_row = cursor.fetchone()

    # Hourly rate: exclude incomplete jobs from both labor and hours
    cursor2 = conn.cursor()
    cursor2.execute(f'''
        SELECT SUM(i.total_labor) as labor
        FROM invoices i
        LEFT JOIN jobs j ON i.job_id = j.id
        WHERE 1=1 {inv_date_filter}
          AND (j.data_status IS NULL OR j.data_status != 'incomplete')
    ''', inv_date_params)
    rate_labor_row = cursor2.fetchone()

    cursor2.execute(f'''
        SELECT SUM(hours) as total FROM time_entries
        WHERE 1=1 {te_date_filter}
          AND (job_id IS NULL OR job_id NOT IN (SELECT id FROM jobs WHERE data_status = 'incomplete'))
    ''', te_date_params)
    rate_hours_row = cursor2.fetchone()

    conn.close()

    total_hours = hours['total'] or 0
    total_labor = revenue['labor'] or 0
    total_materials = revenue['materials'] or 0
    total_expenses = expenses_row['total'] or 0
    total_profit = total_labor + total_materials - total_expenses
    rate_hours = rate_hours_row['total'] or 0
    rate_labor = rate_labor_row['labor'] or 0

    response = {
        'total_labor': total_labor,
        'total_materials': total_materials,
        'total_revenue': total_labor + total_materials,
        'total_expenses': total_expenses,
        'total_profit': total_profit,
        'total_hours': total_hours,
        'avg_hourly_rate': round(rate_labor / rate_hours, 2) if rate_hours > 0 else 0,
        'avg_days_per_job': round(avg_days_row['avg_days'], 1) if avg_days_row and avg_days_row['avg_days'] else 0,
        'customer_count': customers['count'],
        'job_count': jobs_count['count'],
        'invoice_count': invoice_count['count'],
        period_key: revenue_by_period,
        # Always include both keys so frontend can check either
        'revenue_by_year': revenue_by_period if period_key == 'revenue_by_year' else [],
        'revenue_by_month': revenue_by_period if period_key == 'revenue_by_month' else [],
        'recent_jobs': recent_jobs,
        'top_customers': top_customers,
        'revenue_by_category': by_category,
        'estimation_accuracy': {
            'jobs_with_estimates': est_row['total'] if est_row else 0,
            'on_time': est_row['on_time'] if est_row else 0,
            'avg_estimated_days': est_row['avg_estimated'] if est_row else None,
            'avg_actual_days': est_row['avg_actual'] if est_row else None,
        },
        'date_range': date_range,
    }
    return jsonify(response)


# ============================================================
# CUSTOMERS
# ============================================================

@app.route('/api/customers')
def list_customers():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT c.id, c.name, c.phone, c.email, c.address, c.notes, c.cya_notes, c.mileage_from_home,
               COALESCE(j_count.cnt, 0) as job_count,
               COALESCE(inv.labor, 0) as total_labor,
               COALESCE(te.hours, 0) as total_hours,
               j_recent.last_job_date
        FROM customers c
        LEFT JOIN (
            SELECT customer_id, COUNT(*) as cnt FROM jobs
            WHERE status NOT IN ('estimate', 'rejected') GROUP BY customer_id
        ) j_count ON c.id = j_count.customer_id
        LEFT JOIN (
            SELECT customer_id, SUM(total_labor) as labor FROM invoices GROUP BY customer_id
        ) inv ON c.id = inv.customer_id
        LEFT JOIN (
            SELECT customer_id, SUM(hours) as hours FROM time_entries GROUP BY customer_id
        ) te ON c.id = te.customer_id
        LEFT JOIN (
            SELECT customer_id, MAX(start_date) as last_job_date FROM jobs
            WHERE status NOT IN ('estimate', 'rejected') GROUP BY customer_id
        ) j_recent ON c.id = j_recent.customer_id
        WHERE c.name != '_UNASSIGNED'
        ORDER BY j_recent.last_job_date DESC, c.name
    ''')
    customers = rows_to_list(cursor.fetchall())
    conn.close()
    return jsonify(customers)


@app.route('/api/customers', methods=['POST'])
def create_customer():
    data = request.json
    if not data or not data.get('name'):
        return jsonify({'error': 'Customer name is required'}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO customers (name, address, phone, email, notes) VALUES (?, ?, ?, ?, ?)',
            (data['name'], data.get('address'), data.get('phone'),
             data.get('email'), data.get('notes'))
        )
        customer_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Customer already exists'}), 409

    conn.close()
    return jsonify({'id': customer_id, 'name': data['name']}), 201


@app.route('/api/customers/<int:customer_id>', methods=['PUT'])
def update_customer(customer_id):
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE customers SET name = ?, phone = ?, email = ?, address = ?, notes = ?, cya_notes = ?
        WHERE id = ?
    ''', (data.get('name'), data.get('phone'), data.get('email'),
          data.get('address'), data.get('notes'), data.get('cya_notes'), customer_id))
    conn.commit()
    conn.close()
    return jsonify({'id': customer_id, 'message': 'Customer updated'})


@app.route('/api/customers/<int:customer_id>', methods=['DELETE'])
def delete_customer(customer_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT name FROM customers WHERE id = ?', (customer_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Customer not found'}), 404

    cursor.execute('SELECT COUNT(*) as cnt FROM jobs WHERE customer_id = ?', (customer_id,))
    job_count = cursor.fetchone()['cnt']

    force = request.args.get('force') == '1'
    if job_count > 0 and not force:
        conn.close()
        return jsonify({'error': f'Customer has {job_count} job(s). Confirm to delete everything.', 'job_count': job_count}), 409

    cursor.execute('SELECT id FROM jobs WHERE customer_id = ?', (customer_id,))
    job_ids = [r['id'] for r in cursor.fetchall()]
    for jid in job_ids:
        cursor.execute('DELETE FROM services_performed WHERE job_id = ?', (jid,))
        cursor.execute('DELETE FROM payments WHERE job_id = ?', (jid,))
        cursor.execute('DELETE FROM trips WHERE job_id = ?', (jid,))
        cursor.execute('DELETE FROM invoices WHERE job_id = ?', (jid,))
    cursor.execute('DELETE FROM time_entries WHERE customer_id = ?', (customer_id,))
    cursor.execute('DELETE FROM jobs WHERE customer_id = ?', (customer_id,))
    cursor.execute('DELETE FROM customers WHERE id = ?', (customer_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Customer deleted', 'jobs_removed': len(job_ids)})


@app.route('/api/customers/<int:customer_id>/calculate-mileage', methods=['POST'])
def calculate_customer_mileage(customer_id):
    """Geocode the customer address and calculate driving distance from Brian's home."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT address FROM customers WHERE id = ?', (customer_id,))
    row = cursor.fetchone()
    if not row or not row['address']:
        conn.close()
        return jsonify({'error': 'No address on file'}), 400

    address = row['address']
    try:
        # Geocode with Nominatim (OpenStreetMap)
        encoded = urllib.parse.quote(address + ', USA')
        url = f'https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1'
        req = urllib.request.Request(url, headers={'User-Agent': 'BeardHomeServices/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            geo = json.loads(resp.read())
        if not geo:
            conn.close()
            return jsonify({'error': 'Could not geocode address'}), 422
        dest_lat = float(geo[0]['lat'])
        dest_lon = float(geo[0]['lon'])

        # Route with OSRM public API
        osrm_url = (
            f'https://router.project-osrm.org/route/v1/driving/'
            f'{BRIAN_HOME_LON},{BRIAN_HOME_LAT};{dest_lon},{dest_lat}'
            f'?overview=false'
        )
        req2 = urllib.request.Request(osrm_url, headers={'User-Agent': 'BeardHomeServices/1.0'})
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            route = json.loads(resp2.read())

        if route.get('code') != 'Ok' or not route.get('routes'):
            conn.close()
            return jsonify({'error': 'Could not calculate route'}), 422

        meters = route['routes'][0]['distance']
        miles = round(meters / 1609.344, 1)

        cursor.execute('UPDATE customers SET mileage_from_home = ? WHERE id = ?', (miles, customer_id))
        conn.commit()
        conn.close()
        return jsonify({'customer_id': customer_id, 'mileage_from_home': miles})

    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/customers/<int:customer_id>')
def get_customer(customer_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM customers WHERE id = ?', (customer_id,))
    customer = row_to_dict(cursor.fetchone())

    if not customer:
        conn.close()
        return jsonify({'error': 'Customer not found'}), 404

    cursor.execute('''
        SELECT j.*, i.total_labor, i.total_materials
        FROM jobs j
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE j.customer_id = ?
        ORDER BY j.start_date DESC
    ''', (customer_id,))
    customer['jobs'] = rows_to_list(cursor.fetchall())

    cursor.execute('''
        SELECT entry_date, hours, description
        FROM time_entries
        WHERE customer_id = ?
        ORDER BY entry_date DESC
    ''', (customer_id,))
    customer['time_entries'] = rows_to_list(cursor.fetchall())

    conn.close()
    return jsonify(customer)


# ============================================================
# JOBS
# ============================================================

@app.route('/api/jobs')
def list_jobs():
    conn = get_db()
    cursor = conn.cursor()

    customer_id = request.args.get('customer_id')
    where = "WHERE j.status != 'estimate'"
    params = []
    if customer_id:
        where += ' AND j.customer_id = ?'
        params.append(customer_id)

    cursor.execute(f'''
        SELECT j.id, j.customer_id, j.invoice_id, j.start_date, j.status,
               c.name as customer,
               i.total_labor, i.total_materials,
               (SELECT SUM(hours) FROM time_entries WHERE job_id = j.id) as hours
        FROM jobs j
        JOIN customers c ON j.customer_id = c.id
        LEFT JOIN invoices i ON j.id = i.job_id
        {where}
        ORDER BY j.start_date DESC
    ''', params)
    jobs = rows_to_list(cursor.fetchall())
    conn.close()
    return jsonify(jobs)


@app.route('/api/jobs/<int:job_id>')
def get_job(job_id):
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT j.*, c.name as customer,
               i.total_labor, i.total_materials, i.invoice_number
        FROM jobs j
        JOIN customers c ON j.customer_id = c.id
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE j.id = ?
    ''', (job_id,))
    job = row_to_dict(cursor.fetchone())

    if not job:
        conn.close()
        return jsonify({'error': 'Job not found'}), 404

    cursor.execute('''
        SELECT original_description, standardized_description, category, amount, service_type
        FROM services_performed WHERE job_id = ?
    ''', (job_id,))
    job['services'] = rows_to_list(cursor.fetchall())

    cursor.execute('''
        SELECT entry_date, hours, description FROM time_entries
        WHERE job_id = ? ORDER BY entry_date
    ''', (job_id,))
    job['time_entries'] = rows_to_list(cursor.fetchall())

    conn.close()
    return jsonify(job)


@app.route('/api/jobs/full', methods=['POST'])
def create_full_job():
    data = request.json
    if not data.get('customer_id') or not data.get('invoice_number'):
        return jsonify({'error': 'customer_id and invoice_number are required'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        invoice_num = data['invoice_number']
        if not invoice_num.startswith('BHS'):
            invoice_num = 'BHS' + invoice_num
        numeric = invoice_num[3:]
        if len(numeric) == 8:
            start_date = f"{numeric[:4]}-{numeric[4:6]}-{numeric[6:8]}"
        else:
            start_date = data.get('start_date')

        cursor.execute('''
            INSERT INTO jobs (customer_id, invoice_id, project_number, start_date, status, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data['customer_id'], invoice_num, numeric, start_date,
              data.get('status', 'completed'), data.get('notes', '')))
        job_id = cursor.lastrowid

        services = data.get('services', [])
        total_labor = sum(s['amount'] for s in services if s.get('service_type') == 'labor')
        total_materials = sum(s['amount'] for s in services if s.get('service_type') == 'materials')

        cursor.execute('''
            INSERT INTO invoices
            (invoice_number, customer_id, job_id, total_labor, total_materials,
             total_amount, invoice_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'paid')
        ''', (invoice_num, data['customer_id'], job_id, total_labor, total_materials,
              total_labor + total_materials, start_date))
        invoice_id = cursor.lastrowid

        for svc in services:
            cursor.execute('''
                INSERT INTO services_performed
                (invoice_id, job_id, original_description, standardized_description,
                 category, amount, service_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (invoice_id, job_id, svc.get('description', ''),
                  svc.get('description', ''), svc.get('category'),
                  svc.get('amount', 0), svc.get('service_type', 'labor')))

        for te in data.get('time_entries', []):
            cursor.execute('''
                INSERT INTO time_entries
                (customer_id, job_id, entry_date, hours, description, source)
                VALUES (?, ?, ?, ?, ?, 'app')
            ''', (data['customer_id'], job_id, te.get('date'),
                  te.get('hours', 0), te.get('description', '')))

        conn.commit()
        conn.close()

        return jsonify({
            'job_id': job_id,
            'invoice_id': invoice_id,
            'invoice_number': invoice_num,
            'total_labor': total_labor,
            'total_materials': total_materials,
            'services_count': len(services),
            'time_entries_count': len(data.get('time_entries', [])),
            'message': 'Job created successfully'
        }), 201

    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': f'Invoice {data["invoice_number"]} already exists'}), 409
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<int:job_id>/convert', methods=['POST'])
def convert_to_invoice(job_id):
    """Convert an estimate to an invoice."""
    conn = get_db()
    cursor = conn.cursor()

    # Get current invoice number
    inv = cursor.execute('SELECT id, invoice_number FROM invoices WHERE job_id = ?', (job_id,)).fetchone()

    # Rename EST->BHS in invoice number
    if inv and inv['invoice_number'] and inv['invoice_number'].startswith('EST'):
        new_num = 'BHS' + inv['invoice_number'][3:]
        cursor.execute('UPDATE invoices SET invoice_number = ? WHERE job_id = ?', (new_num, job_id))
        cursor.execute('UPDATE jobs SET invoice_id = ?, status = ? WHERE id = ?', (new_num, 'pending', job_id))
    else:
        cursor.execute("UPDATE jobs SET status = 'pending' WHERE id = ?", (job_id,))

    conn.commit()
    conn.close()
    return jsonify({'message': 'Converted to invoice', 'job_id': job_id})


@app.route('/api/jobs/<int:job_id>/start-work', methods=['POST'])
def start_work(job_id):
    """Mark an accepted estimate as in progress (pending -> in_progress)."""
    conn = get_db()
    cursor = conn.cursor()
    job = cursor.execute('SELECT id, status FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if not job:
        conn.close()
        return jsonify({'error': 'Job not found'}), 404
    if job['status'] not in ('pending', 'estimate'):
        conn.close()
        return jsonify({'error': 'Job must be pending or estimate to start work'}), 400
    cursor.execute("UPDATE jobs SET status = 'in_progress' WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Job marked in progress', 'job_id': job_id})


@app.route('/api/jobs/<int:job_id>/trash', methods=['POST'])
def trash_estimate(job_id):
    """Mark an estimate as rejected (trashed) with an optional reason."""
    data = request.json or {}
    reason = data.get('reason', '')

    conn = get_db()
    cursor = conn.cursor()

    job = cursor.execute('SELECT id, status FROM jobs WHERE id = ?', (job_id,)).fetchone()
    if not job:
        conn.close()
        return jsonify({'error': 'Job not found'}), 404
    if job['status'] != 'estimate':
        conn.close()
        return jsonify({'error': 'Job is not an estimate'}), 400

    cursor.execute(
        "UPDATE jobs SET status = 'rejected', notes = CASE WHEN notes IS NULL OR notes = '' THEN ? ELSE notes || char(10) || ? END WHERE id = ?",
        (f'[Rejected] {reason}', f'[Rejected] {reason}', job_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'message': 'Estimate trashed', 'job_id': job_id})


@app.route('/api/jobs/<int:job_id>', methods=['DELETE'])
def delete_job(job_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM jobs WHERE id = ?', (job_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Job not found'}), 404
    cursor.execute('DELETE FROM services_performed WHERE job_id = ?', (job_id,))
    cursor.execute('DELETE FROM payments WHERE job_id = ?', (job_id,))
    cursor.execute('DELETE FROM trips WHERE job_id = ?', (job_id,))
    cursor.execute('DELETE FROM invoices WHERE job_id = ?', (job_id,))
    cursor.execute('UPDATE time_entries SET job_id = NULL WHERE job_id = ?', (job_id,))
    cursor.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Job deleted'})


@app.route('/api/estimates')
def list_estimates():
    """List all estimate-pipeline jobs: pending customer response, accepted, or in progress."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT j.id as job_id,
               COALESCE(i.invoice_number, j.invoice_id) as invoice_number,
               c.name as customer,
               c.phone as customer_phone,
               c.address as customer_address,
               j.status,
               j.start_date,
               j.estimated_days,
               j.notes,
               COALESCE(i.total_labor, 0) as total_labor,
               COALESCE(i.total_materials, 0) as total_materials,
               COALESCE(i.total_amount, i.total_labor + i.total_materials, 0) as total_amount
        FROM jobs j
        JOIN customers c ON j.customer_id = c.id
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE j.status IN ('estimate', 'pending', 'in_progress')
        ORDER BY j.start_date DESC, j.id DESC
    ''')
    estimates = rows_to_list(cursor.fetchall())
    conn.close()

    stage_map = {'estimate': 'pending', 'pending': 'accepted', 'in_progress': 'in_progress'}
    for e in estimates:
        e['pipeline_stage'] = stage_map.get(e['status'], e['status'])

    return jsonify({'estimates': estimates})


@app.route('/api/estimates', methods=['POST'])
def receive_estimate():
    """Receive estimate data posted from the external PDF generator script."""
    data = request.json or {}

    estimate_number  = (data.get('estimate_number') or '').strip()
    customer_name    = (data.get('customer_name') or '').strip()
    customer_phone   = (data.get('customer_phone') or '').strip()
    customer_address = (data.get('customer_address') or '').strip()
    date             = data.get('date') or datetime.today().strftime('%Y-%m-%d')
    line_items       = data.get('line_items', [])
    total            = data.get('total')
    notes            = (data.get('notes') or '').strip()

    if not re.match(r'^BHS\d{8}$', estimate_number):
        return jsonify({'error': 'estimate_number must be BHS followed by 8 digits, e.g. BHS20260627'}), 400
    if not customer_name:
        return jsonify({'error': 'customer_name is required'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Dedup: reject if this estimate number already exists
        existing = cursor.execute(
            'SELECT id FROM jobs WHERE invoice_id = ?', (estimate_number,)
        ).fetchone()
        if existing:
            conn.close()
            return jsonify({'error': 'Estimate already exists', 'job_id': existing['id']}), 409

        # Find customer — match by phone digits first, then by name
        customer_id = None
        phone_digits = re.sub(r'\D', '', customer_phone)

        if phone_digits:
            for row in cursor.execute(
                "SELECT id, phone FROM customers WHERE phone IS NOT NULL AND phone != ''"
            ).fetchall():
                if re.sub(r'\D', '', row['phone'] or '') == phone_digits:
                    customer_id = row['id']
                    break

        if customer_id is None:
            row = cursor.execute(
                'SELECT id FROM customers WHERE name = ?', (customer_name,)
            ).fetchone()
            if row:
                customer_id = row['id']

        if customer_id is None:
            cursor.execute(
                'INSERT INTO customers (name, phone, address) VALUES (?, ?, ?)',
                (customer_name, customer_phone, customer_address)
            )
            customer_id = cursor.lastrowid
        elif customer_address:
            cursor.execute(
                "UPDATE customers SET address = ? WHERE id = ? AND (address IS NULL OR address = '')",
                (customer_address, customer_id)
            )

        # Classify each line item as labor or materials by service name
        total_labor = 0.0
        total_materials = 0.0
        classified = []
        for item in line_items:
            svc_name = (item.get('service') or '').strip()
            svc_desc = (item.get('desc') or svc_name).strip()
            price    = float(item.get('price') or 0)
            svc_type = 'materials' if 'materials' in svc_name.lower() else 'labor'
            if svc_type == 'labor':
                total_labor += price
            else:
                total_materials += price
            classified.append((svc_name, svc_desc, svc_type, price))

        total_amount = float(total) if total is not None else (total_labor + total_materials)
        numeric = estimate_number[3:]

        cursor.execute('''
            INSERT INTO jobs (customer_id, invoice_id, project_number, start_date, status, notes)
            VALUES (?, ?, ?, ?, 'estimate', ?)
        ''', (customer_id, estimate_number, numeric, date, notes))
        job_id = cursor.lastrowid

        cursor.execute('''
            INSERT INTO invoices
            (invoice_number, customer_id, job_id, total_labor, total_materials,
             total_amount, invoice_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')
        ''', (estimate_number, customer_id, job_id,
              total_labor, total_materials, total_amount, date))
        invoice_id = cursor.lastrowid

        for svc_name, svc_desc, svc_type, price in classified:
            cursor.execute('''
                INSERT INTO services_performed
                (invoice_id, job_id, original_description, standardized_description,
                 category, amount, service_type, quantity, unit_of_measure)
                VALUES (?, ?, ?, ?, NULL, ?, ?, 1, 'each')
            ''', (invoice_id, job_id, svc_name, svc_desc, price, svc_type))

        conn.commit()
        conn.close()
        return jsonify({
            'job_id': job_id,
            'invoice_id': invoice_id,
            'estimate_number': estimate_number,
            'customer_id': customer_id,
        }), 201

    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/estimates/check/<estimate_number>')
def check_estimate(estimate_number):
    """Return whether a BHS estimate number already exists. Used by the SMS extractor for dedup."""
    conn = get_db()
    row = conn.cursor().execute(
        'SELECT id FROM jobs WHERE invoice_id = ?', (estimate_number,)
    ).fetchone()
    conn.close()
    return jsonify({'exists': row is not None, 'job_id': row['id'] if row else None})


# ============================================================
# FILING CABINET (main UI - browse/edit all invoices)
# ============================================================

@app.route('/api/filing-cabinet')
def filing_cabinet_list():
    """List all jobs for the sidebar."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT j.id as job_id,
               COALESCE(i.invoice_number, j.invoice_id) as invoice_number,
               c.name as customer,
               CASE WHEN c.name != '_UNASSIGNED' THEN 1 ELSE 0 END as has_customer,
               j.status,
               j.start_date,
               j.estimated_days,
               COALESCE(i.total_labor, 0) as total_labor,
               COALESCE(i.total_materials, 0) as total_materials,
               COALESCE(i.total_amount, i.total_labor + i.total_materials, 0) as total_amount,
               COALESCE((SELECT SUM(hours) FROM time_entries WHERE job_id = j.id), 0) as total_hours,
               COALESCE((SELECT COUNT(DISTINCT entry_date) FROM time_entries WHERE job_id = j.id), 0) as actual_days,
               (SELECT COUNT(*) FROM time_entries WHERE job_id = j.id) as time_entry_count,
               COALESCE((SELECT SUM(amount) FROM payments WHERE job_id = j.id), 0) as total_paid,
               j.data_status
        FROM jobs j
        JOIN customers c ON j.customer_id = c.id
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE j.status NOT IN ('estimate', 'rejected')
        ORDER BY j.start_date DESC, j.id DESC
    ''')
    jobs = rows_to_list(cursor.fetchall())
    conn.close()
    return jsonify({'jobs': jobs})


@app.route('/api/filing-cabinet/<int:job_id>')
def filing_cabinet_get(job_id):
    """Get full job details for editing."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT j.id as job_id, j.customer_id, j.notes, j.status, j.start_date,
               j.estimated_days,
               c.name as customer_name, c.phone as customer_phone,
               c.email as customer_email, c.address as customer_address,
               COALESCE(i.invoice_number, j.invoice_id) as invoice_number,
               i.invoice_date, i.pdf_filename,
               COALESCE(i.total_labor, 0) as total_labor,
               COALESCE(i.total_materials, 0) as total_materials,
               COALESCE(i.total_amount, i.total_labor + i.total_materials, 0) as total_amount,
               i.id as invoice_db_id
        FROM jobs j
        JOIN customers c ON j.customer_id = c.id
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE j.id = ?
    ''', (job_id,))
    job = row_to_dict(cursor.fetchone())

    if not job:
        conn.close()
        return jsonify({'error': 'Job not found'}), 404

    cursor.execute('''
        SELECT id, original_description, standardized_description, category, amount, service_type,
               COALESCE(quantity, 1) as quantity, COALESCE(unit_of_measure, 'each') as unit_of_measure
        FROM services_performed WHERE job_id = ?
        ORDER BY id
    ''', (job_id,))
    job['services'] = rows_to_list(cursor.fetchall())

    cursor.execute('''
        SELECT id, entry_date, start_time, end_time, hours, description,
               cost_code, source, busybusy_project, busybusy_subproject
        FROM time_entries WHERE job_id = ?
        ORDER BY entry_date, id
    ''', (job_id,))
    job['time_entries'] = rows_to_list(cursor.fetchall())

    # Hours and days summary
    job['total_hours'] = sum(te['hours'] or 0 for te in job['time_entries'])
    job['actual_days'] = len({te['entry_date'] for te in job['time_entries'] if te['entry_date']})

    # Day-by-day breakdown: [{date, hours, entries}]
    days_map = {}
    for te in job['time_entries']:
        d = te['entry_date']
        if not d:
            continue
        if d not in days_map:
            days_map[d] = {'date': d, 'hours': 0, 'entries': 0}
        days_map[d]['hours'] += te['hours'] or 0
        days_map[d]['entries'] += 1
    job['days_on_site'] = sorted(days_map.values(), key=lambda x: x['date'])

    # Unlinked time entries for this customer (not yet linked to any job)
    cursor.execute('''
        SELECT id, entry_date, start_time, end_time, hours, description,
               cost_code, source, busybusy_project, busybusy_subproject
        FROM time_entries
        WHERE customer_id = ? AND job_id IS NULL
        ORDER BY entry_date
    ''', (job['customer_id'],))
    job['unlinked_time_entries'] = rows_to_list(cursor.fetchall())

    # All jobs for this customer — used to populate the reassignment dropdown
    cursor.execute('''
        SELECT j.id as job_id,
               COALESCE(i.invoice_number, j.invoice_id) as invoice_number,
               j.start_date, j.status
        FROM jobs j
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE j.customer_id = ?
        ORDER BY j.start_date DESC
    ''', (job['customer_id'],))
    job['customer_jobs'] = rows_to_list(cursor.fetchall())

    # Payments
    cursor.execute('''
        SELECT id, amount, payment_date, payment_method, memo, created_at
        FROM payments WHERE job_id = ?
        ORDER BY payment_date, id
    ''', (job_id,))
    job['payments'] = rows_to_list(cursor.fetchall())
    job['total_paid'] = sum(p['amount'] for p in job['payments'])
    job['balance_due'] = round(job['total_amount'] - job['total_paid'], 2)

    conn.close()
    return jsonify(job)


@app.route('/api/filing-cabinet/new', methods=['POST'])
def filing_cabinet_new():
    """Create a new job/invoice."""
    data = request.json
    if not data.get('customer_id'):
        return jsonify({'error': 'customer_id is required'}), 400

    conn = get_db()
    cursor = conn.cursor()

    try:
        start_date = data.get('start_date') or datetime.today().strftime('%Y-%m-%d')

        # Auto-generate number from date if not provided
        # Estimates use EST prefix; invoices use BHS prefix
        status = data.get('status', 'completed')
        raw_num = data.get('invoice_number') or ''
        if raw_num:
            if raw_num.startswith('BHS') or raw_num.startswith('EST'):
                invoice_num = raw_num
            elif status == 'estimate':
                invoice_num = 'EST' + raw_num
            else:
                invoice_num = 'BHS' + raw_num
        else:
            date_compact = start_date.replace('-', '')
            prefix = 'EST' if status == 'estimate' else 'BHS'
            invoice_num = f"{prefix}{date_compact}"

        numeric = invoice_num.lstrip('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
        if len(numeric) == 8:
            start_date = f"{numeric[:4]}-{numeric[4:6]}-{numeric[6:8]}"

        cursor.execute('''
            INSERT INTO jobs (customer_id, invoice_id, project_number, start_date, status, notes, estimated_days)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (data['customer_id'], invoice_num, numeric, start_date, status,
              data.get('notes', ''), data.get('estimated_days')))
        job_id = cursor.lastrowid

        services = data.get('services', [])
        total_labor = sum(s['amount'] * s.get('quantity', 1) for s in services if s.get('service_type') == 'labor')
        total_materials = sum(s['amount'] * s.get('quantity', 1) for s in services if s.get('service_type') == 'materials')

        invoice_status = 'paid' if status == 'completed' else status
        cursor.execute('''
            INSERT INTO invoices
            (invoice_number, customer_id, job_id, total_labor, total_materials,
             total_amount, invoice_date, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (invoice_num, data['customer_id'], job_id, total_labor, total_materials,
              total_labor + total_materials, start_date, invoice_status))
        invoice_id = cursor.lastrowid

        for svc in services:
            desc = svc.get('original_description') or svc.get('description', '')
            cursor.execute('''
                INSERT INTO services_performed
                (invoice_id, job_id, original_description, standardized_description,
                 category, amount, service_type, quantity, unit_of_measure)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (invoice_id, job_id, desc, desc, svc.get('category'),
                  svc.get('amount', 0), svc.get('service_type', 'labor'),
                  svc.get('quantity', 1), svc.get('unit_of_measure', 'each')))

        for te in data.get('time_entries', []):
            if te.get('hours'):
                cursor.execute('''
                    INSERT INTO time_entries
                    (customer_id, job_id, entry_date, hours, description, source)
                    VALUES (?, ?, ?, ?, ?, 'app')
                ''', (data['customer_id'], job_id, te.get('date'),
                      te.get('hours', 0), te.get('description', '')))

        # Claim any unlinked time entries
        for te_id in data.get('claim_time_entry_ids', []):
            cursor.execute(
                'UPDATE time_entries SET job_id = ? WHERE id = ? AND customer_id = ?',
                (job_id, te_id, data['customer_id'])
            )

        conn.commit()
        conn.close()

        return jsonify({
            'job_id': job_id,
            'invoice_id': invoice_id,
            'invoice_number': invoice_num,
            'total_labor': total_labor,
            'total_materials': total_materials,
        }), 201

    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': f'Invoice number already exists'}), 409
    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


@app.route('/api/filing-cabinet/<int:job_id>', methods=['PUT'])
def filing_cabinet_update(job_id):
    """Update an existing job."""
    data = request.json

    conn = get_db()
    cursor = conn.cursor()

    try:
        # Update job notes/status/estimated_days/photos_album_url
        cursor.execute('''
            UPDATE jobs SET customer_id = ?, notes = ?, estimated_days = ?, photos_album_url = ? WHERE id = ?
        ''', (data.get('customer_id'), data.get('notes', ''),
              data.get('estimated_days'), data.get('photos_album_url'), job_id))

        # Update customer contact info if provided
        customer = data.get('customer', {})
        if customer and data.get('customer_id'):
            cursor.execute('''
                UPDATE customers SET name = ?, phone = ?, email = ?, address = ?
                WHERE id = ?
            ''', (customer.get('name'), customer.get('phone'),
                  customer.get('email'), customer.get('address'),
                  data['customer_id']))

        # Get invoice id
        cursor.execute('SELECT id FROM invoices WHERE job_id = ?', (job_id,))
        inv_row = cursor.fetchone()
        invoice_id = inv_row['id'] if inv_row else None

        services = data.get('services', [])
        total_labor = sum(s.get('amount', 0) for s in services if s.get('service_type') == 'labor')
        total_materials = sum(s.get('amount', 0) for s in services if s.get('service_type') == 'materials')

        if invoice_id:
            # Update invoice totals and customer
            cursor.execute('''
                UPDATE invoices SET customer_id = ?, total_labor = ?, total_materials = ?,
                total_amount = ? WHERE id = ?
            ''', (data.get('customer_id'), total_labor, total_materials,
                  total_labor + total_materials, invoice_id))

            # Replace services — use standardized_description when provided
            cursor.execute('DELETE FROM services_performed WHERE job_id = ?', (job_id,))
            for svc in services:
                std_desc = svc.get('standardized_description') or svc.get('description', '')
                orig_desc = svc.get('original_description') or svc.get('description', '')
                cursor.execute('''
                    INSERT INTO services_performed
                    (invoice_id, job_id, original_description, standardized_description,
                     category, amount, service_type, quantity, unit_of_measure)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (invoice_id, job_id, orig_desc, std_desc,
                      svc.get('category'), svc.get('amount', 0), svc.get('service_type', 'labor'),
                      svc.get('quantity', 1), svc.get('unit_of_measure', 'each')))

        # Handle time entries - update existing, add new
        cursor.execute('SELECT id FROM time_entries WHERE job_id = ?', (job_id,))
        existing_te_ids = {row['id'] for row in cursor.fetchall()}
        submitted_te_ids = {t['id'] for t in data.get('time_entries', []) if t.get('id')}

        # Delete removed entries
        for te_id in existing_te_ids - submitted_te_ids:
            cursor.execute('DELETE FROM time_entries WHERE id = ?', (te_id,))

        for te in data.get('time_entries', []):
            if not te.get('hours'):
                continue
            if te.get('id') and te['id'] in existing_te_ids:
                cursor.execute('''
                    UPDATE time_entries SET entry_date = ?, hours = ?, description = ?
                    WHERE id = ?
                ''', (te.get('entry_date') or te.get('date'),
                      te.get('hours', 0), te.get('description', ''), te['id']))
            else:
                cursor.execute('''
                    INSERT INTO time_entries
                    (customer_id, job_id, entry_date, hours, description, source)
                    VALUES (?, ?, ?, ?, ?, 'app')
                ''', (data.get('customer_id'), job_id,
                      te.get('entry_date') or te.get('date'),
                      te.get('hours', 0), te.get('description', '')))

        # Claim unlinked time entries
        for te_id in data.get('claim_time_entry_ids', []):
            cursor.execute(
                'UPDATE time_entries SET job_id = ? WHERE id = ? AND customer_id = ?',
                (job_id, te_id, data.get('customer_id'))
            )

        conn.commit()

        cursor.execute('SELECT invoice_number FROM invoices WHERE job_id = ?', (job_id,))
        inv = cursor.fetchone()
        conn.close()

        return jsonify({
            'job_id': job_id,
            'invoice_number': inv['invoice_number'] if inv else '',
            'total_labor': total_labor,
            'total_materials': total_materials,
        })

    except Exception as e:
        conn.close()
        return jsonify({'error': str(e)}), 500


# ============================================================
# DATA GAPS / COMPLETENESS
# ============================================================

@app.route('/api/data-gaps', methods=['GET'])
def get_data_gaps():
    conn = get_db()

    # Gap 1+3: Invoices/jobs with no time entries linked
    missing_te = conn.execute("""
        SELECT j.id as job_id,
               COALESCE(i.invoice_number, j.invoice_id) as invoice_number,
               i.invoice_date,
               c.name as customer_name,
               j.customer_id,
               COALESCE(i.total_amount, 0) as total_amount,
               j.data_status,
               COUNT(sp.id) as service_count
        FROM jobs j
        JOIN customers c ON j.customer_id = c.id
        LEFT JOIN invoices i ON j.id = i.job_id
        LEFT JOIN services_performed sp ON sp.job_id = j.id
        WHERE j.status IN ('completed', 'paid', 'pending')
          AND (j.data_status IS NULL OR j.data_status != 'incomplete')
          AND c.name != 'test'
          AND NOT EXISTS (SELECT 1 FROM time_entries te WHERE te.job_id = j.id)
        GROUP BY j.id
        ORDER BY i.invoice_date DESC
    """).fetchall()

    # Gap 2: Time entries with no job linked
    unlinked_te = conn.execute("""
        SELECT te.id, te.entry_date, te.start_time, te.end_time, te.hours,
               te.description, te.customer_id, te.busybusy_project,
               c.name as customer_name
        FROM time_entries te
        LEFT JOIN customers c ON te.customer_id = c.id
        WHERE te.job_id IS NULL
        ORDER BY te.entry_date DESC
    """).fetchall()

    # Gap 4: Overhead - last overhead date and weeks since
    overhead_row = conn.execute("""
        SELECT MAX(expense_date) as last_overhead_date
        FROM materials_expenses
        WHERE is_overhead = 1
    """).fetchone()
    last_oh = overhead_row['last_overhead_date'] if overhead_row else None
    if last_oh:
        weeks_since = conn.execute(
            "SELECT CAST((julianday('now') - julianday(?)) / 7 AS INTEGER) as w",
            (last_oh,)
        ).fetchone()['w']
    else:
        weeks_since = 99

    # Gap 5: Suggested trips - time entries that are sole entry for job+date,
    # have start+end time, customer has mileage, no trip exists for that job+date,
    # and trip_skip != 1
    suggested_trips = conn.execute("""
        SELECT te.id as time_entry_id,
               te.job_id,
               te.entry_date,
               te.customer_id,
               te.hours,
               te.start_time,
               te.end_time,
               c.name as customer_name,
               c.address as customer_address,
               c.mileage_from_home
        FROM time_entries te
        JOIN customers c ON te.customer_id = c.id
        WHERE te.job_id IS NOT NULL
          AND te.start_time IS NOT NULL
          AND te.end_time IS NOT NULL
          AND c.mileage_from_home IS NOT NULL
          AND c.mileage_from_home > 0
          AND (te.trip_skip IS NULL OR te.trip_skip != 1)
          AND NOT EXISTS (
              SELECT 1 FROM trips tr
              WHERE tr.job_id = te.job_id
                AND tr.trip_date = te.entry_date
          )
          AND (
              SELECT COUNT(*) FROM time_entries te2
              WHERE te2.job_id = te.job_id
                AND te2.entry_date = te.entry_date
          ) = 1
        ORDER BY te.entry_date DESC
        LIMIT 50
    """).fetchall()

    conn.close()
    return jsonify({
        'missing_time_entries': [dict(r) for r in missing_te],
        'unlinked_time_entries': [dict(r) for r in unlinked_te],
        'overhead_gap': {
            'zero_overhead_weeks': weeks_since,
            'last_overhead_date': last_oh
        },
        'suggested_trips': [dict(r) for r in suggested_trips]
    })


@app.route('/api/jobs/<int:job_id>/mark-incomplete', methods=['POST'])
def mark_job_incomplete(job_id):
    conn = get_db()
    conn.execute("UPDATE jobs SET data_status = 'incomplete' WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return jsonify({'job_id': job_id, 'data_status': 'incomplete'})


@app.route('/api/suggested-trips/<int:te_id>/confirm', methods=['POST'])
def confirm_suggested_trip(te_id):
    conn = get_db()
    te = conn.execute("""
        SELECT te.entry_date, te.job_id, te.customer_id,
               c.address, c.mileage_from_home, c.name
        FROM time_entries te
        JOIN customers c ON te.customer_id = c.id
        WHERE te.id = ?
    """, (te_id,)).fetchone()
    if not te:
        conn.close()
        return jsonify({'error': 'Time entry not found'}), 404
    conn.execute("""
        INSERT INTO trips (trip_date, trip_type, destination, customer_id, job_id, miles, notes)
        VALUES (?, 'job_site', ?, ?, ?, ?, 'Auto-generated from time entry')
    """, (te['entry_date'], te['address'], te['customer_id'], te['job_id'], te['mileage_from_home']))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Trip confirmed', 'miles': te['mileage_from_home']})


@app.route('/api/suggested-trips/<int:te_id>/skip', methods=['POST'])
def skip_suggested_trip(te_id):
    conn = get_db()
    conn.execute("UPDATE time_entries SET trip_skip = 1 WHERE id = ?", (te_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Skipped'})


# ============================================================
# PAYMENTS
# ============================================================

@app.route('/api/jobs/<int:job_id>/payments', methods=['POST'])
def add_payment(job_id):
    """Record a payment against a job."""
    data = request.json
    if not data or not data.get('amount'):
        return jsonify({'error': 'amount is required'}), 400

    conn = get_db()
    cursor = conn.cursor()

    # Verify job exists and get customer_id + total
    cursor.execute('''
        SELECT j.customer_id,
               COALESCE(i.total_amount, i.total_labor + i.total_materials, 0) as total_amount
        FROM jobs j
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE j.id = ?
    ''', (job_id,))
    job_row = cursor.fetchone()
    if not job_row:
        conn.close()
        return jsonify({'error': 'Job not found'}), 404

    payment_date = data.get('payment_date') or datetime.today().strftime('%Y-%m-%d')
    cursor.execute('''
        INSERT INTO payments (job_id, customer_id, amount, payment_date, payment_method, memo)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (job_id, job_row['customer_id'], float(data['amount']),
          payment_date, data.get('payment_method', 'cash'), data.get('memo', '')))
    payment_id = cursor.lastrowid

    # Check if fully paid and auto-update status
    cursor.execute('SELECT COALESCE(SUM(amount), 0) as total_paid FROM payments WHERE job_id = ?', (job_id,))
    total_paid = cursor.fetchone()['total_paid']
    total_amount = job_row['total_amount']
    if total_amount > 0 and total_paid >= total_amount:
        cursor.execute("UPDATE jobs SET status = 'paid' WHERE id = ?", (job_id,))
        cursor.execute("UPDATE invoices SET status = 'paid' WHERE job_id = ?", (job_id,))
        new_status = 'paid'
    else:
        cursor.execute("UPDATE jobs SET status = 'pending' WHERE id = ? AND status = 'estimate'", (job_id,))
        cursor.execute('SELECT status FROM jobs WHERE id = ?', (job_id,))
        new_status = cursor.fetchone()['status']

    conn.commit()
    conn.close()
    return jsonify({
        'id': payment_id,
        'total_paid': round(total_paid, 2),
        'balance_due': round(max(total_amount - total_paid, 0), 2),
        'status': new_status,
    }), 201


@app.route('/api/payments/<int:payment_id>', methods=['DELETE'])
def delete_payment(payment_id):
    """Remove a payment and re-evaluate job status."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT job_id FROM payments WHERE id = ?', (payment_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Payment not found'}), 404
    job_id = row['job_id']

    cursor.execute('DELETE FROM payments WHERE id = ?', (payment_id,))

    # Re-check balance
    cursor.execute('SELECT COALESCE(SUM(amount), 0) as total_paid FROM payments WHERE job_id = ?', (job_id,))
    total_paid = cursor.fetchone()['total_paid']
    cursor.execute('''
        SELECT COALESCE(i.total_amount, i.total_labor + i.total_materials, 0) as total_amount
        FROM jobs j LEFT JOIN invoices i ON j.id = i.job_id WHERE j.id = ?
    ''', (job_id,))
    total_amount = cursor.fetchone()['total_amount']

    if total_amount > 0 and total_paid >= total_amount:
        new_status = 'paid'
    elif total_paid > 0:
        new_status = 'pending'
    else:
        new_status = 'pending'

    cursor.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_status, job_id))
    cursor.execute("UPDATE invoices SET status = ? WHERE job_id = ?", (new_status, job_id))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted', 'balance_due': round(max(total_amount - total_paid, 0), 2)})


# ============================================================
# TIME ENTRIES
# ============================================================

@app.route('/api/time-entries')
def list_time_entries():
    conn = get_db()
    cursor = conn.cursor()

    customer_id = request.args.get('customer_id')
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    query = '''
        SELECT t.id, t.customer_id, t.job_id, t.entry_date, t.start_time, t.end_time,
               t.hours, t.description, t.cost_code, t.source,
               c.name as customer_name, j.invoice_id, j.id as job_id_check
        FROM time_entries t
        LEFT JOIN customers c ON t.customer_id = c.id
        LEFT JOIN jobs j ON t.job_id = j.id
        WHERE 1=1
    '''
    params = []

    if customer_id:
        query += ' AND t.customer_id = ?'
        params.append(customer_id)
    if start_date:
        query += ' AND t.entry_date >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND t.entry_date <= ?'
        params.append(end_date)

    query += ' ORDER BY t.entry_date DESC LIMIT 500'

    cursor.execute(query, params)
    entries = rows_to_list(cursor.fetchall())
    conn.close()
    return jsonify({'time_entries': entries})


@app.route('/api/time-entries', methods=['POST'])
def add_time_entry():
    data = request.json
    required = ['customer_id', 'entry_date']
    for field in required:
        if field not in data:
            return jsonify({'error': f'Missing required field: {field}'}), 400

    arrive = data.get('arrive_time')  # e.g. "08:30"
    depart = data.get('depart_time')  # e.g. "11:45"
    hours = data.get('hours')
    if arrive and depart and not hours:
        from datetime import datetime as _dt
        fmt = '%H:%M'
        delta = _dt.strptime(depart, fmt) - _dt.strptime(arrive, fmt)
        hours = round(delta.seconds / 3600, 2)
    if not hours:
        return jsonify({'error': 'Either hours or arrive/depart times are required'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO time_entries (customer_id, job_id, entry_date, start_time, end_time, hours, description, cost_code, source)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'app')
    ''', (data['customer_id'], data.get('job_id'), data['entry_date'],
          arrive, depart, hours, data.get('description', ''), data.get('cost_code', '')))
    entry_id = cursor.lastrowid
    conn.commit()
    cursor.execute('''
        SELECT t.id, t.customer_id, t.job_id, t.entry_date, t.start_time, t.end_time,
               t.hours, t.description, t.cost_code, t.source,
               c.name as customer_name, j.invoice_id
        FROM time_entries t
        LEFT JOIN customers c ON t.customer_id = c.id
        LEFT JOIN jobs j ON t.job_id = j.id
        WHERE t.id = ?
    ''', (entry_id,))
    entry = row_to_dict(cursor.fetchone())
    conn.close()
    return jsonify(entry), 201


@app.route('/api/time-entries/<int:te_id>', methods=['PUT'])
def update_time_entry(te_id):
    """Edit a time entry — hours, times, date, description, or reassign job."""
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    conn = get_db()
    cursor = conn.cursor()

    te = cursor.execute('SELECT * FROM time_entries WHERE id = ?', (te_id,)).fetchone()
    if not te:
        conn.close()
        return jsonify({'error': 'Time entry not found'}), 404

    fields = []
    params = []

    if 'hours' in data:
        fields.append('hours = ?')
        params.append(float(data['hours']))
    if 'entry_date' in data:
        fields.append('entry_date = ?')
        params.append(data['entry_date'])
    if 'arrive_time' in data:
        fields.append('start_time = ?')
        params.append(data['arrive_time'])
    if 'depart_time' in data:
        fields.append('end_time = ?')
        params.append(data['depart_time'])
    if 'description' in data:
        fields.append('description = ?')
        params.append(data['description'])
    if 'cost_code' in data:
        fields.append('cost_code = ?')
        params.append(data['cost_code'])
    if 'job_id' in data:
        new_job_id = data['job_id']
        if new_job_id:
            job = cursor.execute('SELECT id, customer_id FROM jobs WHERE id = ?', (new_job_id,)).fetchone()
            if not job:
                conn.close()
                return jsonify({'error': 'Target job not found'}), 404
            fields.append('job_id = ?')
            params.append(new_job_id)
            fields.append('customer_id = ?')
            params.append(job['customer_id'])
        else:
            fields.append('job_id = NULL')

    if not fields:
        conn.close()
        return jsonify({'error': 'No valid fields to update'}), 400

    params.append(te_id)
    cursor.execute(f'UPDATE time_entries SET {", ".join(fields)} WHERE id = ?', params)
    conn.commit()

    updated = cursor.execute('''
        SELECT te.*, c.name as customer_name, j.invoice_id
        FROM time_entries te
        LEFT JOIN customers c ON te.customer_id = c.id
        LEFT JOIN jobs j ON te.job_id = j.id
        WHERE te.id = ?
    ''', (te_id,)).fetchone()
    conn.close()
    return jsonify(dict(updated))


@app.route('/api/time-entries/<int:te_id>', methods=['DELETE'])
def delete_time_entry(te_id):
    conn = get_db()
    cursor = conn.cursor()
    te = cursor.execute('SELECT id FROM time_entries WHERE id = ?', (te_id,)).fetchone()
    if not te:
        conn.close()
        return jsonify({'error': 'Time entry not found'}), 404
    cursor.execute('DELETE FROM time_entries WHERE id = ?', (te_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})


# ============================================================
# EXPENSES
# ============================================================

EXPENSE_CATEGORIES = [
    'Materials & Supplies',
    'Fuel & Transportation',
    'Tools & Equipment',
    'Equipment Repair & Maintenance',
    'Subcontractors',
    'Insurance',
    'Licensing & Permits',
    'Marketing & Advertising',
    'Office & Administrative',
    'Phone & Communications',
    'Clothing & Safety Gear',
    'Professional Development',
    'Disposal & Dump Fees',
    'Other',
]


@app.route('/api/expenses')
def list_expenses():
    conn = get_db()
    cursor = conn.cursor()

    job_id     = request.args.get('job_id')
    overhead   = request.args.get('overhead')  # '1' or '0'
    category   = request.args.get('category')
    start_date = request.args.get('start_date')
    end_date   = request.args.get('end_date')

    query = '''
        SELECT e.id, e.description, e.cost, e.vendor, e.expense_date,
               e.expense_category, e.is_overhead, e.payment_method, e.notes,
               e.job_id, e.customer_id, e.receipt_path,
               c.name as customer_name,
               COALESCE(i.invoice_number, j.invoice_id) as invoice_number
        FROM materials_expenses e
        LEFT JOIN customers c ON e.customer_id = c.id
        LEFT JOIN jobs j ON e.job_id = j.id
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE 1=1
    '''
    params = []

    if job_id:
        query += ' AND e.job_id = ?'
        params.append(job_id)
    if overhead is not None:
        query += ' AND e.is_overhead = ?'
        params.append(int(overhead))
    if category:
        query += ' AND e.expense_category = ?'
        params.append(category)
    if start_date:
        query += ' AND e.expense_date >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND e.expense_date <= ?'
        params.append(end_date)

    query += ' ORDER BY e.expense_date DESC, e.id DESC LIMIT 500'
    cursor.execute(query, params)
    expenses = rows_to_list(cursor.fetchall())
    conn.close()
    return jsonify(expenses)


@app.route('/api/expenses', methods=['POST'])
def create_expense():
    data = request.json
    if not data or not data.get('cost') or not data.get('description'):
        return jsonify({'error': 'description and cost are required'}), 400

    conn = get_db()
    cursor = conn.cursor()
    expense_date = data.get('expense_date') or datetime.today().strftime('%Y-%m-%d')
    is_overhead  = 1 if (data.get('is_overhead') or not data.get('job_id')) else 0
    customer_id  = data.get('customer_id')

    # If job_id given and no customer_id, derive it
    if data.get('job_id') and not customer_id:
        row = cursor.execute('SELECT customer_id FROM jobs WHERE id = ?', (data['job_id'],)).fetchone()
        if row:
            customer_id = row['customer_id']

    cursor.execute('''
        INSERT INTO materials_expenses
        (job_id, customer_id, description, cost, vendor, expense_date,
         expense_category, is_overhead, payment_method, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (data.get('job_id'), customer_id, data['description'],
          float(data['cost']), data.get('vendor', ''), expense_date,
          data.get('expense_category', 'Materials & Supplies'),
          is_overhead, data.get('payment_method', ''), data.get('notes', '')))
    exp_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': exp_id, 'message': 'Expense recorded'}), 201


@app.route('/api/expenses/<int:exp_id>', methods=['PUT'])
def update_expense(exp_id):
    data = request.json
    if not data:
        return jsonify({'error': 'No data'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE materials_expenses SET
            description = ?, cost = ?, vendor = ?, expense_date = ?,
            expense_category = ?, is_overhead = ?, payment_method = ?,
            notes = ?, job_id = ?
        WHERE id = ?
    ''', (data.get('description'), float(data.get('cost', 0)), data.get('vendor', ''),
          data.get('expense_date'), data.get('expense_category'),
          1 if data.get('is_overhead') else 0, data.get('payment_method', ''),
          data.get('notes', ''), data.get('job_id'), exp_id))
    conn.commit()
    conn.close()
    return jsonify({'id': exp_id, 'message': 'Updated'})


@app.route('/api/expenses/<int:exp_id>', methods=['DELETE'])
def delete_expense(exp_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM materials_expenses WHERE id = ?', (exp_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})


@app.route('/api/expenses/categories')
def expense_categories():
    return jsonify(EXPENSE_CATEGORIES)


@app.route('/api/expenses/summary')
def expense_summary():
    """Totals by category and overhead vs job-specific for a date range."""
    conn = get_db()
    cursor = conn.cursor()
    start_date = request.args.get('start_date', '2000-01-01')
    end_date   = request.args.get('end_date', '2099-12-31')

    cursor.execute('''
        SELECT expense_category,
               SUM(CASE WHEN is_overhead = 1 THEN cost ELSE 0 END) as overhead_total,
               SUM(CASE WHEN is_overhead = 0 THEN cost ELSE 0 END) as job_total,
               SUM(cost) as grand_total,
               COUNT(*) as count
        FROM materials_expenses
        WHERE expense_date BETWEEN ? AND ?
        GROUP BY expense_category
        ORDER BY grand_total DESC
    ''', (start_date, end_date))
    by_category = rows_to_list(cursor.fetchall())

    cursor.execute('''
        SELECT
            SUM(CASE WHEN is_overhead = 1 THEN cost ELSE 0 END) as total_overhead,
            SUM(CASE WHEN is_overhead = 0 THEN cost ELSE 0 END) as total_job_costs,
            SUM(cost) as total_expenses
        FROM materials_expenses
        WHERE expense_date BETWEEN ? AND ?
    ''', (start_date, end_date))
    totals = row_to_dict(cursor.fetchone())
    conn.close()
    return jsonify({'by_category': by_category, 'totals': totals})


# ============================================================
# INVOICES
# ============================================================

@app.route('/api/invoices')
def list_invoices():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT i.id, i.invoice_number, i.invoice_date, i.total_labor,
               i.total_materials, i.total_amount, i.status,
               c.name as customer
        FROM invoices i
        JOIN customers c ON i.customer_id = c.id
        ORDER BY i.invoice_date DESC
    ''')
    invoices = rows_to_list(cursor.fetchall())
    conn.close()
    return jsonify(invoices)


# ============================================================
# SERVICE CATEGORIES
# ============================================================

@app.route('/api/categories')
@app.route('/api/service-categories')
def list_categories():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT sc.id, sc.name, sc.description, sc.is_labor,
               sc.parent_id,
               COUNT(sp.id) as usage_count,
               COALESCE(SUM(sp.amount), 0) as total_revenue
        FROM service_categories sc
        LEFT JOIN services_performed sp ON sc.name = sp.category
        GROUP BY sc.id
        ORDER BY sc.parent_id NULLS FIRST, sc.name
    ''')
    categories = rows_to_list(cursor.fetchall())
    conn.close()
    return jsonify(categories)


@app.route('/api/categories', methods=['POST'])
def create_category():
    data = request.json
    if not data or not data.get('name'):
        return jsonify({'error': 'Category name is required'}), 400

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute(
            'INSERT INTO service_categories (name, description, is_labor, parent_id) VALUES (?, ?, ?, ?)',
            (data['name'].strip(), data.get('description', ''),
             1 if data.get('is_labor', True) else 0,
             data.get('parent_id'))
        )
        cat_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Category already exists'}), 409
    conn.close()
    return jsonify({'id': cat_id, 'name': data['name']}), 201


@app.route('/api/categories/<int:cat_id>', methods=['PUT'])
def update_category(cat_id):
    data = request.json
    if not data:
        return jsonify({'error': 'No data'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'UPDATE service_categories SET name=?, description=?, is_labor=?, parent_id=? WHERE id=?',
        (data.get('name'), data.get('description'), 1 if data.get('is_labor', True) else 0,
         data.get('parent_id'), cat_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'id': cat_id, 'message': 'Updated'})


@app.route('/api/categories/<int:cat_id>', methods=['DELETE'])
def delete_category(cat_id):
    conn = get_db()
    cursor = conn.cursor()
    # Prevent deleting categories that have children or are in use
    cursor.execute('SELECT COUNT(*) as cnt FROM service_categories WHERE parent_id = ?', (cat_id,))
    if cursor.fetchone()['cnt'] > 0:
        conn.close()
        return jsonify({'error': 'Category has subcategories — delete those first'}), 409
    cursor.execute('DELETE FROM service_categories WHERE id = ?', (cat_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Deleted'})


# ============================================================
# PRICING SUGGESTIONS (for Estimate form)
# ============================================================

@app.route('/api/pricing/claude-suggest', methods=['POST'])
def pricing_claude_suggest():
    """Use Claude API to suggest pricing for a service description."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set', 'available': False}), 200

    data = request.json or {}
    description = data.get('description', '')
    category = data.get('category', '')
    historical = data.get('historical', {})

    prompt = f"""You are a pricing advisor for a one-person handyman business in Mountain Home, AR (rural Ozarks).

Service to price: {description}
Category: {category}
My historical data for this category: {json.dumps(historical) if historical else 'No history yet'}

Provide a concise JSON response with these fields:
- suggested_low: lower end of a fair price range (integer dollars)
- suggested_high: upper end of a fair price range (integer dollars)
- suggested_price: your single best recommendation (integer dollars)
- rationale: 1-2 sentence plain-English explanation of the pricing
- factors: array of 2-4 short strings noting key factors (difficulty, materials, time, etc.)

Base pricing on: rural Arkansas labor rates (~$45-85/hr skilled trades), realistic job complexity, material costs typical for Mountain Home area, and the goal of staying competitive while being profitable. Respond with ONLY valid JSON, no other text."""

    try:
        req_data = json.dumps({
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 400,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=req_data,
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
        text = result['content'][0]['text'].strip()
        suggestion = json.loads(text)
        suggestion['available'] = True
        return jsonify(suggestion)
    except Exception as e:
        return jsonify({'error': str(e), 'available': False}), 200


@app.route('/api/pricing/suggest')
def pricing_suggest():
    category = request.args.get('category')
    if not category:
        return jsonify({'error': 'category is required'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT AVG(amount) as avg_price, MIN(amount) as min_price,
               MAX(amount) as max_price, COUNT(*) as job_count
        FROM services_performed
        WHERE category = ? AND service_type = 'labor' AND amount > 0
    ''', (category,))
    row = cursor.fetchone()

    cursor.execute('''
        SELECT amount FROM services_performed
        WHERE category = ? AND service_type = 'labor' AND amount > 0
        ORDER BY rowid DESC LIMIT 3
    ''', (category,))
    recent = [r['amount'] for r in cursor.fetchall()]
    conn.close()

    if not row or not row['job_count']:
        return jsonify({'category': category, 'avg_price': None, 'job_count': 0})

    return jsonify({
        'category': category,
        'avg_price': round(row['avg_price'], 2),
        'min_price': round(row['min_price'], 2),
        'max_price': round(row['max_price'], 2),
        'job_count': row['job_count'],
        'recent_prices': recent
    })


@app.route('/api/pricing/suggest-all')
def pricing_suggest_all():
    """Return pricing hints for all categories at once (loaded on page open)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT category,
               ROUND(AVG(amount), 2) as avg_price,
               ROUND(MIN(amount), 2) as min_price,
               ROUND(MAX(amount), 2) as max_price,
               COUNT(*) as job_count
        FROM services_performed
        WHERE service_type = 'labor' AND amount > 0 AND category IS NOT NULL
        GROUP BY category
    ''')
    rows = cursor.fetchall()

    # Avg days on site per category (from jobs that have that service category + time entries)
    cursor.execute('''
        SELECT sp.category,
               ROUND(AVG(day_count), 1) as avg_days
        FROM (
            SELECT sp2.job_id, sp2.category,
                   COUNT(DISTINCT te.entry_date) as day_count
            FROM services_performed sp2
            JOIN time_entries te ON te.job_id = sp2.job_id
            WHERE sp2.service_type = 'labor' AND sp2.category IS NOT NULL
            GROUP BY sp2.job_id, sp2.category
            HAVING day_count > 0
        ) sp
        GROUP BY sp.category
    ''')
    days_by_cat = {r['category']: r['avg_days'] for r in cursor.fetchall()}

    result = {}
    for row in rows:
        cat = row['category']
        cursor.execute('''
            SELECT amount FROM services_performed
            WHERE category = ? AND service_type = 'labor' AND amount > 0
            ORDER BY rowid DESC LIMIT 3
        ''', (cat,))
        recent = [r['amount'] for r in cursor.fetchall()]
        result[cat] = {
            'avg_price': row['avg_price'],
            'min_price': row['min_price'],
            'max_price': row['max_price'],
            'job_count': row['job_count'],
            'recent_prices': recent,
            'avg_days': days_by_cat.get(cat),
        }

    conn.close()
    return jsonify(result)


# ============================================================
# BUSINESS INSIGHTS (Claude-powered analysis)
# ============================================================

_insights_cache = {}  # key -> (timestamp, payload)

@app.route('/api/insights')
def get_insights():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not set', 'available': False}), 200

    force = request.args.get('force') == '1'
    cache_key = 'insights_v1'
    now = _time.time()
    if not force and cache_key in _insights_cache:
        ts, cached = _insights_cache[cache_key]
        if now - ts < 3600:
            return jsonify(cached)

    conn = get_db()
    cursor = conn.cursor()

    # Monthly jobs + revenue, last 24 months
    cursor.execute('''
        SELECT SUBSTR(j.start_date, 1, 7) as month,
               COUNT(j.id) as job_count,
               COALESCE(SUM(i.total_labor + i.total_materials), 0) as revenue
        FROM jobs j
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE j.start_date >= date('now', '-24 months')
          AND j.status NOT IN ('estimate', 'rejected')
        GROUP BY month ORDER BY month
    ''')
    monthly = rows_to_list(cursor.fetchall())

    # Top service categories with seasonal month breakdown
    cursor.execute('''
        SELECT sp.category,
               COUNT(DISTINCT sp.job_id) as job_count,
               ROUND(COALESCE(SUM(sp.amount * COALESCE(sp.quantity, 1)), 0), 0) as total_revenue,
               ROUND(AVG(sp.amount), 0) as avg_per_job,
               GROUP_CONCAT(DISTINCT CAST(CAST(SUBSTR(j.start_date, 6, 2) AS INTEGER) AS TEXT)) as months
        FROM services_performed sp
        JOIN jobs j ON sp.job_id = j.id
        WHERE j.start_date >= date('now', '-24 months')
          AND sp.service_type = 'labor'
          AND sp.category IS NOT NULL AND sp.category != ''
        GROUP BY sp.category
        HAVING job_count > 0
        ORDER BY total_revenue DESC
        LIMIT 15
    ''')
    categories = rows_to_list(cursor.fetchall())

    # Customer repeat rate
    cursor.execute('''
        SELECT customer_id, COUNT(*) as cnt
        FROM jobs
        WHERE start_date >= date('now', '-24 months')
          AND status NOT IN ('estimate', 'rejected')
        GROUP BY customer_id
    ''')
    cust_rows = cursor.fetchall()
    repeat_count  = sum(1 for r in cust_rows if r['cnt'] > 1)
    onetime_count = sum(1 for r in cust_rows if r['cnt'] == 1)

    # 24-month totals
    cursor.execute('''
        SELECT COALESCE(SUM(i.total_labor + i.total_materials), 0) as revenue,
               COUNT(DISTINCT j.id) as jobs,
               COUNT(DISTINCT j.customer_id) as customers,
               COALESCE(SUM(i.total_labor), 0) as labor_revenue,
               COALESCE(SUM(i.total_materials), 0) as materials_revenue
        FROM jobs j
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE j.start_date >= date('now', '-24 months')
          AND j.status NOT IN ('estimate', 'rejected')
    ''')
    totals = dict(cursor.fetchone())

    cursor.execute('''
        SELECT COALESCE(SUM(cost), 0) as total
        FROM materials_expenses
        WHERE expense_date >= date('now', '-24 months')
    ''')
    expenses_total = (cursor.fetchone()['total'] or 0)

    # Avg hourly rate (last 24 months)
    cursor.execute('''
        SELECT SUM(i.total_labor) as labor, SUM(te.hours) as hours
        FROM jobs j
        JOIN invoices i ON j.id = i.job_id
        JOIN (SELECT job_id, SUM(hours) as hours FROM time_entries
              WHERE entry_date >= date('now', '-24 months') AND job_id IS NOT NULL
              GROUP BY job_id) te ON j.id = te.job_id
        WHERE j.start_date >= date('now', '-24 months')
    ''')
    rate_row = cursor.fetchone()
    avg_hr = round((rate_row['labor'] or 0) / rate_row['hours'], 2) if rate_row and (rate_row['hours'] or 0) > 0 else 0

    conn.close()

    # Summarise busy/slow months from monthly job counts
    mo_names = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
    month_agg = {}
    for m in monthly:
        mo = int(m['month'][5:7])
        month_agg[mo] = month_agg.get(mo, 0) + m['job_count']
    ranked = sorted(month_agg.items(), key=lambda x: x[1], reverse=True)
    busy_months = [mo_names[m-1] for m, _ in ranked[:3] if _ > 0]
    slow_months  = [mo_names[m-1] for m, _ in ranked[-3:] if _ > 0]

    revenue = totals.get('revenue') or 0
    profit  = revenue - expenses_total

    summary = {
        'business': "Beard's Home Services, one-man handyman, Mountain Home AR (rural Ozarks)",
        'data_period': 'last 24 months',
        'totals': {
            'jobs': totals.get('jobs', 0),
            'customers_served': totals.get('customers', 0),
            'repeat_customers': repeat_count,
            'one_time_customers': onetime_count,
            'total_revenue': round(revenue),
            'labor_revenue': round(totals.get('labor_revenue') or 0),
            'materials_revenue': round(totals.get('materials_revenue') or 0),
            'total_expenses': round(expenses_total),
            'profit': round(profit),
            'avg_hourly_rate': avg_hr,
        },
        'monthly_breakdown': monthly,
        'service_categories': categories,
        'busiest_months': busy_months,
        'slowest_months': slow_months,
    }

    prompt = f"""You are a no-nonsense business advisor for Brian, who runs a one-man handyman business called Beard's Home Services in Mountain Home, Arkansas. Analyze his real business data from the last 24 months and produce 6 specific, actionable insights.

DATA:
{json.dumps(summary, indent=2)}

Month numbers in 'months' field: 1=Jan 2=Feb 3=Mar 4=Apr 5=May 6=Jun 7=Jul 8=Aug 9=Sep 10=Oct 11=Nov 12=Dec

INSTRUCTIONS:
- Be specific: name actual categories, months, and dollar amounts from the data
- Each action must be something Brian can do in the next 2-4 weeks
- Look for: seasonal timing windows, high-value underutilized service types, slow-season gap fillers, repeat customer opportunities, pricing adjustments, and marketing timing
- If repeat_customers is low relative to total, flag it
- If certain categories spike in certain months, flag the "book ahead" window 2 months earlier
- Think like a contractor who knows the Ozarks market

Return ONLY a valid JSON array of exactly 6 objects, no other text. Each object:
{{
  "type": "seasonal" | "pricing" | "marketing" | "focus" | "efficiency" | "warning",
  "title": "5-8 word punchy headline",
  "insight": "2-3 sentences grounded in the actual numbers",
  "action": "Specific thing Brian should do in the next 2-4 weeks",
  "priority": "high" | "medium" | "low"
}}"""

    try:
        req_data = json.dumps({
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 2000,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=req_data,
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
        text = result['content'][0]['text'].strip()
        # Strip markdown code fences if present
        if text.startswith('```'):
            text = text.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        insights = json.loads(text)
        payload = {'insights': insights, 'available': True, 'summary': {
            'jobs': summary['totals']['jobs'],
            'revenue': summary['totals']['total_revenue'],
            'profit': summary['totals']['profit'],
            'busiest': busy_months,
            'slowest': slow_months,
        }}
        _insights_cache[cache_key] = (_time.time(), payload)
        return jsonify(payload)
    except Exception as e:
        return jsonify({'error': str(e), 'available': False}), 200


# ============================================================
# TRIPS
# ============================================================

TRIP_TYPES = ['job_site', 'supply_planned', 'supply_unplanned', 'other']


@app.route('/api/trips')
def list_trips():
    conn = get_db()
    cursor = conn.cursor()

    start = request.args.get('start')
    end = request.args.get('end')
    trip_type = request.args.get('type')
    customer_id = request.args.get('customer_id')
    job_id = request.args.get('job_id')

    query = '''
        SELECT t.id, t.trip_date, t.trip_type, t.destination,
               t.customer_id, t.job_id, t.miles, t.drive_time_minutes,
               t.notes, t.created_at,
               c.name as customer_name,
               COALESCE(i.invoice_number, j.invoice_id) as job_number
        FROM trips t
        LEFT JOIN customers c ON t.customer_id = c.id
        LEFT JOIN jobs j ON t.job_id = j.id
        LEFT JOIN invoices i ON j.id = i.job_id
        WHERE 1=1
    '''
    params = []

    if start:
        query += ' AND t.trip_date >= ?'
        params.append(start)
    if end:
        query += ' AND t.trip_date <= ?'
        params.append(end)
    if trip_type:
        query += ' AND t.trip_type = ?'
        params.append(trip_type)
    if customer_id:
        query += ' AND t.customer_id = ?'
        params.append(customer_id)
    if job_id:
        query += ' AND t.job_id = ?'
        params.append(job_id)

    query += ' ORDER BY t.trip_date DESC, t.id DESC LIMIT 500'
    cursor.execute(query, params)
    trips = rows_to_list(cursor.fetchall())
    conn.close()
    return jsonify(trips)


@app.route('/api/trips', methods=['POST'])
def create_trip():
    data = request.json
    if not data or not data.get('trip_date') or not data.get('trip_type'):
        return jsonify({'error': 'trip_date and trip_type are required'}), 400
    if data['trip_type'] not in TRIP_TYPES:
        return jsonify({'error': f'trip_type must be one of: {", ".join(TRIP_TYPES)}'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trips (trip_date, trip_type, destination, customer_id, job_id,
                           miles, drive_time_minutes, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (data['trip_date'], data['trip_type'], data.get('destination'),
          data.get('customer_id'), data.get('job_id'),
          data.get('miles'), data.get('drive_time_minutes'), data.get('notes', '')))
    trip_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': trip_id, 'message': 'Trip logged'}), 201


@app.route('/api/trips/<int:trip_id>', methods=['PUT'])
def update_trip(trip_id):
    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM trips WHERE id = ?', (trip_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Trip not found'}), 404

    if data.get('trip_type') and data['trip_type'] not in TRIP_TYPES:
        conn.close()
        return jsonify({'error': f'trip_type must be one of: {", ".join(TRIP_TYPES)}'}), 400

    cursor.execute('''
        UPDATE trips SET trip_date = ?, trip_type = ?, destination = ?, customer_id = ?,
                         job_id = ?, miles = ?, drive_time_minutes = ?, notes = ?
        WHERE id = ?
    ''', (data.get('trip_date'), data.get('trip_type'), data.get('destination'),
          data.get('customer_id'), data.get('job_id'), data.get('miles'),
          data.get('drive_time_minutes'), data.get('notes', ''), trip_id))
    conn.commit()
    conn.close()
    return jsonify({'id': trip_id, 'message': 'Trip updated'})


@app.route('/api/trips/<int:trip_id>', methods=['DELETE'])
def delete_trip(trip_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM trips WHERE id = ?', (trip_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({'error': 'Trip not found'}), 404
    cursor.execute('DELETE FROM trips WHERE id = ?', (trip_id,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'Trip deleted'})


@app.route('/api/trips/summary')
def trips_summary():
    conn = get_db()
    cursor = conn.cursor()

    start = request.args.get('start')
    end = request.args.get('end')

    date_filter = ''
    date_params = []
    if start and end:
        date_filter = 'AND trip_date BETWEEN ? AND ?'
        date_params = [start, end]
    elif start:
        date_filter = 'AND trip_date >= ?'
        date_params = [start]
    elif end:
        date_filter = 'AND trip_date <= ?'
        date_params = [end]

    # Overall totals
    cursor.execute(f'''
        SELECT COALESCE(SUM(miles), 0) as total_miles,
               COALESCE(SUM(drive_time_minutes), 0) as total_drive_minutes
        FROM trips WHERE 1=1 {date_filter}
    ''', date_params)
    totals = cursor.fetchone()

    # By trip type
    cursor.execute(f'''
        SELECT trip_type,
               COUNT(*) as count,
               COALESCE(SUM(miles), 0) as miles,
               COALESCE(SUM(drive_time_minutes), 0) as drive_minutes
        FROM trips WHERE 1=1 {date_filter}
        GROUP BY trip_type
        ORDER BY miles DESC
    ''', date_params)
    by_type = rows_to_list(cursor.fetchall())

    # Monthly breakdown
    cursor.execute(f'''
        SELECT SUBSTR(trip_date, 1, 7) as month,
               COALESCE(SUM(miles), 0) as miles,
               COUNT(*) as trips
        FROM trips WHERE 1=1 {date_filter}
        GROUP BY month
        ORDER BY month
    ''', date_params)
    monthly = rows_to_list(cursor.fetchall())

    conn.close()

    total_miles = totals['total_miles'] or 0
    irs_rate = 0.70  # 2026 IRS mileage rate
    return jsonify({
        'total_miles': total_miles,
        'total_drive_minutes': totals['total_drive_minutes'] or 0,
        'by_type': by_type,
        'monthly': monthly,
        'irs_deduction_estimate': round(total_miles * irs_rate, 2),
    })


# ============================================================
# P&L REPORT
# ============================================================

@app.route('/api/reports/pl')
def pl_report():
    """Profit & Loss report with optional date range, customer, and category filters."""
    conn = get_db()
    cursor = conn.cursor()

    start = request.args.get('start')
    end = request.args.get('end')
    filter_customer_id = request.args.get('customer_id')
    filter_category = request.args.get('category')

    # Build date filter clauses
    if start and end:
        inv_df = 'AND COALESCE(i.invoice_date, j.start_date) BETWEEN ? AND ?'
        inv_dp = [start, end]
        exp_df = 'AND COALESCE(e.expense_date, DATE(e.created_at)) BETWEEN ? AND ?'
        exp_dp = [start, end]
        te_df = 'AND te.date BETWEEN ? AND ?'
        te_dp = [start, end]
        trip_df = 'AND t.trip_date BETWEEN ? AND ?'
        trip_dp = [start, end]
        job_df = 'AND j.start_date BETWEEN ? AND ?'
        job_dp = [start, end]
    elif start:
        inv_df = 'AND COALESCE(i.invoice_date, j.start_date) >= ?'
        inv_dp = [start]
        exp_df = 'AND COALESCE(e.expense_date, DATE(e.created_at)) >= ?'
        exp_dp = [start]
        te_df = 'AND te.date >= ?'
        te_dp = [start]
        trip_df = 'AND t.trip_date >= ?'
        trip_dp = [start]
        job_df = 'AND j.start_date >= ?'
        job_dp = [start]
    elif end:
        inv_df = 'AND COALESCE(i.invoice_date, j.start_date) <= ?'
        inv_dp = [end]
        exp_df = 'AND COALESCE(e.expense_date, DATE(e.created_at)) <= ?'
        exp_dp = [end]
        te_df = 'AND te.date <= ?'
        te_dp = [end]
        trip_df = 'AND t.trip_date <= ?'
        trip_dp = [end]
        job_df = 'AND j.start_date <= ?'
        job_dp = [end]
    else:
        inv_df = ''
        inv_dp = []
        exp_df = ''
        exp_dp = []
        te_df = ''
        te_dp = []
        trip_df = ''
        trip_dp = []
        job_df = ''
        job_dp = []

    # Optional customer filter
    cust_inv_df = ''
    cust_inv_dp = []
    cust_exp_df = ''
    cust_exp_dp = []
    cust_te_df = ''
    cust_te_dp = []
    if filter_customer_id:
        cust_inv_df = 'AND i.customer_id = ?'
        cust_inv_dp = [filter_customer_id]
        cust_exp_df = 'AND e.customer_id = ?'
        cust_exp_dp = [filter_customer_id]
        cust_te_df = 'AND te.customer_id = ?'
        cust_te_dp = [filter_customer_id]

    # Optional category filter (join through services_performed)
    cat_inv_df = ''
    cat_inv_dp = []
    if filter_category:
        cat_inv_df = 'AND EXISTS (SELECT 1 FROM services_performed sp WHERE sp.job_id = j.id AND sp.category = ?)'
        cat_inv_dp = [filter_category]

    # --- Revenue summary ---
    cursor.execute(f'''
        SELECT COALESCE(SUM(i.total_labor), 0) as total_labor,
               COALESCE(SUM(i.total_materials), 0) as total_materials,
               COALESCE(SUM(i.total_amount), 0) as total_amount,
               COUNT(DISTINCT i.id) as job_count
        FROM invoices i
        LEFT JOIN jobs j ON i.job_id = j.id
        WHERE 1=1 {inv_df} {cust_inv_df} {cat_inv_df}
    ''', inv_dp + cust_inv_dp + cat_inv_dp)
    rev_row = cursor.fetchone()

    # --- Expenses summary ---
    cursor.execute(f'''
        SELECT COALESCE(SUM(CASE WHEN e.is_overhead = 1 THEN e.cost ELSE 0 END), 0) as total_overhead,
               COALESCE(SUM(CASE WHEN e.is_overhead = 0 THEN e.cost ELSE 0 END), 0) as total_job_expenses,
               COALESCE(SUM(e.cost), 0) as total_expenses
        FROM materials_expenses e
        WHERE 1=1 {exp_df} {cust_exp_df}
    ''', exp_dp + cust_exp_dp)
    exp_row = cursor.fetchone()

    # --- Hours summary ---
    cursor.execute(f'''
        SELECT COALESCE(SUM(te.hours), 0) as total_hours
        FROM time_entries te
        WHERE 1=1 {te_df} {cust_te_df}
    ''', te_dp + cust_te_dp)
    hours_row = cursor.fetchone()

    # --- Mileage deduction (from trips) ---
    cursor.execute(f'''
        SELECT COALESCE(SUM(t.miles), 0) as total_miles
        FROM trips t
        WHERE 1=1 {trip_df}
    ''', trip_dp)
    miles_row = cursor.fetchone()
    total_miles = miles_row['total_miles'] or 0
    mileage_deduction = round(total_miles * 0.70, 2)

    # --- By month ---
    cursor.execute(f'''
        SELECT SUBSTR(COALESCE(i.invoice_date, j.start_date), 1, 7) as month,
               COALESCE(SUM(i.total_amount), 0) as revenue,
               COUNT(DISTINCT i.id) as job_count
        FROM invoices i
        LEFT JOIN jobs j ON i.job_id = j.id
        WHERE COALESCE(i.invoice_date, j.start_date) IS NOT NULL {inv_df} {cust_inv_df} {cat_inv_df}
        GROUP BY month
        ORDER BY month
    ''', inv_dp + cust_inv_dp + cat_inv_dp)
    by_month_rev = {r['month']: dict(r) for r in cursor.fetchall()}

    cursor.execute(f'''
        SELECT SUBSTR(COALESCE(e.expense_date, DATE(e.created_at)), 1, 7) as month,
               COALESCE(SUM(e.cost), 0) as expenses
        FROM materials_expenses e
        WHERE 1=1 {exp_df} {cust_exp_df}
        GROUP BY month
    ''', exp_dp + cust_exp_dp)
    by_month_exp = {r['month']: r['expenses'] for r in cursor.fetchall()}

    cursor.execute(f'''
        SELECT SUBSTR(te.date, 1, 7) as month,
               COALESCE(SUM(te.hours), 0) as hours
        FROM time_entries te
        WHERE 1=1 {te_df} {cust_te_df}
        GROUP BY month
    ''', te_dp + cust_te_dp)
    by_month_hours = {r['month']: r['hours'] for r in cursor.fetchall()}

    all_months = sorted(set(list(by_month_rev.keys()) + list(by_month_exp.keys()) + list(by_month_hours.keys())))
    by_month = []
    for m in all_months:
        rev = by_month_rev.get(m, {}).get('revenue', 0) or 0
        exp = by_month_exp.get(m, 0) or 0
        hrs = by_month_hours.get(m, 0) or 0
        by_month.append({
            'month': m,
            'revenue': round(rev, 2),
            'expenses': round(exp, 2),
            'profit': round(rev - exp, 2),
            'hours': round(hrs, 2),
        })

    # --- By customer ---
    cursor.execute(f'''
        SELECT c.id as customer_id, c.name as customer_name,
               COALESCE(SUM(i.total_amount), 0) as revenue,
               COUNT(DISTINCT j.id) as job_count
        FROM customers c
        JOIN jobs j ON j.customer_id = c.id
        JOIN invoices i ON i.job_id = j.id
        WHERE c.name != '_UNASSIGNED' {inv_df} {cat_inv_df}
        GROUP BY c.id
        ORDER BY revenue DESC
    ''', inv_dp + cat_inv_dp)
    by_customer_rev = {r['customer_id']: dict(r) for r in cursor.fetchall()}

    cursor.execute(f'''
        SELECT e.customer_id, COALESCE(SUM(e.cost), 0) as expenses
        FROM materials_expenses e
        WHERE e.customer_id IS NOT NULL {exp_df}
        GROUP BY e.customer_id
    ''', exp_dp)
    by_customer_exp = {r['customer_id']: r['expenses'] for r in cursor.fetchall()}

    cursor.execute(f'''
        SELECT te.customer_id, COALESCE(SUM(te.hours), 0) as hours
        FROM time_entries te
        WHERE te.customer_id IS NOT NULL {te_df}
        GROUP BY te.customer_id
    ''', te_dp)
    by_customer_hours = {r['customer_id']: r['hours'] for r in cursor.fetchall()}

    cursor.execute(f'''
        SELECT t.customer_id, COALESCE(SUM(t.miles), 0) as miles
        FROM trips t
        WHERE t.customer_id IS NOT NULL {trip_df}
        GROUP BY t.customer_id
    ''', trip_dp)
    by_customer_miles = {r['customer_id']: r['miles'] for r in cursor.fetchall()}

    by_customer = []
    for cid, row in by_customer_rev.items():
        rev = row['revenue'] or 0
        exp = by_customer_exp.get(cid, 0) or 0
        hrs = by_customer_hours.get(cid, 0) or 0
        mi = by_customer_miles.get(cid, 0) or 0
        by_customer.append({
            'customer_id': cid,
            'customer_name': row['customer_name'],
            'revenue': round(rev, 2),
            'expenses': round(exp, 2),
            'profit': round(rev - exp, 2),
            'hours': round(hrs, 2),
            'job_count': row['job_count'],
            'miles': round(mi, 2),
        })

    # --- By service category ---
    cursor.execute(f'''
        SELECT sp.category,
               COALESCE(SUM(sp.amount), 0) as revenue,
               COUNT(DISTINCT sp.job_id) as job_count
        FROM services_performed sp
        JOIN jobs j ON sp.job_id = j.id
        WHERE sp.service_type = 'labor' AND sp.category IS NOT NULL {job_df} {('AND j.customer_id = ?' if filter_customer_id else '')}
        GROUP BY sp.category
        ORDER BY revenue DESC
    ''', job_dp + ([filter_customer_id] if filter_customer_id else []))
    by_category_raw = rows_to_list(cursor.fetchall())

    cursor.execute(f'''
        SELECT sp.category, COALESCE(SUM(te.hours), 0) as hours
        FROM services_performed sp
        JOIN time_entries te ON te.job_id = sp.job_id
        JOIN jobs j ON sp.job_id = j.id
        WHERE sp.service_type = 'labor' AND sp.category IS NOT NULL {job_df}
        GROUP BY sp.category
    ''', job_dp)
    by_category_hours = {r['category']: r['hours'] for r in cursor.fetchall()}

    by_category_list = []
    for r in by_category_raw:
        cat = r['category']
        rev = r['revenue'] or 0
        jc = r['job_count'] or 0
        hrs = by_category_hours.get(cat, 0) or 0
        by_category_list.append({
            'category': cat,
            'revenue': round(rev, 2),
            'hours': round(hrs, 2),
            'job_count': jc,
            'avg_per_job': round(rev / jc, 2) if jc > 0 else 0,
        })

    # --- Expenses by category ---
    cursor.execute(f'''
        SELECT COALESCE(expense_category, 'Uncategorized') as expense_category,
               COALESCE(SUM(cost), 0) as total,
               COUNT(*) as count,
               MAX(is_overhead) as is_overhead
        FROM materials_expenses e
        WHERE 1=1 {exp_df} {cust_exp_df}
        GROUP BY expense_category
        ORDER BY total DESC
    ''', exp_dp + cust_exp_dp)
    expenses_by_category = rows_to_list(cursor.fetchall())

    # --- Waste indicators (unplanned supply trips) ---
    cursor.execute(f'''
        SELECT COUNT(*) as count, COALESCE(SUM(miles), 0) as miles
        FROM trips t
        WHERE t.trip_type = 'supply_unplanned' {trip_df}
    ''', trip_dp)
    waste_row = cursor.fetchone()
    unplanned_miles = waste_row['miles'] or 0
    unplanned_count = waste_row['count'] or 0
    unplanned_cost = round(unplanned_miles * 0.70, 2)

    # --- Effective hourly rate: exclude incomplete jobs ---
    cursor.execute(f'''
        SELECT COALESCE(SUM(i.total_labor), 0) as labor
        FROM invoices i
        LEFT JOIN jobs j ON i.job_id = j.id
        WHERE 1=1 {inv_df} {cust_inv_df} {cat_inv_df}
          AND (j.data_status IS NULL OR j.data_status != 'incomplete')
    ''', inv_dp + cust_inv_dp + cat_inv_dp)
    rate_labor_row = cursor.fetchone()

    cursor.execute(f'''
        SELECT COALESCE(SUM(te.hours), 0) as hours
        FROM time_entries te
        WHERE 1=1 {te_df} {cust_te_df}
          AND (te.job_id IS NULL OR te.job_id NOT IN (SELECT id FROM jobs WHERE data_status = 'incomplete'))
    ''', te_dp + cust_te_dp)
    rate_hours_row = cursor.fetchone()

    conn.close()

    total_revenue = rev_row['total_amount'] or 0
    total_labor_rev = rev_row['total_labor'] or 0
    total_materials_rev = rev_row['total_materials'] or 0
    total_expenses = exp_row['total_expenses'] or 0
    total_overhead = exp_row['total_overhead'] or 0
    total_job_expenses = exp_row['total_job_expenses'] or 0
    total_hours = hours_row['total_hours'] or 0
    net_profit = total_revenue - total_expenses
    rate_labor = rate_labor_row['labor'] or 0
    rate_hours = rate_hours_row['hours'] or 0
    effective_rate = round(rate_labor / rate_hours, 2) if rate_hours > 0 else 0

    return jsonify({
        'summary': {
            'total_revenue': round(total_revenue, 2),
            'total_labor_revenue': round(total_labor_rev, 2),
            'total_materials_revenue': round(total_materials_rev, 2),
            'total_expenses': round(total_expenses, 2),
            'total_overhead': round(total_overhead, 2),
            'total_job_expenses': round(total_job_expenses, 2),
            'net_profit': round(net_profit, 2),
            'total_hours': round(total_hours, 2),
            'effective_hourly_rate': effective_rate,
            'job_count': rev_row['job_count'] or 0,
            'mileage_deduction_estimate': mileage_deduction,
        },
        'by_month': by_month,
        'by_customer': by_customer,
        'by_category': by_category_list,
        'expenses_by_category': expenses_by_category,
        'waste_indicators': {
            'unplanned_supply_trips': unplanned_count,
            'unplanned_supply_miles': round(unplanned_miles, 2),
            'unplanned_trip_cost_estimate': unplanned_cost,
        },
        'date_range': {'start': start, 'end': end},
    })


# ============================================================
# DAY WRAP-UP — bulk end-of-day data entry
# ============================================================

@app.route('/api/day-wrapup', methods=['POST'])
def day_wrapup():
    """
    Accept all end-of-day data in one request and persist it atomically.
    Body shape:
      {
        date: "2026-04-05",
        jobs: [{
          customer_id, job_id (or null),
          new_job_desc, new_job_type,
          arrive_time, depart_time,   -- "HH:MM" 24h
          services: [{name, category, qty, unit, price, is_material}],
          materials: [{description, cost, vendor}],
          payment: {amount, method, memo} or null,
          log_trip, trip_miles, trip_drive_time, trip_notes
        }],
        other_trips: [{
          purpose, destination, customer_id, job_id,
          miles, drive_time, planned, notes
        }],
        expenses: [{
          category, description, amount, vendor,
          is_overhead, job_id, customer_id
        }]
      }
    """
    data = request.json
    if not data or not data.get('date'):
        return jsonify({'error': 'date is required'}), 400

    date = data['date']
    jobs_in  = data.get('jobs', [])
    trips_in = data.get('other_trips', [])
    exps_in  = data.get('expenses', [])

    PURPOSE_MAP = {
        'site_assessment':   'job_site',
        'measuring':         'job_site',
        'payment_pickup':    'job_site',
        'materials_planned': 'supply_planned',
        'materials_unplanned': 'supply_unplanned',
        'fuel':              'other',
        'other':             'other',
    }

    conn = get_db()
    cursor = conn.cursor()
    summary = {'time_entries': 0, 'services': 0, 'materials': 0,
               'payments': 0, 'trips': 0, 'expenses': 0, 'new_jobs': 0}

    try:
        for job_data in jobs_in:
            cust_id = job_data.get('customer_id')
            job_id  = job_data.get('job_id')

            # Create new job + invoice if needed
            if not job_id and cust_id:
                desc = job_data.get('new_job_desc', 'Work logged via Day Wrap-Up')
                svc_type = job_data.get('new_job_type', 'General Handyman')
                today_str = date
                # derive invoice_id from date + customer
                inv_num = 'BHS' + today_str.replace('-', '')
                # make unique if collision
                existing = cursor.execute(
                    'SELECT COUNT(*) FROM jobs WHERE invoice_id LIKE ?', (inv_num + '%',)
                ).fetchone()[0]
                if existing:
                    inv_num = inv_num + chr(ord('A') + existing - 1)
                cursor.execute('''
                    INSERT INTO jobs (customer_id, invoice_id, project_number,
                                      start_date, end_date, status, notes)
                    VALUES (?, ?, ?, ?, ?, 'completed', ?)
                ''', (cust_id, inv_num, inv_num.replace('BHS',''),
                      today_str, today_str, desc))
                job_id = cursor.lastrowid
                # stub invoice
                cursor.execute('''
                    INSERT INTO invoices (invoice_number, customer_id, job_id,
                                          total_labor, total_materials, total_amount,
                                          invoice_date, status)
                    VALUES (?, ?, ?, 0, 0, 0, ?, 'completed')
                ''', (inv_num, cust_id, job_id, today_str))
                summary['new_jobs'] += 1

            # Time entry
            arrive = job_data.get('arrive_time')
            depart = job_data.get('depart_time')
            hours  = job_data.get('hours')
            if arrive and depart and not hours:
                from datetime import datetime as _dt
                try:
                    delta = _dt.strptime(depart, '%H:%M') - _dt.strptime(arrive, '%H:%M')
                    hours = round(delta.seconds / 3600, 2)
                except Exception:
                    hours = None
            if hours and cust_id:
                notes_te = job_data.get('notes', '')
                cursor.execute('''
                    INSERT INTO time_entries
                        (customer_id, job_id, entry_date, start_time, end_time,
                         hours, description, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'Day Wrap-Up')
                ''', (cust_id, job_id, date, arrive, depart, hours, notes_te))
                summary['time_entries'] += 1

            # Services performed
            inv_row = cursor.execute(
                'SELECT id FROM invoices WHERE job_id = ?', (job_id,)
            ).fetchone() if job_id else None
            inv_id = inv_row['id'] if inv_row else None
            add_labor = 0.0
            add_mats  = 0.0
            for svc in job_data.get('services', []):
                if not svc.get('name') and not svc.get('category'):
                    continue
                price = float(svc.get('price') or 0)
                qty   = float(svc.get('qty') or 1)
                total = round(price * qty, 2)
                is_mat = bool(svc.get('is_material', False))
                cursor.execute('''
                    INSERT INTO services_performed
                        (invoice_id, job_id, original_description, standardized_description,
                         category, amount, service_type, quantity, unit_of_measure)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (inv_id, job_id,
                      svc.get('name', ''), svc.get('name', ''),
                      svc.get('category', ''), total,
                      'materials' if is_mat else 'labor',
                      qty, svc.get('unit', 'job')))
                if is_mat:
                    add_mats += total
                else:
                    add_labor += total
                summary['services'] += 1
            # Update invoice totals
            if inv_id and (add_labor or add_mats):
                cursor.execute('''
                    UPDATE invoices
                    SET total_labor    = total_labor + ?,
                        total_materials = total_materials + ?,
                        total_amount   = total_amount + ?
                    WHERE id = ?
                ''', (add_labor, add_mats, add_labor + add_mats, inv_id))

            # Materials/expenses for this job
            for mat in job_data.get('materials', []):
                if not mat.get('description') or not mat.get('cost'):
                    continue
                cursor.execute('''
                    INSERT INTO materials_expenses
                        (job_id, customer_id, description, cost, vendor,
                         expense_date, expense_category, is_overhead, source)
                    VALUES (?, ?, ?, ?, ?, ?, 'Materials & Supplies', 0, 'Day Wrap-Up')
                ''', (job_id, cust_id, mat['description'],
                      float(mat['cost']), mat.get('vendor', ''), date))
                summary['materials'] += 1

            # Payment
            pmt = job_data.get('payment')
            if pmt and pmt.get('amount') and float(pmt['amount']) > 0 and job_id:
                cursor.execute('''
                    INSERT INTO payments
                        (job_id, customer_id, amount, payment_date, payment_method, memo)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (job_id, cust_id, float(pmt['amount']), date,
                      pmt.get('method', 'Cash'), pmt.get('memo', '')))
                # Auto-update job status
                cursor.execute(
                    'SELECT COALESCE(SUM(amount),0) FROM payments WHERE job_id=?', (job_id,)
                )
                total_paid = cursor.fetchone()[0]
                cursor.execute(
                    'SELECT COALESCE(total_amount,0) FROM invoices WHERE job_id=?', (job_id,)
                )
                inv_total = cursor.fetchone()[0]
                if inv_total > 0 and total_paid >= inv_total:
                    cursor.execute("UPDATE jobs SET status='completed' WHERE id=?", (job_id,))
                    cursor.execute("UPDATE invoices SET status='paid' WHERE job_id=?", (job_id,))
                summary['payments'] += 1

            # Trip to job site
            if job_data.get('log_trip') and job_data.get('trip_miles') and cust_id:
                trip_notes = job_data.get('trip_notes', '')
                cursor.execute('''
                    INSERT INTO trips
                        (trip_date, trip_type, destination, customer_id, job_id,
                         miles, drive_time_minutes, notes)
                    VALUES (?, 'job_site', ?, ?, ?, ?, ?, ?)
                ''', (date, job_data.get('trip_destination', ''),
                      cust_id, job_id,
                      float(job_data['trip_miles']),
                      job_data.get('trip_drive_time'),
                      trip_notes))
                summary['trips'] += 1

        # Other trips
        for t in trips_in:
            if not t.get('purpose'):
                continue
            trip_type = PURPOSE_MAP.get(t['purpose'], 'other')
            purpose_label = {
                'site_assessment': 'Site assessment',
                'measuring': 'Measuring/estimate visit',
                'payment_pickup': 'Picked up payment',
                'materials_planned': 'Materials pickup (planned)',
                'materials_unplanned': 'Materials pickup (unplanned)',
                'fuel': 'Fuel stop',
                'other': 'Other trip',
            }.get(t['purpose'], t['purpose'])
            notes = t.get('notes', '')
            full_notes = f"{purpose_label}. {notes}".strip('. ')
            cursor.execute('''
                INSERT INTO trips
                    (trip_date, trip_type, destination, customer_id, job_id,
                     miles, drive_time_minutes, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (date, trip_type, t.get('destination', ''),
                  t.get('customer_id') or None,
                  t.get('job_id') or None,
                  float(t['miles']) if t.get('miles') else None,
                  t.get('drive_time') or None,
                  full_notes))
            summary['trips'] += 1

        # Other expenses (overhead or job-linked)
        for exp in exps_in:
            if not exp.get('description') or not exp.get('amount'):
                continue
            cursor.execute('''
                INSERT INTO materials_expenses
                    (job_id, customer_id, description, cost, vendor,
                     expense_date, expense_category, is_overhead, payment_method, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (exp.get('job_id') or None,
                  exp.get('customer_id') or None,
                  exp['description'], float(exp['amount']),
                  exp.get('vendor', ''), date,
                  exp.get('category', 'Other'),
                  1 if exp.get('is_overhead', True) else 0,
                  exp.get('payment_method', 'Unknown'),
                  exp.get('notes', '')))
            summary['expenses'] += 1

        conn.commit()
        conn.close()
        return jsonify({'ok': True, 'summary': summary}), 201

    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': str(e)}), 500


# ============================================================
# CLOCK IN / NEAREST CUSTOMER
# ============================================================

def _haversine_miles(lat1, lon1, lat2, lon2):
    R = 3959.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(max(0.0, min(1.0, a))))


@app.route('/api/nearest-customer')
def nearest_customer():
    try:
        user_lat = float(request.args.get('lat', 0))
        user_lon = float(request.args.get('lng', 0))
    except ValueError:
        return jsonify({'error': 'Invalid lat/lng'}), 400

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name, address, customer_lat, customer_lon
        FROM customers
        WHERE address IS NOT NULL AND address != '' AND NOT name LIKE '\_%' ESCAPE '\'
    ''')
    customers = rows_to_list(cursor.fetchall())

    # Geocode up to 4 uncached customers per request (keeps response under ~5s)
    geocoded_count = 0
    for c in customers:
        if c['customer_lat'] is None and geocoded_count < 4:
            try:
                encoded = urllib.parse.quote(c['address'] + ', USA')
                url = f'https://nominatim.openstreetmap.org/search?q={encoded}&format=json&limit=1'
                req = urllib.request.Request(url, headers={'User-Agent': 'BeardHomeServices/1.0'})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    geo = json.loads(resp.read())
                if geo:
                    c['customer_lat'] = float(geo[0]['lat'])
                    c['customer_lon'] = float(geo[0]['lon'])
                    cursor.execute('UPDATE customers SET customer_lat=?, customer_lon=? WHERE id=?',
                                   (c['customer_lat'], c['customer_lon'], c['id']))
                    geocoded_count += 1
                    if geocoded_count < 4:
                        _time.sleep(1.1)  # Nominatim rate limit
            except Exception:
                pass

    conn.commit()
    conn.close()

    results = []
    for c in customers:
        if c['customer_lat'] is not None:
            dist = _haversine_miles(user_lat, user_lon, c['customer_lat'], c['customer_lon'])
            results.append({
                'id': c['id'],
                'name': c['name'],
                'address': c['address'],
                'distance_miles': round(dist, 1)
            })

    results.sort(key=lambda x: x['distance_miles'])
    return jsonify(results[:5])


# ============================================================
# HEALTH CHECK
# ============================================================

@app.route('/api/health')
def health():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM customers')
        count = cursor.fetchone()[0]
        conn.close()
        return jsonify({'status': 'healthy', 'database': 'connected', 'customers': count})
    except Exception as e:
        return jsonify({'status': 'ok', 'database': 'initializing', 'note': str(e)})


# ============================================================
# IMPORT JOB — called by process_completed_job.py when RAILWAY_URL is set
# ============================================================

@app.route('/api/import-job', methods=['POST'])
def import_job():
    key = request.headers.get('X-Admin-Key', '')
    if key != os.environ.get('ADMIN_KEY', ''):
        return jsonify({'error': 'unauthorized'}), 401

    data = request.json
    if not data or not data.get('invoice_number'):
        return jsonify({'error': 'invoice_number is required'}), 400

    inv_num = str(data['invoice_number'])
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('SELECT id FROM invoices WHERE invoice_number = ?', (inv_num,))
    if cursor.fetchone():
        conn.close()
        return jsonify({'error': 'already exists', 'invoice_number': inv_num}), 409

    customer_name = data.get('customer_name') or 'Unknown'
    address = data.get('address')
    phone = data.get('phone')

    cursor.execute('SELECT id, address, phone FROM customers WHERE name = ?', (customer_name,))
    row = cursor.fetchone()
    if row:
        cust_id = row['id']
        if address and not row['address']:
            cursor.execute('UPDATE customers SET address = ? WHERE id = ?', (address, cust_id))
        if phone and not row['phone']:
            cursor.execute('UPDATE customers SET phone = ? WHERE id = ?', (phone, cust_id))
    else:
        cursor.execute('INSERT INTO customers (name, address, phone) VALUES (?, ?, ?)',
                       (customer_name, address, phone))
        cust_id = cursor.lastrowid

    services = data.get('services', [])
    time_entries = data.get('time_entries', [])
    total_labor = sum(s['amount'] for s in services if s.get('type') == 'labor')
    total_materials = sum(s['amount'] for s in services if s.get('type') == 'materials')
    total_amount = data.get('total') or (total_labor + total_materials)

    cursor.execute('''
        INSERT INTO jobs (customer_id, invoice_id, project_number, start_date, status)
        VALUES (?, ?, ?, ?, 'completed')
    ''', (cust_id, inv_num, inv_num, data.get('invoice_date')))
    job_id = cursor.lastrowid

    cursor.execute('''
        INSERT INTO invoices
        (invoice_number, customer_id, job_id, total_labor, total_materials,
         total_amount, invoice_date, status, pdf_filename)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'paid', ?)
    ''', (inv_num, cust_id, job_id, total_labor, total_materials,
          total_amount, data.get('invoice_date'), data.get('pdf_filename')))
    invoice_id = cursor.lastrowid

    for svc in services:
        cursor.execute('''
            INSERT INTO services_performed
            (invoice_id, job_id, original_description, standardized_description,
             category, amount, service_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (invoice_id, job_id,
              svc.get('original', ''), svc.get('standardized', ''),
              svc.get('category', ''), svc.get('amount', 0), svc.get('type', 'labor')))

    svc_desc = ', '.join(s.get('standardized', '') for s in services)
    for te in time_entries:
        cursor.execute('''
            INSERT INTO time_entries
            (customer_id, job_id, entry_date, start_time, end_time, hours,
             description, source, cost_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'manual', 'Billable')
        ''', (cust_id, job_id, te.get('date'), te.get('start_time'),
              te.get('end_time'), te.get('hours', 0), svc_desc))

        cursor.execute('''
            INSERT INTO timeline_visits
            (customer_id, job_id, visit_date, arrival_time, departure_time,
             duration_hours, address, source, matched)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'manual', 1)
        ''', (cust_id, job_id, te.get('date'), te.get('arrival_time'),
              te.get('departure_time'), te.get('hours', 0), address or ''))

    conn.commit()
    conn.close()
    return jsonify({
        'ok': True,
        'job_id': job_id,
        'invoice_number': inv_num,
        'customer': customer_name,
        'total': total_amount,
        'services': len(services),
        'time_entries': len(time_entries),
    }), 201


# ============================================================
# ADMIN — database restore (one-time upload from local PC)
# ============================================================

@app.route('/api/admin/restore-db', methods=['POST'])
def restore_db():
    key = request.headers.get('X-Admin-Key', '')
    if key != os.environ.get('ADMIN_KEY', ''):
        return jsonify({'error': 'unauthorized'}), 401

    if 'db' not in request.files:
        return jsonify({'error': 'no db file in request'}), 400

    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    request.files['db'].save(DB_PATH)
    conn = get_db()
    count = conn.execute('SELECT COUNT(*) FROM customers').fetchone()[0]
    conn.close()
    return jsonify({'ok': True, 'customers': count, 'message': 'Database restored'})


@app.route('/api/admin/backup-db', methods=['GET'])
def backup_db():
    """Download the live database file (requires admin key)."""
    from flask import send_file
    key = request.headers.get('X-Admin-Key', '') or request.args.get('key', '')
    if key != os.environ.get('ADMIN_KEY', ''):
        return jsonify({'error': 'unauthorized'}), 401
    return send_file(DB_PATH, as_attachment=True, download_name='beard_business.db',
                     mimetype='application/x-sqlite3')


# ============================================================
# PDF INVOICE IMPORT
# ============================================================

@app.route('/api/invoice/parse-pdf', methods=['POST'])
def parse_invoice_pdf():
    """Upload a PDF invoice, extract text with pdfplumber, parse with Claude."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['file']
    if not f.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'File must be a PDF'}), 400

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not configured'}), 500

    try:
        import pdfplumber
        pdf_bytes = f.read()
        text = ''
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text += (page.extract_text() or '') + '\n'

        if not text.strip():
            return jsonify({'error': 'Could not extract text from this PDF'}), 422

        prompt = f"""Extract invoice data from this text and return ONLY valid JSON with these fields:
- customer_name (string)
- customer_address (string or null)
- customer_phone (string or null)
- invoice_number (string or null)
- invoice_date (YYYY-MM-DD or null)
- services (array of: description string, amount number, service_type 'labor' or 'materials')
- total_labor (number)
- total_materials (number)
- notes (string or null)

Invoice text:
{text[:4000]}

Return ONLY valid JSON."""

        req_data = json.dumps({
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 1200,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=req_data,
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            result = json.loads(resp.read())
        raw = result['content'][0]['text'].strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        parsed = json.loads(raw)
        parsed['raw_text_preview'] = text[:600]
        return jsonify(parsed)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
# MAPS SCREENSHOT IMPORT
# ============================================================

@app.route('/api/maps-screenshot/parse', methods=['POST'])
def parse_maps_screenshot():
    """Upload a Google Maps / Google Photos screenshot, parse visit info with Claude Vision."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    f = request.files['file']
    ext = os.path.splitext(f.filename.lower())[1]
    media_map = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                 '.png': 'image/png', '.webp': 'image/webp', '.gif': 'image/gif'}
    if ext not in media_map:
        return jsonify({'error': 'File must be an image (jpg/png/webp)'}), 400

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'ANTHROPIC_API_KEY not configured'}), 500

    try:
        img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode()
        media_type = media_map[ext]

        req_data = json.dumps({
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 700,
            'messages': [{
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {'type': 'base64', 'media_type': media_type, 'data': img_b64}
                    },
                    {
                        'type': 'text',
                        'text': """This is a screenshot from Google Maps Timeline or Google Photos showing a location visit. Extract visit info and return ONLY valid JSON:
- visit_date (YYYY-MM-DD or null)
- arrival_time (HH:MM 24hr or null)
- departure_time (HH:MM 24hr or null)
- location_name (string - the place/business name)
- address (string or null - street address if visible)
- city (string or null)
- notes (any other relevant details)

Return ONLY valid JSON."""
                    }
                ]
            }]
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=req_data,
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            result = json.loads(resp.read())
        raw = result['content'][0]['text'].strip()
        if raw.startswith('```'):
            raw = raw.split('\n', 1)[1].rsplit('```', 1)[0].strip()
        return jsonify(json.loads(raw))
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================
<<<<<<< HEAD
# LEADS — inbound SMS & call intake
# ============================================================

import threading as _threading

WEBHOOK_SECRET = os.environ.get('WEBHOOK_SECRET', 'WebhookSecret')
BHS_MEMORY_WEBHOOK_URL = os.environ.get('BHS_MEMORY_WEBHOOK_URL', 'https://bhs-memory-server-production-7ff0.up.railway.app/webhook')


def _normalize_phone(phone):
    """Strip everything except digits, keep leading + for E.164."""
    if not phone:
        return None
    digits = re.sub(r'\D', '', str(phone))
    return digits[-10:] if len(digits) >= 10 else digits


def _match_customer_by_phone(cursor, phone):
    """Return customer_id if we have a matching phone on file."""
    if not phone:
        return None
    normalized = _normalize_phone(phone)
    if not normalized:
        return None
    cursor.execute("SELECT id, phone FROM customers WHERE phone IS NOT NULL AND phone != ''")
    for row in cursor.fetchall():
        if _normalize_phone(row['phone']) == normalized:
            return row['id']
    return None


def _extract_sms_fields(message_texts, api_key):
    """Extract estimate-ready job data from SMS conversation using Claude."""
    if not api_key or not message_texts:
        return {}
    conv = '\n'.join(f'- {t}' for t in message_texts if t)
    prompt = f"""You extract job data from customer text messages to pre-fill a handyman estimate form.

Messages:
{conv}

Return ONLY valid JSON, no explanation:
{{
  "contact_name": "their name if mentioned, or null",
  "address": "full service address if mentioned, or null",
  "access_notes": "lock codes, gate codes, key location, pets, access instructions, or null",
  "service_lines": [
    {{"description": "specific task", "quantity": 1, "unit": "each"}}
  ],
  "materials": "material type, brand, specs, color if mentioned, or null",
  "measurements": "room sizes, dimensions, square footage, or null",
  "timeline": "when they want it done, or null",
  "caller_notes": "other job-relevant details, or null"
}}

Rules:
- service_lines: one entry per distinct task. Infer units from context: flooring/decking/painting=sq.ft., fence/baseboard/trim=lin.ft., doors/windows/fixtures/outlets=each, time-based=hr. Use quantity from context or 1 if unknown.
- Return [] for service_lines if no specific work mentioned yet.
- Never invent data not stated. Use null for missing fields."""
    try:
        req_data = json.dumps({
            'model': 'claude-haiku-4-5-20251001',
            'max_tokens': 500,
            'messages': [{'role': 'user', 'content': prompt}]
        }).encode()
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=req_data,
            headers={
                'x-api-key': api_key,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json',
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
        text = result['content'][0]['text'].strip()
        if '```' in text:
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        return {}


@app.route('/api/webhook/sms', methods=['POST'])
def webhook_sms():
    """Receive forwarded SMS — thread by phone number, extract structured fields via AI."""
    token = request.args.get('token') or request.headers.get('X-Webhook-Token', '')
    if token != WEBHOOK_SECRET:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    from_number = str(data.get('from', '')).strip()
    contact_name = str(data.get('contact', '')).strip() or None
    message = str(data.get('message', '')).strip()
    received_at = data.get('sentStamp') or data.get('receivedStamp') or datetime.utcnow().isoformat()

    if not from_number or not message:
        return jsonify({'error': 'Missing from or message'}), 400

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    conn = get_db()
    cursor = conn.cursor()
    customer_id = _match_customer_by_phone(cursor, from_number)
    norm_from = _normalize_phone(from_number)

    # If this is an existing customer with no active lead, append to their profile notes
    if customer_id:
        active_lead = None
        open_rows = conn.execute(
            "SELECT * FROM leads WHERE source = 'sms' AND status NOT IN ('dismissed', 'converted') ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        for row in open_rows:
            rd = row_to_dict(row)
            if _normalize_phone(rd.get('from_number', '')) == norm_from:
                active_lead = rd
                break

        if not active_lead:
            # Existing customer, no open lead — append to customer notes
            fields = _extract_sms_fields([message], api_key)
            try:
                dt = datetime.fromisoformat(received_at.replace('Z', ''))
            except Exception:
                dt = datetime.utcnow()
            date_str = dt.strftime('%b %d')
            note_parts = [f'[{date_str} Text] {message}']
            extras = []
            if fields.get('service_lines'):
                svc = ', '.join(sl.get('description','') for sl in fields['service_lines'] if sl.get('description'))
                if svc: extras.append(f"Service: {svc}")
            if fields.get('address'):
                extras.append(f"Address: {fields['address']}")
            if fields.get('access_notes'):
                extras.append(f"Access: {fields['access_notes']}")
            if fields.get('measurements'):
                extras.append(f"Measurements: {fields['measurements']}")
            if fields.get('materials'):
                extras.append(f"Materials: {fields['materials']}")
            if fields.get('timeline'):
                extras.append(f"Timeline: {fields['timeline']}")
            if fields.get('caller_notes'):
                extras.append(fields['caller_notes'])
            if extras:
                note_parts.append(' | '.join(extras))
            new_note_line = '\n'.join(note_parts)

            cust = row_to_dict(cursor.execute('SELECT notes FROM customers WHERE id = ?', (customer_id,)).fetchone())
            existing_notes = (cust.get('notes') or '').strip()
            updated_notes = (existing_notes + '\n\n' + new_note_line).strip() if existing_notes else new_note_line
            cursor.execute('UPDATE customers SET notes = ? WHERE id = ?', (updated_notes, customer_id))
            conn.commit()
            conn.close()
            return jsonify({'routed': 'customer_notes', 'customer_id': customer_id}), 200

    # Find existing active lead from same number (unknown caller or lead still open)
    existing = None
    cursor.execute(
        "SELECT * FROM leads WHERE source = 'sms' AND status NOT IN ('dismissed', 'converted') ORDER BY created_at DESC LIMIT 20"
    )
    for row in cursor.fetchall():
        rd = row_to_dict(row)
        if _normalize_phone(rd.get('from_number', '')) == norm_from:
            existing = rd
            break

    if existing:
        meta = {}
        try:
            meta = json.loads(existing.get('metadata') or '{}')
        except Exception:
            pass

        messages = meta.get('messages', [])
        if not messages and existing.get('message'):
            messages = [{'text': existing['message'], 'received_at': existing.get('received_at', '')}]
        messages.append({'text': message, 'received_at': received_at})

        fields = _extract_sms_fields([m['text'] for m in messages], api_key)

        def _keep(new, old):
            return new if new else old

        meta.update({
            'messages': messages,
            'message_count': len(messages),
            'address': _keep(fields.get('address'), meta.get('address')),
            'access_notes': _keep(fields.get('access_notes'), meta.get('access_notes')),
            'service_lines': fields.get('service_lines') or meta.get('service_lines', []),
            'materials': _keep(fields.get('materials'), meta.get('materials')),
            'measurements': _keep(fields.get('measurements'), meta.get('measurements')),
            'timeline': _keep(fields.get('timeline'), meta.get('timeline')),
            'caller_notes': _keep(fields.get('caller_notes'), meta.get('caller_notes')),
        })
        resolved_name = existing.get('contact_name') or fields.get('contact_name') or contact_name

        cursor.execute(
            "UPDATE leads SET metadata = ?, message = ?, contact_name = ?, received_at = ?, status = 'new' WHERE id = ?",
            (json.dumps(meta), message, resolved_name, received_at, existing['id'])
        )
        conn.commit()
        lead = row_to_dict(cursor.execute('SELECT * FROM leads WHERE id = ?', (existing['id'],)).fetchone())
        conn.close()
        return jsonify(lead), 200
    else:
        fields = _extract_sms_fields([message], api_key)
        resolved_name = contact_name or fields.get('contact_name')
        meta = {
            'messages': [{'text': message, 'received_at': received_at}],
            'message_count': 1,
            'address': fields.get('address'),
            'access_notes': fields.get('access_notes'),
            'service_lines': fields.get('service_lines', []),
            'materials': fields.get('materials'),
            'measurements': fields.get('measurements'),
            'timeline': fields.get('timeline'),
            'caller_notes': fields.get('caller_notes'),
        }
        cursor.execute('''
            INSERT INTO leads (source, from_number, contact_name, message, received_at, status, customer_id, metadata)
            VALUES ('sms', ?, ?, ?, ?, 'new', ?, ?)
        ''', (from_number, resolved_name, message, received_at, customer_id, json.dumps(meta)))
        lead_id = cursor.lastrowid
        conn.commit()
        lead = row_to_dict(cursor.execute('SELECT * FROM leads WHERE id = ?', (lead_id,)).fetchone())
        conn.close()
        return jsonify(lead), 201


@app.route('/api/webhook/call', methods=['POST'])
def webhook_call():
    """Receive call summaries from Retell AI — save to leads and forward to bhs-memory-server."""
    token = request.args.get('token') or request.headers.get('X-Webhook-Token', '')
    if token != WEBHOOK_SECRET:
        return jsonify({'error': 'Unauthorized'}), 401

    # Capture raw bytes before parsing — required to forward intact for signature verification
    raw_body = request.get_data()
    retell_sig = request.headers.get('x-retell-signature', '')

    data = json.loads(raw_body) if raw_body else {}

    # Retell structure: { event, call: { from_number, call_analysis: { custom_analysis_data, call_summary } } }
    call = data.get('call', data)
    analysis = call.get('call_analysis', {})
    custom = analysis.get('custom_analysis_data', {})

    from_number = (call.get('from_number') or data.get('from_number') or '').strip()

    # Skip spam calls
    is_spam = str(custom.get('is_spam', 'false')).lower() in ('true', '1')
    if is_spam:
        _threading.Thread(target=_forward_raw(raw_body, retell_sig), daemon=True).start()
        return jsonify({'skipped': 'spam'}), 200

    # Skip calls under 20 seconds (inactivity hang-ups, wrong numbers, accidentals)
    start_ts = call.get('start_timestamp') or 0
    end_ts = call.get('end_timestamp') or 0
    duration_s = (end_ts - start_ts) / 1000 if start_ts and end_ts else 999
    if duration_s < 20:
        _threading.Thread(target=_forward_raw(raw_body, retell_sig), daemon=True).start()
        return jsonify({'skipped': 'too_short'}), 200

    # Skip personal/excluded numbers
    norm_from = _normalize_phone(from_number)
    conn_check = get_db()
    excluded = rows_to_list(conn_check.execute('SELECT phone FROM excluded_numbers').fetchall())
    conn_check.close()
    if any(_normalize_phone(e['phone']) == norm_from for e in excluded):
        return jsonify({'skipped': 'excluded'}), 200

    contact_name = (
        custom.get('caller_name') or data.get('caller_name') or ''
    ).strip() or None

    # Actual field names from William agent: service_needed, job_location, caller_notes
    service = (custom.get('service_needed') or custom.get('service_requested') or '').strip()
    location = (custom.get('job_location') or custom.get('location') or '').strip()
    call_summary = (analysis.get('call_summary') or '').strip()
    caller_notes = (custom.get('caller_notes') or '').strip()

    parts = []
    if service:       parts.append(f"Service: {service}")
    if location:      parts.append(f"Location: {location}")
    if call_summary:  parts.append(f"Summary: {call_summary}")
    if caller_notes:  parts.append(f"Notes: {caller_notes}")
    message = '\n'.join(parts) or 'No details captured'

    received_at = (
        datetime.utcfromtimestamp(call['end_timestamp'] / 1000).isoformat()
        if call.get('end_timestamp') else datetime.utcnow().isoformat()
    )

    meta = json.dumps({
        'service_requested': service,
        'location': location,
        'call_summary': call_summary,
        'caller_notes': caller_notes,
    })

    conn = get_db()
    cursor = conn.cursor()
    customer_id = _match_customer_by_phone(cursor, from_number)

    cursor.execute('''
        INSERT INTO leads (source, from_number, contact_name, message, received_at, status, customer_id, metadata)
        VALUES ('call', ?, ?, ?, ?, 'new', ?, ?)
    ''', (from_number, contact_name, message, received_at, customer_id, meta))
    lead_id = cursor.lastrowid
    conn.commit()
    lead = row_to_dict(cursor.execute('SELECT * FROM leads WHERE id = ?', (lead_id,)).fetchone())
    conn.close()

    def _fwd():
        _forward_raw(raw_body, retell_sig)()
    _threading.Thread(target=_fwd, daemon=True).start()

    return jsonify(lead), 201


def _forward_raw(raw_body, retell_sig):
    def _do():
        try:
            fwd = urllib.request.Request(
                BHS_MEMORY_WEBHOOK_URL,
                data=raw_body,
                headers={'Content-Type': 'application/json', 'x-retell-signature': retell_sig},
                method='POST'
            )
            urllib.request.urlopen(fwd, timeout=8)
        except Exception:
            pass
    return _do


# ── Excluded numbers (personal contacts) ──────────────────────────────────────

@app.route('/api/excluded-numbers', methods=['GET'])
def get_excluded_numbers():
    conn = get_db()
    rows = rows_to_list(conn.execute('SELECT * FROM excluded_numbers ORDER BY label').fetchall())
    conn.close()
    return jsonify(rows)

@app.route('/api/excluded-numbers', methods=['POST'])
def add_excluded_number():
    data = request.get_json() or {}
    phone = _normalize_phone(data.get('phone', ''))
    label = (data.get('label') or '').strip() or None
    if not phone:
        return jsonify({'error': 'phone required'}), 400
    conn = get_db()
    try:
        conn.execute('INSERT INTO excluded_numbers (phone, label) VALUES (?, ?)', (phone, label))
        conn.commit()
    except Exception:
        conn.close()
        return jsonify({'error': 'already exists'}), 409
    row = row_to_dict(conn.execute('SELECT * FROM excluded_numbers WHERE phone = ?', (phone,)).fetchone())
    conn.close()
    return jsonify(row), 201

@app.route('/api/excluded-numbers/<int:nid>', methods=['DELETE'])
def delete_excluded_number(nid):
    conn = get_db()
    conn.execute('DELETE FROM excluded_numbers WHERE id = ?', (nid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/leads', methods=['GET'])
def get_leads():
    status = request.args.get('status')
    conn = get_db()
    cursor = conn.cursor()
    if status:
        cursor.execute('''
            SELECT l.*, c.name as customer_name
            FROM leads l
            LEFT JOIN customers c ON l.customer_id = c.id
            WHERE l.status = ?
            ORDER BY l.received_at DESC, l.created_at DESC
        ''', (status,))
    else:
        cursor.execute('''
            SELECT l.*, c.name as customer_name
            FROM leads l
            LEFT JOIN customers c ON l.customer_id = c.id
            ORDER BY l.received_at DESC, l.created_at DESC
        ''')
    leads = rows_to_list(cursor.fetchall())
    conn.close()
    return jsonify(leads)


@app.route('/api/leads/<int:lead_id>', methods=['PUT'])
def update_lead(lead_id):
    data = request.get_json() or {}
    allowed = {'status', 'notes', 'customer_id', 'job_id', 'contact_name'}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'error': 'Nothing to update'}), 400
    conn = get_db()
    set_clause = ', '.join(f'{k} = ?' for k in updates)
    conn.execute(f'UPDATE leads SET {set_clause} WHERE id = ?', list(updates.values()) + [lead_id])
    conn.commit()
    lead = row_to_dict(conn.execute(
        'SELECT l.*, c.name as customer_name FROM leads l LEFT JOIN customers c ON l.customer_id = c.id WHERE l.id = ?',
        (lead_id,)).fetchone())
    conn.close()
    return jsonify(lead)


@app.route('/api/leads/<int:lead_id>/dismiss', methods=['POST'])
def dismiss_lead(lead_id):
    conn = get_db()
    conn.execute("UPDATE leads SET status = 'dismissed' WHERE id = ?", (lead_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/leads/<int:lead_id>/convert', methods=['POST'])
def convert_lead(lead_id):
    """Convert a lead into a customer note or new customer record."""
    data = request.get_json() or {}
    conn = get_db()
    cursor = conn.cursor()

    lead = row_to_dict(cursor.execute('SELECT * FROM leads WHERE id = ?', (lead_id,)).fetchone())
    if not lead:
        conn.close()
        return jsonify({'error': 'Lead not found'}), 404

    customer_id = data.get('customer_id') or lead.get('customer_id')

    # Create new customer if not linked
    if not customer_id:
        name = data.get('name') or lead.get('contact_name') or lead.get('from_number') or 'Unknown'
        cursor.execute(
            'INSERT INTO customers (name, phone, notes) VALUES (?, ?, ?)',
            (name, lead.get('from_number'), f'Created from SMS lead: {lead.get("message", "")[:200]}')
        )
        customer_id = cursor.lastrowid

    conn.execute(
        "UPDATE leads SET status = 'converted', customer_id = ? WHERE id = ?",
        (customer_id, lead_id)
    )
    conn.commit()
    customer = row_to_dict(cursor.execute('SELECT * FROM customers WHERE id = ?', (customer_id,)).fetchone())
    conn.close()
    return jsonify({'success': True, 'customer': customer, 'customer_id': customer_id})


@app.route('/api/leads/<int:lead_id>', methods=['DELETE'])
def delete_lead(lead_id):
    conn = get_db()
    conn.execute('DELETE FROM leads WHERE id = ?', (lead_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


# ============================================================
# JAZZY PAY — Jazzlyn's work invoice system
# ============================================================

@app.route('/api/jazzy/service-items', methods=['GET'])
def list_jazzy_service_items():
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM jazzy_service_items WHERE is_active = 1 ORDER BY category, sort_order, name'
    ).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@app.route('/api/jazzy/service-items', methods=['POST'])
def create_jazzy_service_item():
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    rate = data.get('default_rate')
    if not name or rate is None:
        return jsonify({'error': 'name and default_rate required'}), 400
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO jazzy_service_items (name, default_rate, category, sort_order) VALUES (?, ?, ?, ?)',
        (name, float(rate), data.get('category', 'General'), int(data.get('sort_order', 0)))
    )
    item_id = cursor.lastrowid
    conn.commit()
    row = conn.execute('SELECT * FROM jazzy_service_items WHERE id = ?', (item_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row)), 201


@app.route('/api/jazzy/service-items/<int:item_id>', methods=['PUT'])
def update_jazzy_service_item(item_id):
    data = request.get_json() or {}
    conn = get_db()
    cursor = conn.cursor()
    item = row_to_dict(cursor.execute('SELECT * FROM jazzy_service_items WHERE id = ?', (item_id,)).fetchone())
    if not item:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    fields, params = [], []
    for col in ('name', 'category', 'sort_order', 'is_active'):
        if col in data:
            fields.append(f'{col} = ?')
            params.append(data[col])
    if 'default_rate' in data:
        fields.append('default_rate = ?')
        params.append(float(data['default_rate']))
    if fields:
        params.append(item_id)
        conn.execute(f'UPDATE jazzy_service_items SET {", ".join(fields)} WHERE id = ?', params)
        conn.commit()
    row = conn.execute('SELECT * FROM jazzy_service_items WHERE id = ?', (item_id,)).fetchone()
    conn.close()
    return jsonify(row_to_dict(row))


@app.route('/api/jazzy/service-items/<int:item_id>', methods=['DELETE'])
def delete_jazzy_service_item(item_id):
    conn = get_db()
    conn.execute('UPDATE jazzy_service_items SET is_active = 0 WHERE id = ?', (item_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


def _next_jazzy_invoice_number(cursor):
    prefix = datetime.now().strftime('JBHS-%Y%m-')
    existing = cursor.execute(
        "SELECT invoice_number FROM jazzy_invoices WHERE invoice_number LIKE ? ORDER BY invoice_number DESC LIMIT 1",
        (prefix + '%',)
    ).fetchone()
    if existing:
        try:
            last_num = int(existing['invoice_number'].split('-')[-1])
        except (ValueError, IndexError):
            last_num = 0
        return f'{prefix}{last_num + 1:02d}'
    return f'{prefix}01'


def _insert_lines(cursor, invoice_id, lines):
    total = 0.0
    for i, line in enumerate(lines):
        qty = max(1, int(line.get('qty') or 1))
        rate = float(line.get('rate') or 0)
        line_total = qty * rate
        total += line_total
        cursor.execute(
            '''INSERT INTO jazzy_invoice_lines
               (invoice_id, service_item_id, description, qty, rate, line_total,
                assignment_type, job_ref, notes, is_complete, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (
                invoice_id,
                int(line['service_item_id']) if line.get('service_item_id') else None,
                (line.get('description') or '').strip(),
                qty, rate, line_total,
                line.get('assignment_type', 'business'),
                (line.get('job_ref') or '').strip(),
                (line.get('notes') or '').strip(),
                1 if line.get('is_complete', True) else 0,
                i,
            )
        )
    return total


@app.route('/api/jazzy/invoices', methods=['GET'])
def list_jazzy_invoices():
    conn = get_db()
    rows = conn.execute('SELECT * FROM jazzy_invoices ORDER BY created_at DESC').fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@app.route('/api/jazzy/invoices', methods=['POST'])
def create_jazzy_invoice():
    data = request.get_json() or {}
    lines = data.get('lines', [])
    status = data.get('status', 'draft')
    if status not in ('draft', 'submitted'):
        status = 'draft'

    conn = get_db()
    cursor = conn.cursor()
    invoice_number = _next_jazzy_invoice_number(cursor)

    submitted_at = datetime.now().isoformat() if status == 'submitted' else None
    cursor.execute(
        'INSERT INTO jazzy_invoices (invoice_number, status, total_amount, notes, submitted_at) VALUES (?, ?, 0, ?, ?)',
        (invoice_number, status, (data.get('notes') or '').strip(), submitted_at)
    )
    invoice_id = cursor.lastrowid
    total = _insert_lines(cursor, invoice_id, lines)
    cursor.execute('UPDATE jazzy_invoices SET total_amount = ? WHERE id = ?', (total, invoice_id))

    conn.commit()
    invoice = row_to_dict(cursor.execute('SELECT * FROM jazzy_invoices WHERE id = ?', (invoice_id,)).fetchone())
    conn.close()
    return jsonify(invoice), 201


@app.route('/api/jazzy/invoices/<int:invoice_id>', methods=['GET'])
def get_jazzy_invoice(invoice_id):
    conn = get_db()
    invoice = row_to_dict(conn.execute('SELECT * FROM jazzy_invoices WHERE id = ?', (invoice_id,)).fetchone())
    if not invoice:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    invoice['lines'] = rows_to_list(conn.execute(
        'SELECT * FROM jazzy_invoice_lines WHERE invoice_id = ? ORDER BY sort_order, id',
        (invoice_id,)
    ).fetchall())
    conn.close()
    return jsonify(invoice)


@app.route('/api/jazzy/invoices/<int:invoice_id>', methods=['PUT'])
def update_jazzy_invoice(invoice_id):
    data = request.get_json() or {}
    conn = get_db()
    cursor = conn.cursor()
    invoice = row_to_dict(cursor.execute('SELECT * FROM jazzy_invoices WHERE id = ?', (invoice_id,)).fetchone())
    if not invoice:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    if invoice['status'] == 'paid':
        conn.close()
        return jsonify({'error': 'Cannot edit a paid invoice'}), 400

    lines = data.get('lines')
    notes = data.get('notes', invoice.get('notes', ''))

    if lines is not None:
        cursor.execute('DELETE FROM jazzy_invoice_lines WHERE invoice_id = ?', (invoice_id,))
        total = _insert_lines(cursor, invoice_id, lines)
        cursor.execute('UPDATE jazzy_invoices SET total_amount = ?, notes = ? WHERE id = ?', (total, notes, invoice_id))
    else:
        cursor.execute('UPDATE jazzy_invoices SET notes = ? WHERE id = ?', (notes, invoice_id))

    conn.commit()
    invoice = row_to_dict(cursor.execute('SELECT * FROM jazzy_invoices WHERE id = ?', (invoice_id,)).fetchone())
    invoice['lines'] = rows_to_list(cursor.execute(
        'SELECT * FROM jazzy_invoice_lines WHERE invoice_id = ? ORDER BY sort_order, id',
        (invoice_id,)
    ).fetchall())
    conn.close()
    return jsonify(invoice)


@app.route('/api/jazzy/invoices/<int:invoice_id>', methods=['DELETE'])
def delete_jazzy_invoice(invoice_id):
    conn = get_db()
    invoice = row_to_dict(conn.execute('SELECT * FROM jazzy_invoices WHERE id = ?', (invoice_id,)).fetchone())
    if not invoice:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    if invoice['status'] == 'paid':
        conn.close()
        return jsonify({'error': 'Cannot delete a paid invoice'}), 400
    conn.execute('DELETE FROM jazzy_invoice_lines WHERE invoice_id = ?', (invoice_id,))
    conn.execute('DELETE FROM jazzy_invoices WHERE id = ?', (invoice_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/jazzy/invoices/<int:invoice_id>/submit', methods=['POST'])
def submit_jazzy_invoice(invoice_id):
    conn = get_db()
    invoice = row_to_dict(conn.execute('SELECT * FROM jazzy_invoices WHERE id = ?', (invoice_id,)).fetchone())
    if not invoice:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    if invoice['status'] != 'draft':
        conn.close()
        return jsonify({'error': 'Only draft invoices can be submitted'}), 400
    conn.execute(
        "UPDATE jazzy_invoices SET status = 'submitted', submitted_at = ? WHERE id = ?",
        (datetime.now().isoformat(), invoice_id)
    )
    conn.commit()
    invoice = row_to_dict(conn.execute('SELECT * FROM jazzy_invoices WHERE id = ?', (invoice_id,)).fetchone())
    conn.close()
    return jsonify(invoice)


@app.route('/api/jazzy/invoices/<int:invoice_id>/mark-paid', methods=['POST'])
def mark_jazzy_invoice_paid(invoice_id):
    data = request.get_json() or {}
    conn = get_db()
    invoice = row_to_dict(conn.execute('SELECT * FROM jazzy_invoices WHERE id = ?', (invoice_id,)).fetchone())
    if not invoice:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    if invoice['status'] == 'paid':
        conn.close()
        return jsonify({'error': 'Already marked paid'}), 400
    conn.execute(
        "UPDATE jazzy_invoices SET status = 'paid', paid_at = ?, paid_notes = ? WHERE id = ?",
        (datetime.now().isoformat(), (data.get('paid_notes') or '').strip(), invoice_id)
    )
    conn.commit()
    invoice = row_to_dict(conn.execute('SELECT * FROM jazzy_invoices WHERE id = ?', (invoice_id,)).fetchone())
    conn.close()
    return jsonify(invoice)
=======
# SMS LEAD EXTRACTOR
# Receives forwarded texts from the SMS Forwarder Android app,
# extracts lead info via Claude, and pushes to ntfy.
# Routes: POST /sms   POST /sms/extract/<phone>   GET /sms/lockbox/<phone>
# ============================================================

_SMS_SECRET   = os.environ.get('WEBHOOK_SECRET', '')
_NTFY_URL     = os.environ.get('NTFY_URL', 'https://ntfy.sh')
_NTFY_TOPIC   = os.environ.get('NTFY_TOPIC', '')
_NTFY_TOKEN   = os.environ.get('NTFY_TOKEN', '')
_THREAD_TTL   = int(os.environ.get('THREAD_TTL_HOURS', '4'))

_SMS_SYSTEM_PROMPT = """You are a lead extraction assistant for Beard's Home Services (BHS), a solo handyman and general contracting business owned by Brian Beard in Mountain Home, Arkansas (Baxter County area). Brian does residential and light commercial work — carpentry, decks, fencing, roofing, concrete, remodeling, painting, and general repairs.

Your job is to analyze an SMS conversation thread and extract structured lead information.

LEAD TYPES:
- new_customer_inquiry: First contact, no prior relationship
- realtor_referral: Contact from or on behalf of a real estate agent
- pre_sale_prep: Property being listed, wants work done before sale
- existing_customer: Returning client who mentions prior work with Brian
- vendor_or_other: Not a customer lead — vendor, wrong number, spam, personal text, solicitation

INSTRUCTIONS:
1. Return ONLY valid JSON — no prose, no markdown, no code fences, no preamble
2. Extract only what is clearly stated in the conversation — do not guess or infer
3. Use null for any field not explicitly mentioned
4. If the conversation is not a customer lead, return exactly: {"lead_type": "vendor_or_other"}

For customer leads, return this exact schema:
{
  "lead_type": "<type>",
  "customer_name": "<name or null>",
  "customer_phone": "<phone or null>",
  "property_address": "<full address or null>",
  "is_rental_or_sale": "<rental|sale|owner-occupied|null>",
  "scope_of_work": "<clear description of work needed or null>",
  "availability": "<when they can be reached or when they want work done or null>",
  "realtor_name": "<name or null>",
  "realtor_phone": "<phone or null>",
  "realtor_email": "<email or null>",
  "lockbox_code": "<code or null>",
  "urgency": "<low|moderate|high|urgent>",
  "additional_notes": "<any other relevant info or null>",
  "confidence": "<low|medium|high>"
}

URGENCY GUIDE:
- urgent: emergency, active damage, same-day need, "ASAP", "right now", flooding, etc.
- high: this week, "need it done soon", time-sensitive, before an event or deadline
- moderate: has a general timeline but flexible, "before winter", "next month", "before listing"
- low: no timeline stated, "whenever you have time", exploratory inquiry

CONFIDENCE GUIDE:
- high: clear name, address, and scope of work all present
- medium: some key fields missing but enough context to follow up
- low: very vague inquiry, minimal information to work with

Always include realtor fields when lead_type is realtor_referral or pre_sale_prep.
Always include lockbox_code if a code is mentioned — even if it appears as a short number in context.
"""

_SMS_MEANINGFUL_FIELDS = {
    'customer_name', 'property_address', 'scope_of_work',
    'availability', 'lockbox_code', 'urgency', 'realtor_name', 'realtor_phone',
}

_BHS_ESTIMATE_RE = re.compile(r'\bBHS\d{8}\b')


def _sms_hash(phone):
    return hashlib.sha256(phone.encode()).hexdigest()[:12]


def _sms_now():
    return datetime.now(timezone.utc).isoformat()


def _sms_get_thread(phone):
    conn = get_db()
    row = conn.execute('SELECT * FROM sms_leads WHERE phone = ?', (phone,)).fetchone()
    conn.close()
    return dict(row) if row else None


def _sms_upsert_message(phone, message, sent_ts, contact=None):
    now = _sms_now()
    new_msg = {'role': 'customer', 'text': message, 'ts': sent_ts or 0}
    if contact:
        new_msg['contact'] = contact
    conn = get_db()
    row = conn.execute('SELECT thread_json FROM sms_leads WHERE phone = ?', (phone,)).fetchone()
    if row:
        thread = json.loads(row['thread_json'] or '[]')
        thread.append(new_msg)
        conn.execute(
            "UPDATE sms_leads SET thread_json = ?, last_message = ?, status = 'active' WHERE phone = ?",
            (json.dumps(thread), now, phone)
        )
    else:
        thread = [new_msg]
        conn.execute(
            "INSERT INTO sms_leads (phone, first_contact, last_message, thread_json, status) VALUES (?, ?, ?, ?, 'active')",
            (phone, now, now, json.dumps(thread))
        )
    conn.commit()
    conn.close()


def _sms_save_extraction(phone, extraction, lockbox_code):
    conn = get_db()
    if lockbox_code:
        conn.execute(
            'UPDATE sms_leads SET last_extraction_json = ?, lockbox_code = ? WHERE phone = ?',
            (json.dumps(extraction), lockbox_code, phone)
        )
    else:
        conn.execute(
            'UPDATE sms_leads SET last_extraction_json = ? WHERE phone = ?',
            (json.dumps(extraction), phone)
        )
    conn.commit()
    conn.close()


def _sms_increment_ntfy(phone):
    conn = get_db()
    conn.execute('UPDATE sms_leads SET ntfy_sent_count = ntfy_sent_count + 1 WHERE phone = ?', (phone,))
    conn.commit()
    conn.close()


def _sms_mark_complete(phone):
    conn = get_db()
    conn.execute("UPDATE sms_leads SET status = 'complete' WHERE phone = ?", (phone,))
    conn.commit()
    conn.close()


def _sms_extract_lead(thread):
    """Call Claude synchronously to extract lead info from a thread list."""
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not set')
    import anthropic as _ant
    client = _ant.Anthropic(api_key=api_key)
    lines = []
    for msg in thread:
        contact = f" ({msg['contact']})" if msg.get('contact') else ''
        lines.append(f"[SMS from {msg['role']}{contact}]: {msg['text']}")
    thread_text = '\n'.join(lines)
    resp = client.messages.create(
        model='claude-sonnet-4-5',
        max_tokens=1000,
        temperature=0,
        system=_SMS_SYSTEM_PROMPT,
        messages=[{'role': 'user', 'content': f'Extract lead information from this SMS conversation:\n\n{thread_text}'}],
    )
    return json.loads(resp.content[0].text.strip())


def _sms_has_new_info(previous, current):
    if previous is None:
        return any(current.get(f) is not None for f in _SMS_MEANINGFUL_FIELDS)
    for field in _SMS_MEANINGFUL_FIELDS:
        prev_val = previous.get(field)
        curr_val = current.get(field)
        if prev_val is None and curr_val is not None:
            return True
        if prev_val and curr_val and str(prev_val).strip() != str(curr_val).strip():
            return True
    return False


def _sms_send_ntfy(extraction, is_final=False):
    """Send an ntfy push notification for a lead extraction result."""
    if not _NTFY_TOPIC:
        return
    lead_type = extraction.get('lead_type', 'new_customer_inquiry')
    labels = {
        'new_customer_inquiry': 'New Inquiry',
        'realtor_referral': 'Realtor Referral',
        'pre_sale_prep': 'Pre-Sale Prep',
        'existing_customer': 'Existing Customer',
    }
    label = labels.get(lead_type, lead_type.replace('_', ' ').title())
    customer_name = extraction.get('customer_name') or 'Unknown'
    prefix = 'Final Lead' if is_final else 'New Lead'
    title = f'{prefix} — {label} — {customer_name}'

    urgency_map = {'urgent': 'max', 'high': 'high', 'moderate': 'default', 'low': 'low'}
    priority = urgency_map.get((extraction.get('urgency') or 'moderate').lower(), 'default')

    lines = []
    if extraction.get('customer_phone'):
        lines.append(f"Phone: {extraction['customer_phone']}")
    if extraction.get('property_address'):
        lines.append(f"Property: {extraction['property_address']}")
    if extraction.get('is_rental_or_sale'):
        lines.append(f"Type: {extraction['is_rental_or_sale'].title()}")
    if extraction.get('scope_of_work'):
        lines.append(f"Scope: {extraction['scope_of_work']}")
    if extraction.get('availability'):
        lines.append(f"Available: {extraction['availability']}")
    if extraction.get('urgency'):
        lines.append(f"Urgency: {extraction['urgency'].title()}")
    if extraction.get('realtor_name'):
        lines.append(f"Realtor: {extraction['realtor_name']}")
    if extraction.get('additional_notes'):
        lines.append(f"Notes: {extraction['additional_notes']}")
    if extraction.get('lockbox_code'):
        lines.append('Lockbox: [PRESENT - check app]')
    if extraction.get('confidence'):
        lines.append(f"Confidence: {extraction['confidence'].title()}")

    headers = {
        'Title': title,
        'Priority': priority,
        'Tags': f"sms,lead,{lead_type}",
        'Content-Type': 'text/plain',
    }
    if _NTFY_TOKEN:
        headers['Authorization'] = f'Bearer {_NTFY_TOKEN}'

    import httpx as _httpx
    _httpx.post(
        f'{_NTFY_URL.rstrip("/")}/{_NTFY_TOPIC}',
        content='\n'.join(lines).encode('utf-8'),
        headers=headers,
        timeout=10.0,
    ).raise_for_status()


def _sms_check_ttl():
    """Fire final notifications for threads that have been silent past TTL."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=_THREAD_TTL)).isoformat()
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM sms_leads WHERE status = 'active' AND last_message < ?", (cutoff,)
    ).fetchall()
    conn.close()
    for row in rows:
        phone = row['phone']
        try:
            thread = json.loads(row['thread_json'] or '[]')
            extraction = _sms_extract_lead(thread)
            if extraction.get('lead_type') != 'vendor_or_other':
                lockbox = extraction.pop('lockbox_code', None)
                _sms_save_extraction(phone, extraction, lockbox)
                _sms_send_ntfy({**extraction, 'lockbox_code': lockbox}, is_final=True)
                _sms_increment_ntfy(phone)
            _sms_mark_complete(phone)
        except Exception as e:
            app.logger.error(f'[sms-ttl] error for {_sms_hash(phone)}: {e}')


def _sms_check_token(token):
    if _SMS_SECRET and token != _SMS_SECRET:
        from flask import abort
        abort(401)


@app.route('/sms', methods=['POST'])
def sms_webhook():
    """Receive forwarded SMS from SMS Forwarder Android app."""
    token = request.args.get('token', '')
    _sms_check_token(token)

    data = request.json or {}
    phone   = data.get('from', '').strip()
    message = data.get('message', '').strip()
    sent_ts = data.get('sentStamp')
    contact = data.get('contact')

    if not phone or not message:
        return jsonify({'ok': False, 'error': 'from and message are required'}), 400

    phone_hash = _sms_hash(phone)
    app.logger.info(f'[sms] received from={phone_hash}')

    _sms_upsert_message(phone, message, sent_ts, contact)

    # Fire TTL completions opportunistically on each incoming message
    try:
        _sms_check_ttl()
    except Exception as e:
        app.logger.error(f'[sms-ttl] {e}')

    # If the message contains a known BHS estimate number, skip extraction —
    # that record was already created by the PDF generator POST.
    for est_num in _BHS_ESTIMATE_RE.findall(message):
        conn = get_db()
        exists = conn.execute('SELECT id FROM jobs WHERE invoice_id = ?', (est_num,)).fetchone()
        conn.close()
        if exists:
            app.logger.info(f'[sms] {phone_hash} references existing estimate {est_num}, skipping')
            return jsonify({'ok': True, 'extracted': False, 'skipped': True, 'reason': 'estimate_exists'})

    thread_record = _sms_get_thread(phone)
    thread = json.loads(thread_record['thread_json'])
    prev_raw = thread_record.get('last_extraction_json')
    prev_extraction = json.loads(prev_raw) if prev_raw else None

    try:
        extraction = _sms_extract_lead(thread)
    except Exception as e:
        app.logger.error(f'[sms-extract] error for {phone_hash}: {e}')
        return jsonify({'ok': True, 'extracted': False})

    if extraction.get('lead_type') == 'vendor_or_other':
        app.logger.info(f'[sms] vendor_or_other suppressed for {phone_hash}')
        return jsonify({'ok': True, 'extracted': False, 'suppressed': True})

    lockbox = extraction.pop('lockbox_code', None)
    _sms_save_extraction(phone, extraction, lockbox)

    if _sms_has_new_info(prev_extraction, extraction):
        try:
            _sms_send_ntfy({**extraction, 'lockbox_code': lockbox})
            _sms_increment_ntfy(phone)
            app.logger.info(f'[sms] ntfy sent for {phone_hash}')
        except Exception as e:
            app.logger.error(f'[sms-ntfy] error for {phone_hash}: {e}')

    return jsonify({'ok': True, 'extracted': True, 'lead_type': extraction.get('lead_type')})


@app.route('/sms/extract/<phone_number>', methods=['POST'])
def sms_manual_extract(phone_number):
    """Force immediate extraction and ntfy notification for a thread."""
    token = request.args.get('token', '')
    _sms_check_token(token)

    thread_record = _sms_get_thread(phone_number)
    if not thread_record:
        return jsonify({'error': 'No thread found for this number'}), 404

    thread = json.loads(thread_record['thread_json'])
    phone_hash = _sms_hash(phone_number)

    try:
        extraction = _sms_extract_lead(thread)
    except Exception as e:
        return jsonify({'error': f'Extraction failed: {e}'}), 500

    if extraction.get('lead_type') == 'vendor_or_other':
        return jsonify({'ok': True, 'suppressed': True})

    lockbox = extraction.pop('lockbox_code', None)
    _sms_save_extraction(phone_number, extraction, lockbox)

    try:
        _sms_send_ntfy({**extraction, 'lockbox_code': lockbox}, is_final=True)
        _sms_increment_ntfy(phone_number)
    except Exception as e:
        app.logger.error(f'[sms-ntfy] manual error for {phone_hash}: {e}')
        return jsonify({'error': f'Extraction succeeded but ntfy failed: {e}'}), 500

    app.logger.info(f'[sms] manual extraction sent for {phone_hash}')
    return jsonify({'ok': True, 'lead_type': extraction.get('lead_type')})


@app.route('/sms/lockbox/<phone_number>')
def sms_lockbox(phone_number):
    """Retrieve a stored lockbox code for a phone number."""
    token = request.args.get('token', '')
    _sms_check_token(token)

    conn = get_db()
    row = conn.execute('SELECT lockbox_code FROM sms_leads WHERE phone = ?', (phone_number,)).fetchone()
    conn.close()
    if not row or not row['lockbox_code']:
        return jsonify({'error': 'No lockbox code on file for this number'}), 404
    return jsonify({'phone': phone_number, 'lockbox_code': row['lockbox_code']})
>>>>>>> f5c2573 (Add SMS lead extractor, estimates pipeline, and Claude AI project knowledge)


# ============================================================
# REACT FRONTEND — serve built files (production / Railway)
# ============================================================

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_react(path):
    if path and os.path.exists(os.path.join(FRONTEND_DIST, path)):
        return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, 'index.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("Starting Beard's Home Services API...")
    print("Database: " + DB_PATH)
    app.run(debug=True, host='0.0.0.0', port=port)
