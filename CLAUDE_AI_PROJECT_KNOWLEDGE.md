# Beard's Home Services — Claude.ai Project Knowledge

Owner: Brian Beard, Mountain Home, AR. Solo handyman / general contractor. Residential + light commercial.

---

## What You Help With Here

Brian creates written estimates here, then a Python/ReportLab script turns them into a PDF.
After the PDF is made, that same script POSTs the estimate data to the BHS app so the job is tracked there automatically.

---

## Estimate Number Format

Always: `BHS` + `YYYYMMDD` of today's date.
Example: `BHS20260627`

If Brian does two estimates the same day, append a letter: `BHS20260627A`, `BHS20260627B`.

---

## API POST Format (exact schema)

When the script POSTs to the app, it must use this exact JSON:

```json
{
  "estimate_number": "BHS20260627",
  "customer_name": "John Smith",
  "customer_phone": "870-555-1234",
  "customer_address": "123 Main St, Mountain Home AR",
  "date": "2026-06-27",
  "line_items": [
    { "service": "Deck Repair Labor", "desc": "Replace 12 rotted deck boards and 2 support posts", "price": 550.00 },
    { "service": "Framing Materials", "desc": "Pressure-treated lumber, hardware", "price": 125.00 }
  ],
  "total": 675.00,
  "notes": "Optional scope notes visible in the app"
}
```

**Labor vs Materials rule**: The app classifies a line item as "materials" if the word "Materials" appears in the `service` field. Everything else is classified as labor. Name material line items accordingly: "Deck Materials", "Paint & Supplies", "Framing Materials", etc.

---

## Service Catalog — Labor Categories

Use these exact service names in the `service` field for labor line items. They map directly to the app's internal pricing catalog.

| Service Name | Typical Work Included |
|---|---|
| General Handyman Labor | Repairs, misc fixes, odd jobs |
| Deck Construction Labor | New deck builds from scratch |
| Deck Repair & Restoration Labor | Deck repairs, board replacement, refinishing, staining |
| Fence Construction Labor | New fence installation (wood, chain link, vinyl) |
| Flooring Installation Labor | Hardwood, LVP, tile, carpet |
| Concrete Pad Installation Labor | Pads, footings, sidewalks, driveways |
| Painting/Staining Labor | Interior/exterior painting, deck staining, trim |
| Bathroom Remodel Labor | Tile, fixtures, vanity, full remodels |
| Door/Window Installation Labor | Doors, windows, trim, weatherstripping |
| Tile Installation Labor | Floor tile, wall tile, backsplash |
| Plumbing Labor | Repairs, fixture replacement, basic installs |
| Gutter & Roofing Labor | Gutter cleaning/install, minor roof repairs |
| Landscaping Labor | Yard work, grading, drainage, mulch |
| Kitchen Remodel Labor | Cabinets, countertops, appliances, full remodels |
| Appliance Installation Labor | Dishwasher, range, water heater installs |
| Outdoor Structure Labor | Pergolas, gazebos, carports, sheds |
| Demolition & Hauling Labor | Demo work, junk removal, disposal |
| Asphalt & Paving Labor | Asphalt repair, seal coating, gravel |
| Screen & Enclosure Labor | Screen porches, enclosures |

If the work doesn't fit any category, use **General Handyman Labor**.

If you're adding a genuinely new service type not listed, name it consistently: `[Type] Labor` for labor, `[Type] Materials` for materials.

---

## Materials Line Items

Name material line items clearly so the app classifies them correctly (any line with "Materials" in the service name → classified as materials):

Examples:
- `Deck Materials` — lumber, screws, joist hangers
- `Framing Materials` — treated lumber, hardware
- `Paint & Supplies` — paint, primer, brushes, tape
- `Flooring Materials` — LVP planks, underlayment, adhesive
- `Concrete Materials` — bags, rebar, form boards
- `Electrical Materials` — outlets, wire, conduit
- `Plumbing Materials` — fittings, pipe, fixtures
- `Misc Materials` — small supplies, fasteners

---

## Pricing Reference (Mountain Home, AR market — Brian's historical averages)

These are rough ranges from Brian's completed jobs. Use these to sanity-check estimates.

| Category | Typical Range | Notes |
|---|---|---|
| General Handyman | $75–$150/hr or $350–$600/day | Day rate preferred |
| Deck Repair | $300–$1,200 | Depends on scope |
| Deck Construction | $2,500–$8,000+ | Size-driven |
| Fence Construction | $500–$2,500 | Per section/linear ft |
| Painting/Staining | $200–$1,500 | Interior vs exterior |
| Flooring | $400–$2,000 | Room-based pricing |
| Bathroom Remodel | $1,500–$6,000 | Tile + labor scope |
| Door/Window | $150–$600 each | Install only |
| Concrete Pad | $500–$2,000 | Size-driven |
| Demolition | $200–$800 | Based on scope/haul |

Brian's approximate labor rate is **$55–$75/hour**. When quoting days, a full day = ~8 hours.

---

## PDF Estimate Structure (what looks good to customers)

1. BHS header with logo/contact info
2. Estimate number + date + customer name/address
3. Line items table: Service | Description | Price
4. Totals section: Labor subtotal, Materials subtotal, **Total**
5. Notes/scope section if needed
6. Signature line / acceptance section

Keep it clean and one page when possible.

---

## What Happens After PDF is Created

1. Brian texts the PDF to the customer
2. The script POSTs the estimate data to: `POST https://[railway-url]/api/estimates`
3. The app stores it, links it to the customer (matched by phone number), and shows it in the Estimates pipeline
4. Brian tracks: Pending → Accepted → In Progress → Paid inside the app

---

## Customer Matching Logic

The app finds existing customers by **phone number first** (digits only, ignoring formatting), then by **exact name match**. If no match, a new customer is created. Always include the customer's phone number in the POST payload so this works correctly.

---

## Common Mistakes to Avoid

- Don't use `EST` prefix — estimate numbers are always `BHS`
- Don't omit `customer_phone` — it's how the app links to existing customer records
- Don't put the word "Labor" in materials line items (it will be miscategorized)
- Don't put the word "Materials" in labor line items (same reason)
- Keep `service` short (it becomes the line item label on the PDF and in the app)
- Keep `desc` descriptive (it's the detail line customers read)
