import { useState, useEffect, useCallback } from 'react'

const fmt = n => `$${(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const INPUT = 'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white'

const STATUS = {
  draft:     { label: 'Draft',     cls: 'bg-gray-100 text-gray-600' },
  submitted: { label: 'Submitted', cls: 'bg-yellow-100 text-yellow-700' },
  paid:      { label: 'Paid',      cls: 'bg-green-100 text-green-700' },
}

const EMPTY_LINE = () => ({
  _key: `${Date.now()}-${Math.random()}`,
  service_item_id: '',
  description: '',
  qty: 1,
  rate: '',
  assignment_type: 'business',
  job_ref: '',
  notes: '',
  is_complete: true,
})

export default function JazzyPay() {
  const [serviceItems, setServiceItems] = useState([])
  const [jobs, setJobs] = useState([])
  const [invoices, setInvoices] = useState([])
  const [loading, setLoading] = useState(true)

  // Builder state
  const [building, setBuilding] = useState(false)
  const [editingDraftId, setEditingDraftId] = useState(null)
  const [lines, setLines] = useState([])
  const [invoiceNotes, setInvoiceNotes] = useState('')
  const [addingLine, setAddingLine] = useState(false)
  const [lineForm, setLineForm] = useState(EMPTY_LINE())
  const [saving, setSaving] = useState(false)

  // Expanded invoice detail
  const [expandedId, setExpandedId] = useState(null)
  const [expandedDetail, setExpandedDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)

  // Service catalog editor
  const [showCatalog, setShowCatalog] = useState(false)
  const [editingItemId, setEditingItemId] = useState(null)
  const [editRate, setEditRate] = useState('')
  const [addingItem, setAddingItem] = useState(false)
  const [newItem, setNewItem] = useState({ name: '', default_rate: '', category: 'General' })

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [items, jobsData, invData] = await Promise.all([
        fetch('/api/jazzy/service-items').then(r => r.json()),
        fetch('/api/jobs').then(r => r.json()),
        fetch('/api/jazzy/invoices').then(r => r.json()),
      ])
      setServiceItems(Array.isArray(items) ? items : [])
      setJobs(Array.isArray(jobsData) ? jobsData : [])
      setInvoices(Array.isArray(invData) ? invData : [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadAll() }, [loadAll])

  // Group service items by category for display
  const itemsByCategory = serviceItems.reduce((acc, item) => {
    if (!acc[item.category]) acc[item.category] = []
    acc[item.category].push(item)
    return acc
  }, {})

  // When a catalog item is selected, auto-fill description + rate
  function handleServiceSelect(val) {
    if (!val || val === 'custom') {
      setLineForm(f => ({ ...f, service_item_id: val || '', description: '', rate: '' }))
      return
    }
    const item = serviceItems.find(s => s.id === parseInt(val))
    if (item) {
      setLineForm(f => ({
        ...f,
        service_item_id: val,
        description: item.name,
        rate: String(item.default_rate),
      }))
    }
  }

  function addLineToInvoice() {
    const desc = lineForm.description.trim()
    const qty = Math.max(1, parseInt(lineForm.qty) || 1)
    const rate = parseFloat(lineForm.rate) || 0
    if (!desc || !rate) return
    setLines(ls => [...ls, { ...lineForm, description: desc, qty, rate, line_total: qty * rate }])
    setLineForm(EMPTY_LINE())
    setAddingLine(false)
  }

  const grandTotal = lines.reduce((s, l) => s + l.line_total, 0)

  function startNewInvoice() {
    setBuilding(true)
    setEditingDraftId(null)
    setLines([])
    setInvoiceNotes('')
    setAddingLine(false)
    setLineForm(EMPTY_LINE())
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function startEditDraft(inv) {
    setExpandedId(null)
    setExpandedDetail(null)
    setEditingDraftId(inv.id)
    setInvoiceNotes(inv.notes || '')
    setBuilding(true)
    setAddingLine(false)
    setLineForm(EMPTY_LINE())
    // Load lines from expanded detail if available, else fetch
    const detail = expandedDetail?.id === inv.id ? expandedDetail : null
    if (detail) {
      setLines(detail.lines.map(l => ({ ...l, _key: `${l.id}-${Math.random()}` })))
    } else {
      fetch(`/api/jazzy/invoices/${inv.id}`).then(r => r.json()).then(d => {
        setLines((d.lines || []).map(l => ({ ...l, _key: `${l.id}-${Math.random()}` })))
      })
    }
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function saveInvoice(status) {
    if (lines.length === 0) { alert('Add at least one line item.'); return }
    setSaving(true)
    try {
      const payload = {
        notes: invoiceNotes,
        status,
        lines: lines.map(({ _key, line_total, ...l }) => ({
          ...l,
          service_item_id: l.service_item_id && l.service_item_id !== 'custom'
            ? parseInt(l.service_item_id) : null,
        })),
      }

      let res
      if (editingDraftId) {
        // Update existing draft (lines + notes), then optionally submit
        res = await fetch(`/api/jazzy/invoices/${editingDraftId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ notes: invoiceNotes, lines: payload.lines }),
        })
        if (!res.ok) throw new Error((await res.json()).error || 'Save failed')
        if (status === 'submitted') {
          const sub = await fetch(`/api/jazzy/invoices/${editingDraftId}/submit`, { method: 'POST' })
          if (!sub.ok) throw new Error((await sub.json()).error || 'Submit failed')
        }
      } else {
        res = await fetch('/api/jazzy/invoices', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        })
        if (!res.ok) throw new Error((await res.json()).error || 'Save failed')
      }

      setBuilding(false)
      setLines([])
      setInvoiceNotes('')
      setEditingDraftId(null)
      await loadAll()
    } catch (e) {
      alert('Error: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  async function deleteInvoice(inv) {
    if (!confirm(`Delete invoice ${inv.invoice_number}?`)) return
    const r = await fetch(`/api/jazzy/invoices/${inv.id}`, { method: 'DELETE' })
    if (r.ok) { setExpandedId(null); setExpandedDetail(null); await loadAll() }
    else alert((await r.json()).error || 'Delete failed')
  }

  async function markPaid(inv) {
    if (!confirm(`Mark ${inv.invoice_number} as paid (${fmt(inv.total_amount)})?`)) return
    const r = await fetch(`/api/jazzy/invoices/${inv.id}/mark-paid`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
    if (r.ok) {
      setExpandedDetail(null)
      await loadAll()
    } else {
      alert((await r.json()).error || 'Failed')
    }
  }

  async function toggleExpand(inv) {
    if (expandedId === inv.id) {
      setExpandedId(null)
      setExpandedDetail(null)
      return
    }
    setExpandedId(inv.id)
    setExpandedDetail(null)
    setLoadingDetail(true)
    try {
      const d = await fetch(`/api/jazzy/invoices/${inv.id}`).then(r => r.json())
      setExpandedDetail(d)
    } finally {
      setLoadingDetail(false)
    }
  }

  // Service catalog edits
  async function saveRate(itemId) {
    const rate = parseFloat(editRate)
    if (isNaN(rate) || rate < 0) return
    await fetch(`/api/jazzy/service-items/${itemId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ default_rate: rate }),
    })
    const updated = await fetch('/api/jazzy/service-items').then(r => r.json())
    setServiceItems(Array.isArray(updated) ? updated : [])
    setEditingItemId(null)
  }

  async function addServiceItem() {
    const name = newItem.name.trim()
    const rate = parseFloat(newItem.default_rate)
    if (!name || isNaN(rate)) return
    await fetch('/api/jazzy/service-items', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...newItem, name, default_rate: rate }),
    })
    const updated = await fetch('/api/jazzy/service-items').then(r => r.json())
    setServiceItems(Array.isArray(updated) ? updated : [])
    setNewItem({ name: '', default_rate: '', category: 'General' })
    setAddingItem(false)
  }

  // Stats
  const totalPaid = invoices.filter(i => i.status === 'paid').reduce((s, i) => s + i.total_amount, 0)
  const totalPending = invoices.filter(i => i.status === 'submitted').reduce((s, i) => s + i.total_amount, 0)
  const totalDraft = invoices.filter(i => i.status === 'draft').reduce((s, i) => s + i.total_amount, 0)

  const CATEGORIES = [...new Set(serviceItems.map(i => i.category)), 'General', 'Social Media', 'Lead Management', 'Job Conversion', 'Admin']
    .filter((v, i, a) => a.indexOf(v) === i)

  return (
    <div className="max-w-4xl mx-auto space-y-5 pb-10">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Jazzlyn Pay</h1>
          <p className="text-sm text-gray-500 mt-0.5">Submit work invoices to Brian</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowCatalog(v => !v)}
            className="border border-gray-200 text-gray-600 px-3 py-2 rounded-lg text-sm hover:bg-gray-50 font-medium"
          >
            {showCatalog ? 'Hide Rates' : 'Service Rates'}
          </button>
          {!building && (
            <button
              onClick={startNewInvoice}
              className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 font-semibold"
            >
              + New Invoice
            </button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <div className="text-xl font-bold text-green-700">{fmt(totalPaid)}</div>
          <div className="text-xs text-gray-500 mt-1">Total Paid</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <div className="text-xl font-bold text-yellow-600">{fmt(totalPending)}</div>
          <div className="text-xs text-gray-500 mt-1">Awaiting Payment</div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 text-center">
          <div className="text-xl font-bold text-gray-500">{fmt(totalDraft)}</div>
          <div className="text-xs text-gray-500 mt-1">Drafts</div>
        </div>
      </div>

      {/* Service Catalog */}
      {showCatalog && (
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-gray-700">Service Rate Catalog</h2>
            <button
              onClick={() => setAddingItem(v => !v)}
              className="text-xs text-blue-600 hover:text-blue-800 font-medium"
            >
              {addingItem ? 'Cancel' : '+ Add Item'}
            </button>
          </div>

          {addingItem && (
            <div className="mb-4 p-3 bg-blue-50 rounded-xl border border-blue-100 space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <div className="col-span-2">
                  <input
                    type="text"
                    value={newItem.name}
                    onChange={e => setNewItem(n => ({ ...n, name: e.target.value }))}
                    placeholder="Service name"
                    className={INPUT}
                    autoFocus
                  />
                </div>
                <select
                  value={newItem.category}
                  onChange={e => setNewItem(n => ({ ...n, category: e.target.value }))}
                  className={INPUT}
                >
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                  <input
                    type="number"
                    step="0.50"
                    min="0"
                    value={newItem.default_rate}
                    onChange={e => setNewItem(n => ({ ...n, default_rate: e.target.value }))}
                    placeholder="0.00"
                    className={`${INPUT} pl-7`}
                  />
                </div>
              </div>
              <button
                onClick={addServiceItem}
                disabled={!newItem.name.trim() || !newItem.default_rate}
                className="bg-blue-600 text-white px-4 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50"
              >
                Add to Catalog
              </button>
            </div>
          )}

          {Object.entries(itemsByCategory).map(([cat, items]) => (
            <div key={cat} className="mb-4 last:mb-0">
              <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-1 px-1">{cat}</div>
              <div className="divide-y divide-gray-50 border border-gray-100 rounded-xl overflow-hidden">
                {items.map(item => (
                  <div key={item.id} className="flex items-center justify-between px-3 py-2 hover:bg-gray-50">
                    <span className="text-sm text-gray-700">{item.name}</span>
                    {editingItemId === item.id ? (
                      <div className="flex items-center gap-2">
                        <span className="text-gray-400 text-sm">$</span>
                        <input
                          type="number"
                          step="0.50"
                          min="0"
                          value={editRate}
                          onChange={e => setEditRate(e.target.value)}
                          className="w-20 border border-blue-300 rounded-lg px-2 py-1 text-sm text-right focus:outline-none focus:ring-2 focus:ring-blue-400"
                          autoFocus
                          onKeyDown={e => { if (e.key === 'Enter') saveRate(item.id); if (e.key === 'Escape') setEditingItemId(null) }}
                        />
                        <button onClick={() => saveRate(item.id)} className="text-xs text-blue-600 font-semibold hover:text-blue-800">Save</button>
                        <button onClick={() => setEditingItemId(null)} className="text-xs text-gray-400 hover:text-gray-600">✕</button>
                      </div>
                    ) : (
                      <div className="flex items-center gap-3">
                        <span className="text-sm font-semibold text-gray-800 tabular-nums">{fmt(item.default_rate)}</span>
                        <button
                          onClick={() => { setEditingItemId(item.id); setEditRate(String(item.default_rate)) }}
                          className="text-xs text-blue-500 hover:text-blue-700"
                        >
                          Edit
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Invoice Builder */}
      {building && (
        <div className="bg-white rounded-xl border border-blue-200 p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-gray-800">
              {editingDraftId ? 'Edit Draft Invoice' : 'New Invoice'}
            </h2>
            <button
              onClick={() => { setBuilding(false); setLines([]); setEditingDraftId(null) }}
              className="text-gray-400 hover:text-gray-600 text-sm px-2 py-1 rounded hover:bg-gray-100"
            >
              ✕ Cancel
            </button>
          </div>

          {/* Lines table */}
          {lines.length > 0 && (
            <div className="border border-gray-100 rounded-xl overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 text-xs text-gray-500 uppercase tracking-wide">
                    <th className="text-left px-3 py-2 font-medium">Description</th>
                    <th className="text-center px-3 py-2 font-medium w-12">Qty</th>
                    <th className="text-right px-3 py-2 font-medium w-16">Rate</th>
                    <th className="text-right px-3 py-2 font-medium w-20">Total</th>
                    <th className="w-6 px-2 py-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {lines.map(line => (
                    <tr key={line._key} className="hover:bg-gray-50">
                      <td className="px-3 py-2.5">
                        <div className="font-medium text-gray-800 text-sm">{line.description}</div>
                        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                            line.assignment_type === 'job'
                              ? 'bg-blue-100 text-blue-700'
                              : 'bg-gray-100 text-gray-500'
                          }`}>
                            {line.assignment_type === 'job' && line.job_ref ? `Job: ${line.job_ref}` : 'Business'}
                          </span>
                          {line.is_complete
                            ? <span className="text-xs text-green-600 font-medium">✓ Done</span>
                            : <span className="text-xs text-orange-500 font-medium">In Progress</span>
                          }
                          {line.notes && (
                            <span className="text-xs text-gray-400 italic truncate max-w-[160px]">{line.notes}</span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-center text-gray-700">{line.qty}</td>
                      <td className="px-3 py-2.5 text-right text-gray-600 tabular-nums">{fmt(line.rate)}</td>
                      <td className="px-3 py-2.5 text-right font-semibold text-gray-900 tabular-nums">{fmt(line.line_total)}</td>
                      <td className="px-2 py-2">
                        <button
                          onClick={() => setLines(ls => ls.filter(l => l._key !== line._key))}
                          className="text-gray-300 hover:text-red-500 text-xl leading-none"
                        >
                          ×
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-blue-50 border-t-2 border-blue-100">
                    <td colSpan={3} className="px-3 py-3 text-sm font-semibold text-gray-700 text-right">Grand Total</td>
                    <td className="px-3 py-3 text-right font-bold text-blue-700 tabular-nums text-base">{fmt(grandTotal)}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}

          {lines.length === 0 && !addingLine && (
            <div className="text-center py-10 border-2 border-dashed border-gray-100 rounded-xl">
              <p className="text-gray-400 text-sm">No lines yet.</p>
              <p className="text-gray-300 text-xs mt-1">Click "Add Line" below to start building your invoice.</p>
            </div>
          )}

          {/* Add Line Form */}
          {addingLine ? (
            <div className="border border-blue-100 bg-slate-50 rounded-xl p-4 space-y-3">
              <div className="text-sm font-semibold text-gray-700">Add Line Item</div>

              {/* Service picker */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">Service *</label>
                <select value={lineForm.service_item_id} onChange={e => handleServiceSelect(e.target.value)} className={INPUT}>
                  <option value="">— select a service —</option>
                  {Object.entries(itemsByCategory).map(([cat, items]) => (
                    <optgroup key={cat} label={cat}>
                      {items.map(item => (
                        <option key={item.id} value={item.id}>
                          {item.name} — {fmt(item.default_rate)}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                  <option value="custom">— Custom (enter description below) —</option>
                </select>
              </div>

              {/* Description — always shown, editable */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">
                  {lineForm.service_item_id && lineForm.service_item_id !== 'custom'
                    ? 'Description (editable)'
                    : 'Description *'}
                </label>
                <input
                  type="text"
                  value={lineForm.description}
                  onChange={e => setLineForm(f => ({ ...f, description: e.target.value }))}
                  placeholder="What did you do?"
                  className={INPUT}
                  autoFocus={!lineForm.service_item_id}
                />
              </div>

              {/* Qty / Rate / Total */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Qty</label>
                  <input
                    type="number"
                    min="1"
                    value={lineForm.qty}
                    onChange={e => setLineForm(f => ({ ...f, qty: e.target.value }))}
                    className={INPUT}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Rate ($)</label>
                  <input
                    type="number"
                    step="0.50"
                    min="0"
                    value={lineForm.rate}
                    onChange={e => setLineForm(f => ({ ...f, rate: e.target.value }))}
                    placeholder="0.00"
                    className={INPUT}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Line Total</label>
                  <div className="w-full border border-gray-100 bg-gray-50 rounded-lg px-3 py-2 text-sm font-semibold text-gray-700 tabular-nums">
                    {fmt((Math.max(1, parseInt(lineForm.qty) || 1)) * (parseFloat(lineForm.rate) || 0))}
                  </div>
                </div>
              </div>

              {/* Assignment */}
              <div>
                <label className="block text-xs text-gray-500 mb-2">Assign to</label>
                <div className="flex gap-6">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="assign"
                      checked={lineForm.assignment_type === 'business'}
                      onChange={() => setLineForm(f => ({ ...f, assignment_type: 'business', job_ref: '' }))}
                    />
                    <span className="text-sm text-gray-700">Business (general)</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="assign"
                      checked={lineForm.assignment_type === 'job'}
                      onChange={() => setLineForm(f => ({ ...f, assignment_type: 'job' }))}
                    />
                    <span className="text-sm text-gray-700">Specific Job</span>
                  </label>
                </div>
              </div>

              {lineForm.assignment_type === 'job' && (
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Which Job?</label>
                  <select
                    value={lineForm.job_ref}
                    onChange={e => setLineForm(f => ({ ...f, job_ref: e.target.value }))}
                    className={INPUT}
                  >
                    <option value="">— select job —</option>
                    {jobs.filter(j => j.status !== 'estimate').map(j => (
                      <option key={j.id} value={j.invoice_id || `#${j.id}`}>
                        {j.customer} — {j.invoice_id || `#${j.id}`} ({j.start_date})
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {/* Notes + completion */}
              <div>
                <label className="block text-xs text-gray-500 mb-1">Notes (what you did, details)</label>
                <input
                  type="text"
                  value={lineForm.notes}
                  onChange={e => setLineForm(f => ({ ...f, notes: e.target.value }))}
                  placeholder="e.g., Posted about the deck project, targeted Mountain Home area"
                  className={INPUT}
                />
              </div>

              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={lineForm.is_complete}
                  onChange={e => setLineForm(f => ({ ...f, is_complete: e.target.checked }))}
                  className="w-4 h-4 accent-blue-600 rounded"
                />
                <span className="text-sm text-gray-700">This task is fully completed</span>
              </label>

              <div className="flex gap-3 pt-1">
                <button
                  onClick={addLineToInvoice}
                  disabled={!lineForm.description.trim() || !lineForm.rate}
                  className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-40 font-semibold"
                >
                  Add to Invoice
                </button>
                <button
                  onClick={() => { setAddingLine(false); setLineForm(EMPTY_LINE()) }}
                  className="text-gray-500 px-4 py-2 rounded-lg text-sm hover:bg-gray-100"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setAddingLine(true)}
              className="w-full border-2 border-dashed border-gray-200 text-gray-400 py-3 rounded-xl text-sm hover:border-blue-300 hover:text-blue-500 transition-colors font-medium"
            >
              + Add Line Item
            </button>
          )}

          {/* Invoice Notes + Submit */}
          {lines.length > 0 && !addingLine && (
            <>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Invoice Notes (optional)</label>
                <textarea
                  value={invoiceNotes}
                  onChange={e => setInvoiceNotes(e.target.value)}
                  placeholder="Any overall notes for this pay period..."
                  rows={2}
                  className={`${INPUT} resize-none`}
                />
              </div>
              <div className="flex gap-3 pt-2">
                <button
                  onClick={() => saveInvoice('submitted')}
                  disabled={saving}
                  className="flex-1 bg-green-600 text-white py-3 rounded-xl text-sm hover:bg-green-700 disabled:opacity-50 font-bold"
                >
                  {saving ? 'Submitting...' : `Submit Invoice — ${fmt(grandTotal)}`}
                </button>
                <button
                  onClick={() => saveInvoice('draft')}
                  disabled={saving}
                  className="bg-gray-100 text-gray-700 px-5 py-3 rounded-xl text-sm hover:bg-gray-200 font-medium whitespace-nowrap"
                >
                  Save Draft
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {/* Invoice History */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Invoice History</h3>
          <span className="text-xs text-gray-400">{invoices.length} invoice{invoices.length !== 1 ? 's' : ''}</span>
        </div>

        {loading && <div className="p-6 text-center text-gray-400 text-sm">Loading...</div>}

        {!loading && invoices.length === 0 && (
          <div className="p-10 text-center text-gray-400 text-sm">
            No invoices yet. Click "+ New Invoice" to create your first one.
          </div>
        )}

        <div className="divide-y divide-gray-50">
          {invoices.map(inv => {
            const s = STATUS[inv.status] || STATUS.draft
            const isExpanded = expandedId === inv.id
            return (
              <div key={inv.id}>
                <div
                  className="px-5 py-3 flex items-center gap-3 hover:bg-gray-50 cursor-pointer"
                  onClick={() => toggleExpand(inv)}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-semibold text-gray-800">{inv.invoice_number}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${s.cls}`}>{s.label}</span>
                    </div>
                    <div className="text-xs text-gray-400 mt-0.5 flex items-center gap-2 flex-wrap">
                      <span>{inv.created_at?.slice(0, 10)}</span>
                      {inv.submitted_at && <><span>·</span><span>Submitted {inv.submitted_at.slice(0, 10)}</span></>}
                      {inv.paid_at && <><span>·</span><span className="text-green-600">Paid {inv.paid_at.slice(0, 10)}</span></>}
                      {inv.notes && <><span>·</span><span className="italic">{inv.notes}</span></>}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <div className="text-base font-bold text-gray-900 tabular-nums">{fmt(inv.total_amount)}</div>
                    <span className={`text-gray-400 text-sm transition-transform ${isExpanded ? 'rotate-180' : ''}`}>▾</span>
                  </div>
                </div>

                {/* Expanded detail */}
                {isExpanded && (
                  <div className="px-5 pb-4 bg-gray-50 border-t border-gray-100">
                    {loadingDetail && !expandedDetail && (
                      <div className="py-4 text-center text-gray-400 text-sm">Loading...</div>
                    )}
                    {expandedDetail && expandedDetail.id === inv.id && (
                      <>
                        <table className="w-full text-sm mt-3">
                          <thead>
                            <tr className="text-xs text-gray-400 uppercase tracking-wide">
                              <th className="text-left py-1 font-medium">Description</th>
                              <th className="text-center py-1 font-medium w-10">Qty</th>
                              <th className="text-right py-1 font-medium w-16">Rate</th>
                              <th className="text-right py-1 font-medium w-20">Total</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-gray-100">
                            {(expandedDetail.lines || []).map(line => (
                              <tr key={line.id}>
                                <td className="py-2 pr-3">
                                  <div className="font-medium text-gray-800">{line.description}</div>
                                  <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                                    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                                      line.assignment_type === 'job'
                                        ? 'bg-blue-100 text-blue-700'
                                        : 'bg-gray-100 text-gray-500'
                                    }`}>
                                      {line.assignment_type === 'job' && line.job_ref ? `Job: ${line.job_ref}` : 'Business'}
                                    </span>
                                    {line.is_complete
                                      ? <span className="text-xs text-green-600">✓ Done</span>
                                      : <span className="text-xs text-orange-500">In Progress</span>
                                    }
                                    {line.notes && <span className="text-xs text-gray-400 italic">{line.notes}</span>}
                                  </div>
                                </td>
                                <td className="py-2 text-center text-gray-600">{line.qty}</td>
                                <td className="py-2 text-right text-gray-500 tabular-nums">{fmt(line.rate)}</td>
                                <td className="py-2 text-right font-semibold text-gray-900 tabular-nums">{fmt(line.line_total)}</td>
                              </tr>
                            ))}
                          </tbody>
                          <tfoot>
                            <tr className="border-t-2 border-gray-200">
                              <td colSpan={3} className="pt-2 text-sm font-semibold text-gray-700 text-right pr-3">Grand Total</td>
                              <td className="pt-2 text-right font-bold text-gray-900 tabular-nums text-base">{fmt(inv.total_amount)}</td>
                            </tr>
                          </tfoot>
                        </table>

                        <div className="flex gap-2 mt-4 flex-wrap">
                          {inv.status === 'submitted' && (
                            <button
                              onClick={() => markPaid(inv)}
                              className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-green-700 font-semibold"
                            >
                              Mark Paid
                            </button>
                          )}
                          {inv.status === 'draft' && (
                            <>
                              <button
                                onClick={() => startEditDraft(inv)}
                                className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 font-medium"
                              >
                                Edit Draft
                              </button>
                              <button
                                onClick={async () => {
                                  const r = await fetch(`/api/jazzy/invoices/${inv.id}/submit`, { method: 'POST' })
                                  if (r.ok) { setExpandedDetail(null); await loadAll() }
                                }}
                                className="bg-yellow-500 text-white px-4 py-2 rounded-lg text-sm hover:bg-yellow-600 font-medium"
                              >
                                Submit
                              </button>
                            </>
                          )}
                          {inv.status !== 'paid' && (
                            <button
                              onClick={() => deleteInvoice(inv)}
                              className="text-red-400 hover:text-red-600 px-3 py-2 rounded-lg text-sm hover:bg-red-50"
                            >
                              Delete
                            </button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
