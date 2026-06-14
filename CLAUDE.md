# Beard's Home Services - Business App

**Owner:** Brian (non-technical). Handyman business in Mountain Home, AR.  
**Last Updated:** 2026-06-14

---

## Project Structure

```
BHSmobileapp/
├── api/
│   ├── app.py                    # Flask API (3,400+ lines, 60 endpoints), port 5000
│   ├── models.py                 # Legacy SQLAlchemy models (NOT used — ignore)
│   ├── seed_data.py              # Historical data loader
│   └── .env                      # Local environment variables
├── data/
│   ├── beard_business.db         # SQLite database (main data store)
│   ├── build_database.py         # Rebuild DB from source JSON files
│   ├── import_invoices.py        # Import old InvoiceBee ZIP invoices
│   ├── import_pdf_invoices.py    # Import new PDF invoices (Oct 2025+)
│   ├── import_busybusy.py        # Import BusyBusy CSV time entries
│   ├── import_timeline.py        # Import Google Maps Timeline visits
│   ├── import_categories.py      # Service category management
│   ├── extract_contacts.py       # Extract phone/address from invoice ZIPs
│   ├── match_invoices_to_time.py # Link time_entries.job_id to jobs
│   ├── fix_data_links.py         # Data quality fixes
│   ├── customer_profitability.py # Revenue analysis
│   ├── process_completed_job.py  # Workflow automation
│   ├── insert_2026_jobs.py       # Bulk job creation
│   ├── time_entries.csv          # BusyBusy export (source file)
│   └── push_to_railway.py        # Railway deployment helper
├── frontend/
│   ├── src/
│   │   ├── App.jsx               # Main app: routing + bottom nav + Clock context
│   │   ├── main.jsx              # Vite entry point
│   │   ├── index.css             # Global styles
│   │   └── pages/
│   │       ├── Dashboard.jsx     # Revenue KPIs, charts, recent jobs, top customers
│   │       ├── Clock.jsx         # GPS-enabled live time clock (start/stop)
│   │       ├── TimeEntry.jsx     # Manual time entry form
│   │       ├── FilingCabinet.jsx # Job dossier: customer card, invoices, services, time, payments
│   │       ├── Customers.jsx     # Customer list, search, add/edit/delete
│   │       ├── Jobs.jsx          # Jobs list with status
│   │       ├── Estimate.jsx      # Create estimates/proposals
│   │       ├── Expenses.jsx      # Materials & overhead tracking
│   │       ├── Trips.jsx         # Mileage log, distance calculation
│   │       ├── DayWrapup.jsx     # End-of-day summary & time aggregation
│   │       ├── Reports.jsx       # Charts: revenue by month/category, margins
│   │       ├── PrintView.jsx     # Printable invoice/estimate
│   │       └── Settings.jsx      # Toggle "More" menu items
│   ├── package.json
│   ├── vite.config.js            # Dev server port 5173, proxies /api → :5000
│   └── index.html
├── Invoices/                     # 68 invoice PDF files
│   ├── invoiceBHS*.pdf           # Old InvoiceBee format (ZIP archives w/ .pdf extension)
│   ├── invoice*.pdf              # New PDF format (Oct 2025+, real PDFs)
│   ├── estimate*.pdf             # Estimates (treated as paid invoices)
│   └── Not-processed-Invoices/   # Drop new PDFs here before running import
├── Receipts/                     # Expense receipts (low priority)
├── .claude/
│   └── agents/                   # Sub-agent markdown specs for invoice workflow
│       ├── database-manager.md
│       ├── invoice-extractor.md
│       ├── service-matcher.md
│       ├── standards-analyzer.md
│       └── workflow-reporter.md
├── CLAUDE.md                     # This file
├── MEMORY.md                     # Current status, known data issues
├── requirements.txt              # Python deps
├── Dockerfile                    # Python 3.13 + Node.js 20
├── railway.json                  # Railway deployment config
├── nixpacks.toml                 # Railway nix build config
├── wsgi.py                       # Gunicorn entry point
├── start_app.bat                 # Windows: launches Flask + Vite
├── start_wrapup.bat              # Windows: launches Day Wrapup page
├── setup_shortcuts.bat           # Windows desktop shortcuts
└── sync_db.bat                   # Database sync helper
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.0+ (Python), port 5000 |
| Database | SQLite 3 — raw `sqlite3` module, **NO SQLAlchemy** |
| Frontend | React 18.3 + Vite 6 + Tailwind CSS v4 + react-router-dom v7 + recharts |
| Frontend dev | Port 5173 (Vite proxies `/api` to Flask :5000) |
| Production server | Gunicorn (2 workers, 120s timeout) |
| Deployment | Railway (Docker + nixpacks) |
| Python version | 3.13 |

---

## How to Run

### Local Development (Windows)

```batch
start_app.bat
```
This opens Flask (:5000) + Vite (:5173) and displays the LAN IP for phone testing.

Manual:
```bash
# Terminal 1 — Flask
cd api && python app.py

# Terminal 2 — React
cd frontend && npm run dev -- --host
```

### Production (Railway)

Push to Railway via Docker. The Dockerfile builds the React frontend into `dist/` then serves it statically from Flask. Health check endpoint: `GET /api/health`.

---

## Database Schema

**DB path:** `data/beard_business.db`  
**Pattern:** Always use `conn.row_factory = sqlite3.Row` and convert with `dict(row)`.

### Tables

#### `customers`
| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| name | TEXT UNIQUE | |
| address | TEXT | |
| phone | TEXT | |
| email | TEXT | |
| notes | TEXT | General notes |
| cya_notes | TEXT | "Cover your ass" notes for tricky customers |
| customer_lat | REAL | Cached geocoords for GPS matching |
| customer_lon | REAL | |
| created_at | TIMESTAMP | |

#### `jobs`
| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| customer_id | FK → customers | |
| invoice_id | TEXT | |
| project_number | TEXT | |
| start_date | DATE | |
| end_date | DATE | |
| status | TEXT | `'completed'`, `'estimate'`, `'in-progress'` |
| estimated_days | INT | |
| notes | TEXT | |
| data_status | TEXT | `'incomplete'` = orphaned time entries |
| photos_album_url | TEXT | Google Photos album link |
| created_at | TIMESTAMP | |

#### `invoices`
| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| invoice_number | TEXT UNIQUE | e.g., `BHS20240110`, `20251010` |
| customer_id | FK → customers | |
| job_id | FK → jobs | |
| total_labor | REAL | |
| total_materials | REAL | |
| total_amount | REAL | |
| invoice_date | DATE | |
| status | TEXT | `'paid'` or `'draft'` |
| pdf_filename | TEXT | |
| created_at | TIMESTAMP | |

#### `services_performed`
| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| invoice_id | FK → invoices | |
| job_id | FK → jobs | |
| original_description | TEXT | Raw text from invoice |
| standardized_description | TEXT | Cleaned/normalized |
| category | TEXT | FK-by-name → service_categories.name |
| amount | REAL | Lump-sum (no quantity column) |
| service_type | TEXT | `'labor'` or `'materials'` |
| created_at | TIMESTAMP | |

#### `time_entries`
| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| customer_id | FK → customers | |
| job_id | FK → jobs | |
| entry_date | DATE | |
| start_time | TIMESTAMP | |
| end_time | TIMESTAMP | |
| hours | REAL | |
| description | TEXT | |
| cost_code | TEXT | |
| source | TEXT | `'busybusy'`, `'clock'`, `'manual'` |
| trip_skip | INT | 1 = user dismissed trip suggestion |
| created_at | TIMESTAMP | |

#### `materials_expenses`
| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| job_id | FK → jobs | |
| customer_id | FK → customers | |
| description | TEXT | |
| cost | REAL | |
| vendor | TEXT | |
| receipt_path | TEXT | |
| expense_date | DATE | |
| source | TEXT | Tracks entry method |
| created_at | TIMESTAMP | |

#### `service_categories`
| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| name | TEXT UNIQUE | e.g., `"Deck Repair & Restoration Labor"` |
| description | TEXT | |
| is_labor | INT | 1 = labor income, 0 = materials passthrough |

**19 labor categories + 1 materials.** Examples: General Handyman Labor, Deck Construction/Repair, Fence, Flooring, Concrete, Painting/Staining, Bathroom/Kitchen Remodel, Door/Window, Tile, Plumbing, Gutter & Roofing, Landscaping, Outdoor Structure, Demolition, Asphalt & Paving, Screen & Enclosure, Appliance Installation, Materials.

#### `timeline_visits` (Google Maps Timeline)
| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| customer_id | FK → customers | |
| job_id | FK → jobs | |
| visit_date | DATE | |
| arrival_time | TIMESTAMP | |
| departure_time | TIMESTAMP | |
| duration_hours | REAL | |
| address | TEXT | |
| source | TEXT | `'google_timeline'` |
| matched | INT | 1 = linked to a job |
| created_at | TIMESTAMP | |

#### `trips` (mileage tracking)
| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| trip_date | DATE | |
| trip_type | TEXT | |
| destination | TEXT | |
| customer_id | FK → customers | |
| job_id | FK → jobs | |
| miles | REAL | |
| drive_time_minutes | INT | |
| notes | TEXT | |
| created_at | TIMESTAMP | |

#### `payments`
| Column | Type | Notes |
|--------|------|-------|
| id | INT PK | |
| job_id | FK → jobs | |
| customer_id | FK → customers | |
| amount | REAL | |
| payment_date | DATE | |
| payment_method | TEXT | `'cash'`, `'check'`, `'ACH'`, etc. |
| memo | TEXT | |

---

## API Endpoints

All endpoints prefixed with `/api/`.

### Dashboard & Analytics
```
GET  /api/dashboard              # Revenue stats, hours, customers, job counts
GET  /api/insights               # Complex analytics
GET  /api/reports/pl             # Profit & loss statement
GET  /api/data-gaps              # Flag missing time entries
GET  /api/health                 # Health check (used by Railway)
```

### Customers
```
GET    /api/customers                            # List all (filterable)
POST   /api/customers                            # Create new customer
GET    /api/customers/<id>                       # Customer detail
PUT    /api/customers/<id>                       # Update customer
DELETE /api/customers/<id>?force=1               # Delete + cascade all jobs/invoices
POST   /api/customers/<id>/calculate-mileage     # Compute drive distance from home
GET    /api/nearest-customer                     # GPS-based nearest customer lookup
```

### Jobs
```
GET    /api/jobs                    # List all jobs
GET    /api/jobs/<id>               # Job details
POST   /api/jobs/full               # Create job + invoice + services
PUT    /api/jobs/<id>               # Update job
DELETE /api/jobs/<id>               # Delete job + invoice, unlinks time entries
POST   /api/jobs/<id>/convert       # Convert estimate → paid invoice
POST   /api/jobs/<id>/trash         # Archive estimate without invoicing
POST   /api/jobs/<id>/mark-incomplete # Flag as incomplete data
POST   /api/jobs/<id>/payments      # Record payment received
GET    /api/estimates               # List all estimates
```

### Filing Cabinet
```
GET    /api/filing-cabinet          # List all jobs with summary
GET    /api/filing-cabinet/<id>     # Full job details (customer, services, time, payments)
POST   /api/filing-cabinet/new      # Create new job with services
PUT    /api/filing-cabinet/<id>     # Update job services & details
```

### Time Entries
```
GET    /api/time-entries                          # List (filterable/sortable)
POST   /api/time-entries                          # Create manual entry
PUT    /api/time-entries/<id>                     # Edit entry
DELETE /api/time-entries/<id>                     # Delete entry
POST   /api/suggested-trips/<te_id>/confirm       # Accept trip suggestion
POST   /api/suggested-trips/<te_id>/skip          # Dismiss trip suggestion
```

### Invoices & Services
```
GET    /api/invoices                    # List all invoices
GET    /api/categories                  # List service categories (same as below)
GET    /api/service-categories          # List service categories
POST   /api/categories                  # Create new category
PUT    /api/categories/<id>             # Update category
DELETE /api/categories/<id>             # Delete category
GET    /api/pricing/suggest             # Claude AI pricing suggestion (single line)
GET    /api/pricing/suggest-all         # Claude AI pricing for all lines
POST   /api/pricing/claude-suggest      # Alternative pricing endpoint
```

### Expenses
```
GET    /api/expenses                    # List all materials & overhead
POST   /api/expenses                    # Add expense
PUT    /api/expenses/<id>               # Update expense
DELETE /api/expenses/<id>               # Delete expense
GET    /api/expenses/categories         # Expense categories
GET    /api/expenses/summary            # Expense totals by period
```

### Trips (Mileage)
```
GET    /api/trips                       # List all trips
POST   /api/trips                       # Record new trip
PUT    /api/trips/<id>                  # Update trip
DELETE /api/trips/<id>                  # Delete trip
GET    /api/trips/summary               # Mileage totals by period
```

### Payments
```
DELETE /api/payments/<id>               # Remove payment record
```

### Admin & Import
```
POST   /api/day-wrapup                  # End-of-day processing (time aggregation)
POST   /api/import-job                  # Bulk job import from JSON
POST   /api/admin/backup-db             # Download SQLite database backup
POST   /api/admin/restore-db            # Upload & restore from backup
POST   /api/invoice/parse-pdf           # Upload PDF → returns parsed JSON
POST   /api/maps-screenshot/parse       # Upload image → returns visit JSON
```

---

## Frontend Pages

Mobile-first responsive design. Bottom navigation on small screens; top nav logic handled in `App.jsx`.

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | Revenue KPIs, charts, recent jobs, top customers |
| Clock | `/clock` | GPS-enabled live time clock (start/stop) |
| Time Entry | `/time` | Manual time entry form |
| Filing Cabinet | `/filing-cabinet` | Full job dossier: customer card, invoice, services, time entries, payments |
| Customers | `/customers` | Customer list, search, add/edit/delete |
| Jobs | `/jobs` | Jobs list with status |
| Estimate | `/estimate` | Create estimate/proposal |
| Expenses | `/expenses` | Materials & overhead tracking |
| Trips | `/trips` | Mileage log, distance calculation |
| Day Wrapup | `/day-wrapup` | End-of-day summary, time aggregation |
| Reports | `/reports` | Charts: revenue by month/category, margins |
| Print View | `/print` | Printable invoice/estimate |
| Settings | `/settings` | Toggle "More" menu items |

**Bottom Nav items (always visible):** Dashboard, Clock, More (configurable via Settings), Settings.

**Frontend state:** Uses React hooks + `localStorage` for app settings and clock state. No Redux/Zustand.

---

## Critical Rules

1. **NEVER use SQLAlchemy** — always raw `sqlite3` module
2. **NEVER Unicode in Python `print()`** on Windows — use ASCII only
3. **ALWAYS use `conn.row_factory = sqlite3.Row` + `dict(row)`** for all DB queries
4. **ALWAYS use subagents for long tasks** to conserve context
5. **NEVER call `pdfplumber` on old InvoiceBee files** — they are ZIP archives despite `.pdf` extension; use `zipfile` module
6. **DB path is always** `data/beard_business.db` (relative to repo root)

---

## Business Logic & Conventions

### Service Classification
- **Labor** = billable income (19 categories, `is_labor=1`)
- **Materials** = customer reimbursement/passthrough — NOT income (`is_labor=0`)
- `services_performed.service_type` = `'labor'` or `'materials'`
- `services_performed.category` = category name string (not FK id)
- Auto-categorization by keyword rules in `import_invoices.py` (`CATEGORY_RULES` dict)

### Job Status Values
- `'completed'` — finished, invoiced
- `'estimate'` — proposal only, not yet accepted
- `'in-progress'` — future use

### Mileage Calculations
- **Brian's home:** 360 County Road 35, Clarkridge, AR 72623
- **Coordinates:** `36.46519470, -92.31659698` (stored as `BRIAN_HOME_LAT/LON` in `app.py`)
- All distance calculations use this as origin

### Trip Suggestions
After a time entry is saved, the UI suggests logging a trip if the customer has an address and hasn't been dismissed before (`trip_skip=0`). User can confirm (creates trip record) or skip (sets `trip_skip=1`).

### Data Quality
- `data_status='incomplete'` on a job = orphaned time entries with no matching invoice
- `cya_notes` column = "cover your ass" notes for tricky customer situations
- All import scripts are idempotent (safe to re-run; duplicates checked)

### Invoice Number Formats
- Old format: `BHS` + 6-digit date → `BHS240110` (legacy edge case)
- Standard old: `BHS` + 8-digit date → `BHS20240110`
- New format (Oct 2025+): plain 8-digit date → `20251010`
- Estimates: `estimate` prefix → also imported as paid invoices (Brian's request)

---

## Data Import Workflows

### Add New Invoices

**Old InvoiceBee format** (files look like `.pdf` but are ZIP archives):
```bash
# Drop files into Invoices/ folder first
cd data
python import_invoices.py          # add --dry-run to preview, --reset to wipe first
python match_invoices_to_time.py --apply
```

**New PDF format** (Oct 2025+, real PDFs, uses pdfplumber):
```bash
# Drop files into Invoices/Not-processed-Invoices/
cd data
python import_pdf_invoices.py      # add --dry-run to preview
python match_invoices_to_time.py --apply
```

### Add BusyBusy Time Entries
```bash
cd data
python import_busybusy.py <path_to_csv>    # deduped by customer+start_time
python match_invoices_to_time.py --apply
```

### Add Google Maps Timeline
```bash
cd data
python import_timeline.py [--start YYYY-MM-DD] [--end YYYY-MM-DD]
```

### Extract Customer Contacts (from invoice ZIPs)
```bash
cd data
python extract_contacts.py
```

### Old InvoiceBee ZIP File Structure
Each file contains:
- `1.txt` — invoice text
- `1.jpeg` — invoice image
- `manifest.json` — metadata
Service line format in text: `Description  Qty  $Price  [$Discount]  *?$Amount`

---

## Current Data State (as of 2026-02-28)

| Metric | Count |
|--------|-------|
| Customers | 59 (deduplicated) |
| Jobs | 68 |
| Invoices | 68 |
| Service line items | 177 |
| Time entries | 380 |
| Timeline visits (Google Maps) | 203 |
| **Total labor income** | **$53,726** |
| **Total materials passthrough** | **$12,867** |
| **Total invoiced** | **$66,267** |

---

## Known Data Issues

- **Dale Kelly** — has time entries (Jan 2024 deck work) but no invoice
- **Manar Jackson** — Jan 2024 time entries (storage, truck wash) don't match the Jul 2025 invoice
- **Tony Beard** — time entry with no matching invoice
- **Janice Butler-Seagress** — was split as IDs 3 and 14; now merged into one record
- **4 customers missing address:** Cassandra Clark, MJ/Tommy Brasher, Christopher Constantine, Tom Mcandless
- **BHS240110** uses 6-digit date (legacy); most others are 8-digit

---

## Project Phases

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 0 | ✅ Done | Invoice extraction (5-agent workflow) |
| Phase 1 | ✅ Done | Database build + import (68 invoices, 59 customers) |
| Phase 2 | ✅ Done | Flask API + React frontend connected |
| Phase 3 | ✅ Done | Estimates, Filing Cabinet, PrintView |
| Phase 4 | ✅ Done | Google Maps Timeline import + GPS time clock + mileage |
| Phase 5 | 🔄 Active | Receipt scanning + P&L reports + advanced insights |
| Phase 6 | 📋 Planned | Local deployment polish, mobile PWA, offline support |

---

## Deployment

### Local (Windows)
- `start_app.bat` — launches Flask + Vite, shows LAN IP for phone
- `sync_db.bat` — database sync helper
- SQLite file at `data/beard_business.db`

### Railway (Cloud)
- Dockerfile: Python 3.13-slim + Node.js 20, builds React into `dist/`
- Gunicorn serves everything (static + API) on `$PORT` (default 8080)
- DB volume mount for persistence at `/app/data/beard_business.db`
- Seed: if volume DB missing, copies bundled DB on startup
- Health check: `GET /api/health`
- Restart on failure (max 10 retries per `railway.json`)

### Database Backup/Restore
```
GET  /api/admin/backup-db    # Download SQLite file
POST /api/admin/restore-db   # Upload & restore from backup
```

---

## Brian's Preferences

- Explain everything in plain business terms, not technical jargon
- FreshBooks-style clean, professional UI
- Mobile-first — Brian uses the app on his phone in the field
- Free tools preferred (Brian has a Claude subscription)
- End-of-day time entry workflow: quick, ~2 minutes per job
- The Day Wrapup page (`/day-wrapup`) is the core daily workflow
