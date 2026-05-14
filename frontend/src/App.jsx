import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Jobs from './pages/Jobs'
import Customers from './pages/Customers'
import TimeEntry from './pages/TimeEntry'
import FilingCabinet from './pages/FilingCabinet'
import PrintView from './pages/PrintView'
import Estimate from './pages/Estimate'
import Expenses from './pages/Expenses'
import Trips from './pages/Trips'
import Reports from './pages/Reports'
import DayWrapup from './pages/DayWrapup'
import Clock from './pages/Clock'
import Settings from './pages/Settings'

const LS_CLOCK = 'bhs_clock_v1'

const ALL_MORE_ITEMS = [
  { key: 'estimate',       to: '/estimate',       label: '+ Estimate' },
  { key: 'customers',      to: '/customers',      label: 'Customers' },
  { key: 'filing-cabinet', to: '/filing-cabinet', label: 'Filing Cabinet' },
  { key: 'jobs',           to: '/jobs',           label: 'Jobs' },
  { key: 'time',           to: '/time',           label: '+ Time Entry' },
  { key: 'trips',          to: '/trips',          label: 'Trips' },
  { key: 'reports',        to: '/reports',        label: 'Reports' },
]

function getHidden() {
  try { return JSON.parse(localStorage.getItem('bhs_settings') || '{}').hidden || [] }
  catch { return [] }
}

function BottomNav() {
  const location = useLocation()
  const [showMore, setShowMore] = useState(false)
  const [clockActive, setClockActive] = useState(false)
  const [hidden, setHidden] = useState(getHidden)

  useEffect(() => {
    const check = () => setClockActive(!!localStorage.getItem(LS_CLOCK))
    check()
    const iv = setInterval(check, 3000)
    return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    const handler = () => setHidden(getHidden())
    window.addEventListener('bhs-settings-changed', handler)
    return () => window.removeEventListener('bhs-settings-changed', handler)
  }, [])

  useEffect(() => setShowMore(false), [location.pathname])

  const isActive = (path) => path === '/' ? location.pathname === '/' : location.pathname.startsWith(path)

  const tabCls = (path) =>
    `flex flex-col items-center gap-0.5 py-2 px-1 flex-1 text-xs font-medium transition-colors ${isActive(path) ? 'text-blue-600' : 'text-slate-500'}`

  return (
    <>
      {showMore && (
        <div className="fixed inset-0 z-40 bg-black/20" onClick={() => setShowMore(false)}>
          <div
            className="absolute bottom-16 left-0 right-0 bg-white border-t border-slate-200 px-4 pt-4 pb-3 grid grid-cols-3 gap-2"
            onClick={e => e.stopPropagation()}
          >
            {ALL_MORE_ITEMS.filter(item => !hidden.includes(item.key)).map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `text-center py-3 px-2 rounded-xl text-sm font-medium transition-colors ${isActive ? 'bg-blue-100 text-blue-700' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`
                }
              >
                {item.label}
              </NavLink>
            ))}
            <NavLink
              to="/settings"
              className={({ isActive }) =>
                `text-center py-3 px-2 rounded-xl text-sm font-medium transition-colors ${isActive ? 'bg-blue-100 text-blue-700' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`
              }
            >
              Settings
            </NavLink>
          </div>
        </div>
      )}

      <div className="fixed bottom-0 left-0 right-0 z-50 bg-white border-t border-slate-200 flex md:hidden print:hidden">
        {/* Dashboard */}
        <NavLink to="/" end className={tabCls('/')}>
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
          </svg>
          Dashboard
        </NavLink>

        {/* Clock */}
        <NavLink to="/clock" className={`${tabCls('/clock')} relative`}>
          {clockActive && (
            <span className="absolute top-1.5 right-[22%] w-2.5 h-2.5 bg-green-500 rounded-full animate-pulse border-2 border-white" />
          )}
          <svg className={`w-6 h-6 ${clockActive ? 'text-green-600' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <circle cx="12" cy="12" r="10" />
            <polyline points="12 6 12 12 16 14" />
          </svg>
          <span className={clockActive ? 'text-green-600' : ''}>
            {clockActive ? 'Clocked In' : 'Clock'}
          </span>
        </NavLink>

        {/* Expenses */}
        <NavLink to="/expenses" className={tabCls('/expenses')}>
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Expense
        </NavLink>

        {/* Day Wrap-Up */}
        <NavLink to="/day-wrapup" className={tabCls('/day-wrapup')}>
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
          Wrap-Up
        </NavLink>

        {/* More */}
        <button
          onClick={() => setShowMore(v => !v)}
          className={`flex flex-col items-center gap-0.5 py-2 px-1 flex-1 text-xs font-medium transition-colors ${showMore ? 'text-blue-600' : 'text-slate-500'}`}
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 12h16M4 18h16" />
          </svg>
          More
        </button>
      </div>
    </>
  )
}

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50">
        <nav className="bg-white shadow-sm border-b border-slate-200 print:hidden">
          <div className="max-w-7xl mx-auto px-4">
            <div className="flex flex-wrap items-center gap-x-1 gap-y-1 py-2 min-h-14">
              <div className="flex items-center mr-2 shrink-0">
                <span className="text-lg font-bold text-slate-800 whitespace-nowrap">Beard's Home Services</span>
              </div>
              <div className="hidden md:flex flex-wrap items-center gap-1">
                <NavLink to="/" end className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-blue-100 text-blue-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                  Dashboard
                </NavLink>
                <NavLink to="/filing-cabinet" className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-blue-100 text-blue-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                  Filing Cabinet
                </NavLink>
                <NavLink to="/jobs" className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-blue-100 text-blue-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                  Jobs
                </NavLink>
                <NavLink to="/customers" className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-blue-100 text-blue-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                  Customers
                </NavLink>
                <NavLink to="/clock" className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-green-100 text-green-700' : 'bg-green-500 text-white hover:bg-green-600'}`}>
                  Clock In/Out
                </NavLink>
                <NavLink to="/time" className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-green-100 text-green-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                  + Time Entry
                </NavLink>
                <NavLink to="/estimate" className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-blue-100 text-blue-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                  + Estimate
                </NavLink>
                <NavLink to="/expenses" className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-orange-100 text-orange-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                  Expenses
                </NavLink>
                <NavLink to="/trips" className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-teal-100 text-teal-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                  Trips
                </NavLink>
                <NavLink to="/reports" className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-indigo-100 text-indigo-700' : 'text-slate-600 hover:bg-slate-100'}`}>
                  Reports
                </NavLink>
                <NavLink to="/day-wrapup" className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${isActive ? 'bg-purple-100 text-purple-700' : 'bg-purple-50 text-purple-600 hover:bg-purple-100'}`}>
                  Day Wrap-Up
                </NavLink>
              </div>
            </div>
          </div>
        </nav>
        <main className="max-w-7xl mx-auto px-4 py-6 pb-24 md:pb-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/filing-cabinet" element={<FilingCabinet />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/customers" element={<Customers />} />
            <Route path="/clock" element={<Clock />} />
            <Route path="/time" element={<TimeEntry />} />
            <Route path="/estimate" element={<Estimate />} />
            <Route path="/print/:jobId" element={<PrintView />} />
            <Route path="/expenses" element={<Expenses />} />
            <Route path="/trips" element={<Trips />} />
            <Route path="/reports" element={<Reports />} />
            <Route path="/day-wrapup" element={<DayWrapup />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
        <BottomNav />
      </div>
    </BrowserRouter>
  )
}

export default App
