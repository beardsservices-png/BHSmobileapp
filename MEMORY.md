# Beard's Business App - Project Memory

## Current Status: Phase 4 - Historical Data Complete, More Coming

**Last Updated:** 2026-02-25

### ✅ Completed
- Phase 1: React frontend (src/, components, pages)
- Phase 2: Flask API + React connected (port 5000 / 5173)
- Phase 3: Estimates, Filing Cabinet, PrintView
- **Invoice import pipeline**: All 52 invoices imported from ZIP files
- **BusyBusy import**: Time entries deduped and linked to jobs
- **Customer contacts extracted**: phone + address from invoice ZIPs → customers table (via data/extract_contacts.py)
- **Filing Cabinet redesigned**: full job dossier (customer card, invoice details, services w/ category dropdown, rich time entries)

### 📁 Project Structure
```
beard-business-app/
├── api/app.py              Flask API, port 5000
├── data/
│   ├── beard_business.db   SQLite DB (main data store)
│   ├── build_database.py   Old: builds from invoice_workflow JSON (legacy)
│   ├── import_invoices.py  NEW: reads invoiceBHS*.pdf ZIPs -> DB (idempotent)
│   ├── import_busybusy.py  BusyBusy CSV -> time_entries (idempotent, deduped)
│   ├── match_invoices_to_time.py  Links time_entries.job_id to jobs
│   ├── extract_contacts.py        Extracts phone/address from ZIPs -> customers
│   ├── fix_data_links.py
│   ├── customer_profitability.py
│   └── time_entries.csv    BusyBusy export (18 entries currently, more coming)
├── Invoices/               52 ZIP files (InvoiceBee format, .pdf extension) — moved here from root
├── Receipts/               receipts_tagger.ods — low priority, import later
└── frontend/src/           React UI
```

### 💾 Database State (as of 2026-02-28)
- **59 customers** (deduplicated 2026-02-28; 15 phantom merges, Janice Butler merged)
- **68 jobs** (1 per invoice)
- **68 invoices** (BHS240110 through Feb 2026; new-format invoices use plain date numbers)
- **177 service line items** (categorized; NO quantity column — all lump-sum qty=1)
- **380 time entries** (all linked, 0 orphans)
- **203 timeline_visits** (Google Maps Timeline, Mar–Dec 2025)
- **Labor income: $53,726** | **Materials passthrough: $12,867** | **Total invoiced: $66,267**
- 4 customers with invoices but no address: Cassandra Clark, MJ/Tommy Brasher, Christopher Constantine, Tom Mcandless

### 🔑 Key Import Scripts

**To add new invoices:**
- Old InvoiceBee format (invoiceBHS*.pdf ZIPs) → `Invoices/` folder, then `cd data && python import_invoices.py`
- New PDF format (invoice*.pdf or estimate*.pdf) → `Invoices/Not-processed-Invoices/`, then `cd data && python import_pdf_invoices.py`
- Then always: `python match_invoices_to_time.py --apply`

**New invoice format notes (Oct 2025+):**
- Real PDFs (not ZIP), uses pdfplumber
- Invoice number = Project # (plain date like 20251010, no BHS prefix)
- "Estimate" files treated as paid invoices (user's request)
- estimate*.pdf files also processed by import_pdf_invoices.py

**To add new BusyBusy time entries**:
```
cd data
python import_busybusy.py <path_to_csv>   # deduped by customer+start_time
python match_invoices_to_time.py --apply
```

### 🔑 Invoice File Format
- Files look like `.pdf` but are **ZIP archives** (InvoiceBee format)
- Each ZIP contains `1.txt` (invoice text), `1.jpeg`, `manifest.json`
- Use `zipfile` module to read - NOT pdfplumber
- Invoice numbers: `BHS` + date (YYMMDD or YYYYMMDD format)
- Service lines: `Description  Qty  $Price  [$Discount]  *?$Amount`

### 🔑 Service Classification
- **Labor** = actual billable income
- **Materials** = passthrough (customer reimbursement, not income)
- Category mapping: 19 labor categories + Materials in `service_categories` table
- `services_performed.service_type` = 'labor' or 'materials'
- `services_performed.category` = category name from `service_categories`

### ⚠️ Known Issues / Data Notes
- `Dale Kelly` has time entries (Jan 2024 deck work) but no matching invoice
- `Manar Jackson` Jan 2024 entries (storage, truck wash) don't match the Jul 2025 invoice
- `Tony Beard` time entry has no invoice
- `Janice Butler-Seagress` = merged (was split as IDs 3 and 14, now one record)
- `BHS240110` uses 6-digit date format (legacy); most others use 8-digit `BHS20XXXXXX`

### 📝 Tech Rules
- NEVER use SQLAlchemy - raw sqlite3 only
- NEVER Unicode in Python print() on Windows - ASCII only
- `conn.row_factory = sqlite3.Row` + `dict(row)` pattern for all queries
- DB path: `data/beard_business.db`
- Flask port 5000, React/Vite port 5173
- Python 3.13 on Windows

### 📍 Brian's Home Location
- Address: 360 County Road 35, Clarkridge, AR 72623
- GPS: 36.46519470, -92.31659698 (exact, user-provided)
- Used as origin for all mileage calculations (`BRIAN_HOME_LAT/LON` in app.py)

### 🔗 Key Endpoints
GET /api/dashboard, /api/customers, /api/jobs, /api/invoices
GET /api/filing-cabinet, /api/time-entries, /api/service-categories
POST /api/customers, /api/jobs/full, /api/time-entries
DELETE /api/customers/<id>?force=1  -- deletes customer + all jobs/invoices
DELETE /api/jobs/<id>               -- deletes job + invoice, unlinks time entries
POST /api/invoice/parse-pdf         -- upload PDF, returns parsed invoice JSON
POST /api/maps-screenshot/parse     -- upload image, returns parsed visit JSON
