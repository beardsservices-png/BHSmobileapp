import { useState, useEffect } from 'react'

const STATUS_TABS = [
  { key: 'new', label: 'New' },
  { key: 'read', label: 'Read' },
  { key: 'converted', label: 'Converted' },
  { key: 'dismissed', label: 'Dismissed' },
]

function timeAgo(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d)) return ts
  const diff = Math.floor((Date.now() - d) / 1000)
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatPhone(num) {
  if (!num) return ''
  const d = num.replace(/\D/g, '')
  if (d.length === 10) return `(${d.slice(0,3)}) ${d.slice(3,6)}-${d.slice(6)}`
  if (d.length === 11 && d[0] === '1') return `(${d.slice(1,4)}) ${d.slice(4,7)}-${d.slice(7)}`
  return num
}

export default function Leads() {
  const [leads, setLeads] = useState([])
  const [tab, setTab] = useState('new')
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [converting, setConverting] = useState(null)
  const [customers, setCustomers] = useState([])
  const [customerSearch, setCustomerSearch] = useState('')
  const [linkCustomerId, setLinkCustomerId] = useState('')
  const [notes, setNotes] = useState({})

  useEffect(() => {
    fetch('/api/customers').then(r => r.json()).then(setCustomers).catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    fetch(`/api/leads?status=${tab}`)
      .then(r => r.json())
      .then(data => { setLeads(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [tab])

  function refresh() {
    fetch(`/api/leads?status=${tab}`)
      .then(r => r.json())
      .then(setLeads)
  }

  async function markRead(id) {
    await fetch(`/api/leads/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'read' })
    })
    refresh()
  }

  async function dismiss(id) {
    await fetch(`/api/leads/${id}/dismiss`, { method: 'POST' })
    refresh()
  }

  async function deleteLead(id) {
    if (!confirm('Delete this lead permanently?')) return
    await fetch(`/api/leads/${id}`, { method: 'DELETE' })
    refresh()
  }

  async function saveNotes(id) {
    await fetch(`/api/leads/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: notes[id] || '' })
    })
    refresh()
  }

  async function convert(lead) {
    const customerId = linkCustomerId || lead.customer_id
    const res = await fetch(`/api/leads/${lead.id}/convert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(customerId ? { customer_id: parseInt(customerId) } : { name: lead.contact_name || lead.from_number })
    })
    if (res.ok) {
      const data = await res.json()
      setConverting(null)
      setLinkCustomerId('')
      setTab('converted')
    }
  }

  const newCount = leads.length

  const filteredCustomers = customers.filter(c =>
    !customerSearch || c.name.toLowerCase().includes(customerSearch.toLowerCase())
  )

  return (
    <div className="max-w-2xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Leads Inbox</h1>
          <p className="text-sm text-slate-500 mt-0.5">Inbound texts from customers</p>
        </div>
        <button
          onClick={refresh}
          className="p-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors"
          title="Refresh"
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>

      {/* Status tabs */}
      <div className="flex border border-slate-200 rounded-xl overflow-hidden bg-white">
        {STATUS_TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
              tab === t.key ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-50'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Lead cards */}
      {loading ? (
        <div className="text-center py-12 text-slate-400">Loading...</div>
      ) : leads.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-2xl border border-slate-200">
          <svg className="w-12 h-12 mx-auto text-slate-300 mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
          <p className="text-slate-500 font-medium">No {tab} leads</p>
          <p className="text-slate-400 text-sm mt-1">
            {tab === 'new' ? 'Forwarded texts will appear here' : `No ${tab} leads yet`}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {leads.map(lead => (
            <div
              key={lead.id}
              className={`bg-white rounded-2xl border transition-all ${
                lead.status === 'new' ? 'border-blue-200 shadow-sm' : 'border-slate-200'
              }`}
            >
              {/* Header row */}
              <div
                className="flex items-start gap-3 p-4 cursor-pointer"
                onClick={() => {
                  setExpanded(expanded === lead.id ? null : lead.id)
                  if (lead.status === 'new') markRead(lead.id)
                }}
              >
                {/* Avatar */}
                <div className={`w-10 h-10 rounded-full flex items-center justify-center text-white font-bold text-sm shrink-0 ${
                  lead.status === 'new' ? 'bg-blue-500' : 'bg-slate-400'
                }`}>
                  {(lead.contact_name || lead.from_number || '?')[0].toUpperCase()}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-semibold text-slate-800 truncate">
                      {lead.contact_name || formatPhone(lead.from_number) || 'Unknown'}
                    </span>
                    <span className="text-xs text-slate-400 shrink-0">{timeAgo(lead.received_at || lead.created_at)}</span>
                  </div>
                  {lead.contact_name && (
                    <div className="text-xs text-slate-500">{formatPhone(lead.from_number)}</div>
                  )}
                  <p className="text-sm text-slate-600 mt-0.5 line-clamp-2">{lead.message}</p>
                  {lead.customer_name && (
                    <span className="inline-block mt-1 text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded-full">
                      {lead.customer_name}
                    </span>
                  )}
                </div>

                {lead.status === 'new' && (
                  <span className="w-2.5 h-2.5 bg-blue-500 rounded-full mt-1.5 shrink-0" />
                )}
              </div>

              {/* Expanded detail */}
              {expanded === lead.id && (
                <div className="px-4 pb-4 space-y-3 border-t border-slate-100 pt-3">
                  {/* Full message */}
                  <div className="bg-slate-50 rounded-xl p-3">
                    <p className="text-sm text-slate-700 whitespace-pre-wrap">{lead.message}</p>
                  </div>

                  {/* Notes */}
                  <div>
                    <label className="text-xs font-medium text-slate-500 uppercase tracking-wide">Your Notes</label>
                    <textarea
                      className="mt-1 w-full border border-slate-200 rounded-lg p-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-300"
                      rows={2}
                      placeholder="Add notes for callback..."
                      value={notes[lead.id] ?? (lead.notes || '')}
                      onChange={e => setNotes(n => ({ ...n, [lead.id]: e.target.value }))}
                    />
                    {notes[lead.id] !== undefined && (
                      <button
                        onClick={() => saveNotes(lead.id)}
                        className="mt-1 text-xs text-blue-600 font-medium"
                      >
                        Save notes
                      </button>
                    )}
                  </div>

                  {/* Convert modal */}
                  {converting === lead.id ? (
                    <div className="border border-blue-200 rounded-xl p-3 bg-blue-50 space-y-2">
                      <p className="text-sm font-semibold text-blue-800">Link to existing customer or create new?</p>
                      <input
                        type="text"
                        placeholder="Search customers..."
                        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
                        value={customerSearch}
                        onChange={e => setCustomerSearch(e.target.value)}
                      />
                      {customerSearch && (
                        <div className="max-h-36 overflow-y-auto rounded-lg border border-slate-200 bg-white">
                          {filteredCustomers.slice(0, 8).map(c => (
                            <button
                              key={c.id}
                              onClick={() => { setLinkCustomerId(c.id); setCustomerSearch(c.name) }}
                              className={`w-full text-left px-3 py-2 text-sm hover:bg-slate-50 ${linkCustomerId === c.id ? 'bg-blue-50 text-blue-700 font-medium' : 'text-slate-700'}`}
                            >
                              {c.name}
                              {c.phone && <span className="text-slate-400 ml-2 text-xs">{formatPhone(c.phone)}</span>}
                            </button>
                          ))}
                        </div>
                      )}
                      <div className="flex gap-2 pt-1">
                        <button
                          onClick={() => convert(lead)}
                          className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-medium"
                        >
                          {linkCustomerId ? 'Link Customer' : 'Create New Customer'}
                        </button>
                        <button
                          onClick={() => { setConverting(null); setLinkCustomerId(''); setCustomerSearch('') }}
                          className="px-3 bg-white border border-slate-200 rounded-lg text-sm text-slate-600"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-2 flex-wrap">
                      {lead.status !== 'converted' && (
                        <button
                          onClick={() => setConverting(lead.id)}
                          className="flex-1 bg-green-600 text-white rounded-xl py-2.5 text-sm font-semibold"
                        >
                          Convert to Customer
                        </button>
                      )}
                      {lead.status === 'converted' && lead.customer_id && (
                        <a
                          href={`/customers`}
                          className="flex-1 text-center bg-green-100 text-green-700 rounded-xl py-2.5 text-sm font-semibold"
                        >
                          View Customer
                        </a>
                      )}
                      {lead.status !== 'dismissed' && (
                        <button
                          onClick={() => dismiss(lead.id)}
                          className="px-4 bg-slate-100 text-slate-600 rounded-xl py-2.5 text-sm font-medium"
                        >
                          Dismiss
                        </button>
                      )}
                      <button
                        onClick={() => deleteLead(lead.id)}
                        className="px-4 bg-red-50 text-red-600 rounded-xl py-2.5 text-sm font-medium"
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* SMS Forwarder setup tip */}
      <div className="bg-slate-50 border border-slate-200 rounded-2xl p-4 text-sm text-slate-500">
        <p className="font-medium text-slate-700 mb-1">SMS Forwarder Setup</p>
        <p>Point SMS Forwarder to:</p>
        <code className="block mt-1 bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-700 break-all">
          {window.location.origin}/api/webhook/sms?token=WebhookSecret
        </code>
        <p className="mt-2">Body template:</p>
        <code className="block mt-1 bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-700">
          {'{"from":"{{from}}","contact":"{{contact}}","message":"{{message}}"}'}
        </code>
      </div>
    </div>
  )
}
