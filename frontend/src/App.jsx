import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
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
              <div className="flex flex-wrap items-center gap-1">
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
        <main className="max-w-7xl mx-auto px-4 py-6">
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
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
