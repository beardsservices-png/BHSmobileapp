import { useState, useEffect, useRef } from 'react'

const LS_KEY = 'bhs_clock_v1'

function fmtElapsed(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function fmtHours(ms) {
  return Math.round(ms / 36000) / 100
}

export default function Clock() {
  // phase: idle | locating | confirming | running | wrapping
  const [phase, setPhase] = useState('idle')
  const [candidates, setCandidates] = useState([])
  const [allCustomers, setAllCustomers] = useState([])
  const [showAll, setShowAll] = useState(false)
  const [selected, setSelected] = useState(null)
  const [startTs, setStartTs] = useState(null)
  const [elapsed, setElapsed] = useState(0)
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const timerRef = useRef(null)

  // Restore active session from localStorage
  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_KEY)
      if (raw) {
        const { customer, startTs: ts } = JSON.parse(raw)
        setSelected(customer)
        setStartTs(ts)
        setElapsed(Math.floor((Date.now() - ts) / 1000))
        setPhase('running')
      }
    } catch {}
  }, [])

  // Live timer
  useEffect(() => {
    clearInterval(timerRef.current)
    if (phase === 'running' && startTs) {
      timerRef.current = setInterval(() => {
        setElapsed(Math.floor((Date.now() - startTs) / 1000))
      }, 1000)
    }
    return () => clearInterval(timerRef.current)
  }, [phase, startTs])

  async function loadAllCustomers() {
    if (allCustomers.length > 0) return
    try {
      const r = await fetch('/api/customers')
      const data = await r.json()
      setAllCustomers(Array.isArray(data) ? data.filter(c => !c.name.startsWith('_')) : [])
    } catch {}
  }

  async function handleClockIn() {
    setError('')
    if (!navigator.geolocation) {
      await loadAllCustomers()
      setShowAll(true)
      setPhase('confirming')
      return
    }
    setPhase('locating')
    navigator.geolocation.getCurrentPosition(
      async pos => {
        const { latitude: lat, longitude: lng } = pos.coords
        try {
          const r = await fetch(`/api/nearest-customer?lat=${lat}&lng=${lng}`)
          const data = await r.json()
          setCandidates(Array.isArray(data) ? data : [])
          setShowAll(data.length === 0)
          if (data.length === 0) await loadAllCustomers()
          setPhase('confirming')
        } catch {
          setError('Could not look up nearby customers.')
          setPhase('idle')
        }
      },
      async () => {
        await loadAllCustomers()
        setShowAll(true)
        setPhase('confirming')
      },
      { enableHighAccuracy: true, timeout: 15000 }
    )
  }

  function confirmCustomer(customer) {
    const ts = Date.now()
    setSelected(customer)
    setStartTs(ts)
    setElapsed(0)
    setCandidates([])
    setShowAll(false)
    setPhase('running')
    localStorage.setItem(LS_KEY, JSON.stringify({ customer, startTs: ts }))
  }

  function handleClockOut() {
    clearInterval(timerRef.current)
    setPhase('wrapping')
  }

  async function handleSave() {
    setSaving(true)
    setError('')
    const nowMs = Date.now()
    const startDate = new Date(startTs)
    const endDate = new Date(nowMs)
    try {
      const res = await fetch('/api/time-entries', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          customer_id: selected.id,
          entry_date: startDate.toISOString().slice(0, 10),
          arrive_time: startDate.toTimeString().slice(0, 5),
          depart_time: endDate.toTimeString().slice(0, 5),
          hours: fmtHours(nowMs - startTs),
          description,
          source: 'clock',
        }),
      })
      if (!res.ok) throw new Error('Server error')
      localStorage.removeItem(LS_KEY)
      setPhase('idle')
      setSelected(null)
      setStartTs(null)
      setElapsed(0)
      setDescription('')
    } catch {
      setError('Failed to save. Try again.')
    } finally {
      setSaving(false)
    }
  }

  function handleDiscard() {
    clearInterval(timerRef.current)
    localStorage.removeItem(LS_KEY)
    setPhase('idle')
    setSelected(null)
    setStartTs(null)
    setElapsed(0)
    setDescription('')
    setError('')
  }

  return (
    <div className="max-w-sm mx-auto px-2">
      {error && (
        <div className="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ── IDLE ── */}
      {phase === 'idle' && (
        <div className="text-center pt-12 pb-8">
          <div className="w-24 h-24 rounded-full bg-slate-100 flex items-center justify-center mx-auto mb-6">
            <svg className="w-12 h-12 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold text-slate-800 mb-2">Ready to work?</h1>
          <p className="text-slate-500 text-sm mb-10">Tap Clock In — the app will find your job from your location.</p>
          <button
            onClick={handleClockIn}
            className="w-full bg-green-500 hover:bg-green-600 active:bg-green-700 text-white text-2xl font-bold py-7 rounded-2xl shadow-lg active:scale-95 transition-all"
          >
            CLOCK IN
          </button>
          <button
            onClick={async () => { await loadAllCustomers(); setShowAll(true); setPhase('confirming') }}
            className="mt-5 text-sm text-slate-400 hover:text-slate-600"
          >
            Pick customer manually
          </button>
        </div>
      )}

      {/* ── LOCATING ── */}
      {phase === 'locating' && (
        <div className="text-center pt-20">
          <div className="w-16 h-16 rounded-full bg-blue-50 flex items-center justify-center mx-auto mb-5 animate-pulse">
            <svg className="w-8 h-8 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/>
              <circle cx="12" cy="9" r="2.5"/>
            </svg>
          </div>
          <p className="text-lg text-slate-600 font-medium">Finding your location...</p>
          <p className="text-sm text-slate-400 mt-2">Allow location access if prompted</p>
        </div>
      )}

      {/* ── CONFIRMING ── */}
      {phase === 'confirming' && (
        <div className="pt-6 pb-8">
          <h2 className="text-xl font-bold text-slate-800 mb-1">
            {showAll ? 'Select Customer' : 'Nearby Job Sites'}
          </h2>
          <p className="text-sm text-slate-400 mb-5">
            {showAll ? 'Scroll to find your customer.' : 'Tap the right one to start your clock.'}
          </p>

          {!showAll && candidates.length > 0 && (
            <div className="space-y-3 mb-4">
              {candidates.map(c => (
                <button
                  key={c.id}
                  onClick={() => confirmCustomer(c)}
                  className="w-full text-left bg-white border-2 border-slate-200 hover:border-green-400 active:border-green-500 rounded-2xl p-4 shadow-sm active:scale-95 transition-all"
                >
                  <div className="font-bold text-slate-800 text-lg">{c.name}</div>
                  <div className="text-sm text-slate-400 mt-0.5 truncate">{c.address}</div>
                  <div className="text-sm font-semibold text-green-600 mt-1">{c.distance_miles} mi away</div>
                </button>
              ))}
              <button
                onClick={async () => { await loadAllCustomers(); setShowAll(true) }}
                className="w-full text-center py-3 text-sm text-slate-400 hover:text-slate-600"
              >
                Not listed — pick different customer
              </button>
            </div>
          )}

          {showAll && (
            <div className="space-y-2 mb-4 max-h-[60vh] overflow-y-auto">
              {allCustomers.map(c => (
                <button
                  key={c.id}
                  onClick={() => confirmCustomer(c)}
                  className="w-full text-left bg-white border border-slate-200 hover:border-green-400 rounded-xl px-4 py-3 active:scale-95 transition-all"
                >
                  <div className="font-semibold text-slate-800">{c.name}</div>
                  {c.address && <div className="text-xs text-slate-400 mt-0.5 truncate">{c.address}</div>}
                </button>
              ))}
            </div>
          )}

          <button
            onClick={handleDiscard}
            className="w-full text-center py-3 text-sm text-slate-400 hover:text-slate-600"
          >
            Cancel
          </button>
        </div>
      )}

      {/* ── RUNNING ── */}
      {phase === 'running' && selected && (
        <div className="text-center pt-10 pb-8">
          <div className="flex items-center justify-center gap-2 mb-3">
            <span className="w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse inline-block" />
            <span className="text-sm font-semibold text-green-600 uppercase tracking-widest">Clocked In</span>
          </div>
          <h2 className="text-2xl font-bold text-slate-800">{selected.name}</h2>
          {selected.address && (
            <p className="text-sm text-slate-400 mt-1 mb-8 truncate">{selected.address}</p>
          )}
          {!selected.address && <div className="mb-8" />}
          <div className="text-7xl font-mono font-bold text-slate-800 tabular-nums tracking-tight mb-12">
            {fmtElapsed(elapsed)}
          </div>
          <button
            onClick={handleClockOut}
            className="w-full bg-red-500 hover:bg-red-600 active:bg-red-700 text-white text-2xl font-bold py-7 rounded-2xl shadow-lg active:scale-95 transition-all"
          >
            CLOCK OUT
          </button>
          <button
            onClick={handleDiscard}
            className="mt-5 text-sm text-slate-400 hover:text-red-500"
          >
            Discard session
          </button>
        </div>
      )}

      {/* ── WRAPPING UP ── */}
      {phase === 'wrapping' && (
        <div className="pt-8 pb-8 space-y-6">
          <div className="text-center">
            <div className="w-16 h-16 rounded-full bg-green-100 flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-green-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-slate-800">Nice work!</h2>
            <div className="text-5xl font-mono font-bold text-slate-700 mt-3">{fmtElapsed(elapsed)}</div>
            <div className="text-slate-500 mt-1">{selected?.name}</div>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              What did you work on? <span className="text-slate-400 font-normal">(optional)</span>
            </label>
            <textarea
              rows={3}
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="e.g. Replaced bathroom faucet, patched drywall..."
              className="w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
              autoFocus
            />
          </div>

          <button
            onClick={handleSave}
            disabled={saving}
            className="w-full bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white text-lg font-bold py-5 rounded-2xl disabled:opacity-50 active:scale-95 transition-all"
          >
            {saving ? 'Saving...' : 'Save & Done'}
          </button>
          <button
            onClick={() => { setPhase('running'); clearInterval(timerRef.current); timerRef.current = setInterval(() => setElapsed(Math.floor((Date.now() - startTs) / 1000)), 1000) }}
            className="w-full text-center py-2 text-sm text-slate-400 hover:text-slate-600"
          >
            Not done yet — go back
          </button>
        </div>
      )}
    </div>
  )
}
