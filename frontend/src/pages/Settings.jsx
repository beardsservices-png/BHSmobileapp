import { useState } from 'react'

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

export default function Settings() {
  const [hidden, setHidden] = useState(getHidden)

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
