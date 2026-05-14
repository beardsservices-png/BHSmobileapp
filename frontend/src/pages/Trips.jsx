import { useState, useEffect } from 'react'

const fmt = n => `$${(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const fmtMiles = n => `${(n || 0).toFixed(1)} mi`
const fmtTime = mins => {
  const m = Math.round(mins || 0)
  return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`
}

const IRS_RATE = 0.70

const INPUT = 'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white'

const TRIP_TYPES = [
  { value: 'job_site',          label: 'Job Site',            short: 'Job Site',       color: 'bg-blue-100 text-blue-700' },
  { value: 'supply_planned',    label: 'Planned Supply Run',  short: 'Supply Run',     color: 'bg-green-100 text-green-700' },
  { value: 'supply_unplanned',  label: 'Unplanned Supply Run',short: 'Unplanned Run',  color: 'bg-amber-100 text-amber-700' },
  { value: 'other',             label: 'Other',               short: 'Other',          color: 'bg-gray-100 text-gray-600' },
]

function tripTypeInfo(value) {
  return TRIP_TYPES.find(t => t.value === value) || TRIP_TYPES[3]
}

function currentMonthRange() {
  const now = new Date()
  const y = now.getFullYear()
  const m = String(now.getMonth() + 1).padStart(2, '0')
  const lastDay = new Date(y, now.getMonth() + 1, 0).getDate()
  return {
    start: `${y}-${m}-01`,
    end:   `${y}-${m}-${String(lastDay).padStart(2, '0')}`,
  }
}

const EMPTY_FORM = () => ({
  trip_date:          new Date().toISOString().slice(0, 10),
  trip_type:          'job_site',
  destination:        '',
  customer_id:        '',
  job_id:             '',
  miles:              '',
  drive_time_minutes: '',
  notes:              '',
})

export default function Trips() {
  const [trips, setTrips]         = useState([])
  const [summary, setSummary]     = useState(null)
  const [customers, setCustomers] = useState([])
  const [jobs, setJobs]           = useState([])
  const [loading, setLoading]     = useState(true)
  const [saving, setSaving]       = useState(false)

  const [showForm, setShowForm]   = useState(false)
  const [form, setForm]           = useState(EMPTY_FORM())
  const [editId, setEditId]       = useState(null)

  const defaultRange = currentMonthRange()
  const [filterStart,   setFilterStart]   = useState(defaultRange.start)
  const [filterEnd,     setFilterEnd]     = useState(defaultRange.end)
  const [filterType,    setFilterType]    = useState('')
  const [filterCustomer, setFilterCustomer] = useState('')
  // applied values (only change when Apply is clicked)
  const [appliedStart,   setAppliedStart]   = useState(defaultRange.start)
  const [appliedEnd,     setAppliedEnd]     = useState(defaultRange.end)
  const [appliedType,    setAppliedType]    = useState('')
  const [appliedCustomer, setAppliedCustomer] = useState('')

  useEffect(() => {
    Promise.all([
      fetch('/api/customers').then(r => r.json()),
      fetch('/api/jobs').then(r => r.json()),
    ]).then(([cData, jData]) => {
      setCustomers(Array.isArray(cData) ? cData : [])
      setJobs(Array.isArray(jData) ? jData : [])
    })
    loadData(defaultRange.start, defaultRange.end, '', '')
  }, [])

  async function loadData(start, end, type, customerId) {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (start)      params.set('start', start)
      if (end)        params.set('end', end)
      if (type)       params.set('type', type)
      if (customerId) params.set('customer_id', customerId)

      const sumParams = new URLSearchParams()
      if (start) sumParams.set('start', start)
      if (end)   sumParams.set('end', end)

      const [tripData, sumData] = await Promise.all([
        fetch(`/api/trips?${params}`).then(r => r.json()),
        fetch(`/api/trips/summary?${sumParams}`).then(r => r.json()),
      ])
      setTrips(Array.isArray(tripData) ? tripData : [])
      setSummary(sumData || null)
    } finally {
      setLoading(false)
    }
  }

  function applyFilters() {
    setAppliedStart(filterStart)
    setAppliedEnd(filterEnd)
    setAppliedType(filterType)
    setAppliedCustomer(filterCustomer)
    loadData(filterStart, filterEnd, filterType, filterCustomer)
  }

  async function handleSave() {
    if (!form.destination.trim() || !form.miles) return
    setSaving(true)
    try {
      const url    = editId ? `/api/trips/${editId}` : '/api/trips'
      const method = editId ? 'PUT' : 'POST'
      const { _milesAutoTime, ...formData } = form
      const r = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          miles:              parseFloat(form.miles) || 0,
          drive_time_minutes: form.drive_time_minutes ? parseInt(form.drive_time_minutes) : null,
          customer_id:        form.customer_id ? parseInt(form.customer_id) : null,
          job_id:             form.job_id ? parseInt(form.job_id) : null,
        }),
      })
      if (!r.ok) throw new Error((await r.json()).error || 'Failed to save')
      setForm(EMPTY_FORM())
      setEditId(null)
      setShowForm(false)
      loadData(appliedStart, appliedEnd, appliedType, appliedCustomer)
    } catch (e) {
      alert('Error saving trip: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id) {
    if (!confirm('Delete this trip?')) return
    await fetch(`/api/trips/${id}`, { method: 'DELETE' })
    loadData(appliedStart, appliedEnd, appliedType, appliedCustomer)
  }

  function startEdit(trip) {
    setForm({
      trip_date:          trip.trip_date || new Date().toISOString().slice(0, 10),
      trip_type:          trip.trip_type || 'job_site',
      destination:        trip.destination || '',
      customer_id:        trip.customer_id ? String(trip.customer_id) : '',
      job_id:             trip.job_id ? String(trip.job_id) : '',
      miles:              trip.miles != null ? String(trip.miles) : '',
      drive_time_minutes: trip.drive_time_minutes != null ? String(trip.drive_time_minutes) : '',
      notes:              trip.notes || '',
    })
    setEditId(trip.id)
    setShowForm(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function cancelForm() {
    setForm(EMPTY_FORM())
    setEditId(null)
    setShowForm(false)
  }

  // jobs filtered to selected customer in form
  const formJobs = form.customer_id
    ? jobs.filter(j => String(j.customer_id) === String(form.customer_id))
    : jobs

  // bottom totals for filtered list
  const totalMiles    = trips.reduce((s, t) => s + (t.miles || 0), 0)
  const totalMinutes  = trips.reduce((s, t) => s + (t.drive_time_minutes || 0), 0)
  const totalDeduct   = totalMiles * IRS_RATE
  const unplannedCount = trips.filter(t => t.trip_type === 'supply_unplanned').length

  return (
    <div className="max-w-5xl mx-auto space-y-5 pb-10">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Trip Log</h1>
        <button
          onClick={() => { if (showForm && !editId) { cancelForm() } else { setForm(EMPTY_FORM()); setEditId(null); setShowForm(true) } }}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 font-medium"
        >
          {showForm && !editId ? 'Cancel' : '+ Log a Trip'}
        </button>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <div className="text-xl font-bold text-gray-900">
            {fmtMiles(summary?.total_miles)}
          </div>
          <div className="text-xs text-gray-500 mt-1">Miles This Month</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <div className="text-xl font-bold text-gray-700">
            {summary?.total_drive_time_minutes != null
              ? fmtTime(summary.total_drive_time_minutes)
              : '—'}
          </div>
          <div className="text-xs text-gray-500 mt-1">Drive Time</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <div className="text-xl font-bold text-green-600">
            {fmt((summary?.total_miles || 0) * IRS_RATE)}
          </div>
          <div className="text-xs text-gray-500 mt-1">IRS Deduction Est.</div>
        </div>
        <div className={`rounded-xl border p-4 text-center ${
          (summary?.unplanned_count || 0) > 0
            ? 'bg-amber-50 border-amber-200'
            : 'bg-white border-gray-200'
        }`}>
          <div className={`text-xl font-bold ${
            (summary?.unplanned_count || 0) > 0 ? 'text-amber-600' : 'text-gray-400'
          }`}>
            {summary?.unplanned_count ?? 0}
          </div>
          <div className={`text-xs mt-1 ${
            (summary?.unplanned_count || 0) > 0 ? 'text-amber-600' : 'text-gray-500'
          }`}>
            Unplanned Trips
            {(summary?.unplanned_count || 0) > 0 && ' (wasted runs)'}
          </div>
        </div>
      </div>

      {/* Add / Edit Form */}
      {showForm && (
        <div className="bg-white rounded-xl border border-blue-200 p-5">
          <h2 className="text-sm font-semibold text-gray-700 mb-4">
            {editId ? 'Edit Trip' : 'Log a New Trip'}
          </h2>
          <div className="grid grid-cols-2 gap-4">

            <div>
              <label className="block text-xs text-gray-500 mb-1">Date</label>
              <input
                type="date"
                value={form.trip_date}
                onChange={e => setForm(f => ({ ...f, trip_date: e.target.value }))}
                className={INPUT}
              />
            </div>

            <div>
              <label className="block text-xs text-gray-500 mb-1">Trip Type *</label>
              <select
                value={form.trip_type}
                onChange={e => setForm(f => ({
                  ...f,
                  trip_type: e.target.value,
                  customer_id: e.target.value !== 'job_site' ? '' : f.customer_id,
                  job_id: e.target.value !== 'job_site' ? '' : f.job_id,
                }))}
                className={INPUT}
              >
                {TRIP_TYPES.map(t => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              {form.trip_type === 'supply_unplanned' && (
                <p className="text-xs text-amber-600 mt-1">
                  Unplanned runs cost extra time and fuel — better planning can reduce these.
                </p>
              )}
            </div>

            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Destination *</label>
              <input
                type="text"
                value={form.destination}
                onChange={e => setForm(f => ({ ...f, destination: e.target.value }))}
                placeholder="e.g. Ace Hardware, 123 Main St, Lowe's..."
                className={INPUT}
                autoFocus
              />
            </div>

            {/* Customer — only for job_site */}
            {form.trip_type === 'job_site' && (
              <div>
                <label className="block text-xs text-gray-500 mb-1">Customer (optional)</label>
                <select
                  value={form.customer_id}
                  onChange={e => setForm(f => ({ ...f, customer_id: e.target.value, job_id: '' }))}
                  className={INPUT}
                >
                  <option value="">-- select customer --</option>
                  {customers.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Job — only for job_site and when customer selected (or all jobs if no customer) */}
            {form.trip_type === 'job_site' && (
              <div>
                <label className="block text-xs text-gray-500 mb-1">Job (optional)</label>
                <select
                  value={form.job_id}
                  onChange={e => setForm(f => ({ ...f, job_id: e.target.value }))}
                  className={INPUT}
                >
                  <option value="">-- select job --</option>
                  {formJobs.map(j => (
                    <option key={j.id} value={j.id}>
                      {j.customer ? `${j.customer} — ` : ''}{j.invoice_id || `#${j.id}`}{j.start_date ? ` (${j.start_date})` : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div>
              <label className="block text-xs text-gray-500 mb-1">Miles (one-way) *</label>
              <input
                type="number"
                step="0.1"
                min="0"
                value={form.miles}
                onChange={e => {
                  const mi = parseFloat(e.target.value) || 0
                  const autoMins = mi > 0 ? String(Math.round((mi / 30) * 60 / 5) * 5) : ''
                  setForm(f => ({
                    ...f,
                    miles: e.target.value,
                    drive_time_minutes: f.drive_time_minutes === '' || f._milesAutoTime ? autoMins : f.drive_time_minutes,
                    _milesAutoTime: true,
                  }))
                }}
                placeholder="0.0"
                className={INPUT}
              />
              {form.miles && (
                <p className="text-xs text-green-700 mt-1">
                  Tax deduction: {fmt(parseFloat(form.miles || 0) * IRS_RATE)} at ${IRS_RATE}/mi
                </p>
              )}
            </div>

            <div>
              <label className="block text-xs text-gray-500 mb-1">Drive Time (minutes)</label>
              <input
                type="number"
                step="5"
                min="0"
                value={form.drive_time_minutes}
                onChange={e => setForm(f => ({ ...f, drive_time_minutes: e.target.value, _milesAutoTime: false }))}
                placeholder="auto-estimated"
                className={INPUT}
              />
              {form._milesAutoTime && form.drive_time_minutes && (
                <p className="text-xs text-gray-400 mt-1">Estimated at 30 mph avg — tap to adjust</p>
              )}
            </div>

            <div className="col-span-2">
              <label className="block text-xs text-gray-500 mb-1">Notes (optional)</label>
              <textarea
                rows={2}
                value={form.notes}
                onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                placeholder="What did you pick up? Any details..."
                className={`${INPUT} resize-none`}
              />
            </div>
          </div>

          <div className="flex gap-3 mt-4">
            <button
              onClick={handleSave}
              disabled={saving || !form.destination.trim() || !form.miles}
              className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50 font-medium"
            >
              {saving ? 'Saving...' : editId ? 'Save Changes' : 'Save Trip'}
            </button>
            <button
              onClick={cancelForm}
              className="text-gray-600 px-4 py-2 rounded-lg text-sm hover:bg-gray-100"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Filter bar */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-500 mb-1">From</label>
            <input
              type="date"
              value={filterStart}
              onChange={e => setFilterStart(e.target.value)}
              className={INPUT}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">To</label>
            <input
              type="date"
              value={filterEnd}
              onChange={e => setFilterEnd(e.target.value)}
              className={INPUT}
            />
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Trip Type</label>
            <select
              value={filterType}
              onChange={e => setFilterType(e.target.value)}
              className={INPUT}
            >
              <option value="">All Types</option>
              {TRIP_TYPES.map(t => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">Customer</label>
            <select
              value={filterCustomer}
              onChange={e => setFilterCustomer(e.target.value)}
              className={INPUT}
            >
              <option value="">All Customers</option>
              {customers.map(c => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={applyFilters}
              className="w-full bg-gray-800 text-white px-4 py-2 rounded-lg text-sm hover:bg-gray-900 font-medium"
            >
              Apply
            </button>
          </div>
        </div>
      </div>

      {/* Trip list */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Trips</h3>
          <div className="text-sm font-semibold text-gray-700">
            {trips.length} trip{trips.length !== 1 ? 's' : ''} &middot; {fmtMiles(totalMiles)}
          </div>
        </div>

        {loading && (
          <div className="p-6 text-center text-gray-400 text-sm">Loading...</div>
        )}

        {!loading && trips.length === 0 && (
          <div className="p-8 text-center text-gray-400 text-sm">
            No trips found for this period. Click "+ Log a Trip" to add one.
          </div>
        )}

        {/* Table header (md+) */}
        {!loading && trips.length > 0 && (
          <>
            <div className="hidden md:grid grid-cols-[90px_140px_1fr_140px_80px_70px_1fr_80px] gap-2 px-5 py-2 bg-gray-50 text-xs font-semibold text-gray-400 uppercase tracking-wide border-b border-gray-100">
              <div>Date</div>
              <div>Type</div>
              <div>Destination</div>
              <div>Customer</div>
              <div className="text-right">Miles</div>
              <div className="text-right">Time</div>
              <div>Notes</div>
              <div></div>
            </div>

            <div className="divide-y divide-gray-50">
              {trips.map(trip => {
                const typeInfo = tripTypeInfo(trip.trip_type)
                const isUnplanned = trip.trip_type === 'supply_unplanned'
                return (
                  <div
                    key={trip.id}
                    className={`px-5 py-3 hover:bg-gray-50 ${isUnplanned ? 'bg-amber-50/30' : ''}`}
                  >
                    {/* Mobile layout */}
                    <div className="md:hidden space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-sm font-medium text-gray-900">{trip.destination}</span>
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${typeInfo.color}`}>
                            {typeInfo.short}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <button
                            onClick={() => startEdit(trip)}
                            className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDelete(trip.id)}
                            className="text-gray-300 hover:text-red-500 text-lg leading-none"
                          >
                            &times;
                          </button>
                        </div>
                      </div>
                      <div className="text-xs text-gray-400 flex flex-wrap gap-2">
                        <span>{trip.trip_date}</span>
                        {trip.customer_name && <><span>&middot;</span><span>{trip.customer_name}</span></>}
                        <span>&middot;</span><span className="font-medium text-gray-600">{fmtMiles(trip.miles)}</span>
                        {trip.drive_time_minutes && <><span>&middot;</span><span>{fmtTime(trip.drive_time_minutes)}</span></>}
                        {trip.notes && <><span>&middot;</span><span className="italic">{trip.notes}</span></>}
                      </div>
                    </div>

                    {/* Desktop layout */}
                    <div className="hidden md:grid grid-cols-[90px_140px_1fr_140px_80px_70px_1fr_80px] gap-2 items-center">
                      <div className="text-xs text-gray-500">{trip.trip_date}</div>
                      <div>
                        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${typeInfo.color}`}>
                          {typeInfo.short}
                        </span>
                      </div>
                      <div className="text-sm text-gray-800 truncate" title={trip.destination}>
                        {trip.destination}
                      </div>
                      <div className="text-xs text-gray-500 truncate">
                        {trip.customer_name || '—'}
                      </div>
                      <div className="text-sm font-semibold text-gray-800 tabular-nums text-right">
                        {fmtMiles(trip.miles)}
                      </div>
                      <div className="text-xs text-gray-500 text-right">
                        {trip.drive_time_minutes ? fmtTime(trip.drive_time_minutes) : '—'}
                      </div>
                      <div className="text-xs text-gray-400 italic truncate" title={trip.notes || ''}>
                        {trip.notes || ''}
                      </div>
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => startEdit(trip)}
                          className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(trip.id)}
                          className="text-gray-300 hover:text-red-500 text-lg leading-none"
                        >
                          &times;
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Bottom totals row */}
            <div className="px-5 py-3 border-t border-gray-100 bg-gray-50 flex flex-wrap items-center gap-6 text-sm">
              <div>
                <span className="text-gray-500 text-xs">Total Miles</span>
                <div className="font-bold text-gray-800">{fmtMiles(totalMiles)}</div>
              </div>
              <div>
                <span className="text-gray-500 text-xs">Total Drive Time</span>
                <div className="font-bold text-gray-800">{fmtTime(totalMinutes)}</div>
              </div>
              <div>
                <span className="text-gray-500 text-xs">IRS Deduction ({trips.length} trips)</span>
                <div className="font-bold text-green-700">{fmt(totalDeduct)}</div>
              </div>
              {unplannedCount > 0 && (
                <div>
                  <span className="text-amber-600 text-xs">Unplanned Runs</span>
                  <div className="font-bold text-amber-600">{unplannedCount}</div>
                </div>
              )}
              <div className="ml-auto text-xs text-gray-400">
                Rate: ${IRS_RATE}/mi (IRS 2026)
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
