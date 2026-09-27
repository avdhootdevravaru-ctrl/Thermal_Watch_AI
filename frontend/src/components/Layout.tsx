import { useEffect, useState } from 'react'
import { Outlet, NavLink, Link } from 'react-router-dom'
import { Activity, Map, AlertTriangle, BarChart3, BrainCircuit, Fingerprint } from 'lucide-react'
import { api } from '@/api/client'
import './Layout.css'

export default function Layout() {
  const [dataMode, setDataMode] = useState<'DEMO DATA' | 'FIRMS SNAPSHOT' | 'LIVE MODE' | 'OFFLINE'>('OFFLINE')
  const [sourceStatus, setSourceStatus] = useState<string>('UNAVAILABLE')

  useEffect(() => {
    void api.getHealth().then((health) => {
      setDataMode(health.data_mode)
      setSourceStatus(health.source_status ?? 'UNAVAILABLE')
    }).catch(() => setDataMode('OFFLINE'))
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
              <div className="brand-name">ThermalWatch<span className="brand-accent">.AI</span></div>
              <div className="brand-tag">GEOSPATIAL INTELLIGENCE · SIH 2026</div>
            </div>
          </Link>
        </div>

        <nav className="topnav">
          <NavLink to="/" end className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}>
            <Map size={14} />
            <span>Live monitoring</span>
          </NavLink>
          <NavLink to="/events" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}>
            <AlertTriangle size={14} />
            <span>Events</span>
          </NavLink>
          <NavLink to="/analytics" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}><BarChart3 size={14} /><span>Analytics</span></NavLink>
          <NavLink to="/model" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}><BrainCircuit size={14} /><span>Model</span></NavLink>
          <NavLink to="/evidence" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}><Fingerprint size={14} /><span>Evidence</span></NavLink>
        </nav>

        <div className="topbar-right">
          <div className="system-status">
            <span className="status-dot" />
            <span className="status-label">{dataMode}</span>
            <span className="status-meta mono">{dataMode === 'DEMO DATA' ? 'SYNTHETIC SCENARIOS' : dataMode === 'FIRMS SNAPSHOT' ? 'NASA FIRMS · LOCAL CAPTURE' : dataMode === 'LIVE MODE' ? sourceStatus.replace(/_/g, ' ') : 'API UNAVAILABLE'}</span>
          </div>
        </div>
      </header>

      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
