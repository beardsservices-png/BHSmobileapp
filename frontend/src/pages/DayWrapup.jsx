import { useState, useEffect, useRef } from 'react'

const API = '/api'

const today = () => new Date().toISOString().slice(0, 10)

const PAYMENT_METHODS = ['Cash', 'Check', 'Venmo', 'Zelle', 'PayPal', 'Credit Card', 'Debit Card', 'Bank Transfer', 'Other']

const EXPENSE_CATEGORIES = [
  'Materials & Supplies', 'Fuel & Transportation', 'Tools & Equipment',
  'Equipment Repair', 'Subcontractors', 'Insurance', 'Licensing',
  'Marketing', 'Office', 'Phone', 'Clothing', 'Professional Dev',
  'Disposal Fees', 'Other',
]

const TRIP_PURPOSES = [
  { value: 'site_assessment',       label: 'Site Assessment / Estimate Visit',    type: 'job_site',   warn: false },
  { value: 'measuring',             label: 'Measuring / Pre-job Visit',            type: 'job_site',   warn: false },
  { value: 'payment_pickup',        label: 'Picked Up a Payment',                  type: 'job_site',   warn: false },
  { value: 'materials_planned',     label: 'Materials Pickup (planned)',            type: 'supply',     warn: false },
  { value: 'materials_unplanned',   label: 'Materials Pickup (unplanned / forgot)', type: 'supply',     warn: true  },
  { value: 'fuel',                  label: 'Fuel Stop',                             type: 'other',      warn: false },
  { value: 'other',                 label: 'Other',                                 type: 'other',      warn: false },
]

const SERVICE_TYPES = [
  'General Handyman', 'Painting - Exterior', 'Painting - Interior',
  'Roofing - Metal Roof', 'Roofing - Shingle', 'Plumbing',
  'Electrical', 'Carpentry', 'Drywall', 'Flooring', 'HVAC',
  'Insulation', 'Pressure Washing', 'Landscaping', 'Concrete',
  'Siding', 'Windows & Doors', 'Cleaning', 'Other',
]

function makeJob() {
  return {
    _id: Date.now() + Math.random(),
    customer_id: '',
    job_id: '',
    new_job_desc: '',
    new_job_type: 'General Handyman',
    arrive_time: '',
    depart_time: '',
    services: [],
    materials: [],
    payment: null,
    log_trip: true,
    trip_miles: '',
    trip_drive_time: '',
    trip_destination: '',
    trip_notes: '',
    notes: '',
  }
}

function makeService() {
  return { _id: Date.now() + Math.random(), name: '', category: '', qty: 1, unit: 'job', price: '', is_material: false }
}

function makeMaterial() {
  return { _id: Date.now() + Math.random(), description: '', cost: '', vendor: '' }
}

function makeTrip() {
  return { _id: Date.now() + Math.random(), purpose: '', destination: '', customer_id: '', job_id: '', miles: '', drive_time: '', notes: '' }
}

function makeExpense() {
  return { _id: Date.now() + Math.random(), category: 'Fuel & Transportation', description: '', amount: '', vendor: '', is_overhead: true, job_id: '', customer_id: '', payment_method: 'Cash' }
}

function calcHours(arrive, depart) {
  if (!arrive || !depart) return null
  const [ah, am] = arrive.split(':').map(Number)
  const [dh, dm] = depart.split(':').map(Number)
  const mins = (dh * 60 + dm) - (ah * 60 + am)
  if (mins <= 0) return null
  return Math.round(mins / 60 * 100) / 100
}

// ─── Step indicator ────────────────────────────────────────────────────────────
function Steps({ step, steps }) {
  return (
    <div className="flex items-center gap-0 mb-8 overflow-x-auto pb-1">
      {steps.map((s, i) => (
        <div key={i} className="flex items-center shrink-0">
          <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium transition-all
            ${i === step ? 'bg-blue-600 text-white shadow-sm' :
              i < step  ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-400'}`}>
            {i < step ? '✓' : i + 1}. {s}
          </div>
          {i < steps.length - 1 && (
            <div className={`w-6 h-0.5 mx-1 ${i < step ? 'bg-green-400' : 'bg-slate-200'}`} />
          )}
        </div>
      ))}
    </div>
  )
}

// ─── Question label ────────────────────────────────────────────────────────────
function Q({ children, sub }) {
  return (
    <div className="mb-1">
      <p className="text-sm font-semibold text-slate-700">{children}</p>
      {sub && <p className="text-xs text-slate-400">{sub}</p>}
    </div>
  )
}

// ─── Job card ──────────────────────────────────────────────────────────────────
function JobCard({ job, idx, customers, allJobs, onChange, onRemove }) {
  const custJobs = allJobs.filter(j => String(j.customer_id) === String(job.customer_id))
  const selectedCust = customers.find(c => String(c.id) === String(job.customer_id))
  const hours = calcHours(job.arrive_time, job.depart_time)

  function set(field, val) { onChange({ ...job, [field]: val }) }

  function setService(sid, field, val) {
    onChange({ ...job, services: job.services.map(s => s._id === sid ? { ...s, [field]: val } : s) })
  }
  function addService() { onChange({ ...job, services: [...job.services, makeService()] }) }
  function removeService(sid) { onChange({ ...job, services: job.services.filter(s => s._id !== sid) }) }

  function setMaterial(mid, field, val) {
    onChange({ ...job, materials: job.materials.map(m => m._id === mid ? { ...m, [field]: val } : m) })
  }
  function addMaterial() { onChange({ ...job, materials: [...job.materials, makeMaterial()] }) }
  function removeMaterial(mid) { onChange({ ...job, materials: job.materials.filter(m => m._id !== mid) }) }

  const hasPayment = !!job.payment
  function togglePayment(on) {
    set('payment', on ? { amount: '', method: 'Cash', memo: '' } : null)
  }
  function setPayment(field, val) {
    set('payment', { ...job.payment, [field]: val })
  }

  // Auto-fill miles when customer changes
  function handleCustomerChange(custId) {
    const c = customers.find(x => String(x.id) === String(custId))
    onChange({
      ...job,
      customer_id: custId,
      job_id: '',
      trip_destination: c?.address || '',
      trip_miles: c?.mileage_from_home ? String(c.mileage_from_home) : job.trip_miles,
    })
  }

  const inputCls = "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
  const labelCls = "text-xs font-medium text-slate-500 mb-0.5 block"

  return (
    <div className="border-2 border-blue-100 rounded-xl p-5 bg-white shadow-sm space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-blue-700 text-base">Job #{idx + 1}</h3>
        {idx > 0 && (
          <button onClick={onRemove} className="text-xs text-red-400 hover:text-red-600">Remove</button>
        )}
      </div>

      {/* Customer */}
      <div>
        <Q>Who did you work for?</Q>
        <select value={job.customer_id} onChange={e => handleCustomerChange(e.target.value)} className={inputCls}>
          <option value="">— Pick a customer —</option>
          {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>

      {/* Job */}
      {job.customer_id && (
        <div>
          <Q>Which job?</Q>
          <select value={job.job_id} onChange={e => set('job_id', e.target.value)} className={inputCls}>
            <option value="">— Start a new job —</option>
            {custJobs.map(j => (
              <option key={j.id} value={j.id}>{j.invoice_id || j.id} — {j.notes?.slice(0,50) || '(no description)'}</option>
            ))}
          </select>
          {!job.job_id && (
            <div className="mt-2 space-y-2">
              <input placeholder="Briefly describe the new job (e.g. Replace bathroom faucet)"
                value={job.new_job_desc} onChange={e => set('new_job_desc', e.target.value)} className={inputCls} />
              <select value={job.new_job_type} onChange={e => set('new_job_type', e.target.value)} className={inputCls}>
                {SERVICE_TYPES.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
          )}
        </div>
      )}

      {/* Time on site */}
      {job.customer_id && (
        <div>
          <Q>Time on site</Q>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>Arrived</label>
              <input type="time" value={job.arrive_time} onChange={e => set('arrive_time', e.target.value)} className={inputCls} />
            </div>
            <div>
              <label className={labelCls}>Left</label>
              <input type="time" value={job.depart_time} onChange={e => set('depart_time', e.target.value)} className={inputCls} />
            </div>
          </div>
          {hours && (
            <p className="text-xs text-green-600 mt-1">= {hours} hours on site</p>
          )}
        </div>
      )}

      {/* Services */}
      {job.customer_id && (
        <div>
          <Q>What work did you do?</Q>
          {job.services.length === 0 && (
            <p className="text-xs text-slate-400 mb-2">No service lines yet — tap + to add.</p>
          )}
          <div className="space-y-2">
            {job.services.map(svc => (
              <div key={svc._id} className="bg-slate-50 rounded-lg p-3 space-y-2">
                <div className="flex gap-2">
                  <input placeholder="Service description (e.g. Install pipe boot)" value={svc.name}
                    onChange={e => setService(svc._id, 'name', e.target.value)}
                    className="flex-1 border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
                  <button onClick={() => removeService(svc._id)} className="text-slate-300 hover:text-red-400 text-lg leading-none">×</button>
                </div>
                <input placeholder="Category (e.g. Roofing - Metal Roof)" value={svc.category}
                  onChange={e => setService(svc._id, 'category', e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
                <div className="grid grid-cols-4 gap-2">
                  <div>
                    <label className={labelCls}>Qty</label>
                    <input type="number" min="0" step="0.5" value={svc.qty}
                      onChange={e => setService(svc._id, 'qty', e.target.value)}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
                  </div>
                  <div>
                    <label className={labelCls}>Unit</label>
                    <input placeholder="job" value={svc.unit}
                      onChange={e => setService(svc._id, 'unit', e.target.value)}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
                  </div>
                  <div>
                    <label className={labelCls}>Price $</label>
                    <input type="number" min="0" step="0.01" placeholder="0.00" value={svc.price}
                      onChange={e => setService(svc._id, 'price', e.target.value)}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
                  </div>
                  <div className="flex flex-col justify-end pb-1.5">
                    <label className="flex items-center gap-1 text-xs text-slate-500 cursor-pointer">
                      <input type="checkbox" checked={svc.is_material}
                        onChange={e => setService(svc._id, 'is_material', e.target.checked)} />
                      Material
                    </label>
                  </div>
                </div>
                {svc.qty && svc.price && (
                  <p className="text-xs text-green-600">= ${(parseFloat(svc.qty||0) * parseFloat(svc.price||0)).toFixed(2)}</p>
                )}
              </div>
            ))}
          </div>
          <button onClick={addService}
            className="mt-2 w-full py-1.5 rounded-lg border-2 border-dashed border-blue-200 text-blue-500 text-sm hover:border-blue-400 hover:text-blue-600">
            + Add service line
          </button>
        </div>
      )}

      {/* Materials for this job */}
      {job.customer_id && (
        <div>
          <Q>Did you pick up any materials for this job?</Q>
          {job.materials.length === 0 && (
            <p className="text-xs text-slate-400 mb-2">Nothing yet — tap + to add.</p>
          )}
          <div className="space-y-2">
            {job.materials.map(mat => (
              <div key={mat._id} className="bg-slate-50 rounded-lg p-3">
                <div className="flex gap-2 mb-2">
                  <input placeholder="What was it? (e.g. Pipe boots, caulk)" value={mat.description}
                    onChange={e => setMaterial(mat._id, 'description', e.target.value)}
                    className="flex-1 border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
                  <button onClick={() => removeMaterial(mat._id)} className="text-slate-300 hover:text-red-400 text-lg leading-none">×</button>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className={labelCls}>Cost $</label>
                    <input type="number" min="0" step="0.01" placeholder="0.00" value={mat.cost}
                      onChange={e => setMaterial(mat._id, 'cost', e.target.value)}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
                  </div>
                  <div>
                    <label className={labelCls}>Where from?</label>
                    <input placeholder="Lowe's, Home Depot…" value={mat.vendor}
                      onChange={e => setMaterial(mat._id, 'vendor', e.target.value)}
                      className="w-full border border-slate-300 rounded-lg px-2 py-1.5 text-sm" />
                  </div>
                </div>
              </div>
            ))}
          </div>
          <button onClick={addMaterial}
            className="mt-2 w-full py-1.5 rounded-lg border-2 border-dashed border-slate-200 text-slate-400 text-sm hover:border-slate-400 hover:text-slate-600">
            + Add material purchase
          </button>
        </div>
      )}

      {/* Payment */}
      {job.customer_id && (
        <div>
          <Q>Did they pay today?</Q>
          <div className="flex gap-3 mb-3">
            {[['Yes', true], ['No', false]].map(([label, val]) => (
              <button key={label} onClick={() => togglePayment(val)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium border transition-colors
                  ${hasPayment === val
                    ? 'bg-green-600 text-white border-green-600'
                    : 'bg-white text-slate-600 border-slate-300 hover:border-slate-400'}`}>
                {label}
              </button>
            ))}
          </div>
          {hasPayment && (
            <div className="bg-green-50 rounded-lg p-3 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className={labelCls}>Amount $</label>
                  <input type="number" min="0" step="0.01" placeholder="0.00" value={job.payment.amount}
                    onChange={e => setPayment('amount', e.target.value)}
                    className="w-full border border-green-300 rounded-lg px-2 py-1.5 text-sm" />
                </div>
                <div>
                  <label className={labelCls}>How did they pay?</label>
                  <select value={job.payment.method} onChange={e => setPayment('method', e.target.value)}
                    className="w-full border border-green-300 rounded-lg px-2 py-1.5 text-sm">
                    {PAYMENT_METHODS.map(m => <option key={m}>{m}</option>)}
                  </select>
                </div>
              </div>
              <input placeholder="Memo (optional)" value={job.payment.memo}
                onChange={e => setPayment('memo', e.target.value)}
                className="w-full border border-green-300 rounded-lg px-2 py-1.5 text-sm" />
            </div>
          )}
        </div>
      )}

      {/* Trip to job site */}
      {job.customer_id && (
        <div>
          <Q>Log the drive to this job?</Q>
          <div className="flex gap-3 mb-3">
            {[['Yes', true], ['No', false]].map(([label, val]) => (
              <button key={label} onClick={() => set('log_trip', val)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium border transition-colors
                  ${job.log_trip === val
                    ? 'bg-teal-600 text-white border-teal-600'
                    : 'bg-white text-slate-600 border-slate-300 hover:border-slate-400'}`}>
                {label}
              </button>
            ))}
          </div>
          {job.log_trip && (
            <div className="bg-teal-50 rounded-lg p-3 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className={labelCls}>One-way miles</label>
                  <input type="number" min="0" step="0.1" placeholder="0"
                    value={job.trip_miles}
                    onChange={e => set('trip_miles', e.target.value)}
                    className="w-full border border-teal-300 rounded-lg px-2 py-1.5 text-sm" />
                  {selectedCust?.mileage_from_home && (
                    <p className="text-xs text-teal-600 mt-0.5">
                      Stored: {selectedCust.mileage_from_home} mi
                      <button className="ml-1 underline" onClick={() => set('trip_miles', selectedCust.mileage_from_home)}>use</button>
                    </p>
                  )}
                </div>
                <div>
                  <label className={labelCls}>Drive time (min)</label>
                  <input type="number" min="0" step="1" placeholder="0"
                    value={job.trip_drive_time}
                    onChange={e => set('trip_drive_time', e.target.value)}
                    className="w-full border border-teal-300 rounded-lg px-2 py-1.5 text-sm" />
                </div>
              </div>
              {job.trip_miles && (
                <p className="text-xs text-teal-600">
                  IRS deduction: ${(parseFloat(job.trip_miles) * 0.70).toFixed(2)} @ $0.70/mi
                </p>
              )}
            </div>
          )}
        </div>
      )}

      {/* Notes */}
      {job.customer_id && (
        <div>
          <Q>Anything else to note about this job?</Q>
          <textarea rows={2} placeholder="Gate code, CYA note, customer feedback, what's left to do…"
            value={job.notes} onChange={e => set('notes', e.target.value)}
            className={inputCls + ' resize-none'} />
        </div>
      )}
    </div>
  )
}

// ─── Trip card ─────────────────────────────────────────────────────────────────
function TripCard({ trip, idx, customers, allJobs, onChange, onRemove }) {
  const purpose = TRIP_PURPOSES.find(p => p.value === trip.purpose)
  const custJobs = allJobs.filter(j => String(j.customer_id) === String(trip.customer_id))
  function set(f, v) { onChange({ ...trip, [f]: v }) }
  const inputCls = "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-400"
  const labelCls = "text-xs font-medium text-slate-500 mb-0.5 block"

  return (
    <div className={`border-2 rounded-xl p-5 bg-white shadow-sm space-y-4 ${purpose?.warn ? 'border-amber-200' : 'border-teal-100'}`}>
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-teal-700 text-base">Trip #{idx + 1}</h3>
        <button onClick={onRemove} className="text-xs text-red-400 hover:text-red-600">Remove</button>
      </div>

      <div>
        <Q>What was this trip for?</Q>
        <select value={trip.purpose} onChange={e => set('purpose', e.target.value)} className={inputCls}>
          <option value="">— Select trip type —</option>
          {TRIP_PURPOSES.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
        {purpose?.warn && (
          <p className="text-xs text-amber-600 mt-1">Unplanned trip — this shows up as waste in your reports.</p>
        )}
      </div>

      {trip.purpose && (
        <>
          <div>
            <Q>Where did you go?</Q>
            <input placeholder="Lowe's, 123 Main St, etc." value={trip.destination}
              onChange={e => set('destination', e.target.value)} className={inputCls} />
          </div>

          {['site_assessment','measuring','payment_pickup'].includes(trip.purpose) && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Q>Customer (if any)</Q>
                <select value={trip.customer_id} onChange={e => set('customer_id', e.target.value)} className={inputCls}>
                  <option value="">— None —</option>
                  {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              {trip.customer_id && (
                <div>
                  <Q>Which job?</Q>
                  <select value={trip.job_id} onChange={e => set('job_id', e.target.value)} className={inputCls}>
                    <option value="">— None / New —</option>
                    {custJobs.map(j => <option key={j.id} value={j.id}>{j.invoice_id || j.id}</option>)}
                  </select>
                </div>
              )}
            </div>
          )}

          {['materials_planned','materials_unplanned'].includes(trip.purpose) && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Q>For which customer / job?</Q>
                <select value={trip.customer_id} onChange={e => set('customer_id', e.target.value)} className={inputCls}>
                  <option value="">— Overhead / General —</option>
                  {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              {trip.customer_id && (
                <div>
                  <Q>Which job?</Q>
                  <select value={trip.job_id} onChange={e => set('job_id', e.target.value)} className={inputCls}>
                    <option value="">— None / New —</option>
                    {custJobs.map(j => <option key={j.id} value={j.id}>{j.invoice_id || j.id}</option>)}
                  </select>
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelCls}>One-way miles</label>
              <input type="number" min="0" step="0.1" placeholder="0"
                value={trip.miles}
                onChange={e => {
                  const mi = parseFloat(e.target.value) || 0
                  const autoMins = mi > 0 ? String(Math.round((mi / 30) * 60 / 5) * 5) : ''
                  set('miles', e.target.value)
                  if (!trip.drive_time) set('drive_time', autoMins)
                }}
                className={inputCls} />
              {trip.miles && (
                <p className="text-xs text-teal-600 mt-0.5">
                  IRS deduction: ${(parseFloat(trip.miles) * 0.70).toFixed(2)}
                </p>
              )}
            </div>
            <div>
              <label className={labelCls}>Drive time (min)</label>
              <input type="number" min="0" step="5" placeholder="estimated"
                value={trip.drive_time} onChange={e => set('drive_time', e.target.value)} className={inputCls} />
            </div>
          </div>

          <div>
            <label className={labelCls}>Notes (optional)</label>
            <input placeholder="Any details…" value={trip.notes}
              onChange={e => set('notes', e.target.value)} className={inputCls} />
          </div>
        </>
      )}
    </div>
  )
}

// ─── Expense card ──────────────────────────────────────────────────────────────
function ExpenseCard({ exp, idx, customers, allJobs, onChange, onRemove }) {
  const custJobs = allJobs.filter(j => String(j.customer_id) === String(exp.customer_id))
  const fileRef = useRef(null)
  function set(f, v) { onChange({ ...exp, [f]: v }) }
  const inputCls = "w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-orange-400"
  const labelCls = "text-xs font-medium text-slate-500 mb-0.5 block"

  function handlePhoto(e) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = evt => set('receipt_photo', evt.target.result)
    reader.readAsDataURL(file)
  }

  return (
    <div className="border-2 border-orange-100 rounded-xl p-5 bg-white shadow-sm space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-orange-700 text-base">Expense #{idx + 1}</h3>
        <div className="flex items-center gap-3">
          {/* Camera / receipt button */}
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className={`flex items-center gap-1 text-xs px-2 py-1 rounded-lg border transition-colors ${
              exp.receipt_photo ? 'border-green-400 text-green-700 bg-green-50' : 'border-slate-300 text-slate-500 hover:border-orange-400 hover:text-orange-600'
            }`}
            title="Take or attach a receipt photo"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            {exp.receipt_photo ? 'Receipt ✓' : 'Receipt'}
          </button>
          <input ref={fileRef} type="file" accept="image/*" capture="environment"
            className="hidden" onChange={handlePhoto} />
          <button onClick={onRemove} className="text-xs text-red-400 hover:text-red-600">Remove</button>
        </div>
      </div>

      {/* Receipt photo preview */}
      {exp.receipt_photo && (
        <div className="relative">
          <img src={exp.receipt_photo} alt="Receipt" className="w-full max-h-40 object-contain rounded-lg border border-green-200" />
          <button onClick={() => set('receipt_photo', null)}
            className="absolute top-1 right-1 bg-white border border-red-200 rounded-full w-5 h-5 flex items-center justify-center text-red-400 hover:text-red-600 text-xs">
            ×
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>Category</label>
          <select value={exp.category} onChange={e => set('category', e.target.value)} className={inputCls}>
            {EXPENSE_CATEGORIES.map(c => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div>
          <label className={labelCls}>Amount $</label>
          <input type="number" min="0" step="0.01" placeholder="0.00"
            value={exp.amount} onChange={e => set('amount', e.target.value)} className={inputCls} />
        </div>
      </div>

      <div>
        <label className={labelCls}>What was it for?</label>
        <input placeholder="Describe the expense" value={exp.description}
          onChange={e => set('description', e.target.value)} className={inputCls} />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>Where / Who paid to?</label>
          <input placeholder="Casey's, Lowe's, etc." value={exp.vendor}
            onChange={e => set('vendor', e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className={labelCls}>How did you pay?</label>
          <select value={exp.payment_method} onChange={e => set('payment_method', e.target.value)} className={inputCls}>
            {PAYMENT_METHODS.map(m => <option key={m}>{m}</option>)}
          </select>
        </div>
      </div>

      <div>
        <Q>Is this tied to a specific job?</Q>
        <div className="flex gap-3 mb-2">
          {[['General overhead', true], ['Job-specific', false]].map(([label, val]) => (
            <button key={label} onClick={() => set('is_overhead', val)}
              className={`px-3 py-1 rounded-full text-sm font-medium border transition-colors
                ${exp.is_overhead === val
                  ? 'bg-orange-600 text-white border-orange-600'
                  : 'bg-white text-slate-600 border-slate-300 hover:border-slate-400'}`}>
              {label}
            </button>
          ))}
        </div>
        {!exp.is_overhead && (
          <div className="grid grid-cols-2 gap-2">
            <select value={exp.customer_id} onChange={e => set('customer_id', e.target.value)} className={inputCls}>
              <option value="">— Customer —</option>
              {customers.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
            {exp.customer_id && (
              <select value={exp.job_id} onChange={e => set('job_id', e.target.value)} className={inputCls}>
                <option value="">— Job —</option>
                {custJobs.map(j => <option key={j.id} value={j.id}>{j.invoice_id || j.id}</option>)}
              </select>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ─── Review section ────────────────────────────────────────────────────────────
function ReviewLine({ label, value, color = 'text-slate-700' }) {
  return (
    <div className="flex justify-between text-sm py-1 border-b border-slate-100">
      <span className="text-slate-500">{label}</span>
      <span className={`font-medium ${color}`}>{value}</span>
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────────
export default function DayWrapup() {
  const [step, setStep]       = useState(0)
  const [date, setDate]       = useState(today())
  const [jobs, setJobs]       = useState([makeJob()])
  const [trips, setTrips]     = useState([])
  const [existingTrips, setExistingTrips] = useState([])  // trips already in DB for this date
  const [expenses, setExpenses] = useState([])
  const [customers, setCustomers] = useState([])
  const [allJobs, setAllJobs]   = useState([])
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone]       = useState(null)  // summary object on success

  const STEPS = ['Date', 'Job Work', 'Other Trips', 'Expenses', 'Review & Submit']

  useEffect(() => {
    Promise.all([
      fetch(`${API}/customers`).then(r => r.json()),
      fetch(`${API}/jobs`).then(r => r.json()),
    ]).then(([custs, jbs]) => {
      // API already returns customers sorted by most recent job date
      setCustomers(Array.isArray(custs) ? custs.filter(c => !c.name.startsWith('_')) : [])
      setAllJobs(Array.isArray(jbs) ? jbs : [])
    }).catch(() => {})
  }, [])

  // Fetch already-logged trips whenever the date changes
  useEffect(() => {
    fetch(`${API}/trips?start=${date}&end=${date}`)
      .then(r => r.json())
      .then(data => setExistingTrips(Array.isArray(data) ? data : []))
      .catch(() => setExistingTrips([]))
  }, [date])

  function updateJob(idx, val) { setJobs(jobs.map((j, i) => i === idx ? val : j)) }
  function addJob() { setJobs([...jobs, makeJob()]) }
  function removeJob(idx) { setJobs(jobs.filter((_, i) => i !== idx)) }

  function updateTrip(idx, val) { setTrips(trips.map((t, i) => i === idx ? val : t)) }
  function removeTrip(idx) { setTrips(trips.filter((_, i) => i !== idx)) }

  function updateExp(idx, val) { setExpenses(expenses.map((e, i) => i === idx ? val : e)) }
  function removeExp(idx) { setExpenses(expenses.filter((_, i) => i !== idx)) }

  async function handleSubmit() {
    setSubmitting(true)
    const payload = {
      date,
      jobs: jobs.filter(j => j.customer_id).map(j => ({
        customer_id: j.customer_id ? parseInt(j.customer_id) : null,
        job_id: j.job_id ? parseInt(j.job_id) : null,
        new_job_desc: j.new_job_desc,
        new_job_type: j.new_job_type,
        arrive_time: j.arrive_time,
        depart_time: j.depart_time,
        services: j.services.filter(s => s.name).map(s => ({
          name: s.name, category: s.category,
          qty: parseFloat(s.qty) || 1, unit: s.unit,
          price: parseFloat(s.price) || 0, is_material: s.is_material,
        })),
        materials: j.materials.filter(m => m.description && m.cost).map(m => ({
          description: m.description, cost: parseFloat(m.cost), vendor: m.vendor,
        })),
        payment: (j.payment && j.payment.amount) ? {
          amount: parseFloat(j.payment.amount), method: j.payment.method, memo: j.payment.memo,
        } : null,
        log_trip: j.log_trip,
        trip_miles: j.trip_miles ? parseFloat(j.trip_miles) : null,
        trip_drive_time: j.trip_drive_time ? parseInt(j.trip_drive_time) : null,
        trip_destination: j.trip_destination,
        trip_notes: j.notes,
        notes: j.notes,
      })),
      other_trips: trips.filter(t => t.purpose).map(t => ({
        purpose: t.purpose, destination: t.destination,
        customer_id: t.customer_id ? parseInt(t.customer_id) : null,
        job_id: t.job_id ? parseInt(t.job_id) : null,
        miles: t.miles ? parseFloat(t.miles) : null,
        drive_time: t.drive_time ? parseInt(t.drive_time) : null,
        notes: t.notes,
      })),
      expenses: expenses.filter(e => e.description && e.amount).map(e => ({
        category: e.category, description: e.description,
        amount: parseFloat(e.amount), vendor: e.vendor,
        is_overhead: e.is_overhead,
        job_id: e.job_id ? parseInt(e.job_id) : null,
        customer_id: e.customer_id ? parseInt(e.customer_id) : null,
        payment_method: e.payment_method,
      })),
    }

    try {
      const res = await fetch(`${API}/day-wrapup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const body = await res.json()
      if (!res.ok) throw new Error(body.error || 'Server error')
      setDone(body.summary)
    } catch (err) {
      alert('Error saving: ' + err.message)
    } finally {
      setSubmitting(false)
    }
  }

  // ── Success screen ──────────────────────────────────────────────────────────
  if (done) {
    const totalPmts = jobs.reduce((sum, j) => sum + (parseFloat(j.payment?.amount) || 0), 0)
    const totalMiles = [
      ...jobs.filter(j => j.log_trip).map(j => parseFloat(j.trip_miles) || 0),
      ...trips.map(t => parseFloat(t.miles) || 0),
    ].reduce((a, b) => a + b, 0)
    return (
      <div className="max-w-lg mx-auto text-center py-12 space-y-6">
        <div className="text-6xl">✅</div>
        <h2 className="text-2xl font-bold text-slate-800">Day Saved!</h2>
        <p className="text-slate-500">Everything for {date} is recorded.</p>
        <div className="bg-white rounded-xl border border-slate-200 p-5 text-left space-y-1">
          <ReviewLine label="Jobs / time entries"   value={done.time_entries} />
          <ReviewLine label="Service lines added"   value={done.services} />
          <ReviewLine label="Material purchases"    value={done.materials} />
          <ReviewLine label="Payments collected"    value={`${done.payments} — $${totalPmts.toFixed(2)}`} color="text-green-600" />
          <ReviewLine label="Trips logged"          value={`${done.trips} — ${totalMiles.toFixed(1)} mi`} />
          <ReviewLine label="Expenses recorded"     value={done.expenses} />
          {done.new_jobs > 0 && <ReviewLine label="New jobs created" value={done.new_jobs} color="text-blue-600" />}
        </div>
        <div className="flex gap-3 justify-center">
          <button onClick={() => { setDone(null); setStep(0); setJobs([makeJob()]); setTrips([]); setExpenses([]) }}
            className="px-5 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700">
            Start New Day
          </button>
          <a href="/" className="px-5 py-2 rounded-lg border border-slate-300 text-slate-600 font-medium hover:bg-slate-50">
            Go to Dashboard
          </a>
        </div>
      </div>
    )
  }

  // ── Review step ─────────────────────────────────────────────────────────────
  function renderReview() {
    const validJobs = jobs.filter(j => j.customer_id)
    const validTrips = trips.filter(t => t.purpose)
    const validExps = expenses.filter(e => e.description && e.amount)
    const totalPmts = validJobs.reduce((s, j) => s + (parseFloat(j.payment?.amount) || 0), 0)
    const totalJobMiles = validJobs.filter(j => j.log_trip).reduce((s, j) => s + (parseFloat(j.trip_miles) || 0), 0)
    const totalOtherMiles = validTrips.reduce((s, t) => s + (parseFloat(t.miles) || 0), 0)
    const totalExpenses = validExps.reduce((s, e) => s + (parseFloat(e.amount) || 0), 0)
    const totalServices = validJobs.flatMap(j => j.services).reduce((s, sv) => s + (parseFloat(sv.price||0) * parseFloat(sv.qty||1)), 0)

    return (
      <div className="space-y-5">
        <div className="bg-blue-50 rounded-xl p-4 space-y-2">
          <h3 className="font-bold text-blue-800 text-sm uppercase tracking-wide">Summary for {date}</h3>
          <ReviewLine label="Jobs worked"        value={validJobs.length} />
          <ReviewLine label="Services billed"    value={`${validJobs.flatMap(j=>j.services).filter(s=>s.name).length} lines — $${totalServices.toFixed(2)}`} color="text-green-600" />
          <ReviewLine label="Payments collected" value={totalPmts > 0 ? `$${totalPmts.toFixed(2)}` : 'None'} color={totalPmts > 0 ? 'text-green-600' : 'text-slate-500'} />
          <ReviewLine label="Job site miles"     value={`${totalJobMiles.toFixed(1)} mi — $${(totalJobMiles * 0.70).toFixed(2)} deduction`} />
          <ReviewLine label="Other trips"        value={`${validTrips.length} trips — ${totalOtherMiles.toFixed(1)} mi`} />
          <ReviewLine label="Expenses"           value={totalExpenses > 0 ? `-$${totalExpenses.toFixed(2)}` : 'None'} color={totalExpenses > 0 ? 'text-red-500' : 'text-slate-500'} />
        </div>

        {validJobs.map((job, i) => {
          const cust = customers.find(c => String(c.id) === String(job.customer_id))
          const hrs = calcHours(job.arrive_time, job.depart_time)
          return (
            <div key={job._id} className="bg-white border border-slate-200 rounded-xl p-4 space-y-1">
              <p className="font-semibold text-slate-700">{cust?.name || 'Customer'}</p>
              {hrs && <p className="text-xs text-slate-500">{job.arrive_time} – {job.depart_time} ({hrs} hrs)</p>}
              {job.services.filter(s => s.name).map(s => (
                <p key={s._id} className="text-xs text-slate-600">
                  • {s.name} × {s.qty} {s.unit} @ ${s.price} = ${(parseFloat(s.price||0)*parseFloat(s.qty||1)).toFixed(2)}
                </p>
              ))}
              {job.materials.filter(m=>m.description).map(m => (
                <p key={m._id} className="text-xs text-slate-500">Materials: {m.description} ${m.cost}</p>
              ))}
              {job.payment?.amount && (
                <p className="text-xs text-green-600">Payment: ${job.payment.amount} ({job.payment.method})</p>
              )}
              {job.log_trip && job.trip_miles && (
                <p className="text-xs text-teal-600">Drive: {job.trip_miles} mi</p>
              )}
            </div>
          )
        })}

        {validTrips.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-1">
            <p className="font-semibold text-slate-700 text-sm">Other Trips</p>
            {validTrips.map(t => {
              const p = TRIP_PURPOSES.find(x => x.value === t.purpose)
              return (
                <p key={t._id} className={`text-xs ${p?.warn ? 'text-amber-600' : 'text-slate-500'}`}>
                  • {p?.label || t.purpose}{t.destination ? ` → ${t.destination}` : ''}{t.miles ? ` (${t.miles} mi)` : ''}
                </p>
              )
            })}
          </div>
        )}

        {validExps.length > 0 && (
          <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-1">
            <p className="font-semibold text-slate-700 text-sm">Expenses</p>
            {validExps.map(e => (
              <p key={e._id} className="text-xs text-slate-500">
                • {e.category}: {e.description} — ${e.amount}{e.vendor ? ` at ${e.vendor}` : ''}
              </p>
            ))}
          </div>
        )}

        <button onClick={handleSubmit} disabled={submitting || validJobs.length === 0}
          className="w-full py-3 rounded-xl bg-green-600 text-white font-bold text-base hover:bg-green-700 disabled:opacity-50 transition-colors">
          {submitting ? 'Saving…' : 'Save My Day ✓'}
        </button>
        {validJobs.length === 0 && (
          <p className="text-center text-xs text-slate-400">Add at least one job to save.</p>
        )}
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-800">End-of-Day Wrap-Up</h1>
        <p className="text-slate-500 text-sm">Answer a few questions and everything gets logged automatically.</p>
      </div>

      <Steps step={step} steps={STEPS} />

      {/* Step 0: Date */}
      {step === 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-6">
          <div>
            <Q>What day are you wrapping up?</Q>
            <input type="date" value={date} onChange={e => setDate(e.target.value)}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 max-w-xs" />
          </div>
          <button onClick={() => setStep(1)}
            className="w-full py-2.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700">
            Next: Log Job Work →
          </button>
        </div>
      )}

      {/* Step 1: Jobs */}
      {step === 1 && (
        <div className="space-y-5">
          {jobs.map((job, i) => (
            <JobCard key={job._id} job={job} idx={i}
              customers={customers} allJobs={allJobs}
              onChange={val => updateJob(i, val)}
              onRemove={() => removeJob(i)} />
          ))}
          <button onClick={addJob}
            className="w-full py-2.5 rounded-xl border-2 border-dashed border-blue-200 text-blue-500 font-medium hover:border-blue-400 hover:text-blue-600">
            + Add another job
          </button>
          <div className="flex gap-3">
            <button onClick={() => setStep(0)} className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-600 hover:bg-slate-50">← Back</button>
            <button onClick={() => setStep(2)} className="flex-1 py-2.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700">
              Next: Other Trips →
            </button>
          </div>
        </div>
      )}

      {/* Step 2: Other trips */}
      {step === 2 && (
        <div className="space-y-5">
          <div className="bg-teal-50 border border-teal-200 rounded-xl p-4">
            <p className="text-sm font-semibold text-teal-800 mb-1">Other trips today</p>
            <p className="text-xs text-teal-600">
              Any drives that weren't direct job site visits — materials runs, estimates, picking up payments, fuel stops.
              Don't log trips already covered in the job cards above.
            </p>
          </div>

          {/* Already-logged trips for this date */}
          {existingTrips.length > 0 && (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Already logged for {date}</p>
              <div className="space-y-1.5">
                {existingTrips.map(t => (
                  <div key={t.id} className="flex items-center gap-2 text-xs text-slate-600">
                    <span className="w-1.5 h-1.5 rounded-full bg-teal-400 flex-shrink-0" />
                    <span className="font-medium">{t.destination || '(no destination)'}</span>
                    {t.miles && <span className="text-slate-400">· {t.miles} mi</span>}
                    {t.drive_time_minutes && <span className="text-slate-400">· {t.drive_time_minutes} min</span>}
                    {t.customer_name && <span className="text-slate-400">· {t.customer_name}</span>}
                  </div>
                ))}
              </div>
              <p className="text-xs text-slate-400 mt-2">These are already saved — only add new ones below.</p>
            </div>
          )}

          {trips.length === 0 && existingTrips.length === 0 && (
            <div className="text-center text-slate-400 text-sm py-4">No other trips — tap + to add one.</div>
          )}
          {trips.map((t, i) => (
            <TripCard key={t._id} trip={t} idx={i}
              customers={customers} allJobs={allJobs}
              onChange={val => updateTrip(i, val)}
              onRemove={() => removeTrip(i)} />
          ))}
          <button onClick={() => setTrips([...trips, makeTrip()])}
            className="w-full py-2.5 rounded-xl border-2 border-dashed border-teal-200 text-teal-500 font-medium hover:border-teal-400 hover:text-teal-600">
            + Add a trip
          </button>
          <div className="flex gap-3">
            <button onClick={() => setStep(1)} className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-600 hover:bg-slate-50">← Back</button>
            <button onClick={() => setStep(3)} className="flex-1 py-2.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700">
              Next: Expenses →
            </button>
          </div>
        </div>
      )}

      {/* Step 3: Expenses */}
      {step === 3 && (
        <div className="space-y-5">
          <div className="bg-orange-50 border border-orange-200 rounded-xl p-4">
            <p className="text-sm font-semibold text-orange-800 mb-1">Business expenses today</p>
            <p className="text-xs text-orange-600">
              Fuel receipts, tool purchases, supplies, anything you spent money on for the business.
              Materials purchased <em>for a specific job</em> were already covered in the job cards above.
            </p>
          </div>
          {expenses.length === 0 && (
            <div className="text-center text-slate-400 text-sm py-4">No expenses — tap + to add one.</div>
          )}
          {expenses.map((e, i) => (
            <ExpenseCard key={e._id} exp={e} idx={i}
              customers={customers} allJobs={allJobs}
              onChange={val => updateExp(i, val)}
              onRemove={() => removeExp(i)} />
          ))}
          <button onClick={() => setExpenses([...expenses, makeExpense()])}
            className="w-full py-2.5 rounded-xl border-2 border-dashed border-orange-200 text-orange-500 font-medium hover:border-orange-400 hover:text-orange-600">
            + Add an expense
          </button>
          <div className="flex gap-3">
            <button onClick={() => setStep(2)} className="px-5 py-2.5 rounded-xl border border-slate-300 text-slate-600 hover:bg-slate-50">← Back</button>
            <button onClick={() => setStep(4)} className="flex-1 py-2.5 rounded-xl bg-blue-600 text-white font-semibold hover:bg-blue-700">
              Review & Save →
            </button>
          </div>
        </div>
      )}

      {/* Step 4: Review */}
      {step === 4 && (
        <div className="space-y-5">
          {renderReview()}
          <button onClick={() => setStep(3)} className="w-full py-2 rounded-xl border border-slate-300 text-slate-500 text-sm hover:bg-slate-50">
            ← Go back and edit
          </button>
        </div>
      )}
    </div>
  )
}
