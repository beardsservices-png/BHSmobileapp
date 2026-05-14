import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'

function formatPhone(raw) {
  const digits = (raw || '').replace(/\D/g, '').slice(0, 10)
  if (digits.length < 4) return digits
  if (digits.length < 7) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`
}

export default function Customers() {
  const [customers, setCustomers] = useState([])
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ name: '', address: '', phone: '', email: '', notes: '', cya_notes: '' })
  const [saving, setSaving] = useState(false)
  const [calcMileage, setCalcMileage] = useState(false)
  const [mobileView, setMobileView] = useState('list') // 'list' | 'detail'

  useEffect(() => {
    fetch('/api/customers')
      .then(r => r.json())
      .then(data => { setCustomers(Array.isArray(data) ? data : (data.customers || [])); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selected) return
    setDetail(null)
    fetch(`/api/customers/${selected.id}`)
      .then(r => r.json())
      .then(setDetail)
      .catch(() => {})
  }, [selected])

  const filtered = customers.filter(c =>
    !search || c.name.toLowerCase().includes(search.toLowerCase())
  ).filter(c => !c.name.startsWith('_'))

  const fmt = (n) => `$${(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`

  async function pickFromContacts() {
    if (!navigator.contacts?.select) {
      alert('Contacts picker is not supported on this browser. Type the details manually.')
      return
    }
    try {
      const supported = await navigator.contacts.getProperties()
      const props = ['name', 'tel', 'address', 'email'].filter(p => supported.includes(p))
      const results = await navigator.contacts.select(props, { multiple: false })
      if (!results?.length) return
      const c = results[0]
      const name = c.name?.[0] || ''
      const phone = c.tel?.[0] || ''
      const email = c.email?.[0] || ''
      let address = ''
      if (c.address?.[0]) {
        const a = c.address[0]
        address = [a.streetAddress, a.city, a.state, a.postalCode].filter(Boolean).join(', ')
      }
      setForm(f => ({
        ...f,
        name: name || f.name,
        phone: phone ? formatPhone(phone) : f.phone,
        address: address || f.address,
        email: email || f.email,
      }))
    } catch (err) {
      if (err.name !== 'AbortError') alert('Could not open contacts: ' + err.message)
    }
  }

  async function handleSave() {
    if (!form.name.trim()) return
    setSaving(true)
    try {
      const r = await fetch('/api/customers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      })
      if (!r.ok) { const e = await r.json(); throw new Error(e.error || 'Failed') }
      const newC = await r.json()
      // Reload full list so totals are included
      const listR = await fetch('/api/customers')
      const listData = await listR.json()
      setCustomers(Array.isArray(listData) ? listData : (listData.customers || []))
      setForm({ name: '', address: '', phone: '', email: '', notes: '', cya_notes: '' })
      setShowForm(false)
      setSelected({ id: newC.id, name: newC.name })
    } catch (e) {
      alert('Error saving customer: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleCalcMileage(customerId) {
    setCalcMileage(true)
    try {
      const r = await fetch(`/api/customers/${customerId}/calculate-mileage`, { method: 'POST' })
      const data = await r.json()
      if (data.error) { alert('Mileage error: ' + data.error); return }
      setDetail(prev => ({ ...prev, mileage_from_home: data.mileage_from_home }))
    } catch {
      alert('Could not calculate mileage')
    } finally {
      setCalcMileage(false)
    }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-500">Loading customers...</div>
  )

  return (
    <div className="flex h-full gap-0 -m-6">
      {/* Left panel - customer list (always visible on md+, hidden on mobile when detail shown) */}
      <div className={`${mobileView === 'detail' ? 'hidden' : 'flex'} md:flex w-full md:w-72 bg-white border-r border-gray-200 flex-col flex-shrink-0`}>
        <div className="p-4 border-b border-gray-100">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-lg font-bold text-gray-900">Customers</h1>
            <button
              onClick={() => { setShowForm(true); setSelected(null); setMobileView('detail') }}
              className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700"
            >
              + New
            </button>
          </div>
          <input
            type="text"
            placeholder="Search customers..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
        <div className="overflow-y-auto flex-1">
          {filtered.map(c => (
            <button
              key={c.id}
              onClick={() => { setSelected(c); setShowForm(false); setMobileView('detail') }}
              className={`w-full text-left px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition-colors ${selected?.id === c.id ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''}`}
            >
              <div className="font-medium text-gray-900 text-sm">{c.name}</div>
              <div className="text-xs text-gray-500 mt-0.5 flex gap-2">
                <span>{c.job_count || 0} jobs</span>
                {c.last_job_date && <span className="text-gray-400">{c.last_job_date}</span>}
              </div>
              {c.cya_notes && (
                <div className="text-xs text-amber-700 mt-0.5 truncate">
                  {c.cya_notes.slice(0, 60)}{c.cya_notes.length > 60 ? '...' : ''}
                </div>
              )}
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-gray-400 text-sm">No customers found</div>
          )}
        </div>
        <div className="p-3 border-t border-gray-100 text-xs text-gray-400 text-center">
          {filtered.length} customers
        </div>
      </div>

      {/* Right panel - detail (always visible on md+, hidden on mobile when list shown) */}
      <div className={`${mobileView === 'list' ? 'hidden' : 'flex'} md:flex flex-col flex-1 overflow-y-auto bg-gray-50`}>
        {/* Mobile back button */}
        <div className="md:hidden flex items-center gap-2 px-4 py-3 bg-white border-b border-gray-200">
          <button
            onClick={() => { setMobileView('list'); setShowForm(false) }}
            className="flex items-center gap-1 text-sm text-blue-600 font-medium"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Customers
          </button>
          {selected && <span className="text-sm text-gray-500 truncate">/ {selected.name}</span>}
        </div>
        <div className="flex-1 overflow-y-auto p-4 md:p-6">
        {showForm && (
          <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">New Customer</h2>
              <button
                onClick={pickFromContacts}
                className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800 border border-blue-200 hover:bg-blue-50 px-3 py-1.5 rounded-lg transition-colors"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
                Pick from Contacts
              </button>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-700 mb-1">Name *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Customer name"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-700 mb-1">Address</label>
                <input
                  type="text"
                  value={form.address}
                  onChange={e => setForm(f => ({ ...f, address: e.target.value }))}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Street address"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Phone</label>
                <input
                  type="text"
                  value={form.phone}
                  onChange={e => setForm(f => ({ ...f, phone: formatPhone(e.target.value) }))}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="(870) 555-1234"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-700 mb-1">Email</label>
                <input
                  type="email"
                  value={form.email}
                  onChange={e => setForm(f => ({ ...f, email: e.target.value }))}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="email@example.com"
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-700 mb-1">Notes</label>
                <textarea
                  value={form.notes}
                  onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                  rows={2}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  placeholder="Any notes..."
                />
              </div>
              <div className="col-span-2">
                <label className="block text-xs font-medium text-gray-700 mb-1">
                  Notes
                  <span className="ml-1 font-normal text-gray-400">— gate codes, pets, access instructions, job preferences</span>
                </label>
                <textarea
                  value={form.cya_notes}
                  onChange={e => setForm(f => ({ ...f, cya_notes: e.target.value }))}
                  rows={3}
                  className="w-full border border-amber-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 bg-amber-50"
                  placeholder="Dog in backyard, gate code is 1234, prefers text not call..."
                />
              </div>
            </div>
            <div className="flex gap-3 mt-4">
              <button
                onClick={handleSave}
                disabled={saving}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Customer'}
              </button>
              <button
                onClick={() => setShowForm(false)}
                className="text-gray-600 px-4 py-2 rounded-lg text-sm hover:bg-gray-100"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {!selected && !showForm && (
          <div className="flex flex-col items-center justify-center h-64 text-gray-400">
            <div className="text-4xl mb-3">👤</div>
            <div className="text-lg font-medium">Select a customer</div>
            <div className="text-sm">or create a new one</div>
          </div>
        )}

        {selected && (
          <CustomerDetail
            customer={selected}
            detail={detail}
            fmt={fmt}
            onCalcMileage={() => handleCalcMileage(selected.id)}
            calcMileage={calcMileage}
            onDetailChange={setDetail}
          />
        )}
        </div>
      </div>
    </div>
  )
}

function CustomerDetail({ customer, detail, fmt, onCalcMileage, calcMileage, onDetailChange }) {
  if (!detail) return (
    <div className="flex items-center justify-center h-32 text-gray-400">Loading...</div>
  )

  const [saving, setSaving] = useState(false)
  const [cyaNotes, setCyaNotes] = useState(detail.cya_notes || '')

  async function handleSaveCya() {
    setSaving(true)
    try {
      await fetch(`/api/customers/${customer.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cya_notes: cyaNotes }),
      })
      if (onDetailChange) onDetailChange({ ...detail, cya_notes: cyaNotes })
    } catch {
      alert('Error saving notes')
    } finally {
      setSaving(false)
    }
  }

  const cyaChanged = cyaNotes !== (detail.cya_notes || '')

  const totalRevenue = detail.jobs?.reduce((s, j) => s + (j.total_amount || 0), 0) || 0
  const totalHours = detail.time_entries?.reduce((s, t) => s + (t.hours || 0), 0) || 0
  const avgRate = totalHours > 0 ? totalRevenue / totalHours : 0

  // Compute total miles driven (round-trip * number of jobs as proxy)
  const jobCount = detail.jobs?.length || 0
  const totalMiles = detail.mileage_from_home != null ? Math.round(detail.mileage_from_home * 2 * jobCount) : null

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">{customer.name}</h2>
            {detail.address && <p className="text-gray-500 text-sm mt-1">{detail.address}</p>}
            <div className="flex gap-4 mt-2">
              {detail.phone && <a href={`tel:${detail.phone}`} className="text-sm text-blue-600">{detail.phone}</a>}
              {detail.email && <a href={`mailto:${detail.email}`} className="text-sm text-blue-600">{detail.email}</a>}
            </div>

            {/* Mileage — internal only */}
            <div className="mt-2 flex items-center gap-3 text-xs text-gray-400">
              {detail.mileage_from_home != null ? (
                <>
                  <span className="bg-gray-100 rounded px-2 py-0.5">
                    <span className="font-medium text-gray-600">{detail.mileage_from_home} mi</span> one-way from home
                  </span>
                  {totalMiles != null && (
                    <span className="bg-gray-100 rounded px-2 py-0.5">
                      ~{totalMiles} mi total driven (est.)
                    </span>
                  )}
                  <span className="italic text-gray-300">internal only</span>
                </>
              ) : (
                detail.address && (
                  <span className="text-gray-400 italic">Mileage not calculated</span>
                )
              )}
              {detail.address && (
                <button
                  onClick={onCalcMileage}
                  disabled={calcMileage}
                  className="text-blue-600 hover:text-blue-800 border border-blue-200 rounded px-2 py-0.5 hover:bg-blue-50 disabled:opacity-50"
                >
                  {calcMileage ? 'Calculating...' : detail.mileage_from_home ? 'Recalculate' : 'Calculate Mileage'}
                </button>
              )}
            </div>
          </div>
          <Link
            to={`/estimate?customer=${customer.id}`}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700"
          >
            New Estimate
          </Link>
        </div>
        {detail.notes && <p className="mt-3 text-sm text-gray-600 bg-gray-50 rounded-lg p-3">{detail.notes}</p>}

        {/* Notes */}
        <div className="mt-4 border border-amber-300 rounded-xl bg-amber-50 p-4">
          <div className="mb-2">
            <span className="text-sm font-semibold text-amber-900">Notes</span>
            <span className="ml-2 text-xs text-amber-700">gate codes, pets, access instructions, job preferences</span>
          </div>
          <textarea
            rows={4}
            value={cyaNotes}
            onChange={e => setCyaNotes(e.target.value)}
            placeholder="Dog in backyard, gate code is 1234, prefers text not call, gets upset if you're late..."
            className="w-full border border-amber-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 bg-amber-50 placeholder-amber-400 text-amber-900 resize-y"
          />
          {cyaChanged && (
            <button
              onClick={handleSaveCya}
              disabled={saving}
              className="mt-2 bg-amber-600 text-white px-4 py-1.5 rounded-lg text-sm hover:bg-amber-700 disabled:opacity-50 font-medium"
            >
              {saving ? 'Saving...' : 'Save Notes'}
            </button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">{fmt(totalRevenue)}</div>
          <div className="text-xs text-gray-500 mt-1">Total Revenue</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">{totalHours.toFixed(1)}h</div>
          <div className="text-xs text-gray-500 mt-1">Hours Worked</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <div className="text-2xl font-bold text-gray-900">{avgRate > 0 ? fmt(avgRate) : '—'}</div>
          <div className="text-xs text-gray-500 mt-1">Avg $/Hour</div>
        </div>
      </div>

      {/* Jobs */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="px-5 py-3 border-b border-gray-100 font-semibold text-gray-800 text-sm">
          Jobs ({detail.jobs?.length || 0})
        </div>
        <div className="divide-y divide-gray-50">
          {(detail.jobs || []).map(job => (
            <div key={job.id} className="px-5 py-3 flex items-center justify-between hover:bg-gray-50">
              <div>
                <div className="text-sm font-medium text-gray-900">{job.invoice_id || `Job #${job.id}`}</div>
                <div className="text-xs text-gray-500">{job.start_date}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-sm font-semibold">{fmt(job.total_amount)}</div>
                <Link
                  to={`/filing-cabinet?job=${job.id}`}
                  className="text-xs text-blue-600 hover:text-blue-800"
                >
                  View →
                </Link>
              </div>
            </div>
          ))}
          {(!detail.jobs || detail.jobs.length === 0) && (
            <div className="px-5 py-6 text-center text-gray-400 text-sm">No jobs yet</div>
          )}
        </div>
      </div>

      {/* Recent Time Entries */}
      {detail.time_entries?.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200">
          <div className="px-5 py-3 border-b border-gray-100 font-semibold text-gray-800 text-sm">
            Recent Time Entries
          </div>
          <div className="divide-y divide-gray-50">
            {detail.time_entries.slice(0, 10).map(t => (
              <div key={t.id} className="px-5 py-3 flex items-center justify-between">
                <div>
                  <div className="text-sm text-gray-800">{t.description || 'No description'}</div>
                  <div className="text-xs text-gray-500">{t.entry_date}</div>
                </div>
                <div className="text-sm font-medium text-gray-700">{(t.hours || 0).toFixed(1)}h</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
