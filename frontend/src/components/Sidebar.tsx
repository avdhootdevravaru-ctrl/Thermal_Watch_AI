import { AlertTriangle, Activity, TrendingUp, Clock } from 'lucide-react'
import type { MapHotspotsResponse, ThermalEventRead, HistoricalStatistics, DataQualityReport } from '@/types'
import './Sidebar.css'

interface SidebarProps {
  summary: MapHotspotsResponse['risk_summary'] | null
  totalEvents: number
  recentEvents: ThermalEventRead[]
  historicalStatistics: HistoricalStatistics | null
  dataQualityReport: DataQualityReport | null
  onEventClick: (eventId: number) => void
  onRunIngestion: () => void
  isIngesting: boolean
}

export default function Sidebar({
  summary,
  totalEvents,
  recentEvents,
  historicalStatistics,
  dataQualityReport,
  onEventClick,
  onRunIngestion,
  isIngesting,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <section className="panel">
        <header className="panel-header">
          <h3 className="panel-title">
            <Activity size={14} />
            <span>Risk Posture</span>
          </h3>
        </header>
        <div className="risk-grid">
          <RiskCard
            severity="high"
            label="HIGH"
            count={summary?.high ?? 0}
            description="Persistent thermal sources (≥5 detections)"
          />
          <RiskCard
            severity="medium"
            label="MEDIUM"
            count={summary?.medium ?? 0}
            description="Active thermal events"
          />
          <RiskCard
            severity="low"
            label="LOW"
            count={summary?.low ?? 0}
            description="Resolved or transient"
          />
        </div>
      </section>

      <section className="panel">
        <header className="panel-header">
          <h3 className="panel-title">
            <TrendingUp size={14} />
            <span>Ingestion</span>
          </h3>
        </header>
        <button
          className="ingest-btn"
          onClick={onRunIngestion}
          disabled={isIngesting}
        >
          {isIngesting ? (
            <>
              <span className="spinner" />
              <span>Running FIRMS ingest…</span>
            </>
          ) : (
            <>
              <span>▶</span>
              <span>Trigger FIRMS Ingestion</span>
            </>
          )}
        </button>
        <p className="panel-footnote mono">
          {totalEvents} thermal events indexed
        </p>
      </section>

      {/* HISTORICAL INTELLIGENCE SUMMARY */}
      <section className="panel">
        <header className="panel-header">
          <h3 className="panel-title">
            <Clock size={14} />
            <span>Historical Intelligence</span>
          </h3>
        </header>
        <div className="historical-stats">
          <div className="stat-row">
            <span className="stat-label">Total Observations</span>
            <span className="stat-value mono">{historicalStatistics?.total_observations ?? dataQualityReport?.total_observations ?? 0}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Total Events</span>
            <span className="stat-value mono">{historicalStatistics?.total_events ?? 0}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Data Status</span>
            <span className={`status-pill status-${historicalStatistics?.status?.toLowerCase() ?? 'unknown'}`}>
              {historicalStatistics?.status ?? dataQualityReport?.status ?? 'UNKNOWN'}
            </span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Duplicate Observations</span>
            <span className="stat-value mono">{dataQualityReport?.duplicate_count ?? 0}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Orphan Events</span>
            <span className="stat-value mono warning">{dataQualityReport?.orphan_events ?? 0}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Observation Mismatches</span>
            <span className="stat-value mono warning">{dataQualityReport?.observation_count_mismatches ?? 0}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Recurring Locations</span>
            <span className="stat-value mono">{dataQualityReport?.recurring_locations ?? 0}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Active Locations</span>
            <span className="stat-value mono">{historicalStatistics?.active_locations ?? 0}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">Persistent Sources</span>
            <span className="stat-value mono">{historicalStatistics?.persistent_sources ?? 0}</span>
          </div>
        </div>
      </section>

      <section className="panel flex-1">
        <header className="panel-header">
          <h3 className="panel-title">
            <AlertTriangle size={14} />
            <span>Recent Detections</span>
          </h3>
        </header>
        <div className="event-list">
          {recentEvents.length === 0 ? (
            <div className="empty-state">
              <p>No thermal events yet.</p>
              <p className="empty-hint">Trigger a FIRMS ingestion run to populate the system.</p>
            </div>
          ) : (
            recentEvents.map((e) => (
              <button
                key={e.id}
                className={`event-row status-${e.status.toLowerCase()}`}
                onClick={() => onEventClick(e.id)}
              >
                <div className="event-row-head">
                  <span className="event-id mono">#{e.id}</span>
                  <span className={`status-pill status-${e.status.toLowerCase()}`}>
                    {e.status}
                  </span>
                </div>
                <div className="event-row-coord mono">
                  {e.latitude.toFixed(3)}, {e.longitude.toFixed(3)}
                </div>
                <div className="event-row-meta">
                  <span>{e.observation_count} det.</span>
                  <span>·</span>
                  <span>persistence {e.persistence_score.toFixed(1)}</span>
                </div>
              </button>
            ))
          )}
        </div>
      </section>
    </aside>
  )
}

function RiskCard({
  severity,
  label,
  count,
  description,
}: {
  severity: 'high' | 'medium' | 'low'
  label: string
  count: number
  description: string
}) {
  return (
    <div className={`risk-card risk-${severity}`}>
      <div className="risk-card-label">{label}</div>
      <div className="risk-card-count mono">{count}</div>
      <div className="risk-card-desc">{description}</div>
    </div>
  )
}
