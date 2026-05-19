import { useState, useEffect } from 'react'

function calcHours(arrive, depart) {
  if (!arrive || !depart) return ''
  const [ah, am] = arrive.split(':').map(Number)
  const [dh, dm] = depart.split(':').map(Number)
  const mins = (dh * 60 + dm) - (ah * 60 + am)
  if (mins <= 0) return ''
  return Math.round(mins / 60 * 100) / 100
}

const BLANK_FORM = {
  customer_id: '',
  job_id: '',
  entry_date: new Date().toISOString().slice(0, 10),
  arrive_time: '',
  depart_time: '',
  hours: '',
  description: '',
  cost_code: '',
}

export default function TimeEntry() {
  const [entries, setEntries] = useState([])
  const [customers, setCustomers] = useState([])
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [filterCustomer, setFilterCustomer] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [deletingId, setDeletingId] = useState(null)
  const [form, setForm] = useState(BLANK_FORM)

  useEffect(() => {
    Promise.all([
      fetch('/api/time-entries').then(r => r.json()),
      fetch('/api/customers').then(r => r.json()),
      fetch('/api/jobs').then(r => r.json()),
    ]).then(([timeData, custData, jobData]) => {
      setEntries(timeData.time_entries || [])
      setCustomers((Array.isArray(custData) ? custData : []).filter(c => !c.name.startsWith('_')))
      setJobs(Array.isArray(jobData) ? jobData : [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const customerJobs = jobs.filter(j => form.customer_id && String(j.customer_id) === form.customer_id)

  function handleCustomerChange(e) {
    setForm(f => ({ ...f, customer_id: e.target.value, job_id: '' }))
  }

  async function handleSave() {
    const hours = form.hours || calcHours(form.arrive_time, form.depart_time)
    if (!form.customer_id || !form.entry_date || !hours) {
      alert('Customer, date, and either arrive/depart times or hours are required.')
      return
    }
    setSaving(true)
    try {
      const r = await fetch('/api/time-entries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: parseInt(form.customer_id),
          job_id: form.job_id ? parseInt(form.job_id) : null,
          entry_date: form.entry_date,
          arrive_time: form.arrive_time || null,
          depart_time: form.depart_time || null,
          hours: parseFloat(hours),
          description: form.description,
          cost_code: form.cost_code,
        })
      })
      const newEntry = await r.json()
      setEntries(prev => [newEntry, ...prev])
      setForm(f => ({
        ...f,
        arrive_time: '',
        depart_time: '',
        hours: '',
        description: '',
        cost_code: '',
        job_id: '',
      }))
      setShowForm(false)
    } catch {
      alert('Error saving time entry')
    } finally {
      setSaving(false)
    }
  }

  function handleEdit(entry) {
    setEditingId(entry.id)
    setForm({
      customer_id: String(entry.customer_id || ''),
      job_id: String(entry.job_id || ''),
      entry_date: entry.entry_date || new Date().toISOString().slice(0, 10),
      arrive_time: entry.arrive_time || entry.start_time || '',
      depart_time: entry.depart_time || entry.end_time || '',
      hours: String(entry.hours || ''),
      description: entry.description || '',
      cost_code: entry.cost_code || '',
    })
    setShowForm(true)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function handleUpdate() {
    const hours = form.hours || calcHours(form.arrive_time, form.depart_time)
    if (!form.entry_date || !hours) {
      alert('Date and hours are required.')
      return
    }
    setSaving(true)
    try {
      const r = await fetch(`/api/time-entries/${editingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: form.customer_id ? parseInt(form.customer_id) : undefined,
          job_id: form.job_id ? parseInt(form.job_id) : null,
          entry_date: form.entry_date,
          arrive_time: form.arrive_time || null,
          depart_time: form.depart_time || null,
          hours: parseFloat(hours),
          description: form.description,
          cost_code: form.cost_code,
        })
      })
      const updated = await r.json()
      setEntries(prev => prev.map(e => e.id === editingId ? { ...e, ...updated } : e))
      setEditingId(null)
      setForm(BLANK_FORM)
      setShowForm(false)
    } catch {
      alert('Error updating time entry')
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id) {
    if (!window.confirm('Delete this time entry? This cannot be undone.')) return
    setDeletingId(id)
    try {
      await fetch(`/api/time-entries/${id}`, { method: 'DELETE' })
      setEntries(prev => prev.filter(e => e.id !== id))
    } catch {
      alert('Error deleting time entry')
    } finally {
      setDeletingId(null)
    }
  }

  const filtered = entries.filter(e =>
    !filterCustomer || String(e.customer_id) === filterCustomer
  )

  const totalHours = filtered.reduce((s, e) => s + (e.hours || 0), 0)

  const byDate = filtered.reduce((acc, e) => {
    const d = e.entry_date || 'Unknown'
    if (!acc[d]) acc[d] = []
    acc[d].push(e)
    return acc
  }, {})
  const sortedDates = Object.keys(byDate).sort((a, b) => b.localeCompare(a))

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-500">Loading time entries...</div>
  )

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Time Tracking</h1>
        <button
          onClick={() => {
            if (showForm) { setShowForm(false); setEditingId(null); setForm(BLANK_FORM) }
            else setShowForm(true)
          }}
          className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700"
        >
          {showForm ? 'Cancel' : '+ Log Time'}
        </button>
      </div>

      {showForm && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <h2 className="text-base font-semibold text-gray-900 mb-4">{editingId ? 'Edit Time Entry' : 'Log Time Entry'}</h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2 md:col-span-1">
              <label className="block text-xs font-medium text-gray-700 mb-1">Customer *</label>
              <select
                value={form.customer_id}
                onChange={handleCustomerChange}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select customer...</option>
                {customers.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Date *</label>
              <input
                type="date"
                value={form.entry_date}
                onChange={e => setForm(f => ({ ...f, entry_date: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-700 mb-1">Job (optional)</label>
              <select
                value={form.job_id}
                onChange={e => setForm(f => ({ ...f, job_id: e.target.value }))}
                disabled={!form.customer_id}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
              >
                <option value="">{form.customer_id ? 'No specific job' : 'Select a customer first'}</option>
                {customerJobs.map(j => (
                  <option key={j.id} value={j.id}>
                    {j.invoice_id || `#${j.id}`} — {j.start_date || 'no date'}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Arrive</label>
              <input
                type="time"
                value={form.arrive_time}
                onChange={e => setForm(f => ({ ...f, arrive_time: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Depart</label>
              <input
                type="time"
                value={form.depart_time}
                onChange={e => setForm(f => ({ ...f, depart_time: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {calcHours(form.arrive_time, form.depart_time) && (
              <div className="col-span-2 text-sm text-green-700 font-medium bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                Duration: {calcHours(form.arrive_time, form.depart_time)}h
              </div>
            )}
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Hours (if not using times)</label>
              <input
                type="number"
                step="0.25"
                min="0"
                value={form.hours}
                onChange={e => setForm(f => ({ ...f, hours: e.target.value }))}
                placeholder="e.g. 2.5"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Cost Code / Label</label>
              <input
                type="text"
                value={form.cost_code}
                onChange={e => setForm(f => ({ ...f, cost_code: e.target.value }))}
                placeholder="e.g. fence repair, supply run"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="col-span-2">
              <label className="block text-xs font-medium text-gray-700 mb-1">Description</label>
              <textarea
                rows={2}
                value={form.description}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
                placeholder="What work was done?"
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
          <div className="flex gap-3 mt-4">
            <button
              onClick={editingId ? handleUpdate : handleSave}
              disabled={saving}
              className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {saving ? 'Saving...' : editingId ? 'Save Changes' : 'Save Entry'}
            </button>
            <button
              onClick={() => { setShowForm(false); setEditingId(null); setForm(BLANK_FORM) }}
              className="text-gray-600 px-4 py-2 rounded-lg text-sm hover:bg-gray-100"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center gap-4 bg-white rounded-xl border border-gray-200 px-5 py-3">
        <div className="flex-1">
          <select
            value={filterCustomer}
            onChange={e => setFilterCustomer(e.target.value)}
            className="border border-gray-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="">All customers</option>
            {customers.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="text-sm text-gray-600">
          <span className="font-semibold text-gray-900">{totalHours.toFixed(1)}h</span> total
          {' · '}
          <span className="font-semibold text-gray-900">{filtered.length}</span> entries
        </div>
      </div>

      <div className="space-y-4">
        {sortedDates.map(date => (
          <div key={date} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="px-5 py-2.5 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
              <span className="text-sm font-semibold text-gray-700">{formatDate(date)}</span>
              <span className="text-xs text-gray-500">
                {byDate[date].reduce((s, e) => s + (e.hours || 0), 0).toFixed(1)}h
              </span>
            </div>
            <div className="divide-y divide-gray-50">
              {byDate[date].map(entry => (
                <div key={entry.id} className="px-5 py-3 flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900">{entry.customer_name || '—'}</div>
                    {entry.invoice_id && (
                      <div className="text-xs text-blue-600 mt-0.5">{entry.invoice_id}</div>
                    )}
                    {entry.start_time && entry.end_time && (
                      <div className="text-xs text-gray-400">{entry.start_time} &ndash; {entry.end_time}</div>
                    )}
                    {entry.description && (
                      <div className="text-xs text-gray-500 mt-0.5 truncate">{entry.description}</div>
                    )}
                    {entry.cost_code && (
                      <span className="inline-block mt-1 text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                        {entry.cost_code}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 ml-4">
                    <div className="text-sm font-semibold text-gray-900 tabular-nums">
                      {(entry.hours || 0).toFixed(2)}h
                    </div>
                    <button
                      onClick={() => handleEdit(entry)}
                      title="Edit"
                      className="p-1 text-gray-400 hover:text-blue-600 rounded transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                    </button>
                    <button
                      onClick={() => handleDelete(entry.id)}
                      disabled={deletingId === entry.id}
                      title="Delete"
                      className="p-1 text-gray-400 hover:text-red-500 rounded transition-colors disabled:opacity-40"
                    >
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
        {sortedDates.length === 0 && (
          <div className="bg-white rounded-xl border border-gray-200 px-5 py-16 text-center text-gray-400">
            <div className="text-3xl mb-3">&#9201;</div>
            <div className="text-lg font-medium mb-1">No time entries yet</div>
            <div className="text-sm">Click &quot;Log Time&quot; to add your first entry</div>
          </div>
        )}
      </div>
    </div>
  )
}

function formatDate(dateStr) {
  if (!dateStr || dateStr === 'Unknown') return 'Unknown Date'
  try {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'long', day: 'numeric', year: 'numeric' })
  } catch {
    return dateStr
  }
}
