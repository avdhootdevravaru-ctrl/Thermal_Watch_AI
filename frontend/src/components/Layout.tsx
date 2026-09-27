import { useEffect, useState } from 'react'
import { Outlet, NavLink, Link } from 'react-router-dom'
import { Activity, Map, AlertTriangle, BarChart3, BrainCircuit, Fingerprint, HeartPulse, Moon, Sun, ShieldAlert } from 'lucide-react'
import { api } from '@/api/client'
import './Layout.css'

export default function Layout() {
  const [dataMode, setDataMode] = useState<'DEMO DATA' | 'FIRMS SNAPSHOT' | 'LIVE MODE' | 'OFFLINE'>('OFFLINE')
  const [sourceStatus, setSourceStatus] = useState<string>('UNAVAILABLE')
  const [captureTime, setCaptureTime] = useState<string | null>(null)
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    try { return localStorage.getItem('ignis-theme') === 'light' ? 'light' : 'dark' } catch { return 'dark' }
  })

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem('ignis-theme', theme) } catch { /* Storage can be disabled. */ }
  }, [theme])

  useEffect(() => {
    const updateStatus = () => {
      void api.getHealth().then((health) => {
        setDataMode(health.data_mode)
        setSourceStatus(health.source_status ?? 'UNAVAILABLE')
      }).catch(() => setDataMode('OFFLINE'))
      void api.getFirmsStatus().then((status) => setCaptureTime(status.capture_timestamp))
        .catch(() => setCaptureTime(null))
    }
    updateStatus()
    const timer = window.setInterval(updateStatus, 30000)
    window.addEventListener('ignis:feed-refreshed', updateStatus)
    return () => { window.clearInterval(timer); window.removeEventListener('ignis:feed-refreshed', updateStatus) }
  }, [])

  return (
    <div className="layout">
      <header className="topbar">
        <div className="topbar-left">
          <Link to="/" className="brand">
            <div className="brand-mark">
              <Activity size={20} strokeWidth={2.5} />
            </div>
            <div className="brand-text">
              <div className="brand-name">IGN<span className="brand-accent">IS</span></div>
              <div className="brand-tag">THERMAL INTELLIGENCE &amp; RISK MONITORING</div>
            </div>
          </Link>
        </div>

        <nav className="topnav">
          <NavLink to="/" end aria-label="Monitoring" title="Monitoring" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}>
            <Map size={14} />
            <span>Monitoring</span>
          </NavLink>
          <NavLink to="/events" aria-label="Events" title="Events" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}>
            <AlertTriangle size={14} />
            <span>Events</span>
          </NavLink>
          <NavLink to="/analytics" aria-label="Analytics" title="Analytics" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}><BarChart3 size={14} /><span>Analytics</span></NavLink>
          <NavLink to="/risk" aria-label="Risk" title="Risk" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}><ShieldAlert size={14} /><span>Risk</span></NavLink>
          <NavLink to="/model" aria-label="Model" title="Model" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}><BrainCircuit size={14} /><span>Model</span></NavLink>
          <NavLink to="/evidence" aria-label="Evidence" title="Evidence" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}><Fingerprint size={14} /><span>Evidence</span></NavLink>
          <NavLink to="/health" aria-label="Health" title="Health" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}><HeartPulse size={14} /><span>Health</span></NavLink>
        </nav>

        <div className="topbar-right">
          <div className={`system-status ${dataMode === 'OFFLINE' ? 'offline' : ''}`}>
            <span className="status-dot" />
            <span className="status-label">{dataMode === 'LIVE MODE' ? 'DATABASE MODE' : dataMode}</span>
            <span className="status-meta mono">{dataMode === 'DEMO DATA' ? 'SYNTHETIC SCENARIOS' : dataMode === 'FIRMS SNAPSHOT' ? 'NASA FIRMS · LOCAL CAPTURE' : dataMode === 'LIVE MODE' ? sourceStatus.replace(/_/g, ' ') : 'API UNAVAILABLE'}</span>
          </div>
          {captureTime && <span className="capture-time" title="Last FIRMS capture">Updated {new Date(captureTime).toLocaleString()}</span>}
          <button className="theme-toggle" type="button" onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`} title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}>{theme === 'dark' ? <Sun size={17} /> : <Moon size={17} />}</button>
        </div>
      </header>

      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
