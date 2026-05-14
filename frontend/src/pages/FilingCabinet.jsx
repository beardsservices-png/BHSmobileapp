import { useState, useEffect, useCallback, Fragment } from 'react'
import { Link } from 'react-router-dom'

function useCopyToClipboard() {
  const [copied, setCopied] = useState(false)
  function copy(text) {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }).catch(() => {})
  }
  return [copied, copy]
}

const API = '/api'
const fmt = n => `$${(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const fmtHours = h => `${(h || 0).toFixed(1)}h`

const UOM_OPTIONS = [
  'each', 'sq.ft.', 'lin.ft.', 'hr', 'day', 'cu.yd.', 'sq.yd.',
  'piece', 'bag', 'gallon', 'roll', 'sheet', 'bundle', 'load',
]

function fmtTime(ts) {
  if (!ts) return null
  const m = ts.match(/(\d{2}):(\d{2})/)
  if (!m) return null
  let h = parseInt(m[1], 10)
  const min = m[2]
  const ampm = h >= 12 ? 'PM' : 'AM'
  if (h > 12) h -= 12
  if (h === 0) h = 12
  return `${h}:${min} ${ampm}`
}

function formatPhone(raw) {
  const digits = (raw || '').replace(/\D/g, '').slice(0, 10)
  if (digits.length < 4) return digits
  if (digits.length < 7) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`
  return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`
}

const STATUS_COLORS = {
  completed: 'bg-green-100 text-green-700',
  paid:      'bg-green-100 text-green-700',
  pending:   'bg-yellow-100 text-yellow-700',
  estimate:  'bg-blue-100 text-blue-700',
}
function StatusBadge({ status }) {
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[status] || 'bg-gray-100 text-gray-600'}`}>
      {status}
    </span>
  )
}

const INPUT    = 'w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white'
const INPUT_SM = 'w-full border border-gray-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white'

// The sidebar tabs and what statuses they match
const TABS = [
  { key: 'all',      label: 'All',       match: null },
  { key: 'estimate', label: 'Estimates', match: ['estimate'] },
  { key: 'invoice',  label: 'Invoices',  match: ['completed', 'paid', 'pending'] },
  { key: 'gaps',     label: 'Data Gaps', match: null },
]

// ─────────────────────────────────────────────────────────────────
export default function FilingCabinet() {
  const [jobs, setJobs]               = useState([])
  const [categories, setCategories]   = useState([])
  const [selectedId, setSelectedId]   = useState(null)
  const [detail, setDetail]           = useState(null)
  const [loading, setLoading]         = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [search, setSearch]           = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [saving, setSaving]           = useState(false)
  const [edited, setEdited]           = useState(false)
  const [calcMileage, setCalcMileage] = useState(false)

  // Payment form state
  const [paymentForm, setPaymentForm] = useState({
    amount: '', payment_method: 'cash', payment_date: new Date().toISOString().slice(0, 10), memo: '',
  })
  const [addingPayment, setAddingPayment] = useState(false)
  const [converting, setConverting] = useState(false)

  // ── Data Gaps state ───────────────────────────────────────────
  const [gaps, setGaps] = useState(null)
  const [gapsLoading, setGapsLoading] = useState(false)
  const [allJobs, setAllJobs] = useState([])
  const [hoursForm, setHoursForm] = useState({})
  const [linkJob, setLinkJob] = useState({})
  const today = new Date().toISOString().slice(0, 10)
  const [overheadForm, setOverheadForm] = useState({
    expense_date: today, expense_category: 'Fuel & Transportation',
    cost: '', vendor: '', notes: '',
  })
  const [mobileView, setMobileView] = useState('list') // 'list' | 'detail'
  const [gapSections, setGapSections] = useState({
    missing_time: true, unlinked: true, overhead: true, suggested: true,
  })

  useEffect(() => {
    // Check ?job= param
    const params = new URLSearchParams(window.location.search)
    const jobParam = params.get('job')
    if (jobParam) setSelectedId(parseInt(jobParam))

    Promise.all([
      fetch(`${API}/filing-cabinet`).then(r => r.json()),
      fetch(`${API}/service-categories`).then(r => r.json()),
    ]).then(([jobData, catData]) => {
      setJobs(jobData.jobs || jobData || [])
      setCategories(catData || [])
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedId) return
    setDetailLoading(true)
    setEdited(false)
    fetch(`${API}/filing-cabinet/${selectedId}`)
      .then(r => r.json())
      .then(data => { setDetail(data); setDetailLoading(false) })
      .catch(() => setDetailLoading(false))
  }, [selectedId])

  const refreshList = useCallback(async () => {
    const r = await fetch(`${API}/filing-cabinet`)
    const data = await r.json()
    setJobs(data.jobs || data || [])
  }, [])

  // Load gaps when the gaps tab is active
  useEffect(() => {
    if (statusFilter !== 'gaps') return
    setGapsLoading(true)
    Promise.all([
      fetch(`${API}/data-gaps`).then(r => r.json()),
      fetch(`${API}/jobs`).then(r => r.json()),
    ]).then(([gapData, jobList]) => {
      setGaps(gapData)
      setAllJobs(Array.isArray(jobList) ? jobList : [])
      setGapsLoading(false)
    }).catch(() => setGapsLoading(false))
  }, [statusFilter])

  const refreshGaps = useCallback(() => {
    setGapsLoading(true)
    Promise.all([
      fetch(`${API}/data-gaps`).then(r => r.json()),
      fetch(`${API}/jobs`).then(r => r.json()),
    ]).then(([gapData, jobList]) => {
      setGaps(gapData)
      setAllJobs(Array.isArray(jobList) ? jobList : [])
      setGapsLoading(false)
    }).catch(() => setGapsLoading(false))
  }, [])

  // Filter sidebar
  const filtered = jobs.filter(j => {
    const q = search.toLowerCase()
    const matchSearch = !q ||
      (j.customer || '').toLowerCase().includes(q) ||
      (j.invoice_number || '').toLowerCase().includes(q)
    const tab = TABS.find(t => t.key === statusFilter)
    const matchStatus = !tab?.match || tab.match.includes(j.status)
    return matchSearch && matchStatus
  })

  // ── Save ──────────────────────────────────────────────────────
  async function handleSave() {
    if (!detail) return
    setSaving(true)
    try {
      const payload = {
        customer_id: detail.customer_id,
        notes: detail.notes,
        status: detail.status,
        services: detail.services,
        time_entries: detail.time_entries,
        photos_album_url: detail.photos_album_url || null,
        customer: {
          name:    detail.customer_name,
          phone:   detail.customer_phone,
          email:   detail.customer_email,
          address: detail.customer_address,
        },
      }
      const res = await fetch(`${API}/filing-cabinet/${detail.job_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) throw new Error('Save failed')
      setEdited(false)
      await refreshList()
    } catch {
      alert('Error saving changes')
    } finally {
      setSaving(false)
    }
  }

  // ── Claim unlinked time entry ─────────────────────────────────
  async function handleClaim(teId) {
    if (!detail) return
    try {
      await fetch(`${API}/filing-cabinet/${detail.job_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: detail.customer_id,
          notes: detail.notes,
          services: detail.services,
          time_entries: detail.time_entries,
          claim_time_entry_ids: [teId],
        }),
      })
      const r = await fetch(`${API}/filing-cabinet/${detail.job_id}`)
      setDetail(await r.json())
    } catch {
      alert('Error claiming time entry')
    }
  }

  // ── Reassign time entry ────────────────────────────────────────
  async function handleReassign(teId, newJobId) {
    try {
      await fetch(`${API}/time-entries/${teId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: newJobId }),
      })
      const r = await fetch(`${API}/filing-cabinet/${detail.job_id}`)
      setDetail(await r.json())
      await refreshList()
    } catch {
      alert('Error reassigning time entry')
    }
  }

  // ── Add payment ───────────────────────────────────────────────
  async function handleAddPayment() {
    if (!detail || !paymentForm.amount) return
    setAddingPayment(true)
    try {
      const r = await fetch(`${API}/jobs/${detail.job_id}/payments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(paymentForm),
      })
      if (!r.ok) throw new Error((await r.json()).error || 'Failed')
      // Refresh full detail so payments + status update
      const detail2 = await fetch(`${API}/filing-cabinet/${detail.job_id}`)
      setDetail(await detail2.json())
      setPaymentForm(prev => ({ ...prev, amount: '', memo: '' }))
      await refreshList()
    } catch (e) {
      alert('Error adding payment: ' + e.message)
    } finally {
      setAddingPayment(false)
    }
  }

  // ── Delete payment ─────────────────────────────────────────────
  async function handleDeletePayment(paymentId) {
    if (!confirm('Remove this payment?')) return
    try {
      await fetch(`${API}/payments/${paymentId}`, { method: 'DELETE' })
      const r = await fetch(`${API}/filing-cabinet/${detail.job_id}`)
      setDetail(await r.json())
      await refreshList()
    } catch {
      alert('Error removing payment')
    }
  }

  // ── Calculate mileage ─────────────────────────────────────────
  async function handleCalcMileage() {
    if (!detail?.customer_id) return
    setCalcMileage(true)
    try {
      const r = await fetch(`${API}/customers/${detail.customer_id}/calculate-mileage`, { method: 'POST' })
      const data = await r.json()
      if (data.error) { alert('Mileage error: ' + data.error); return }
      setDetail(prev => ({ ...prev, mileage_from_home: data.mileage_from_home }))
    } catch {
      alert('Could not calculate mileage')
    } finally {
      setCalcMileage(false)
    }
  }

  // ── Convert estimate to invoice ───────────────────────────────
  async function handleConvert() {
    if (!window.confirm('Convert this estimate to an invoice? The EST number will become a BHS number.')) return
    setConverting(true)
    try {
      await fetch(`${API}/jobs/${detail.job_id}/convert`, { method: 'POST' })
      // Refresh job list and selected job
      const [listRes, jobRes] = await Promise.all([
        fetch(`${API}/filing-cabinet`).then(r => r.json()),
        fetch(`${API}/filing-cabinet/${detail.job_id}`).then(r => r.json()),
      ])
      setJobs(listRes.jobs || listRes || [])
      setDetail(jobRes)
    } catch {
      alert('Error converting estimate')
    } finally {
      setConverting(false)
    }
  }

  // ── Detail state helpers ──────────────────────────────────────
  function setField(key, value) {
    setEdited(true)
    setDetail(prev => ({ ...prev, [key]: value }))
  }

  function updateService(idx, field, value) {
    setEdited(true)
    setDetail(prev => {
      const services = [...(prev.services || [])]
      services[idx] = { ...services[idx], [field]: value }
      return { ...prev, services }
    })
  }

  function addService() {
    setEdited(true)
    setDetail(prev => ({
      ...prev,
      services: [...(prev.services || []), {
        id: null, original_description: '', standardized_description: '',
        category: '', amount: 0, service_type: 'labor', quantity: 1, unit_of_measure: 'each',
      }],
    }))
  }

  function removeService(idx) {
    setEdited(true)
    setDetail(prev => ({
      ...prev,
      services: (prev.services || []).filter((_, i) => i !== idx),
    }))
  }

  // Computed totals
  const totalLabor     = (detail?.services || []).filter(s => s.service_type === 'labor').reduce((s, i) => s + (parseFloat(i.amount) || 0), 0)
  const totalMaterials = (detail?.services || []).filter(s => s.service_type !== 'labor').reduce((s, i) => s + (parseFloat(i.amount) || 0), 0)
  const totalHours     = (detail?.time_entries || []).reduce((s, t) => s + (t.hours || 0), 0)

  const topLevelCats = categories.filter(c => !c.parent_id)
  const subcatMap    = categories.reduce((m, c) => {
    if (c.parent_id) { if (!m[c.parent_id]) m[c.parent_id] = []; m[c.parent_id].push(c) }
    return m
  }, {})

  const isEstimate = detail?.status === 'estimate'

  const [linkCopied, copyLink] = useCopyToClipboard()

  // ─────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full gap-0 -m-6">

      {/* ══ LEFT SIDEBAR ══════════════════════════════════════════ */}
      <div className={`${mobileView === 'detail' ? 'hidden' : 'flex'} md:flex w-full md:w-72 bg-white border-r border-gray-200 flex-col flex-shrink-0`}>
        <div className="p-4 border-b border-gray-100">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-lg font-bold text-gray-900">Filing Cabinet</h1>
            <Link
              to="/estimate"
              className="text-xs bg-blue-600 text-white px-3 py-1.5 rounded-lg hover:bg-blue-700 font-medium"
            >
              + New
            </Link>
          </div>
          <input
            type="text"
            placeholder="Search customer or number..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 mb-2"
          />
          <div className="flex gap-1 flex-wrap">
            {TABS.map(tab => {
              const isGaps = tab.key === 'gaps'
              const isActive = statusFilter === tab.key
              const gapCount = gaps
                ? (gaps.missing_time_entries?.length || 0) + (gaps.unlinked_time_entries?.length || 0) + (gaps.suggested_trips?.length || 0)
                : null
              return (
                <button
                  key={tab.key}
                  onClick={() => { setStatusFilter(tab.key); if (tab.key === 'gaps') setMobileView('detail') }}
                  className={`flex-1 py-1 text-xs rounded-md font-medium transition-colors flex items-center justify-center gap-1 ${
                    isActive
                      ? isGaps ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'
                      : isGaps ? 'text-amber-600 hover:bg-amber-50' : 'text-gray-500 hover:bg-gray-100'
                  }`}
                >
                  {tab.label}
                  {isGaps && gapCount !== null && gapCount > 0 && (
                    <span className="bg-amber-500 text-white text-xs font-bold rounded-full px-1.5 py-0 leading-5 min-w-5 text-center">
                      {gapCount}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>

        <div className="overflow-y-auto flex-1">
          {loading && <div className="p-4 text-gray-400 text-sm text-center">Loading...</div>}
          {filtered.map(job => {
            const isSelected = selectedId === job.job_id
            return (
              <button
                key={job.job_id}
                onClick={() => { setSelectedId(job.job_id); setMobileView('detail') }}
                className={`w-full text-left px-4 py-3 border-b border-gray-50 hover:bg-gray-50 transition-colors ${
                  isSelected ? 'bg-blue-50 border-l-4 border-l-blue-500' : ''
                }`}
              >
                <div className="flex items-center justify-between mb-0.5">
                  <div className="font-medium text-gray-900 text-sm truncate flex-1 mr-2">
                    {job.customer || 'Unknown'}
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {job.data_status === 'incomplete' && (
                      <span className="text-xs px-1.5 py-0.5 rounded-full font-medium bg-amber-100 text-amber-700">
                        Incomplete
                      </span>
                    )}
                    <StatusBadge status={job.status} />
                  </div>
                </div>
                <div className="flex items-center justify-between">
                  <div className="text-xs text-gray-500">{job.invoice_number || `#${job.job_id}`}</div>
                  <div className="text-xs font-semibold text-gray-700">{fmt(job.total_amount)}</div>
                </div>
                <div className="flex items-center justify-between mt-0.5">
                  <div className="text-xs text-gray-400">{job.start_date || ''}</div>
                  {job.total_hours > 0 && (
                    <div className="text-xs text-gray-400">{fmtHours(job.total_hours)}</div>
                  )}
                </div>
              </button>
            )
          })}
          {!loading && filtered.length === 0 && (
            <div className="p-6 text-center text-gray-400 text-sm">No jobs found</div>
          )}
        </div>

        <div className="p-3 border-t border-gray-100 text-xs text-gray-400 text-center">
          {filtered.length} of {jobs.length} jobs
        </div>
      </div>

      {/* ══ RIGHT DOSSIER PANEL ═══════════════════════════════════ */}
      <div className={`${mobileView === 'list' ? 'hidden' : 'flex'} md:flex flex-col flex-1 overflow-y-auto bg-gray-50`}>
        {/* Mobile back button */}
        <div className="md:hidden flex items-center gap-2 px-4 py-3 bg-white border-b border-gray-200 flex-shrink-0">
          <button
            onClick={() => setMobileView('list')}
            className="flex items-center gap-1 text-sm text-blue-600 font-medium"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
            </svg>
            Filing Cabinet
          </button>
          {detail && <span className="text-sm text-gray-500 truncate">/ {detail.customer_name || detail.invoice_id}</span>}
        </div>
        <div className="flex-1 overflow-y-auto">

        {/* ── GAPS VIEW ─────────────────────────────────────────── */}
        {statusFilter === 'gaps' && (
          <DataGapsPanel
            gaps={gaps}
            loading={gapsLoading}
            allJobs={allJobs}
            hoursForm={hoursForm}
            setHoursForm={setHoursForm}
            linkJob={linkJob}
            setLinkJob={setLinkJob}
            overheadForm={overheadForm}
            setOverheadForm={setOverheadForm}
            today={today}
            sections={gapSections}
            setSections={setGapSections}
            refreshGaps={refreshGaps}
          />
        )}

        {statusFilter !== 'gaps' && !selectedId && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <div className="text-5xl mb-4">🗂</div>
            <div className="text-xl font-medium">Select a job</div>
            <div className="text-sm mt-1">or create a new estimate</div>
          </div>
        )}

        {statusFilter !== 'gaps' && selectedId && detailLoading && (
          <div className="flex items-center justify-center h-64 text-gray-400">Loading...</div>
        )}

        {statusFilter !== 'gaps' && selectedId && detail && !detailLoading && (
          <div className="p-6 space-y-4 max-w-4xl">

            {/* ── TOOLBAR ────────────────────────────────────────── */}
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h2 className="text-2xl font-bold text-gray-900">{detail.customer_name}</h2>
                <div className="text-sm text-gray-500 mt-0.5 flex items-center gap-2 flex-wrap">
                  <span className="font-mono">{detail.invoice_number}</span>
                  <span>·</span>
                  <span>{detail.invoice_date || detail.start_date}</span>
                  <span>·</span>
                  <StatusBadge status={detail.status} />
                </div>
              </div>
              <div className="flex flex-wrap gap-2 flex-shrink-0">
                <button
                  onClick={() => window.open(`/print/${detail.job_id}`, '_blank')}
                  className="bg-white border border-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm hover:bg-gray-50 font-medium"
                >
                  Preview {isEstimate ? 'Estimate' : 'Invoice'}
                </button>
                <button
                  onClick={() => copyLink(window.location.origin + '/print/' + detail.job_id)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium border transition-colors ${
                    linkCopied
                      ? 'bg-green-100 border-green-300 text-green-700'
                      : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  {linkCopied ? 'Copied!' : 'Copy Print Link'}
                </button>
                {detail.status === 'estimate' && (
                  <button
                    onClick={handleConvert}
                    disabled={converting}
                    className="bg-green-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-green-700 disabled:opacity-50 font-medium"
                  >
                    {converting ? 'Converting...' : 'Convert to Invoice \u2192'}
                  </button>
                )}
                {edited && (
                  <button
                    onClick={handleSave}
                    disabled={saving}
                    className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50 font-medium"
                  >
                    {saving ? 'Saving...' : 'Save Changes'}
                  </button>
                )}
              </div>
            </div>

            {/* ── CUSTOMER CARD ──────────────────────────────────── */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Customer</h3>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Name</label>
                  <input
                    type="text"
                    value={detail.customer_name || ''}
                    onChange={e => setField('customer_name', e.target.value)}
                    className={INPUT}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Phone</label>
                  <input
                    type="text"
                    value={detail.customer_phone || ''}
                    onChange={e => setField('customer_phone', formatPhone(e.target.value))}
                    placeholder="(870) 555-1234"
                    className={INPUT}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Email</label>
                  <input
                    type="email"
                    value={detail.customer_email || ''}
                    onChange={e => setField('customer_email', e.target.value)}
                    placeholder="email@example.com"
                    className={INPUT}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Address</label>
                  <input
                    type="text"
                    value={detail.customer_address || ''}
                    onChange={e => setField('customer_address', e.target.value)}
                    placeholder="123 Main St, Mountain Home AR 72653"
                    className={INPUT}
                  />
                </div>
              </div>

              {/* Mileage — internal only */}
              <div className="mt-3 pt-3 border-t border-gray-100 flex items-center gap-4">
                <div className="text-xs text-gray-400">
                  <span className="font-medium text-gray-500">Drive from home:</span>{' '}
                  {detail.mileage_from_home != null
                    ? <span className="font-semibold text-gray-700">{detail.mileage_from_home} mi one-way</span>
                    : <span className="italic">not calculated</span>
                  }
                  <span className="ml-1 text-gray-400">(internal only)</span>
                </div>
                {detail.customer_address && (
                  <button
                    onClick={handleCalcMileage}
                    disabled={calcMileage}
                    className="text-xs text-blue-600 hover:text-blue-800 border border-blue-200 rounded px-2 py-1 hover:bg-blue-50 disabled:opacity-50"
                  >
                    {calcMileage ? 'Calculating...' : detail.mileage_from_home ? 'Recalculate' : 'Calculate Mileage'}
                  </button>
                )}
              </div>
            </div>

            {/* ── JOB DETAILS ────────────────────────────────────── */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
                {isEstimate ? 'Estimate Details' : 'Invoice Details'}
              </h3>
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">
                    {isEstimate ? 'Estimate #' : 'Invoice #'}
                  </label>
                  <input
                    type="text"
                    value={detail.invoice_number || ''}
                    readOnly
                    className={`${INPUT} bg-gray-50 text-gray-500 cursor-default`}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Date</label>
                  <input
                    type="date"
                    value={detail.invoice_date || detail.start_date || ''}
                    onChange={e => setField('invoice_date', e.target.value)}
                    className={INPUT}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Status</label>
                  <select
                    value={detail.status || 'completed'}
                    onChange={e => setField('status', e.target.value)}
                    className={INPUT}
                  >
                    <option value="estimate">Estimate</option>
                    <option value="pending">Pending</option>
                    <option value="completed">Completed</option>
                    <option value="paid">Paid</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Estimated days on site</label>
                  <input
                    type="number"
                    min="1"
                    max="60"
                    value={detail.estimated_days || ''}
                    onChange={e => setField('estimated_days', e.target.value ? parseInt(e.target.value) : null)}
                    placeholder="Your guess"
                    className={INPUT}
                  />
                </div>
                <div className="col-span-3">
                  <label className="block text-xs text-gray-400 mb-1">Notes</label>
                  <textarea
                    rows={2}
                    value={detail.notes || ''}
                    onChange={e => setField('notes', e.target.value)}
                    placeholder="Job notes..."
                    className={INPUT}
                  />
                </div>
                <div className="col-span-3">
                  <label className="block text-xs text-gray-400 mb-1">Google Photos Album</label>
                  <input
                    type="url"
                    value={detail.photos_album_url || ''}
                    onChange={e => setField('photos_album_url', e.target.value)}
                    placeholder="Paste Google Photos album link..."
                    className={INPUT}
                  />
                  {detail.photos_album_url && (
                    <a
                      href={detail.photos_album_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block mt-1 text-xs text-blue-600 hover:text-blue-800 hover:underline"
                    >
                      Open album →
                    </a>
                  )}
                </div>
              </div>
            </div>

            {/* ── SERVICES TABLE ─────────────────────────────────── */}
            <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  Services &amp; Line Items
                </h3>
                <button onClick={addService} className="text-xs text-blue-600 hover:text-blue-800 font-medium">
                  + Add Line
                </button>
              </div>

              {/* Column headers */}
              <div className="grid gap-2 px-5 py-2 text-xs text-gray-400 font-medium bg-gray-50 border-b border-gray-100"
                   style={{gridTemplateColumns: '3fr 1.5fr 55px 60px 75px 80px 28px'}}>
                <div>Description</div>
                <div>Category</div>
                <div>Type</div>
                <div className="text-center">Qty</div>
                <div>Unit</div>
                <div className="text-right">Amount</div>
                <div></div>
              </div>

              <div className="divide-y divide-gray-50">
                {(detail.services || []).map((svc, idx) => (
                  <div key={idx}
                       className="grid gap-2 px-5 py-2 items-center"
                       style={{gridTemplateColumns: '3fr 1.5fr 55px 60px 75px 80px 28px'}}>
                    <input
                      type="text"
                      value={svc.standardized_description || svc.original_description || ''}
                      onChange={e => {
                        updateService(idx, 'standardized_description', e.target.value)
                        updateService(idx, 'original_description', e.target.value)
                      }}
                      placeholder="Service description"
                      className={INPUT_SM}
                    />
                    <select
                      value={svc.category || ''}
                      onChange={e => updateService(idx, 'category', e.target.value)}
                      className={INPUT_SM}
                    >
                      <option value="">-- category --</option>
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
                      value={svc.service_type || 'labor'}
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
                      value={svc.quantity ?? 1}
                      onChange={e => updateService(idx, 'quantity', parseFloat(e.target.value) || 1)}
                      className={`${INPUT_SM} text-center`}
                    />
                    <select
                      value={svc.unit_of_measure || 'each'}
                      onChange={e => updateService(idx, 'unit_of_measure', e.target.value)}
                      className={INPUT_SM}
                    >
                      {UOM_OPTIONS.map(u => <option key={u} value={u}>{u}</option>)}
                    </select>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={svc.amount || ''}
                      onChange={e => updateService(idx, 'amount', parseFloat(e.target.value) || 0)}
                      className={`${INPUT_SM} text-right`}
                    />
                    <button
                      onClick={() => removeService(idx)}
                      className="text-gray-300 hover:text-red-500 text-xl leading-none font-light text-center"
                    >
                      ×
                    </button>
                  </div>
                ))}
                {(!detail.services || detail.services.length === 0) && (
                  <div className="px-5 py-6 text-center text-gray-400 text-sm">
                    No services —{' '}
                    <button onClick={addService} className="text-blue-600 hover:underline">add one</button>
                  </div>
                )}
              </div>

              {/* Totals footer */}
              <div className="border-t border-gray-200 px-5 py-4 bg-gray-50">
                <div className="flex justify-end">
                  <div className="space-y-1 text-sm min-w-52">
                    <div className="flex justify-between text-gray-600">
                      <span>Labor</span>
                      <span className="tabular-nums">{fmt(totalLabor)}</span>
                    </div>
                    {totalMaterials > 0 && (
                      <div className="flex justify-between text-gray-500">
                        <span>Materials (passthrough)</span>
                        <span className="tabular-nums">{fmt(totalMaterials)}</span>
                      </div>
                    )}
                    <div className="flex justify-between font-bold text-gray-900 text-base pt-1 border-t border-gray-200">
                      <span>Total</span>
                      <span className="tabular-nums">{fmt(totalLabor + totalMaterials)}</span>
                    </div>
                    {totalHours > 0 && totalLabor > 0 && (
                      <div className="flex justify-between text-xs text-gray-400 pt-1">
                        <span>{fmtHours(totalHours)} logged</span>
                        <span>{fmt(totalLabor / totalHours)}/hr</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* ── PAYMENTS ───────────────────────────────────────── */}
            {!isEstimate && (
              <PaymentsSection
                detail={detail}
                paymentForm={paymentForm}
                setPaymentForm={setPaymentForm}
                onAdd={handleAddPayment}
                onDelete={handleDeletePayment}
                adding={addingPayment}
              />
            )}

            {/* ── TIME ENTRIES ────────────────────────────────────── */}
            {(detail.time_entries?.length > 0 || detail.unlinked_time_entries?.length > 0) && (
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <div className="px-5 py-3 border-b border-gray-100">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
                      Time on Site
                    </h3>
                    <div className="flex items-center gap-4 text-sm">
                      {totalHours > 0 && (
                        <span className="text-gray-500">{fmtHours(totalHours)} total</span>
                      )}
                    </div>
                  </div>
                  {(detail.actual_days > 0 || detail.estimated_days) && (
                    <DaysComparison estimated={detail.estimated_days} actual={detail.actual_days} />
                  )}
                </div>

                {detail.days_on_site?.length > 0 && (
                  <div className="px-5 py-3 border-b border-gray-100 bg-gray-50">
                    <div className="flex flex-wrap gap-2">
                      {detail.days_on_site.map((day, i) => (
                        <div key={day.date} className="flex items-center gap-1.5 bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-xs">
                          <span className="font-semibold text-gray-500">Day {i + 1}</span>
                          <span className="text-gray-400">·</span>
                          <span className="text-gray-700">{day.date}</span>
                          <span className="text-gray-400">·</span>
                          <span className="font-medium text-gray-800">{day.hours.toFixed(1)}h</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {detail.time_entries?.length > 0 && (
                  <div className="divide-y divide-gray-50">
                    {detail.time_entries.map(t => (
                      <TimeEntryRow
                        key={t.id} entry={t}
                        customerJobs={detail.customer_jobs}
                        currentJobId={detail.job_id}
                        onReassign={handleReassign}
                      />
                    ))}
                  </div>
                )}

                {detail.unlinked_time_entries?.length > 0 && (
                  <>
                    <div className="px-5 py-2 bg-amber-50 border-t border-amber-100">
                      <span className="text-xs font-medium text-amber-700">
                        {detail.unlinked_time_entries.length} unlinked {detail.unlinked_time_entries.length === 1 ? 'entry' : 'entries'} for this customer
                      </span>
                    </div>
                    <div className="divide-y divide-gray-50">
                      {detail.unlinked_time_entries.map(t => (
                        <TimeEntryRow
                          key={t.id} entry={t} unlinked
                          onClaim={() => handleClaim(t.id)}
                          customerJobs={detail.customer_jobs}
                          currentJobId={detail.job_id}
                          onReassign={handleReassign}
                        />
                      ))}
                    </div>
                  </>
                )}
              </div>
            )}

          </div>
        )}
        </div>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────
// Payments Section
// ─────────────────────────────────────────────────────────────────
const PAYMENT_METHODS = ['Cash', 'Check', 'Venmo', 'Zelle', 'PayPal', 'Credit Card', 'Debit Card', 'Bank Transfer', 'Other']

function PaymentsSection({ detail, paymentForm, setPaymentForm, onAdd, onDelete, adding }) {
  const totalAmount  = detail.total_amount || 0
  const totalPaid    = (detail.payments || []).reduce((s, p) => s + (p.amount || 0), 0)
  const balanceDue   = Math.max(totalAmount - totalPaid, 0)
  const paidInFull   = totalAmount > 0 && balanceDue === 0
  const pctPaid      = totalAmount > 0 ? Math.min((totalPaid / totalAmount) * 100, 100) : 0

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 border-b border-gray-100 flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Payments</h3>
        {paidInFull ? (
          <span className="text-xs font-bold text-green-700 bg-green-100 px-3 py-1 rounded-full">
            PAID IN FULL
          </span>
        ) : (
          <span className="text-sm font-semibold text-red-600">
            Balance Due: {fmt(balanceDue)}
          </span>
        )}
      </div>

      {/* Progress bar */}
      {totalAmount > 0 && (
        <div className="px-5 pt-3 pb-1">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>{fmt(totalPaid)} paid</span>
            <span>{fmt(totalAmount)} total</span>
          </div>
          <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-2 rounded-full transition-all ${paidInFull ? 'bg-green-500' : 'bg-blue-500'}`}
              style={{ width: `${pctPaid}%` }}
            />
          </div>
        </div>
      )}

      {/* Existing payments */}
      {(detail.payments || []).length > 0 && (
        <div className="divide-y divide-gray-50 mt-2">
          {detail.payments.map(p => (
            <div key={p.id} className="px-5 py-2.5 flex items-center justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-green-700">{fmt(p.amount)}</span>
                  <span className="text-xs text-gray-400">·</span>
                  <span className="text-xs text-gray-500 capitalize">{p.payment_method}</span>
                  <span className="text-xs text-gray-400">·</span>
                  <span className="text-xs text-gray-500">{p.payment_date}</span>
                </div>
                {p.memo && <div className="text-xs text-gray-400 mt-0.5 truncate">{p.memo}</div>}
              </div>
              <button
                onClick={() => onDelete(p.id)}
                className="text-gray-300 hover:text-red-500 text-lg leading-none"
                title="Remove payment"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {(!detail.payments || detail.payments.length === 0) && (
        <div className="px-5 py-3 text-xs text-gray-400 italic">No payments recorded yet.</div>
      )}

      {/* Add payment form */}
      {!paidInFull && (
        <div className="px-5 py-4 bg-gray-50 border-t border-gray-100">
          <p className="text-xs font-semibold text-gray-500 mb-3">Record a Payment</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Amount *</label>
              <div className="relative">
                <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={paymentForm.amount}
                  onChange={e => setPaymentForm(f => ({ ...f, amount: e.target.value }))}
                  placeholder={balanceDue > 0 ? balanceDue.toFixed(2) : '0.00'}
                  className="w-full border border-gray-200 rounded-lg pl-7 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                  onFocus={e => { if (!paymentForm.amount && balanceDue > 0) setPaymentForm(f => ({ ...f, amount: balanceDue.toFixed(2) })) }}
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Method</label>
              <select
                value={paymentForm.payment_method}
                onChange={e => setPaymentForm(f => ({ ...f, payment_method: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
              >
                {PAYMENT_METHODS.map(m => (
                  <option key={m} value={m.toLowerCase().replace(/ /g, '_')}>{m}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Date Received</label>
              <input
                type="date"
                value={paymentForm.payment_date}
                onChange={e => setPaymentForm(f => ({ ...f, payment_date: e.target.value }))}
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Memo (optional)</label>
              <input
                type="text"
                value={paymentForm.memo}
                onChange={e => setPaymentForm(f => ({ ...f, memo: e.target.value }))}
                placeholder="Check #, note..."
                className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
              />
            </div>
          </div>
          <button
            onClick={onAdd}
            disabled={adding || !paymentForm.amount}
            className="mt-3 bg-green-600 text-white px-5 py-2 rounded-lg text-sm hover:bg-green-700 disabled:opacity-50 font-medium"
          >
            {adding ? 'Recording...' : 'Record Payment'}
          </button>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
function DaysComparison({ estimated, actual }) {
  if (!estimated && !actual) return null
  const diff   = actual && estimated ? actual - estimated : null
  const onTime = diff !== null && diff <= 0
  return (
    <div className="flex items-center gap-3 mt-2 flex-wrap">
      {estimated && (
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-gray-400">Estimated:</span>
          <span className="font-semibold text-gray-700">{estimated} day{estimated !== 1 ? 's' : ''}</span>
        </div>
      )}
      {actual > 0 && (
        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-gray-400">Actual:</span>
          <span className="font-semibold text-gray-700">{actual} day{actual !== 1 ? 's' : ''}</span>
        </div>
      )}
      {diff !== null && (
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${onTime ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
          {onTime ? (diff === 0 ? 'On estimate' : `${Math.abs(diff)} day${Math.abs(diff) !== 1 ? 's' : ''} under`) : `${diff} day${diff !== 1 ? 's' : ''} over`}
        </span>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
function TimeEntryRow({ entry, unlinked, onClaim, customerJobs, currentJobId, onReassign }) {
  const startTime = fmtTime(entry.start_time)
  const endTime   = fmtTime(entry.end_time)
  const timeRange = startTime && endTime ? `${startTime} – ${endTime}` : null
  const multiJob  = customerJobs && customerJobs.length > 1

  return (
    <div className={`px-5 py-3 flex items-center justify-between gap-4 ${unlinked ? 'bg-amber-50/40' : ''}`}>
      <div className="flex-1 min-w-0">
        <div className="text-sm text-gray-800 truncate">{entry.description || 'No description'}</div>
        <div className="text-xs text-gray-400 mt-0.5 flex items-center gap-2 flex-wrap">
          <span>{entry.entry_date}</span>
          {timeRange && <span>{timeRange}</span>}
          {entry.cost_code && (
            <span className="bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded text-xs">{entry.cost_code}</span>
          )}
          <span className={`px-1.5 py-0.5 rounded text-xs ${entry.source === 'busybusy' ? 'bg-purple-100 text-purple-600' : 'bg-gray-100 text-gray-500'}`}>
            {entry.source || 'manual'}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <div className="text-sm font-semibold text-gray-700 tabular-nums">
          {(entry.hours || 0).toFixed(2)}h
        </div>
        {multiJob && onReassign && (
          <select
            value={unlinked ? '' : String(currentJobId)}
            onChange={e => e.target.value !== '' && onReassign(entry.id, parseInt(e.target.value))}
            className="text-xs border border-gray-200 rounded px-1.5 py-1 text-gray-500 bg-white focus:outline-none focus:ring-1 focus:ring-blue-400 max-w-36"
          >
            {unlinked && <option value="">— assign to —</option>}
            {customerJobs.map(j => (
              <option key={j.job_id} value={String(j.job_id)}>{j.invoice_number}</option>
            ))}
          </select>
        )}
        {unlinked && !multiJob && onClaim && (
          <button
            onClick={onClaim}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium border border-blue-200 rounded px-2 py-1 hover:bg-blue-50"
          >
            Claim
          </button>
        )}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────
// Data Gaps Panel
// ─────────────────────────────────────────────────────────────────

function calcHoursFromTimes(arrive, depart) {
  if (!arrive || !depart) return 0
  const [ah, am] = arrive.split(':').map(Number)
  const [dh, dm] = depart.split(':').map(Number)
  const mins = (dh * 60 + dm) - (ah * 60 + am)
  return mins > 0 ? parseFloat((mins / 60).toFixed(2)) : 0
}

const OVERHEAD_CATEGORIES = [
  'Fuel & Transportation', 'Tools & Equipment', 'Equipment Repair',
  'Insurance', 'Licensing', 'Marketing', 'Office & Phone',
  'Clothing', 'Professional Development', 'Other',
]

function GapSectionHeader({ title, count, open, onToggle, colorClass }) {
  return (
    <button
      onClick={onToggle}
      className={`w-full flex items-center justify-between px-5 py-3 border-b border-gray-100 hover:bg-gray-50 transition-colors ${colorClass || ''}`}
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-700 uppercase tracking-wide">{title}</span>
        {count > 0 && (
          <span className="bg-amber-100 text-amber-700 text-xs font-bold rounded-full px-2 py-0">{count}</span>
        )}
        {count === 0 && (
          <span className="bg-green-100 text-green-700 text-xs font-medium rounded-full px-2 py-0">All clear</span>
        )}
      </div>
      <span className="text-gray-400 text-sm">{open ? '▲' : '▼'}</span>
    </button>
  )
}

function DataGapsPanel({
  gaps, loading, allJobs,
  hoursForm, setHoursForm,
  linkJob, setLinkJob,
  overheadForm, setOverheadForm,
  today, sections, setSections,
  refreshGaps,
}) {
  const [savingHours, setSavingHours] = useState({})
  const [markingIncomplete, setMarkingIncomplete] = useState({})
  const [linkingSaving, setLinkingSaving] = useState({})
  const [addingOverhead, setAddingOverhead] = useState(false)
  const [confirmingTrip, setConfirmingTrip] = useState({})

  function toggleSection(key) {
    setSections(prev => ({ ...prev, [key]: !prev[key] }))
  }

  // ── Section 1: Enter hours inline ────────────────────────────
  async function handleSaveHours(gap) {
    const form = hoursForm[gap.job_id] || {}
    if (!form.entry_date || !form.arrive_time || !form.depart_time) {
      alert('Please fill in date, arrive, and depart times.')
      return
    }
    setSavingHours(prev => ({ ...prev, [gap.job_id]: true }))
    try {
      const res = await fetch(`${API}/time-entries`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: gap.customer_id,
          job_id: gap.job_id,
          entry_date: form.entry_date,
          arrive_time: form.arrive_time,
          depart_time: form.depart_time,
        }),
      })
      if (!res.ok) throw new Error((await res.json()).error || 'Failed')
      setHoursForm(prev => { const n = { ...prev }; delete n[gap.job_id]; return n })
      refreshGaps()
    } catch (e) {
      alert('Error saving time entry: ' + e.message)
    } finally {
      setSavingHours(prev => ({ ...prev, [gap.job_id]: false }))
    }
  }

  async function handleMarkIncomplete(gap) {
    if (!window.confirm(`Mark "${gap.invoice_number}" as final but incomplete? This flags it has no time records.`)) return
    setMarkingIncomplete(prev => ({ ...prev, [gap.job_id]: true }))
    try {
      await fetch(`${API}/jobs/${gap.job_id}/mark-incomplete`, { method: 'POST' })
      refreshGaps()
    } catch {
      alert('Error marking incomplete')
    } finally {
      setMarkingIncomplete(prev => ({ ...prev, [gap.job_id]: false }))
    }
  }

  // ── Section 2: Link time entry ────────────────────────────────
  async function handleLinkEntry(entry) {
    const jobId = linkJob[entry.id]
    if (!jobId) { alert('Select a job to link to.'); return }
    setLinkingSaving(prev => ({ ...prev, [entry.id]: true }))
    try {
      const res = await fetch(`${API}/time-entries/${entry.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_id: parseInt(jobId) }),
      })
      if (!res.ok) throw new Error((await res.json()).error || 'Failed')
      setLinkJob(prev => { const n = { ...prev }; delete n[entry.id]; return n })
      refreshGaps()
    } catch (e) {
      alert('Error linking entry: ' + e.message)
    } finally {
      setLinkingSaving(prev => ({ ...prev, [entry.id]: false }))
    }
  }

  // ── Section 3: Add overhead expense ──────────────────────────
  async function handleAddOverhead(e) {
    e.preventDefault()
    if (!overheadForm.cost || !overheadForm.expense_category) {
      alert('Amount and category are required.')
      return
    }
    setAddingOverhead(true)
    try {
      const res = await fetch(`${API}/expenses`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          is_overhead: true,
          job_id: null,
          expense_date: overheadForm.expense_date,
          expense_category: overheadForm.expense_category,
          cost: parseFloat(overheadForm.cost),
          vendor: overheadForm.vendor,
          notes: overheadForm.notes,
        }),
      })
      if (!res.ok) throw new Error((await res.json()).error || 'Failed')
      setOverheadForm({ expense_date: today, expense_category: 'Fuel & Transportation', cost: '', vendor: '', notes: '' })
      refreshGaps()
    } catch (e) {
      alert('Error adding expense: ' + e.message)
    } finally {
      setAddingOverhead(false)
    }
  }

  // ── Section 4: Confirm / Skip trip ───────────────────────────
  async function handleConfirmTrip(teId) {
    setConfirmingTrip(prev => ({ ...prev, [teId]: 'confirming' }))
    try {
      await fetch(`${API}/suggested-trips/${teId}/confirm`, { method: 'POST' })
      refreshGaps()
    } catch {
      alert('Error confirming trip')
    } finally {
      setConfirmingTrip(prev => { const n = { ...prev }; delete n[teId]; return n })
    }
  }

  async function handleSkipTrip(teId) {
    setConfirmingTrip(prev => ({ ...prev, [teId]: 'skipping' }))
    try {
      await fetch(`${API}/suggested-trips/${teId}/skip`, { method: 'POST' })
      refreshGaps()
    } catch {
      alert('Error skipping trip')
    } finally {
      setConfirmingTrip(prev => { const n = { ...prev }; delete n[teId]; return n })
    }
  }

  if (loading) {
    return <div className="flex items-center justify-center h-64 text-gray-400 text-sm">Loading data gaps...</div>
  }

  if (!gaps) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-gray-400">
        <div className="text-lg font-medium">No data loaded</div>
        <div className="text-sm mt-1">Switch away and back to retry</div>
      </div>
    )
  }

  const missingTime = gaps.missing_time_entries || []
  const unlinked    = gaps.unlinked_time_entries || []
  const overhead    = gaps.overhead_gap || {}
  const suggested   = gaps.suggested_trips || []

  const totalGaps = missingTime.length + unlinked.length + suggested.length

  return (
    <div className="p-6 space-y-4 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Data Gaps</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            {totalGaps === 0
              ? 'No data gaps found — records look complete.'
              : `${totalGaps} item${totalGaps !== 1 ? 's' : ''} need attention`}
          </p>
        </div>
      </div>

      {/* ── Section 1: Invoices Missing Time Entries ─────────── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <GapSectionHeader
          title="Invoices Missing Time Entries"
          count={missingTime.length}
          open={sections.missing_time}
          onToggle={() => toggleSection('missing_time')}
        />
        {sections.missing_time && (
          missingTime.length === 0 ? (
            <div className="px-5 py-6 flex items-center gap-2 text-green-700">
              <span className="text-xl">&#10003;</span>
              <span className="text-sm font-medium">All invoices have time entries logged</span>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-100 text-xs text-gray-400 font-medium">
                    <th className="px-5 py-2 text-left">Invoice #</th>
                    <th className="px-3 py-2 text-left">Date</th>
                    <th className="px-3 py-2 text-left">Customer</th>
                    <th className="px-3 py-2 text-right">Billed</th>
                    <th className="px-3 py-2 text-center">Services</th>
                    <th className="px-5 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {missingTime.map(gap => {
                    const formOpen = !!hoursForm[gap.job_id]
                    const form = hoursForm[gap.job_id] || {}
                    const hrs = calcHoursFromTimes(form.arrive_time, form.depart_time)
                    return (
                      <Fragment key={gap.job_id}>
                        <tr className="hover:bg-gray-50">
                          <td className="px-5 py-3 font-mono text-gray-700">{gap.invoice_number || `#${gap.job_id}`}</td>
                          <td className="px-3 py-3 text-gray-500">{gap.invoice_date || ''}</td>
                          <td className="px-3 py-3 text-gray-700">{gap.customer_name}</td>
                          <td className="px-3 py-3 text-right tabular-nums text-gray-700">{fmt(gap.total_amount)}</td>
                          <td className="px-3 py-3 text-center text-gray-500">{gap.service_count || 0}</td>
                          <td className="px-5 py-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <button
                                onClick={() => setHoursForm(prev => {
                                  const n = { ...prev }
                                  if (n[gap.job_id]) { delete n[gap.job_id] }
                                  else { n[gap.job_id] = { entry_date: today, arrive_time: '', depart_time: '' } }
                                  return n
                                })}
                                className="text-xs border border-blue-300 text-blue-600 rounded px-2.5 py-1 hover:bg-blue-50 font-medium"
                              >
                                {formOpen ? 'Cancel' : 'Enter Hours'}
                              </button>
                              <button
                                onClick={() => handleMarkIncomplete(gap)}
                                disabled={markingIncomplete[gap.job_id]}
                                className="text-xs border border-amber-300 text-amber-600 rounded px-2.5 py-1 hover:bg-amber-50 font-medium disabled:opacity-50"
                              >
                                {markingIncomplete[gap.job_id] ? 'Marking...' : 'Mark Final (Incomplete)'}
                              </button>
                            </div>
                          </td>
                        </tr>
                        {formOpen && (
                          <tr className="bg-blue-50/40">
                            <td colSpan={6} className="px-5 py-3">
                              <div className="flex items-end gap-3 flex-wrap">
                                <div>
                                  <label className="block text-xs text-gray-500 mb-1">Date</label>
                                  <input
                                    type="date"
                                    value={form.entry_date || today}
                                    onChange={e => setHoursForm(prev => ({ ...prev, [gap.job_id]: { ...prev[gap.job_id], entry_date: e.target.value } }))}
                                    className="border border-gray-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white"
                                  />
                                </div>
                                <div>
                                  <label className="block text-xs text-gray-500 mb-1">Arrive</label>
                                  <input
                                    type="time"
                                    value={form.arrive_time || ''}
                                    onChange={e => setHoursForm(prev => ({ ...prev, [gap.job_id]: { ...prev[gap.job_id], arrive_time: e.target.value } }))}
                                    className="border border-gray-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white"
                                  />
                                </div>
                                <div>
                                  <label className="block text-xs text-gray-500 mb-1">Depart</label>
                                  <input
                                    type="time"
                                    value={form.depart_time || ''}
                                    onChange={e => setHoursForm(prev => ({ ...prev, [gap.job_id]: { ...prev[gap.job_id], depart_time: e.target.value } }))}
                                    className="border border-gray-200 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500 bg-white"
                                  />
                                </div>
                                {hrs > 0 && (
                                  <div className="text-sm text-gray-600 font-medium pb-1.5">{hrs}h</div>
                                )}
                                <button
                                  onClick={() => handleSaveHours(gap)}
                                  disabled={savingHours[gap.job_id]}
                                  className="bg-blue-600 text-white px-4 py-1.5 rounded text-sm hover:bg-blue-700 disabled:opacity-50 font-medium"
                                >
                                  {savingHours[gap.job_id] ? 'Saving...' : 'Save'}
                                </button>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )
        )}
      </div>

      {/* ── Section 2: Unlinked Time Entries ─────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <GapSectionHeader
          title="Unlinked Time Entries"
          count={unlinked.length}
          open={sections.unlinked}
          onToggle={() => toggleSection('unlinked')}
        />
        {sections.unlinked && (
          unlinked.length === 0 ? (
            <div className="px-5 py-6 text-sm text-gray-500">All time entries are linked to jobs</div>
          ) : (
            <div className="divide-y divide-gray-50">
              {unlinked.map(entry => {
                const customerJobs = allJobs.filter(j => j.customer_id === entry.customer_id)
                return (
                  <div key={entry.id} className="px-5 py-3 flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-gray-800 truncate">
                        {entry.description || entry.busybusy_project || 'No description'}
                      </div>
                      <div className="text-xs text-gray-400 mt-0.5 flex items-center gap-2 flex-wrap">
                        <span>{entry.entry_date}</span>
                        <span className="text-gray-300">·</span>
                        <span className="font-medium text-gray-600">{entry.customer_name}</span>
                        <span className="text-gray-300">·</span>
                        <span>{(entry.hours || 0).toFixed(2)}h</span>
                        {entry.start_time && entry.end_time && (
                          <span>{fmtTime(entry.start_time)} – {fmtTime(entry.end_time)}</span>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {customerJobs.length > 0 ? (
                        <>
                          <select
                            value={linkJob[entry.id] || ''}
                            onChange={e => setLinkJob(prev => ({ ...prev, [entry.id]: e.target.value }))}
                            className="text-xs border border-gray-200 rounded px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-blue-400 max-w-44"
                          >
                            <option value="">-- select job --</option>
                            {customerJobs.map(j => (
                              <option key={j.job_id} value={j.job_id}>
                                {j.invoice_number || `#${j.job_id}`}
                              </option>
                            ))}
                          </select>
                          <button
                            onClick={() => handleLinkEntry(entry)}
                            disabled={linkingSaving[entry.id] || !linkJob[entry.id]}
                            className="text-xs bg-blue-600 text-white rounded px-3 py-1.5 hover:bg-blue-700 disabled:opacity-50 font-medium"
                          >
                            {linkingSaving[entry.id] ? 'Linking...' : 'Link'}
                          </button>
                        </>
                      ) : (
                        <span className="text-xs text-gray-400 italic">No jobs for this customer</span>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )
        )}
      </div>

      {/* ── Section 3: Overhead Expenses ─────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <GapSectionHeader
          title="Overhead Expenses"
          count={overhead.zero_overhead_weeks > 2 ? 1 : 0}
          open={sections.overhead}
          onToggle={() => toggleSection('overhead')}
        />
        {sections.overhead && (
          <div className="p-5 space-y-4">
            {overhead.zero_overhead_weeks > 2 && (
              <div className="flex items-center gap-2 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
                <span className="text-amber-600 font-bold text-lg">!</span>
                <span className="text-sm text-amber-700 font-medium">
                  No overhead expenses logged in {overhead.zero_overhead_weeks} week{overhead.zero_overhead_weeks !== 1 ? 's' : ''}
                  {overhead.last_overhead_date ? ` (last: ${overhead.last_overhead_date})` : ''}
                </span>
              </div>
            )}
            <form onSubmit={handleAddOverhead}>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">Quick-Add Overhead Expense</p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Date</label>
                  <input
                    type="date"
                    value={overheadForm.expense_date}
                    onChange={e => setOverheadForm(f => ({ ...f, expense_date: e.target.value }))}
                    className={INPUT}
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Category</label>
                  <select
                    value={overheadForm.expense_category}
                    onChange={e => setOverheadForm(f => ({ ...f, expense_category: e.target.value }))}
                    className={INPUT}
                  >
                    {OVERHEAD_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Amount ($) *</label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">$</span>
                    <input
                      type="number"
                      step="0.01"
                      min="0.01"
                      value={overheadForm.cost}
                      onChange={e => setOverheadForm(f => ({ ...f, cost: e.target.value }))}
                      placeholder="0.00"
                      className="w-full border border-gray-200 rounded-lg pl-7 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Vendor</label>
                  <input
                    type="text"
                    value={overheadForm.vendor}
                    onChange={e => setOverheadForm(f => ({ ...f, vendor: e.target.value }))}
                    placeholder="Home Depot, Shell, etc."
                    className={INPUT}
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-xs text-gray-400 mb-1">Notes (optional)</label>
                  <input
                    type="text"
                    value={overheadForm.notes}
                    onChange={e => setOverheadForm(f => ({ ...f, notes: e.target.value }))}
                    placeholder="Brief description..."
                    className={INPUT}
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={addingOverhead || !overheadForm.cost}
                className="mt-3 bg-blue-600 text-white px-5 py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50 font-medium"
              >
                {addingOverhead ? 'Adding...' : 'Add Expense'}
              </button>
            </form>
          </div>
        )}
      </div>

      {/* ── Section 4: Suggested Trips ───────────────────────── */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <GapSectionHeader
          title="Suggested Trips"
          count={suggested.length}
          open={sections.suggested}
          onToggle={() => toggleSection('suggested')}
        />
        {sections.suggested && (
          suggested.length === 0 ? (
            <div className="px-5 py-6 flex items-center gap-2 text-green-700">
              <span className="text-xl">&#10003;</span>
              <span className="text-sm font-medium">No trip suggestions — all clear</span>
            </div>
          ) : (
            <>
              <div className="divide-y divide-gray-50">
                {suggested.map(trip => (
                  <div key={trip.time_entry_id} className="px-5 py-3 flex items-center justify-between gap-4 flex-wrap">
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-gray-800">{trip.customer_name}</div>
                      <div className="text-xs text-gray-400 mt-0.5 flex items-center gap-2 flex-wrap">
                        <span>{trip.entry_date}</span>
                        <span className="text-gray-300">·</span>
                        <span className="font-semibold text-gray-600">{trip.mileage_from_home} mi one-way</span>
                        <span className="text-gray-300">·</span>
                        <span>{(trip.hours || 0).toFixed(1)}h worked</span>
                        {trip.start_time && trip.end_time && (
                          <>
                            <span className="text-gray-300">·</span>
                            <span>{fmtTime(trip.start_time)} – {fmtTime(trip.end_time)}</span>
                          </>
                        )}
                      </div>
                      {trip.customer_address && (
                        <div className="text-xs text-gray-400 mt-0.5 truncate">{trip.customer_address}</div>
                      )}
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <button
                        onClick={() => handleConfirmTrip(trip.time_entry_id)}
                        disabled={!!confirmingTrip[trip.time_entry_id]}
                        className="text-xs bg-green-600 text-white rounded px-3 py-1.5 hover:bg-green-700 disabled:opacity-50 font-medium"
                      >
                        {confirmingTrip[trip.time_entry_id] === 'confirming' ? 'Confirming...' : 'Confirm Trip'}
                      </button>
                      <button
                        onClick={() => handleSkipTrip(trip.time_entry_id)}
                        disabled={!!confirmingTrip[trip.time_entry_id]}
                        className="text-xs text-gray-400 hover:text-gray-600 rounded px-2 py-1.5 font-medium disabled:opacity-50"
                      >
                        {confirmingTrip[trip.time_entry_id] === 'skipping' ? 'Skipping...' : 'Skip'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="px-5 py-3 bg-gray-50 border-t border-gray-100">
                <p className="text-xs text-gray-400">
                  Only showing jobs where mileage has been calculated.{' '}
                  <Link to="/customers" className="text-blue-500 hover:underline">Go to Customers</Link>{' '}
                  to calculate mileage for more customers.
                </p>
              </div>
            </>
          )
        )}
      </div>
    </div>
  )
}
