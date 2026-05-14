import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'

export default function Jobs() {
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const navigate = useNavigate()

  useEffect(() => {
    fetch('/api/jobs')
      .then(r => r.json())
      .then(data => { setJobs(Array.isArray(data) ? data : []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const filtered = jobs.filter(j => {
    const matchSearch = !search ||
      (j.customer || '').toLowerCase().includes(search.toLowerCase()) ||
      (j.invoice_id || '').toLowerCase().includes(search.toLowerCase())
    const matchStatus = statusFilter === 'all' || j.status === statusFilter
    return matchSearch && matchStatus
  })

  const fmt = (n) => `$${(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`

  const statusCounts = jobs.reduce((acc, j) => {
    acc[j.status] = (acc[j.status] || 0) + 1
    return acc
  }, {})

  if (loading) return (
    <div className="flex items-center justify-center h-64 text-gray-500">Loading jobs...</div>
  )

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Jobs</h1>
        <div className="flex gap-3">
          <Link
            to="/estimate"
            className="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700"
          >
            + New Estimate
          </Link>
          <Link
            to="/filing-cabinet"
            className="bg-white border border-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm hover:bg-gray-50"
          >
            Filing Cabinet
          </Link>
        </div>
      </div>

      {/* Status filter tabs */}
      <div className="flex gap-2 bg-gray-100 p-1 rounded-lg w-fit">
        {['all', 'completed', 'pending', 'paid'].map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              statusFilter === s
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {s === 'all' ? `All (${jobs.length})` : `${capitalize(s)} (${statusCounts[s] || 0})`}
          </button>
        ))}
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="Search by customer or invoice number..."
        value={search}
        onChange={e => setSearch(e.target.value)}
        className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
      />

      {/* Jobs table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="grid grid-cols-12 px-5 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide border-b border-gray-100 bg-gray-50">
          <div className="col-span-3">Customer</div>
          <div className="col-span-2">Invoice #</div>
          <div className="col-span-2">Date</div>
          <div className="col-span-2 text-right">Labor</div>
          <div className="col-span-2 text-right">Total</div>
          <div className="col-span-1">Status</div>
        </div>
        <div className="divide-y divide-gray-50">
          {filtered.map(job => (
            <div
              key={job.id}
              onClick={() => navigate(`/filing-cabinet?job=${job.id}`)}
              className="grid grid-cols-12 px-5 py-3 hover:bg-gray-50 cursor-pointer items-center"
            >
              <div className="col-span-3 font-medium text-gray-900 text-sm truncate pr-2">
                {job.customer || '—'}
              </div>
              <div className="col-span-2 text-sm text-gray-600">
                {job.invoice_id || `#${job.id}`}
              </div>
              <div className="col-span-2 text-sm text-gray-500">
                {job.start_date || '—'}
              </div>
              <div className="col-span-2 text-right text-sm text-gray-700">
                {fmt(job.total_labor)}
              </div>
              <div className="col-span-2 text-right text-sm font-semibold text-gray-900">
                {fmt((job.total_labor || 0) + (job.total_materials || 0))}
              </div>
              <div className="col-span-1">
                <StatusBadge status={job.status} />
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="px-5 py-12 text-center text-gray-400">
              No jobs found
              {search && (
                <button
                  onClick={() => setSearch('')}
                  className="block mx-auto mt-2 text-blue-600 text-sm hover:underline"
                >
                  Clear search
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Summary footer */}
      {filtered.length > 0 && (
        <div className="bg-gray-50 rounded-xl border border-gray-200 px-5 py-3 flex gap-6 text-sm">
          <div>
            <span className="text-gray-500">Showing: </span>
            <span className="font-semibold text-gray-900">{filtered.length} jobs</span>
          </div>
          <div>
            <span className="text-gray-500">Total Revenue: </span>
            <span className="font-semibold text-gray-900">
              {fmt(filtered.reduce((s, j) => s + (j.total_labor || 0) + (j.total_materials || 0), 0))}
            </span>
          </div>
          <div>
            <span className="text-gray-500">Total Labor: </span>
            <span className="font-semibold text-gray-900">
              {fmt(filtered.reduce((s, j) => s + (j.total_labor || 0), 0))}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  const map = {
    completed: 'bg-green-100 text-green-700',
    paid: 'bg-green-100 text-green-700',
    pending: 'bg-yellow-100 text-yellow-700',
    estimate: 'bg-blue-100 text-blue-700',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${map[status] || 'bg-gray-100 text-gray-600'}`}>
      {status}
    </span>
  )
}

function capitalize(s) {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
