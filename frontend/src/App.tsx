import { useEffect, useState } from 'react'
import { HashRouter, Routes, Route, NavLink } from 'react-router-dom'
import Overview from './pages/Overview'
import Traces from './pages/Traces'
import TraceDetailPage from './pages/TraceDetail'
import Controllers from './pages/Controllers'
import Diff from './pages/Diff'
import History from './pages/History'

const SEMANTIC_RULE =
  'CCReplay answers what a congestion-control implementation computes at a recorded Linux ' +
  'congestion-control callback boundary. It does not claim what network trajectory or ' +
  'performance that implementation would have produced.'

function useTheme() {
  const [theme, setTheme] = useState<'light' | 'dark'>(
    (localStorage.getItem('ccr-theme') as 'light' | 'dark') || 'dark'
  )
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('ccr-theme', theme)
  }, [theme])
  return { theme, toggle: () => setTheme((t) => (t === 'light' ? 'dark' : 'light')) }
}

export default function App() {
  const { theme, toggle } = useTheme()

  return (
    <HashRouter>
      <header className="app-topbar">
        <span className="app-brand">CCReplay Studio</span>
        <nav className="app-nav">
          <NavLink to="/" end>
            Overview
          </NavLink>
          <NavLink to="/traces">Traces</NavLink>
          <NavLink to="/controllers">Controllers</NavLink>
          <NavLink to="/diff">Diff</NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
        <button className="theme-toggle" onClick={toggle}>
          {theme === 'light' ? '🌙 Dark' : '☀️ Light'}
        </button>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/traces" element={<Traces />} />
          <Route path="/traces/:id" element={<TraceDetailPage />} />
          <Route path="/controllers" element={<Controllers />} />
          <Route path="/diff" element={<Diff />} />
          <Route path="/history" element={<History />} />
        </Routes>
      </main>
      <footer className="app-footer">{SEMANTIC_RULE}</footer>
    </HashRouter>
  )
}
