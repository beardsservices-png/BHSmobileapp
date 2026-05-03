import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'

const LS_CLOCK = 'bhs_clock_v1'

function fmtElapsed(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
}

function ClockBanner() {
  const navigate = useNavigate()
  const [session, setSession] = useState(null)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_CLOCK)
      if (raw) setSession(JSON.parse(raw))
    } catch {}
  }, [])

  useEffect(() => {
    if (!session) return
    const iv = setInterval(() => setElapsed(Math.floor((Date.now() - session.startTs) / 1000)), 1000)
    return () => clearInterval(iv)
  }, [session])

  if (!session) return null

  return (
    <button
      onClick={() => navigate('/clock')}
      className="w-full flex items-center gap-3 bg-green-500 hover:bg-green-600 text-white px-4 py-3 rounded-xl transition-colors"
    >
      <span className="w-2.5 h-2.5 bg-white rounded-full animate-pulse shrink-0" />
      <div className="flex-1 text-left min-w-0">
        <span className="font-semibold">Clocked in</span>
        <span className="mx-2 opacity-70">—</span>
        <span className="truncate">{session.customer?.name}</span>
      </div>
      <span className="font-mono font-bold tabular-nums shrink-0">{fmtElapsed(elapsed)}</span>
      <svg className="w-4 h-4 opacity-70 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
      </svg>
    </button>
  )
}
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

const fmt  = n => `$${(n || 0).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
const fmtD = n => `$${(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
const fmtH = n => `${(n || 0).toFixed(1)}h`

function getRange(preset) {
  const now = new Date()
  const pad = n => String(n).padStart(2, '0')
  const fmtDate = d => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`
  if (preset === 'week') {
    const start = new Date(now); start.setDate(now.getDate() - now.getDay())
    return { start: fmtDate(start), end: fmtDate(now) }
  }
  if (preset === 'month') {
    return { start: `${now.getFullYear()}-${pad(now.getMonth()+1)}-01`, end: fmtDate(now) }
  }
  if (preset === 'quarter') {
    const q = Math.floor(now.getMonth() / 3)
    const qStart = new Date(now.getFullYear(), q * 3, 1)
    return { start: fmtDate(qStart), end: fmtDate(now) }
  }
  if (preset === 'year') {
    return { start: `${now.getFullYear()}-01-01`, end: fmtDate(now) }
  }
  return { start: null, end: null } // all time
}

function getRangeLabel(preset, customStart, customEnd) {
  const now = new Date()
  if (preset === 'week') return 'This Week'
  if (preset === 'month') {
    return now.toLocaleString('default', { month: 'long', year: 'numeric' })
  }
  if (preset === 'quarter') {
    const q = Math.floor(now.getMonth() / 3) + 1
    return `Q${q} ${now.getFullYear()}`
  }
  if (preset === 'year') return `${now.getFullYear()}`
  if (preset === 'custom' && customStart && customEnd) return `${customStart} to ${customEnd}`
  return null
}

export default function Dashboard() {
  const [stats, setStats]       = useState(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState(null)
  const [activePreset, setActivePreset] = useState('all')
  const [customStart, setCustomStart]   = useState('')
  const [customEnd, setCustomEnd]       = useState('')

  const fetchDashboard = useCallback((start, end) => {
    setLoading(true)
    let url = '/api/dashboard'
    if (start && end) url += `?start=${start}&end=${end}`
    fetch(url)
      .then(r => r.json())
      .then(data => { setStats(data); setLoading(false) })
      .catch(err => { setError(err.message); setLoading(false) })
  }, [])

  useEffect(() => {
    fetchDashboard(null, null)
  }, [fetchDashboard])

  function handlePreset(preset) {
    setActivePreset(preset)
    setCustomStart('')
    setCustomEnd('')
    const range = getRange(preset)
    fetchDashboard(range.start, range.end)
  }

  function handleCustomApply() {
    if (customStart && customEnd) {
      setActivePreset('custom')
      fetchDashboard(customStart, customEnd)
    }
  }

  const rangeLabel = getRangeLabel(activePreset, customStart, customEnd)

  const useMonthChart = activePreset !== 'all' && stats?.revenue_by_month?.length > 0
  const chartData = useMonthChart ? stats.revenue_by_month : stats?.revenue_by_year
  const chartKey  = useMonthChart ? 'month' : 'year'

  if (error) return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">Error: {error}</div>
  )

  const est = stats?.estimation_accuracy || {}

  const presets = [
    { key: 'week',    label: 'This Week' },
    { key: 'month',   label: 'This Month' },
    { key: 'quarter', label: 'This Quarter' },
    { key: 'year',    label: 'This Year' },
    { key: 'all',     label: 'All Time' },
  ]

  return (
    <div className="space-y-6">

      <ClockBanner />

      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">
          Dashboard
          {rangeLabel && (
            <span className="ml-2 text-lg font-normal text-gray-500">— {rangeLabel}</span>
          )}
        </h1>
        <div className="text-sm text-gray-500">Beard's Home Services</div>
      </div>

      {/* Date Range Filter Bar */}
      <div className="bg-white rounded-xl border border-gray-200 px-4 py-3 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5 flex-wrap">
          {presets.map(p => (
            <button
              key={p.key}
              onClick={() => handlePreset(p.key)}
              className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                activePreset === p.key
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <input
            type="date"
            value={customStart}
            onChange={e => setCustomStart(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <span className="text-gray-400 text-sm">to</span>
          <input
            type="date"
            value={customEnd}
            onChange={e => setCustomEnd(e.target.value)}
            className="text-sm border border-gray-200 rounded-lg px-2 py-1.5 text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <button
            onClick={handleCustomApply}
            disabled={!customStart || !customEnd}
            className="text-sm px-3 py-1.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Apply
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64 text-gray-500">Loading dashboard...</div>
      ) : (
        <>
          {/* Primary KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Labor Revenue"  value={fmt(stats?.total_labor)}     color="green" />
            <StatCard label="Avg $/Hour"     value={fmtD(stats?.avg_hourly_rate)} color="blue"  />
            <StatCard label="Hours Tracked"  value={fmtH(stats?.total_hours)}    color="purple"/>
            <StatCard label="Avg Days / Job" value={`${stats?.avg_days_per_job || 0} days`} color="amber" />
          </div>

          {/* Secondary counters */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Customers"     value={stats?.customer_count || 0}  small />
            <StatCard label="Jobs"          value={stats?.job_count || 0}        small />
            <StatCard label="Invoices"      value={stats?.invoice_count || 0}    small />
            <StatCard label="Materials"     value={fmt(stats?.total_materials)}  small />
          </div>

          {/* Estimation accuracy banner */}
          {est.jobs_with_estimates > 0 && (
            <div className="bg-blue-50 border border-blue-200 rounded-xl p-5">
              <h2 className="text-sm font-semibold text-blue-900 mb-3">Estimation Accuracy</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
                <div>
                  <div className="text-2xl font-bold text-blue-800">{est.jobs_with_estimates}</div>
                  <div className="text-xs text-blue-600 mt-0.5">Jobs with estimates</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-blue-800">
                    {est.jobs_with_estimates > 0
                      ? `${Math.round((est.on_time / est.jobs_with_estimates) * 100)}%`
                      : '—'}
                  </div>
                  <div className="text-xs text-blue-600 mt-0.5">On or under estimate</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-blue-800">{est.avg_estimated_days ?? '—'}</div>
                  <div className="text-xs text-blue-600 mt-0.5">Avg estimated days</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-blue-800">{est.avg_actual_days ?? '—'}</div>
                  <div className="text-xs text-blue-600 mt-0.5">Avg actual days</div>
                </div>
              </div>
            </div>
          )}

          {/* Revenue chart — monthly when filtered, yearly for all time */}
          {chartData?.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-base font-semibold text-gray-800 mb-4">
                {useMonthChart ? 'Revenue by Month' : 'Revenue by Year'}
              </h2>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={chartData} barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey={chartKey} tick={{ fontSize: 12 }} />
                  <YAxis tickFormatter={v => `$${(v/1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={v => fmtD(v)} />
                  <Bar dataKey="total_labor"     name="Labor"     fill="#22c55e" radius={[4,4,0,0]} />
                  <Bar dataKey="total_materials" name="Materials" fill="#e5e7eb" radius={[4,4,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Two-column: Recent jobs + Top customers */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">

            {/* Recent jobs */}
            <div className="bg-white rounded-xl border border-gray-200">
              <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
                <h2 className="text-base font-semibold text-gray-800">Recent Jobs</h2>
                <Link to="/filing-cabinet" className="text-sm text-blue-600 hover:text-blue-800">View all →</Link>
              </div>
              <div className="divide-y divide-gray-50">
                {(stats?.recent_jobs || []).slice(0, 8).map(job => (
                  <Link
                    key={job.id}
                    to={`/filing-cabinet?job=${job.id}`}
                    className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 transition-colors"
                  >
                    <div className="min-w-0">
                      <div className="font-medium text-gray-900 text-sm truncate">{job.customer_name}</div>
                      <div className="text-xs text-gray-400 flex items-center gap-2 mt-0.5">
                        <span>{job.start_date}</span>
                        {job.actual_days > 0 && <span>· {job.actual_days}d on site</span>}
                      </div>
                    </div>
                    <div className="text-right flex-shrink-0 ml-3">
                      <div className="text-sm font-semibold text-gray-900">{fmt(job.total_labor)}</div>
                      <StatusBadge status={job.status} />
                    </div>
                  </Link>
                ))}
                {(!stats?.recent_jobs || stats.recent_jobs.length === 0) && (
                  <div className="px-5 py-8 text-center text-gray-400 text-sm">No jobs yet</div>
                )}
              </div>
            </div>

            {/* Top customers */}
            <div className="bg-white rounded-xl border border-gray-200">
              <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
                <h2 className="text-base font-semibold text-gray-800">Top Customers</h2>
                <Link to="/customers" className="text-sm text-blue-600 hover:text-blue-800">View all →</Link>
              </div>
              <div className="divide-y divide-gray-50">
                {(stats?.top_customers || []).map((c, i) => (
                  <div key={c.id} className="flex items-center justify-between px-5 py-3 hover:bg-gray-50">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-xs font-bold text-gray-300 w-4">{i + 1}</span>
                      <div className="min-w-0">
                        <div className="font-medium text-gray-900 text-sm truncate">{c.name}</div>
                        <div className="text-xs text-gray-400">
                          {c.job_count} job{c.job_count !== 1 ? 's' : ''}
                          {c.total_hours > 0 && ` · ${fmtH(c.total_hours)}`}
                        </div>
                      </div>
                    </div>
                    <div className="text-sm font-semibold text-gray-900 flex-shrink-0 ml-3">
                      {fmt(c.total_revenue)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Revenue by service category */}
          {stats?.revenue_by_category?.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200">
              <div className="px-5 py-4 border-b border-gray-100">
                <h2 className="text-base font-semibold text-gray-800">Revenue by Service Type</h2>
              </div>
              <div className="divide-y divide-gray-50">
                {stats.revenue_by_category.map(cat => {
                  const pct = stats.total_labor > 0
                    ? Math.round((cat.total_revenue / stats.total_labor) * 100)
                    : 0
                  return (
                    <div key={cat.category} className="px-5 py-3 flex items-center gap-4">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-gray-800 truncate">{cat.category}</span>
                          <div className="flex items-center gap-3 flex-shrink-0 ml-3 text-xs text-gray-500">
                            <span>{cat.job_count} job{cat.job_count !== 1 ? 's' : ''}</span>
                            <span className="font-semibold text-gray-900">{fmt(cat.total_revenue)}</span>
                          </div>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-1.5">
                          <div
                            className="bg-blue-500 h-1.5 rounded-full"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function StatCard({ label, value, color = 'gray', small = false }) {
  const colors = {
    blue:   'bg-blue-50 text-blue-700',
    green:  'bg-green-50 text-green-700',
    purple: 'bg-purple-50 text-purple-700',
    amber:  'bg-amber-50 text-amber-700',
    gray:   'bg-gray-50 text-gray-700',
  }
  return (
    <div className={`rounded-xl p-4 ${small ? 'bg-gray-50' : colors[color] || colors.gray}`}>
      <div className={`font-bold ${small ? 'text-xl text-gray-900' : 'text-2xl'}`}>{value}</div>
      <div className={`text-xs mt-1 ${small ? 'text-gray-500' : 'opacity-75'}`}>{label}</div>
    </div>
  )
}

function StatusBadge({ status }) {
  const map = {
    completed: 'bg-green-100 text-green-700',
    paid:      'bg-green-100 text-green-700',
    pending:   'bg-yellow-100 text-yellow-700',
    estimate:  'bg-blue-100 text-blue-700',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium mt-0.5 inline-block ${map[status] || 'bg-gray-100 text-gray-600'}`}>
      {status}
    </span>
  )
}
