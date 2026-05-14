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
  const [activePreset, setActivePreset] = useState('month')
  const [insights, setInsights]         = useState(null)
  const [insightsLoading, setInsightsLoading] = useState(false)
  const [insightsError, setInsightsError]     = useState(null)
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
    const range = getRange('month')
    fetchDashboard(range.start, range.end)
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

  async function loadInsights(force = false) {
    setInsightsLoading(true)
    setInsightsError(null)
    try {
      const r = await fetch(`/api/insights${force ? '?force=1' : ''}`)
      const data = await r.json()
      if (data.available === false) {
        setInsightsError(data.error || 'Claude API not available')
      } else {
        setInsights(data)
      }
    } catch (e) {
      setInsightsError('Failed to load insights')
    } finally {
      setInsightsLoading(false)
    }
  }

  const rangeLabel = getRangeLabel(activePreset, customStart, customEnd)

  const useMonthChart = activePreset !== 'all' && stats?.revenue_by_month?.length > 0

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
            <StatCard label="Profit"         value={fmt(stats?.total_profit)}     color="green" />
            <StatCard label="Avg $/Hour"     value={fmtD(stats?.avg_hourly_rate)} color="blue"  />
            <StatCard label="Hours Tracked"  value={fmtH(stats?.total_hours)}    color="purple"/>
            <StatCard label="Avg Days / Job" value={`${stats?.avg_days_per_job || 0} days`} color="amber" />
          </div>

          {/* Secondary counters */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Revenue"   value={fmt(stats?.total_revenue)}  small />
            <StatCard label="Expenses"  value={fmt(stats?.total_expenses)} small />
            <StatCard label="Jobs"      value={stats?.job_count || 0}      small />
            <StatCard label="Customers" value={stats?.customer_count || 0} small />
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

          {/* Revenue chart — monthly data only (no "revenue by year" chart) */}
          {useMonthChart && stats.revenue_by_month.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-base font-semibold text-gray-800 mb-4">Revenue by Month</h2>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={stats.revenue_by_month} barGap={4}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="month" tick={{ fontSize: 12 }} />
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

          {/* Business Health Panel */}
          {stats && (
            <BusinessHealth stats={stats} rangeLabel={rangeLabel} />
          )}

          {/* ── Business Insights ──────────────────────────────────────── */}
          <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
              <div>
                <h2 className="text-base font-semibold text-gray-800">Business Insights</h2>
                <p className="text-xs text-gray-400 mt-0.5">AI analysis of your last 24 months of data</p>
              </div>
              <div className="flex gap-2">
                {insights && (
                  <button
                    onClick={() => loadInsights(true)}
                    disabled={insightsLoading}
                    className="text-xs text-gray-500 hover:text-gray-700 px-3 py-1.5 rounded-lg hover:bg-gray-100 disabled:opacity-40"
                  >
                    Refresh
                  </button>
                )}
                {!insights && (
                  <button
                    onClick={() => loadInsights(false)}
                    disabled={insightsLoading}
                    className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                  >
                    {insightsLoading ? (
                      <>
                        <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        Analyzing...
                      </>
                    ) : (
                      <>&#10024; Get Insights</>
                    )}
                  </button>
                )}
              </div>
            </div>

            {!insights && !insightsLoading && !insightsError && (
              <div className="px-5 py-10 text-center text-gray-400">
                <div className="text-3xl mb-2">&#128200;</div>
                <div className="text-sm font-medium text-gray-500 mb-1">Ready to analyze your business</div>
                <div className="text-xs text-gray-400">Looks at seasonal trends, pricing gaps, slow seasons, and repeat customer opportunities</div>
              </div>
            )}

            {insightsLoading && (
              <div className="px-5 py-10 text-center text-gray-400">
                <div className="w-8 h-8 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
                <div className="text-sm text-gray-500">Reading 24 months of your data...</div>
              </div>
            )}

            {insightsError && (
              <div className="px-5 py-6 text-center">
                <div className="text-sm text-red-600 mb-2">{insightsError}</div>
                {insightsError.includes('ANTHROPIC_API_KEY') && (
                  <div className="text-xs text-gray-400">Set the ANTHROPIC_API_KEY environment variable to enable this feature.</div>
                )}
              </div>
            )}

            {insights?.insights && (
              <>
                {insights.summary && (
                  <div className="flex gap-6 px-5 py-3 bg-indigo-50 border-b border-indigo-100 text-xs text-indigo-700">
                    <span><strong>{insights.summary.jobs}</strong> jobs analyzed</span>
                    <span>Revenue <strong>{fmt(insights.summary.revenue)}</strong></span>
                    <span>Profit <strong>{fmt(insights.summary.profit)}</strong></span>
                    {insights.summary.busiest?.length > 0 && (
                      <span>Busiest: <strong>{insights.summary.busiest.join(', ')}</strong></span>
                    )}
                  </div>
                )}
                <div className="divide-y divide-gray-50">
                  {insights.insights.map((ins, i) => (
                    <InsightCard key={i} insight={ins} />
                  ))}
                </div>
                <div className="px-5 py-3 bg-gray-50 border-t border-gray-100 text-xs text-gray-400 text-right">
                  Generated by Claude · cached 1 hour ·{' '}
                  <button onClick={() => loadInsights(true)} className="underline hover:text-gray-600">regenerate</button>
                </div>
              </>
            )}
          </div>
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

function BusinessHealth({ stats, rangeLabel }) {
  const revenue = stats.total_revenue || 0
  const expenses = stats.total_expenses || 0
  const profit = stats.total_profit || 0
  const jobs = stats.job_count || 0
  const hours = stats.total_hours || 0
  const rate = stats.avg_hourly_rate || 0

  const profitPct = revenue > 0 ? Math.round((profit / revenue) * 100) : null
  const expensePct = revenue > 0 ? Math.round((expenses / revenue) * 100) : null
  const revenuePerJob = jobs > 0 ? revenue / jobs : null
  const profitPerJob = jobs > 0 ? profit / jobs : null
  const TARGET_RATE = 50

  // Profit margin color
  const marginColor = profitPct === null ? 'text-gray-400'
    : profitPct >= 60 ? 'text-green-600'
    : profitPct >= 40 ? 'text-yellow-600'
    : 'text-red-600'

  // Rate vs target
  const rateColor = rate >= TARGET_RATE ? 'text-green-600' : rate > 0 ? 'text-red-600' : 'text-gray-400'

  if (revenue === 0) return null

  return (
    <div className="bg-white rounded-xl border border-gray-200">
      <div className="px-5 py-4 border-b border-gray-100">
        <h2 className="text-base font-semibold text-gray-800">Business Health</h2>
        {rangeLabel && <p className="text-xs text-gray-400 mt-0.5">{rangeLabel}</p>}
      </div>
      <div className="p-5 space-y-4">

        {/* Margin + rate row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-gray-50 rounded-xl p-4 text-center">
            <div className={`text-2xl font-bold ${marginColor}`}>
              {profitPct !== null ? `${profitPct}%` : '—'}
            </div>
            <div className="text-xs text-gray-500 mt-1">Profit Margin</div>
            {profitPct !== null && profitPct < 40 && (
              <div className="text-xs text-red-500 mt-1">Below target (40%)</div>
            )}
          </div>
          <div className="bg-gray-50 rounded-xl p-4 text-center">
            <div className={`text-2xl font-bold ${rateColor}`}>
              {rate > 0 ? `$${Math.round(rate)}` : '—'}
            </div>
            <div className="text-xs text-gray-500 mt-1">Hourly Rate</div>
            {rate > 0 && rate < TARGET_RATE && (
              <div className="text-xs text-red-500 mt-1">Below ${TARGET_RATE}/hr target</div>
            )}
          </div>
          <div className="bg-gray-50 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-gray-800">
              {expensePct !== null ? `${expensePct}%` : '—'}
            </div>
            <div className="text-xs text-gray-500 mt-1">Expense Ratio</div>
            {expensePct !== null && expensePct > 30 && (
              <div className="text-xs text-amber-600 mt-1">High — review costs</div>
            )}
          </div>
          <div className="bg-gray-50 rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-gray-800">
              {revenuePerJob !== null ? fmt(revenuePerJob) : '—'}
            </div>
            <div className="text-xs text-gray-500 mt-1">Revenue / Job</div>
          </div>
        </div>

        {/* Service breakdown — jobs + revenue per type, sorted by revenue */}
        {stats.revenue_by_category?.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">Revenue by Service</h3>
            <div className="space-y-2">
              {stats.revenue_by_category.slice(0, 6).map(cat => {
                const pct = revenue > 0 ? (cat.total_revenue / revenue) * 100 : 0
                const avgPerJob = cat.job_count > 0 ? cat.total_revenue / cat.job_count : 0
                return (
                  <div key={cat.category}>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-gray-700 truncate flex-1 mr-2">{cat.category}</span>
                      <div className="flex items-center gap-3 text-gray-500 flex-shrink-0">
                        <span>{cat.job_count} job{cat.job_count !== 1 ? 's' : ''}</span>
                        <span className="text-gray-400">{fmt(avgPerJob)}/job</span>
                        <span className="font-semibold text-gray-800 w-16 text-right">{fmt(cat.total_revenue)}</span>
                      </div>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div className="bg-green-500 h-1.5 rounded-full" style={{ width: `${Math.min(pct, 100)}%` }} />
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}

        {/* Actionable flags */}
        {(profitPct !== null && profitPct < 40) || (rate > 0 && rate < TARGET_RATE) || (expensePct !== null && expensePct > 30) ? (
          <div className="border-t border-gray-100 pt-4">
            <h3 className="text-xs font-semibold text-amber-700 uppercase tracking-wide mb-2">Things to watch</h3>
            <div className="space-y-1.5">
              {rate > 0 && rate < TARGET_RATE && (
                <div className="flex items-start gap-2 text-xs text-gray-600">
                  <span className="text-red-500 mt-0.5">&#8599;</span>
                  <span>Your effective rate is <strong>${Math.round(rate)}/hr</strong> — raise prices or reduce low-value jobs to hit ${TARGET_RATE}/hr.</span>
                </div>
              )}
              {profitPct !== null && profitPct < 40 && (
                <div className="flex items-start gap-2 text-xs text-gray-600">
                  <span className="text-amber-500 mt-0.5">&#8599;</span>
                  <span>Profit margin is <strong>{profitPct}%</strong> — check expenses in the Expenses page for anything to cut.</span>
                </div>
              )}
              {expensePct !== null && expensePct > 30 && (
                <div className="flex items-start gap-2 text-xs text-gray-600">
                  <span className="text-amber-500 mt-0.5">&#8599;</span>
                  <span>Expenses are <strong>{expensePct}%</strong> of revenue this period — review materials and supply runs.</span>
                </div>
              )}
            </div>
          </div>
        ) : null}

      </div>
    </div>
  )
}

function InsightCard({ insight }) {
  const typeStyles = {
    seasonal:   { badge: 'bg-blue-100 text-blue-700',   icon: '&#127793;' },
    pricing:    { badge: 'bg-green-100 text-green-700',  icon: '&#128176;' },
    marketing:  { badge: 'bg-purple-100 text-purple-700',icon: '&#128227;' },
    focus:      { badge: 'bg-amber-100 text-amber-700',  icon: '&#127919;' },
    efficiency: { badge: 'bg-teal-100 text-teal-700',    icon: '&#9889;'   },
    warning:    { badge: 'bg-red-100 text-red-700',      icon: '&#9888;'   },
  }
  const priority = {
    high:   'bg-red-500',
    medium: 'bg-yellow-400',
    low:    'bg-gray-300',
  }
  const style = typeStyles[insight.type] || typeStyles.focus

  return (
    <div className="px-5 py-4">
      <div className="flex items-start gap-3">
        <span className="text-xl mt-0.5 shrink-0" dangerouslySetInnerHTML={{ __html: style.icon }} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${style.badge}`}>
              {insight.type}
            </span>
            <span className={`w-2 h-2 rounded-full shrink-0 ${priority[insight.priority] || priority.low}`} title={`${insight.priority} priority`} />
            <h3 className="text-sm font-semibold text-gray-900">{insight.title}</h3>
          </div>
          <p className="text-sm text-gray-600 mb-2">{insight.insight}</p>
          <div className="flex items-start gap-2 bg-indigo-50 border border-indigo-100 rounded-lg px-3 py-2">
            <span className="text-indigo-500 font-bold text-xs shrink-0 mt-0.5">ACTION</span>
            <p className="text-xs text-indigo-800">{insight.action}</p>
          </div>
        </div>
      </div>
    </div>
  )
}
