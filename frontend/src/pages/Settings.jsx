import { useState, useEffect } from 'react'

const TOGGLEABLE = [
  { key: 'filing-cabinet', label: 'Filing Cabinet', desc: 'View and manage all jobs' },
  { key: 'jobs',           label: 'Jobs',            desc: 'Jobs list view' },
  { key: 'time',           label: '+ Time Entry',    desc: 'Manual time entry form' },
  { key: 'expenses',       label: 'Expenses',        desc: 'Track materials and overhead' },
  { key: 'trips',          label: 'Trips',           desc: 'Mileage and drive log' },
  { key: 'reports',        label: 'Reports',         desc: 'Business reports and charts' },
  { key: 'day-wrapup',     label: 'Day Wrap-Up',     desc: 'End of day summary' },
]

const FIXED = [
  { label: 'Home (Dashboard)', desc: 'Revenue stats and overview' },
  { label: 'Clock In/Out',     desc: 'GPS time tracking' },
  { label: 'Estimate',         desc: 'Create new job estimates' },
  { label: 'Customers',        desc: 'Customer list and details' },
]

function getHidden() {
  try { return JSON.parse(localStorage.getItem('bhs_settings') || '{}').hidden || [] }
  catch { return [] }
}

function formatPhone(num) {
  const d = (num || '').replace(/\D/g, '')
  if (d.length === 10) return `(${d.slice(0,3)}) ${d.slice(3,6)}-${d.slice(6)}`
  return num
}

export default function Settings() {
  const [hidden, setHidden] = useState(getHidden)
  const [excluded, setExcluded] = useState([])
  const [newPhone, setNewPhone] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    fetch('/api/excluded-numbers').then(r => r.json()).then(setExcluded).catch(() => {})
  }, [])

  async function addNumber() {
    if (!newPhone.trim()) return
    const res = await fetch('/api/excluded-numbers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: newPhone.trim(), label: newLabel.trim() })
    })
    if (res.ok) {
      const row = await res.json()
      setExcluded(e => [...e, row])
      setNewPhone(''); setNewLabel(''); setAdding(false)
    }
  }

  async function removeNumber(id) {
    await fetch(`/api/excluded-numbers/${id}`, { method: 'DELETE' })
    setExcluded(e => e.filter(n => n.id !== id))
  }

  function toggle(key) {
    setHidden(prev => {
      const next = prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
      localStorage.setItem('bhs_settings', JSON.stringify({ hidden: next }))
      window.dispatchEvent(new Event('bhs-settings-changed'))
      return next
    })
  }

  function reset() {
    setHidden([])
    localStorage.setItem('bhs_settings', JSON.stringify({ hidden: [] }))
    window.dispatchEvent(new Event('bhs-settings-changed'))
  }

  return (
    <div className="max-w-lg mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-800">Settings</h1>
        <button onClick={reset} className="text-sm text-slate-400 hover:text-slate-600">
          Reset to defaults
        </button>
      </div>

      {/* Toggleable More menu items */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 bg-slate-50 border-b border-slate-100">
          <p className="text-sm font-semibold text-slate-700">More Menu Pages</p>
          <p className="text-xs text-slate-400 mt-0.5">Show or hide items in the More menu</p>
        </div>
        <div className="divide-y divide-slate-50">
          {TOGGLEABLE.map(item => {
            const on = !hidden.includes(item.key)
            return (
              <div key={item.key} className="flex items-center justify-between px-5 py-4">
                <div>
                  <div className="text-sm font-medium text-slate-800">{item.label}</div>
                  <div className="text-xs text-slate-400">{item.desc}</div>
                </div>
                <button
                  onClick={() => toggle(item.key)}
                  className={`relative w-11 h-6 rounded-full transition-colors duration-200 ${on ? 'bg-blue-600' : 'bg-slate-200'}`}
                >
                  <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200 ${on ? 'translate-x-5' : 'translate-x-0'}`} />
                </button>
              </div>
            )
          })}
        </div>
      </div>

      {/* Personal contacts — excluded from Leads inbox */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 bg-slate-50 border-b border-slate-100 flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-700">Personal Contacts</p>
            <p className="text-xs text-slate-400 mt-0.5">Calls from these numbers won't create leads</p>
          </div>
          <button
            onClick={() => setAdding(a => !a)}
            className="text-xs font-semibold text-blue-600 px-3 py-1.5 bg-blue-50 rounded-lg"
          >
            + Add
          </button>
        </div>

        {adding && (
          <div className="px-5 py-3 border-b border-slate-100 space-y-2">
            <input
              type="tel"
              placeholder="Phone number"
              value={newPhone}
              onChange={e => setNewPhone(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
            <input
              type="text"
              placeholder="Name (optional)"
              value={newLabel}
              onChange={e => setNewLabel(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
            />
            <div className="flex gap-2">
              <button onClick={addNumber} className="flex-1 bg-blue-600 text-white rounded-lg py-2 text-sm font-semibold">Save</button>
              <button onClick={() => setAdding(false)} className="px-4 bg-slate-100 text-slate-600 rounded-lg text-sm">Cancel</button>
            </div>
          </div>
        )}

        <div className="divide-y divide-slate-50">
          {excluded.length === 0 && !adding && (
            <p className="px-5 py-4 text-sm text-slate-400">No personal contacts added yet</p>
          )}
          {excluded.map(n => (
            <div key={n.id} className="flex items-center justify-between px-5 py-3">
              <div>
                <div className="text-sm font-medium text-slate-800">{n.label || formatPhone(n.phone)}</div>
                {n.label && <div className="text-xs text-slate-400">{formatPhone(n.phone)}</div>}
              </div>
              <button
                onClick={() => removeNumber(n.id)}
                className="text-xs text-red-500 font-medium px-2 py-1 hover:bg-red-50 rounded"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Fixed nav items (info only) */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-3 bg-slate-50 border-b border-slate-100">
          <p className="text-sm font-semibold text-slate-700">Bottom Nav — Always Visible</p>
          <p className="text-xs text-slate-400 mt-0.5">These four tabs are always shown</p>
        </div>
        <div className="divide-y divide-slate-50">
          {FIXED.map(item => (
            <div key={item.label} className="flex items-center justify-between px-5 py-4">
              <div>
                <div className="text-sm font-medium text-slate-800">{item.label}</div>
                <div className="text-xs text-slate-400">{item.desc}</div>
              </div>
              <div className="relative w-11 h-6 rounded-full bg-blue-600 opacity-40">
                <span className="absolute top-0.5 right-0.5 w-5 h-5 bg-white rounded-full shadow" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
