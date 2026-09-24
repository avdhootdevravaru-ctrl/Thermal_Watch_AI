import { Outlet, NavLink, Link } from 'react-router-dom'
import { Activity, Map, AlertTriangle } from 'lucide-react'
import './Layout.css'

export default function Layout() {
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
            <span>Map</span>
          </NavLink>
          <NavLink to="/events" className={({ isActive }) => `topnav-link ${isActive ? 'is-active' : ''}`}>
            <AlertTriangle size={14} />
            <span>Events</span>
          </NavLink>
        </nav>

        <div className="topbar-right">
          <div className="system-status">
            <span className="status-dot" />
            <span className="status-label">LIVE FEED</span>
            <span className="status-meta mono">VIIRS NOAA-20</span>
          </div>
        </div>
      </header>

      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
