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
from datetime import datetime
import math
import time as _time

BRIAN_HOME_LAT = 36.3345   # Mountain Home, AR
BRIAN_HOME_LON = -92.3857

app = Flask(__name__)
CORS(app)

# Database path — Railway sets DB_PATH env var pointing to a volume
DB_PATH = os.environ.get(
    'DB_PATH',
    os.path.join(os.path.dirname(__file__), '..', 'data', 'beard_business.db')
)

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

    cursor.execute("SELECT COUNT(*) as count FROM customers WHERE name != '_UNASSIGNED'")
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
        WHERE 1=1 {job_date_filter}
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
    rate_hours = rate_hours_row['total'] or 0
    rate_labor = rate_labor_row['labor'] or 0

    response = {
        'total_labor': total_labor,
        'total_materials': revenue['materials'] or 0,
        'total_revenue': total_labor + (revenue['materials'] or 0),
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
               COALESCE(te.hours, 0) as total_hours
        FROM customers c
        LEFT JOIN (
            SELECT customer_id, COUNT(*) as cnt FROM jobs GROUP BY customer_id
        ) j_count ON c.id = j_count.customer_id
        LEFT JOIN (
            SELECT customer_id, SUM(total_labor) as labor FROM invoices GROUP BY customer_id
        ) inv ON c.id = inv.customer_id
        LEFT JOIN (
            SELECT customer_id, SUM(hours) as hours FROM time_entries GROUP BY customer_id
        ) te ON c.id = te.customer_id
        WHERE c.name != '_UNASSIGNED'
        ORDER BY c.name
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

    cursor.execute('''
        SELECT j.id, j.invoice_id, j.start_date, j.status,
               c.name as customer,
               i.total_labor, i.total_materials,
               (SELECT SUM(hours) FROM time_entries WHERE job_id = j.id) as hours
        FROM jobs j
        JOIN customers c ON j.customer_id = c.id
        LEFT JOIN invoices i ON j.id = i.job_id
        ORDER BY j.start_date DESC
    ''')
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
        SELECT t.id, t.entry_date, t.start_time, t.end_time, t.hours, t.description, t.cost_code,
               c.name as customer, j.invoice_id
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

    query += ' ORDER BY t.entry_date DESC LIMIT 100'

    cursor.execute(query, params)
    entries = rows_to_list(cursor.fetchall())
    conn.close()
    return jsonify(entries)


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
    conn.close()
    return jsonify({'id': entry_id, 'message': 'Time entry added'}), 201


@app.route('/api/time-entries/<int:te_id>', methods=['PUT'])
def reassign_time_entry(te_id):
    """Move a time entry to a different job (or unassign it)."""
    data = request.json
    if not data or 'job_id' not in data:
        return jsonify({'error': 'job_id is required'}), 400

    conn = get_db()
    cursor = conn.cursor()

    te = cursor.execute('SELECT id, customer_id FROM time_entries WHERE id = ?', (te_id,)).fetchone()
    if not te:
        conn.close()
        return jsonify({'error': 'Time entry not found'}), 404

    new_job_id = data['job_id']
    if new_job_id:
        job = cursor.execute('SELECT id, customer_id FROM jobs WHERE id = ?', (new_job_id,)).fetchone()
        if not job:
            conn.close()
            return jsonify({'error': 'Target job not found'}), 404
        cursor.execute(
            'UPDATE time_entries SET job_id = ?, customer_id = ? WHERE id = ?',
            (new_job_id, job['customer_id'], te_id)
        )
    else:
        cursor.execute('UPDATE time_entries SET job_id = NULL WHERE id = ?', (te_id,))

    conn.commit()
    conn.close()
    return jsonify({'id': te_id, 'job_id': new_job_id, 'message': 'Reassigned'})


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
