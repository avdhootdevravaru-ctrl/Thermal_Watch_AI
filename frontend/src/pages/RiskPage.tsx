import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, ShieldAlert } from 'lucide-react'
import { api } from '@/api/client'
import type { HotspotMarker, ThermalEventDetail } from '@/types'
import { locationLabel } from '@/utils/intelligence'
import './IntelligencePage.css'

export default function RiskPage() {
  const [summary, setSummary] = useState<{ high: number; medium: number; low: number } | null>(null)
  const [total, setTotal] = useState<number | null>(null)
  const [priority, setPriority] = useState<Array<{ marker: HotspotMarker; event: ThermalEventDetail | null }>>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    void api.getMapHotspots({ limit: 1000 }).then(async (map) => {
      const high = map.markers.filter((marker) => marker.risk_severity?.toLowerCase() === 'high')
        .sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0))
      const details = await Promise.allSettled(high.map((marker) => api.getEvent(marker.event_id)))
      if (!active) return
      setSummary(map.risk_summary)
      setTotal(map.total)
      setPriority(high.map((marker, index) => ({ marker, event: details[index].status === 'fulfilled' ? details[index].value : null })))
    }).catch(() => { if (active) setError(true) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  return <div className="intelligence-page">
    <div className="command-eyebrow"><ShieldAlert size={14} /> IGNIS · RISK INTELLIGENCE</div>
    <h1>Operational priority</h1>
    <p className="intelligence-intro">Risk is a rule-based investigation priority derived from observed thermal behavior. It is separate from the anomaly model and does not predict fire cause.</p>
    {loading && <p className="intelligence-loading">Loading assessed event clusters…</p>}
    {error && <div className="command-error" role="status">Risk assessment is unavailable. Check the backend and refresh.</div>}
    {summary && <div className="risk-intelligence-grid">
      <article className="card-surface intelligence-card"><span className="section-kicker">CURRENT DISTRIBUTION</span><h2>{total ?? 'N/A'} assessed event clusters</h2>
        {(['high', 'medium', 'low'] as const).map((level) => <div className="risk-intelligence-row" key={level}><span className={`risk-badge risk-${level}`}>{level.toUpperCase()}</span><strong>{summary[level]}</strong><div className="distribution-track"><div className={`fill-${level}`} style={{ width: `${total ? summary[level] / total * 100 : 0}%` }} /></div></div>)}
        <p>High ≥50, medium 25–49, low &lt;25 on the current 0–100 operational scale.</p>
      </article>
      <article className="card-surface intelligence-card"><span className="section-kicker">METHOD</span><h2>Interpretable risk rules</h2>
        <p>Each event assessment exposes its score, severity, contributing factors, and explanation through the existing risk API. Thermal intensity, repeated detections, and persistence can raise priority.</p>
        <p>Priority is an analyst triage aid. Satellite heat detections alone cannot verify fire, identify an industrial cause, or predict escalation.</p>
        <Link to="/model" className="subtle-link">See model vs risk methods <ArrowUpRight size={14} /></Link>
      </article>
      <article className="card-surface intelligence-card risk-priority-card"><span className="section-kicker">HIGH PRIORITY QUEUE</span><h2>Events requiring review</h2>
        {priority.length ? priority.map(({ marker, event }) => <Link className="risk-priority-link" to={`/events/${marker.event_id}`} key={marker.event_id}>
          <span><strong>Event #{marker.event_id}</strong><small>{event ? locationLabel(event) : `${marker.latitude.toFixed(3)}° N, ${marker.longitude.toFixed(3)}° E`}</small></span>
          <span className="risk-badge risk-high">{marker.risk_score?.toFixed(0) ?? 'N/A'}/100</span><ArrowUpRight size={15} />
        </Link>) : <p>No high priority events in the current capture.</p>}
      </article>
    </div>}
  </div>
}
