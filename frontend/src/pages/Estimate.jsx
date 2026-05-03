import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

const EMPTY_SERVICE = () => ({
  original_description: '',
  standardized_description: '',
  category: '',
  subcategory: '',
  service_type: 'labor',
  quantity: 1,
  unit_of_measure: 'each',
  amount: '',
})

const UOM_OPTIONS = [
  'each', 'sq.ft.', 'lin.ft.', 'hr', 'day', 'cu.yd.', 'sq.yd.',
  'piece', 'bag', 'gallon', 'roll', 'sheet', 'bundle', 'load',
]

const INPUT = 'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'
const INPUT_SM = 'w-full border border-gray-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500'
const fmt = n => `$${(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function formatPhone(raw) {
  const digits = raw.replace(/\D/g, '').slice(0, 10)
  if (digits.length < 4) return digits
  if (digits.length < 7) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`
}

export default function Estimate() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const [customers, setCustomers]       = useState([])
  const [categories, setCategories]     = useState([])
  const [pricingHints, setPricingHints] = useState({})
  const [saving, setSaving]             = useState(false)

  // New-customer inline form
  const [showNewCust, setShowNewCust]   = useState(false)
  const [newCust, setNewCust]           = useState({ name: '', phone: '', email: '', address: '' })
  const [creatingCust, setCreatingCust] = useState(false)

  // Claude pricing state
  const [claudeSuggestion, setClaudeSuggestion] = useState({})
  const [loadingClaude, setLoadingClaude]       = useState({})

  const [form, setForm] = useState({
    customer_id:    searchParams.get('customer') || '',
    invoice_number: '',
    start_date:     new Date().toISOString().slice(0, 10),
    status:         'estimate',
    estimated_days: '',
    notes:          '',
    services:       [EMPTY_SERVICE()],
  })

  useEffect(() => {
    Promise.all([
      fetch('/api/customers').then(r => r.json()),
      fetch('/api/service-categories').then(r => r.json()),
      fetch('/api/pricing/suggest-all').then(r => r.json()),
    ]).then(([custData, catData, priceData]) => {
      setCustomers((Array.isArray(custData) ? custData : []).filter(c => !c.name.startsWith('_')))
      setCategories(Array.isArray(catData) ? catData : [])
      setPricingHints(priceData || {})
    })
  }, [])

  function updateForm(field, value) {
    setForm(f => ({ ...f, [field]: value }))
  }

  function updateService(idx, field, value) {
    setForm(f => {
      const services = [...f.services]
      services[idx] = { ...services[idx], [field]: value }
      if (field === 'category' && value && pricingHints[value]) {
        const hint = pricingHints[value]
        if (!services[idx].amount) services[idx].amount = hint.avg_price || ''
      }
      return { ...f, services }
    })
  }

  function addService() {
    setForm(f => ({ ...f, services: [...f.services, EMPTY_SERVICE()] }))
  }

  function removeService(idx) {
    if (form.services.length === 1) return
    setForm(f => ({ ...f, services: f.services.filter((_, i) => i !== idx) }))
  }

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
      setNewCust(n => ({
        ...n,
        name: name || n.name,
        phone: phone ? formatPhone(phone) : n.phone,
        address: address || n.address,
        email: email || n.email,
      }))
    } catch (err) {
      if (err.name !== 'AbortError') alert('Could not open contacts: ' + err.message)
    }
  }

  // Create a new customer on the fly
  async function handleCreateCustomer() {
    if (!newCust.name.trim()) { alert('Customer name is required.'); return }
    setCreatingCust(true)
    try {
      const r = await fetch('/api/customers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newCust),
      })
      if (!r.ok) { const e = await r.json(); throw new Error(e.error || 'Failed') }
      const created = await r.json()
      setCustomers(prev => [...prev, { ...created, name: newCust.name }].sort((a, b) => a.name.localeCompare(b.name)))
      updateForm('customer_id', String(created.id))
      setNewCust({ name: '', phone: '', email: '', address: '' })
      setShowNewCust(false)
    } catch (e) {
      alert('Error creating customer: ' + e.message)
    } finally {
      setCreatingCust(false)
    }
  }

  // Ask Claude for pricing suggestion on a line item
  async function fetchClaudeSuggestion(idx) {
    const svc = form.services[idx]
    if (!svc.original_description.trim()) { alert('Enter a service description first.'); return }
    setLoadingClaude(prev => ({ ...prev, [idx]: true }))
    try {
      const historical = svc.category ? pricingHints[svc.category] : null
      const r = await fetch('/api/pricing/claude-suggest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: svc.original_description,
          category: svc.category,
          historical,
        }),
      })
      const data = await r.json()
      if (data.available === false && data.error === 'ANTHROPIC_API_KEY not set') {
        setClaudeSuggestion(prev => ({ ...prev, [idx]: { unavailable: true } }))
      } else {
        setClaudeSuggestion(prev => ({ ...prev, [idx]: data }))
      }
    } catch {
      // silent fail
    } finally {
      setLoadingClaude(prev => ({ ...prev, [idx]: false }))
    }
  }

  function suggestDays() {
    const dayHints = form.services.map(s => pricingHints[s.category]?.avg_days).filter(Boolean)
    if (dayHints.length === 0) return null
    return Math.ceil(Math.max(...dayHints))
  }

  async function handleSave(andConvert = false) {
    if (!form.customer_id) { alert('Please select a customer.'); return }
    const services = form.services.filter(s => s.original_description.trim())
    if (services.length === 0) { alert('Add at least one service line item.'); return }

    setSaving(true)
    try {
      const payload = {
        customer_id:    parseInt(form.customer_id),
        invoice_number: form.invoice_number || undefined,
        start_date:     form.start_date,
        status:         andConvert ? 'completed' : 'estimate',
        notes:          form.notes,
        estimated_days: form.estimated_days ? parseInt(form.estimated_days) : null,
        services: services.map(s => ({
          original_description:     s.original_description,
          standardized_description: s.original_description,
          category:                 s.category,
          service_type:             s.service_type,
          amount:                   parseFloat(s.amount) || 0,
          quantity:                 parseFloat(s.quantity) || 1,
          unit_of_measure:          s.unit_of_measure || 'each',
        })),
      }

      const r = await fetch('/api/filing-cabinet/new', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify(payload),
      })
      if (!r.ok) throw new Error((await r.json()).error || 'Save failed')
      const saved = await r.json()
      navigate(`/filing-cabinet?job=${saved.job_id}`)
    } catch (e) {
      alert('Error saving: ' + e.message)
    } finally {
      setSaving(false)
    }
  }

  // Derived
  const topLevelCats = categories.filter(c => !c.parent_id)
  const subcatMap    = categories.reduce((m, c) => {
    if (c.parent_id) { if (!m[c.parent_id]) m[c.parent_id] = []; m[c.parent_id].push(c) }
    return m
  }, {})

  const totalLabor     = form.services.filter(s => s.service_type === 'labor').reduce((s, i) => s + (parseFloat(i.amount) || 0), 0)
  const totalMaterials = form.services.filter(s => s.service_type !== 'labor').reduce((s, i) => s + (parseFloat(i.amount) || 0), 0)
  const daySuggestion  = suggestDays()

  return (
    <div className="max-w-5xl mx-auto space-y-5 pb-10">

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">New Estimate</h1>
        <div className="flex gap-3">
          <button
            onClick={() => handleSave(false)}
            disabled={saving}
            className="bg-white border border-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50 font-medium"
          >
            {saving ? 'Saving...' : 'Save as Estimate'}
          </button>
          <button
            onClick={() => handleSave(true)}
            disabled={saving}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50 font-medium"
          >
            Save as Invoice
          </button>
        </div>
      </div>

      {/* Customer + Job Info */}
      <div className="bg-white rounded-xl border border-gray-200 p-5">
        <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-4">Job Information</h2>
        <div className="grid grid-cols-2 gap-4">

          {/* Customer selector */}
          <div className="col-span-2 md:col-span-1">
            <label className="block text-xs text-gray-500 mb-1">Customer *</label>
            <div className="flex gap-2">
              <select
                value={form.customer_id}
                onChange={e => updateForm('customer_id', e.target.value)}
                className={INPUT}
              >
                <option value="">Select customer...</option>
                {customers.map(c => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              <button
                onClick={() => { setShowNewCust(v => !v); if (showNewCust) updateForm('customer_id', '') }}
                className="shrink-0 text-xs text-blue-600 border border-blue-200 rounded-lg px-3 py-2 hover:bg-blue-50 font-medium whitespace-nowrap"
              >
                {showNewCust ? '✕ Cancel' : '+ New'}
              </button>
            </div>
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">Date</label>
            <input
              type="date"
              value={form.start_date}
              onChange={e => updateForm('start_date', e.target.value)}
              className={INPUT}
            />
          </div>

          {/* New Customer inline form */}
          {showNewCust && (
            <div className="col-span-2 bg-blue-50 border border-blue-200 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs font-semibold text-blue-700">New Customer — fill in their info</p>
                <button
                  onClick={pickFromContacts}
                  className="flex items-center gap-1 text-xs text-blue-600 hover:text-blue-800 border border-blue-300 hover:bg-blue-100 px-2.5 py-1.5 rounded-lg transition-colors bg-white"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                  Pick from Contacts
                </button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2">
                  <label className="block text-xs text-gray-500 mb-1">Name *</label>
                  <input
                    type="text"
                    value={newCust.name}
                    onChange={e => setNewCust(n => ({ ...n, name: e.target.value }))}
                    placeholder="Full name"
                    className={INPUT}
                    autoFocus
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Phone</label>
                  <input
                    type="text"
                    value={newCust.phone}
                    onChange={e => setNewCust(n => ({ ...n, phone: formatPhone(e.target.value) }))}
                    placeholder="(870) 555-1234"
                    className={INPUT}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 mb-1">Email</label>
                  <input
                    type="email"
                    value={newCust.email}
                    onChange={e => setNewCust(n => ({ ...n, email: e.target.value }))}
                    placeholder="email@example.com"
                    className={INPUT}
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs text-gray-500 mb-1">Address</label>
                  <input
                    type="text"
                    value={newCust.address}
                    onChange={e => setNewCust(n => ({ ...n, address: e.target.value }))}
                    placeholder="123 Main St, Mountain Home AR 72653"
                    className={INPUT}
                  />
                </div>
              </div>
              <div className="flex gap-2 mt-3">
                <button
                  onClick={handleCreateCustomer}
                  disabled={creatingCust}
                  className="bg-blue-600 text-white text-xs px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                >
                  {creatingCust ? 'Saving...' : 'Save Customer & Select'}
                </button>
                <button
                  onClick={() => setShowNewCust(false)}
                  className="text-gray-500 text-xs px-3 py-2 rounded-lg hover:bg-white"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div>
            <label className="block text-xs text-gray-500 mb-1">Estimate # (optional — auto-assigned if blank)</label>
            <input
              type="text"
              value={form.invoice_number}
              onChange={e => updateForm('invoice_number', e.target.value)}
              placeholder="e.g. EST20260224 or leave blank"
              className={INPUT}
            />
          </div>

          <div>
            <label className="block text-xs text-gray-500 mb-1">
              Estimated days on site
              {daySuggestion && !form.estimated_days && (
                <button
                  onClick={() => updateForm('estimated_days', String(daySuggestion))}
                  className="ml-2 text-blue-600 hover:underline font-normal"
                >
                  Suggest: {daySuggestion} day{daySuggestion !== 1 ? 's' : ''}
                </button>
              )}
            </label>
            <input
              type="number"
              min="1"
              max="60"
              value={form.estimated_days}
              onChange={e => updateForm('estimated_days', e.target.value)}
              placeholder="Your guess..."
              className={INPUT}
            />
          </div>

          <div className="col-span-2">
            <label className="block text-xs text-gray-500 mb-1">Notes</label>
            <textarea
              rows={2}
              value={form.notes}
              onChange={e => updateForm('notes', e.target.value)}
              placeholder="Job notes, special instructions..."
              className={INPUT}
            />
          </div>
        </div>
      </div>

      {/* Line Items */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Services &amp; Line Items</h2>
          <button onClick={addService} className="text-xs text-blue-600 hover:text-blue-800 font-medium">
            + Add Line
          </button>
        </div>

        {/* Column headers */}
        <div className="grid gap-2 px-5 py-2 text-xs text-gray-400 font-medium bg-gray-50 border-b border-gray-100"
             style={{gridTemplateColumns: '3fr 1.5fr 55px 80px 80px 80px 28px'}}>
          <div>Description</div>
          <div>Category</div>
          <div>Type</div>
          <div className="text-center">Qty</div>
          <div>Unit</div>
          <div className="text-right">Amount</div>
          <div></div>
        </div>

        <div className="divide-y divide-gray-50">
          {form.services.map((svc, idx) => {
            const hint      = pricingHints[svc.category]
            const claude    = claudeSuggestion[idx]
            const loading   = loadingClaude[idx]
            const parentCat = topLevelCats.find(c => c.name === svc.category)
            const subOpts   = parentCat ? (subcatMap[parentCat.id] || []) : []

            return (
              <div key={idx}>
                <div className="grid gap-2 px-5 py-2 items-center"
                     style={{gridTemplateColumns: '3fr 1.5fr 55px 80px 80px 80px 28px'}}>
                  <input
                    type="text"
                    value={svc.original_description}
                    onChange={e => updateService(idx, 'original_description', e.target.value)}
                    placeholder="What was done?"
                    className={INPUT_SM}
                  />

                  {/* Category: group top-level and sub */}
                  <select
                    value={svc.category}
                    onChange={e => updateService(idx, 'category', e.target.value)}
                    className={INPUT_SM}
                  >
                    <option value="">Category...</option>
                    {topLevelCats.map(c => (
                      <optgroup key={c.id} label={c.name}>
                        <option value={c.name}>{c.name} (general)</option>
                        {(subcatMap[c.id] || []).map(sub => (
                          <option key={sub.id} value={sub.name}>{sub.name}</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>

                  <select
                    value={svc.service_type}
                    onChange={e => updateService(idx, 'service_type', e.target.value)}
                    className={INPUT_SM}
                  >
                    <option value="labor">Labor</option>
                    <option value="materials">Materials</option>
                  </select>

                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={svc.quantity}
                    onChange={e => updateService(idx, 'quantity', e.target.value)}
                    placeholder="1"
                    className={`${INPUT_SM} text-center`}
                  />

                  <select
                    value={svc.unit_of_measure}
                    onChange={e => updateService(idx, 'unit_of_measure', e.target.value)}
                    className={INPUT_SM}
                  >
                    {UOM_OPTIONS.map(u => <option key={u} value={u}>{u}</option>)}
                  </select>

                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={svc.amount}
                    onChange={e => updateService(idx, 'amount', e.target.value)}
                    placeholder="0.00"
                    className={`${INPUT_SM} text-right`}
                  />

                  <button
                    onClick={() => removeService(idx)}
                    className="text-gray-300 hover:text-red-500 text-xl leading-none font-light text-center"
                  >
                    ×
                  </button>
                </div>

                {/* Pricing hints row */}
                <div className="px-5 pb-2 flex flex-wrap items-center gap-3 text-xs text-gray-400">
                  {hint && svc.service_type === 'labor' && (
                    <>
                      <span>Historical avg:</span>
                      <button
                        onClick={() => updateService(idx, 'amount', hint.avg_price)}
                        className="text-blue-500 hover:text-blue-700 font-medium"
                      >
                        {fmt(hint.avg_price)} avg
                      </button>
                      <span className="text-gray-300">|</span>
                      <span>{fmt(hint.min_price)} – {fmt(hint.max_price)}</span>
                      <span className="text-gray-300">|</span>
                      <span>{hint.job_count} past job{hint.job_count !== 1 ? 's' : ''}</span>
                    </>
                  )}

                  {/* Claude suggestion */}
                  {!claude && (
                    <button
                      onClick={() => fetchClaudeSuggestion(idx)}
                      disabled={loading}
                      className="ml-auto text-purple-600 hover:text-purple-800 font-medium border border-purple-200 rounded px-2 py-0.5 hover:bg-purple-50 disabled:opacity-50"
                    >
                      {loading ? 'Asking Claude...' : 'Ask Claude for price'}
                    </button>
                  )}

                  {claude?.unavailable && (
                    <span className="ml-auto text-gray-400 italic text-xs">
                      Claude pricing: set ANTHROPIC_API_KEY env var to enable
                    </span>
                  )}

                  {claude && !claude.unavailable && !claude.error && (
                    <div className="w-full bg-purple-50 border border-purple-100 rounded-lg px-3 py-2 mt-1">
                      <div className="flex items-center gap-3 flex-wrap">
                        <span className="text-purple-700 font-semibold text-xs">Claude suggests:</span>
                        <button
                          onClick={() => updateService(idx, 'amount', claude.suggested_price)}
                          className="text-purple-600 hover:text-purple-800 font-bold"
                        >
                          {fmt(claude.suggested_price)}
                        </button>
                        <span className="text-purple-400">({fmt(claude.suggested_low)} – {fmt(claude.suggested_high)})</span>
                        <button
                          onClick={() => setClaudeSuggestion(prev => { const n = {...prev}; delete n[idx]; return n })}
                          className="ml-auto text-gray-400 hover:text-gray-600 text-xs"
                        >
                          ✕
                        </button>
                      </div>
                      <p className="text-xs text-purple-600 mt-1">{claude.rationale}</p>
                      {claude.factors?.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-1">
                          {claude.factors.map((f, i) => (
                            <span key={i} className="bg-purple-100 text-purple-600 px-1.5 py-0.5 rounded text-xs">{f}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Totals */}
        <div className="border-t border-gray-200 px-5 py-4 bg-gray-50">
          <div className="flex justify-end">
            <div className="w-56 space-y-1.5 text-sm">
              {totalLabor > 0 && (
                <div className="flex justify-between text-gray-600">
                  <span>Labor</span>
                  <span className="font-medium tabular-nums">{fmt(totalLabor)}</span>
                </div>
              )}
              {totalMaterials > 0 && (
                <div className="flex justify-between text-gray-500">
                  <span>Materials</span>
                  <span className="font-medium tabular-nums">{fmt(totalMaterials)}</span>
                </div>
              )}
              <div className="flex justify-between font-bold text-gray-900 text-base pt-1.5 border-t border-gray-300">
                <span>Total</span>
                <span className="tabular-nums">{fmt(totalLabor + totalMaterials)}</span>
              </div>
              {form.estimated_days && (
                <div className="flex justify-between text-xs text-gray-400 pt-1">
                  <span>Est. days on site</span>
                  <span>{form.estimated_days} day{form.estimated_days !== '1' ? 's' : ''}</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom actions */}
      <div className="flex justify-end gap-3">
        <button
          onClick={() => handleSave(false)}
          disabled={saving}
          className="bg-white border border-gray-200 text-gray-700 px-6 py-2.5 rounded-lg text-sm hover:bg-gray-50 disabled:opacity-50 font-medium"
        >
          Save as Estimate
        </button>
        <button
          onClick={() => handleSave(true)}
          disabled={saving}
          className="bg-blue-600 text-white px-6 py-2.5 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50 font-medium"
        >
          Save as Invoice
        </button>
      </div>
    </div>
  )
}
