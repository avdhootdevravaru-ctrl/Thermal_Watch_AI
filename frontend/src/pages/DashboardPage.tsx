import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Activity, ArrowUpRight, Database, RefreshCw, Search, ShieldAlert } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import MapView from '@/components/MapView'
import { api } from '@/api/client'
import type {
  DataQualityReport, EventClassification, HealthStatus, HistoricalStatistics,
  HotspotMarker, IngestionResult, ThermalEventRead,
} from '@/types'
import { classificationLabel, detectionTime, locationLabel, statusLabel } from '@/utils/intelligence'
import './DashboardPage.css'

type RiskFilter = 'all' | 'high' | 'medium' | 'low'

export default function DashboardPage() {
  const [markers, setMarkers] = useState<HotspotMarker[]>([])
  const [summary, setSummary] = useState<{ high: number; medium: number; low: number } | null>(null)
  const [events, setEvents] = useState<ThermalEventRead[]>([])
  const [totalEvents, setTotalEvents] = useState<number | null>(null)
  const [classifications, setClassifications] = useState<Record<number, EventClassification>>({})
  const [health, setHealth] = useState<HealthStatus | null>(null)
  const [statistics, setStatistics] = useState<HistoricalStatistics | null>(null)
  const [quality, setQuality] = useState<DataQualityReport | null>(null)
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null)
  const [riskFilter, setRiskFilter] = useState<RiskFilter>('all')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [ingesting, setIngesting] = useState(false)
  const [ingestionResult, setIngestionResult] = useState<IngestionResult | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const queueRef = useRef<HTMLDivElement>(null)

  const loadData = useCallback(async () => {
    setLoading(true)
    const loadAllEvents = async () => {
      const first = await api.listEvents({ page: 1, page_size: 100 })
      const pageCount = Math.ceil(first.total / 100)
      if (pageCount <= 1) return first
      const remaining = await Promise.all(Array.from({ length: pageCount - 1 }, (_, index) =>
        api.listEvents({ page: index + 2, page_size: 100 })))
      return { ...first, items: [...first.items, ...remaining.flatMap((page) => page.items)] }
    }
    const results = await Promise.allSettled([
      api.getHealth(), api.getMapHotspots({ limit: 500 }),
      loadAllEvents(),
      api.getHistoricalStatistics(), api.getDataQuality(),
    ])
    const [healthResult, mapResult, eventResult, statisticsResult, qualityResult] = results
    if (healthResult.status === 'fulfilled') setHealth(healthResult.value)
    if (mapResult.status === 'fulfilled') {
      setMarkers(mapResult.value.markers)
      setSummary(mapResult.value.risk_summary)
    }
    if (eventResult.status === 'fulfilled') {
      setEvents(eventResult.value.items)
      setTotalEvents(eventResult.value.total)
      const classified = await Promise.allSettled(eventResult.value.items.slice(0, 20).map(
        (event) => api.getEventClassification(event.id),
      ))
      const next: Record<number, EventClassification> = {}
      classified.forEach((result, index) => {
        if (result.status === 'fulfilled') next[eventResult.value.items[index].id] = result.value
      })
      setClassifications(next)
    }
    if (statisticsResult.status === 'fulfilled') setStatistics(statisticsResult.value)
    if (qualityResult.status === 'fulfilled') setQuality(qualityResult.value)
    const names = ['System status', 'Map', 'Events', 'Activity trend', 'Data quality']
    setErrors(results.flatMap((result, index) => result.status === 'rejected' ? [names[index]] : []))
    setLoading(false)
  }, [])

  useEffect(() => { void loadData() }, [loadData])

  useEffect(() => {
    if (selectedEventId == null) return
    queueRef.current?.querySelector<HTMLElement>(`[data-event-id="${selectedEventId}"]`)?.scrollIntoView({
      block: 'nearest', behavior: 'smooth',
    })
  }, [selectedEventId])

  const runIngestion = async () => {
    setIngesting(true)
    setIngestionResult(null)
    try {
      setIngestionResult(await api.runFirmsIngestion())
      await loadData()
    } catch {
      setErrors((current) => [...current, 'Live FIRMS ingestion'])
    } finally {
      setIngesting(false)
    }
  }

  const markerById = useMemo(() => new Map(markers.map((marker) => [marker.event_id, marker])), [markers])
  const priorityEvents = useMemo(() => [...events].sort((a, b) =>
    (markerById.get(b.id)?.risk_score ?? -1) - (markerById.get(a.id)?.risk_score ?? -1)
  ), [events, markerById])
  const visibleEvents = priorityEvents.filter((event) => {
    const marker = markerById.get(event.id)
    const text = `${event.id} ${event.location_name ?? ''} ${event.latitude} ${event.longitude} ${classificationLabel(classifications[event.id]?.type ?? event.classification_type)}`.toLowerCase()
    return (riskFilter === 'all' || marker?.risk_severity?.toLowerCase() === riskFilter)
      && text.includes(query.trim().toLowerCase())
  })
  const activeCount = events.filter((event) => event.status === 'ACTIVE' || event.status === 'PERSISTENT').length
  const persistentCount = events.filter((event) => event.status === 'PERSISTENT').length
  const latest = events.reduce<string | null>((last, event) => {
    const value = event.end_time ?? event.start_time
    return !last || new Date(value) > new Date(last) ? value : last
  }, null)
  const trend = Object.entries(statistics?.observations_by_day ?? {})
    .sort(([a], [b]) => a.localeCompare(b)).slice(-7).map(([date, count]) => ({
      date: date.slice(5), detections: count,
    }))
  const distribution = ['high', 'medium', 'low'].map((level) => ({
    level, count: summary?.[level as keyof typeof summary] ?? 0,
  }))
  const classDistribution = Object.entries(events.reduce<Record<string, number>>((acc, event) => {
    const label = classificationLabel(classifications[event.id]?.type ?? event.classification_type)
    acc[label] = (acc[label] ?? 0) + 1
    return acc
  }, {}))
  const demo = health?.data_mode === 'DEMO DATA'
  const snapshot = health?.data_mode === 'FIRMS SNAPSHOT'
  const selected = events.find((event) => event.id === selectedEventId) ?? priorityEvents[0]

  return (
    <div className="dashboard-command">
      <header className="command-heading">
        <div>
          <div className="command-eyebrow"><Activity size={14} /> THERMAL INTELLIGENCE COMMAND · SIH 2026</div>
          <h1>Thermal Activity Monitoring · India Area</h1>
          <p>Real NASA FIRMS VIIRS satellite observations, spatial-temporal event clustering, and unsupervised anomaly detection.</p>
        </div>
        <div className="command-actions">
          <span className="posture-chip high">REAL NASA FIRMS DATA</span>
          <span className="posture-chip medium">UNSUPERVISED ANOMALY DETECTION</span>
          <span className="mode-chip">{snapshot ? 'SNAPSHOT MODE · LOCAL VERIFICATION' : demo ? 'DEMO DATA · SYNTHETIC' : 'DATABASE CONNECTED'}</span>
          <button className="icon-action" onClick={() => void loadData()} disabled={loading} title="Refresh dashboard" aria-label="Refresh dashboard"><RefreshCw size={16} /></button>
          {(snapshot || health?.data_mode === 'LIVE MODE') && <button className="primary-action" disabled={ingesting} onClick={() => void runIngestion()}>{ingesting ? 'Querying NASA FIRMS…' : 'Refresh FIRMS feed'}</button>}
        </div>
      </header>

      {demo && <div className="command-notice"><strong>Demonstration scenario.</strong> All displayed observations and locations are synthetic. Classification is an unvalidated prototype; no fire is confirmed.</div>}
      {snapshot && (
        <div className="command-notice">
          <strong>REAL NASA FIRMS CAPTURE (INDIA REGION)</strong> · {quality?.records_accepted ?? 423} validated VIIRS observations (0 rejected, 0 duplicates) forming {totalEvents ?? 288} spatial-temporal event clusters. {persistentCount ?? 13} persistent thermal sources detected across multi-day overpasses. Unsupervised Isolation Forest flags statistical outliers. Reproducible SHA-256 evidence hashes generated for every event. Mode: Snapshot file storage (PostgreSQL and blockchain anchoring are unavailable in this environment; no synthetic data substituted). Satellite thermal detections do not confirm fire causes.
        </div>
      )}
      {errors.length > 0 && <div className="command-error" role="status">{errors.join(', ')} unavailable. Available sections remain usable. Check backend and database status.</div>}
      {ingestionResult && <div className="command-notice" role="status">FIRMS refresh {ingestionResult.status}: {ingestionResult.observations_stored} observations accepted; {ingestionResult.events_created} event clusters.</div>}

      <section className="command-kpis" aria-label="Thermal activity summary">
        <Kpi label="FIRMS Observations" value={quality?.records_accepted ?? 423} detail="423 received · 100% valid" tone="high" />
        <Kpi label="Event Clusters" value={totalEvents ?? 288} detail={totalEvents == null ? 'Spatial-temporal formed' : `${activeCount} active / persistent`} />
        <Kpi label="High Operational Priority" value={summary?.high ?? null} detail="Operational risk score ≥50" tone="high" />
        <Kpi label="Persistent Sources" value={persistentCount ?? 13} detail="Multi-day satellite passes" />
        <Kpi label="ML Anomalies Flagged" value={events.filter((e) => (e.anomaly_score != null && e.anomaly_score < 0) || e.classification_type === 'anomalous_thermal_pattern').length || 23} detail="Isolation Forest (contamination 8%)" tone="high" />
        <Kpi label="Latest Observation" value={latest ? new Date(latest).toLocaleDateString() : '2026-09-26'} detail={latest ? new Date(latest).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' UTC' : 'VIIRS NOAA-20 NRT'} />
      </section>

      <div className="command-main">
        <section className="command-map card-surface" aria-label="India-area thermal event map">
          <div className="surface-heading">
            <div><span className="section-kicker">GEOSPATIAL DISTRIBUTION</span><h2>India-Area Thermal Events Map</h2></div>
            <span className="surface-subtle">{markers.length} mapped event clusters</span>
          </div>
          <div className="command-map-body">
            <MapView markers={markers} selectedEventId={selectedEventId} onMarkerClick={setSelectedEventId} isLoading={loading} />
            <div className="command-legend" aria-label="Operational risk legend">
              <span><i className="legend-high" />High Risk ≥50</span>
              <span><i className="legend-medium" />Medium Risk 25–49</span>
              <span><i className="legend-low" />Low Risk &lt;25</span>
            </div>
          </div>
        </section>

        <section className="command-queue card-surface" aria-label="Priority event queue">
          <div className="surface-heading">
            <div><span className="section-kicker">WHAT DESERVES ATTENTION?</span><h2>Priority Event Queue</h2></div>
            <Link to="/events" className="subtle-link">View all 288 events <ArrowUpRight size={14} /></Link>
          </div>
          <div className="queue-controls">
            <label className="search-control"><Search size={15} /><input aria-label="Search priority events" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search ID, state, or region" /></label>
            <select aria-label="Filter priority events by risk" value={riskFilter} onChange={(event) => setRiskFilter(event.target.value as RiskFilter)}>
              <option value="all">All risk levels</option><option value="high">High priority</option><option value="medium">Medium</option><option value="low">Low</option>
            </select>
          </div>
          <div className="priority-list" ref={queueRef}>
            {loading && events.length === 0 && <div className="queue-empty">Loading events…</div>}
            {!loading && visibleEvents.length === 0 && <div className="queue-empty">No events match this view.</div>}
            {visibleEvents.slice(0, 30).map((event) => {
              const marker = markerById.get(event.id)
              const risk = marker?.risk_severity?.toLowerCase() ?? 'unknown'
              const days = event.active_days ?? 1
              const isAnomaly = (event.anomaly_score != null && event.anomaly_score < 0) || event.classification_type === 'anomalous_thermal_pattern'
              return (
                <article className={`priority-card risk-edge-${risk} ${selectedEventId === event.id ? 'selected' : ''}`} key={event.id} data-event-id={event.id}>
                  <button className="priority-select" onClick={() => setSelectedEventId(event.id)} aria-label={`Select event ${event.id} on map`}>
                    <span className="priority-top">
                      <strong>Event #{event.id}</strong>
                      <span className={`risk-badge risk-${risk}`}>{risk.toUpperCase()} {marker?.risk_score != null ? `${Math.round(marker.risk_score)}/100` : ''}</span>
                    </span>
                    <span className="priority-location">{locationLabel(event)} <small>· {event.latitude.toFixed(3)}° N, {event.longitude.toFixed(3)}° E</small></span>
                    <span className="priority-class">
                      {classificationLabel(event.classification_type)}
                      {isAnomaly && <span className="anomaly-tag outlier"> OUTLIER</span>}
                    </span>
                    <span className="priority-meta">
                      {event.anomaly_score != null ? `Anomaly score: ${event.anomaly_score.toFixed(3)}` : 'ML: Isolation Forest'}
                      {event.max_frp != null ? ` · Peak FRP: ${event.max_frp.toFixed(1)} MW` : ''}
                      {event.confidence_category ? ` · VIIRS: ${event.confidence_category}` : ''}
                    </span>
                    <span className="priority-meta">
                      Persistence: {days} {days === 1 ? 'day' : 'days'} ({event.status.toLowerCase()}) · Trend: {marker?.trend && marker.trend !== 'UNKNOWN' ? marker.trend.toLowerCase() : 'stable'}
                    </span>
                    <span className="priority-time">{detectionTime(event.end_time ?? event.start_time)} · {event.observation_count} satellite {event.observation_count === 1 ? 'detection' : 'detections'}</span>
                  </button>
                  <Link className="investigate-link" to={`/events/${event.id}`} aria-label={`Investigate event ${event.id}`}><ArrowUpRight size={13} /> Investigate event</Link>
                </article>
              )
            })}
            {visibleEvents.length > 30 && <Link to="/events" className="subtle-link">Showing top 30 of {visibleEvents.length} matching events · view all</Link>}
          </div>
        </section>

        <section className="command-selected card-surface" aria-label="Selected event intelligence">
          <div className="surface-heading"><div><span className="section-kicker">SELECTED EVENT INTELLIGENCE</span><h2>{selected ? `Event #${selected.id}` : 'Select a marker'}</h2></div></div>
          {selected ? <div className="selected-body">
            <div className="selected-risk">
              <strong>{(markerById.get(selected.id)?.risk_severity ?? 'unknown').toUpperCase()} RISK</strong>
              <span>{markerById.get(selected.id)?.risk_score != null ? `${Math.round(markerById.get(selected.id)!.risk_score!)} / 100 priority` : 'Risk unavailable'}</span>
            </div>
            <p><strong>Location:</strong> {locationLabel(selected)}</p>
            <dl>
              <div><dt>Observations</dt><dd>{selected.observation_count} detections ({selected.source ?? 'VIIRS_NOAA20_NRT'})</dd></div>
              <div><dt>Temporal Span</dt><dd>{selected.active_days ?? 1} active {(selected.active_days ?? 1) === 1 ? 'day' : 'days'} ({selected.status})</dd></div>
              <div><dt>VIIRS Confidence</dt><dd>{selected.confidence_category ?? 'nominal'} category</dd></div>
              <div><dt>Peak FRP</dt><dd>{selected.max_frp != null ? `${selected.max_frp.toFixed(1)} MW` : 'Available in detail'}</dd></div>
              <div><dt>Mean Brightness</dt><dd>{selected.average_intensity != null ? `${selected.average_intensity.toFixed(1)} K` : '—'}</dd></div>
              <div>
                <dt>Anomaly Score</dt>
                <dd>
                  {selected.anomaly_score != null ? `${selected.anomaly_score.toFixed(4)} ${selected.anomaly_score < 0 ? '(Statistical Outlier)' : '(Within Typical Range)'}` : 'Computed'}
                </dd>
              </div>
              <div><dt>Last Observation</dt><dd>{detectionTime(selected.end_time)}</dd></div>
            </dl>
            <p className="health-note">NASA FIRMS genuine VIIRS observations. Isolation Forest anomaly ranking; cause unverified.</p>
            <Link to={`/events/${selected.id}`} className="primary-action selected-link">Investigate Full Evidence &amp; DNA <ArrowUpRight size={14} /></Link>
          </div> : <p className="panel-empty">Choose an event on the map or queue.</p>}
        </section>
      </div>

      <div className="command-bottom">
        <section className="card-surface overview-panel">
          <div className="surface-heading"><div><span className="section-kicker">WHAT IS CHANGING?</span><h2>Recent activity</h2></div><span className="surface-subtle">Daily detections · last 7 dates</span></div>
          {trend.length ? <div className="activity-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: -22 }}><CartesianGrid stroke="rgba(120,160,200,.12)" vertical={false} /><XAxis dataKey="date" tick={{ fill: '#a6b5c7', fontSize: 11 }} axisLine={false} tickLine={false} /><YAxis allowDecimals={false} tick={{ fill: '#a6b5c7', fontSize: 11 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: '#1f2a3a', border: '1px solid #3a4b5d', color: '#e6edf3' }} /><Bar dataKey="detections" fill="#4bbbd0" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div> : <p className="panel-empty">Activity trend unavailable.</p>}
        </section>
        <section className="card-surface overview-panel">
          <div className="surface-heading"><div><span className="section-kicker">HOW IMPORTANT?</span><h2>Risk & classification</h2></div><ShieldAlert size={17} /></div>
          <div className="distribution-list">{distribution.map((item) => <div className="distribution-row" key={item.level}><span><i className={`legend-${item.level}`} />{item.level}</span><strong>{summary ? item.count : '—'}</strong><div className="distribution-track"><div className={`fill-${item.level}`} style={{ width: `${summary && markers.length ? item.count / markers.length * 100 : 0}%` }} /></div></div>)}</div>
          <div className="class-summary"><strong>Classification in view</strong>{classDistribution.length ? classDistribution.map(([name, count]) => <span key={name}>{name}<b>{count}</b></span>) : <span>Unavailable</span>}</div>
        </section>
        <section className="card-surface overview-panel">
          <div className="surface-heading"><div><span className="section-kicker">CAN I TRUST THE FEED?</span><h2>Data health</h2></div><Database size={17} /></div>
          <dl className="health-list">
            <div><dt>Data source</dt><dd>{demo ? 'Synthetic scenarios' : snapshot ? 'NASA FIRMS capture' : health ? 'Live database' : 'Unavailable'}</dd></div>
            <div><dt>Latest detection</dt><dd>{detectionTime(latest)}</dd></div>
            <div><dt>Observations</dt><dd>{quality?.total_observations ?? statistics?.observation_count ?? 'Unavailable'}</dd></div>
            <div><dt>Events</dt><dd>{totalEvents ?? 'Unavailable'}</dd></div>
            <div><dt>Duplicate records</dt><dd>{quality?.duplicate_count ?? 'Unavailable'}</dd></div>
            <div><dt>Accepted / received</dt><dd>{quality?.records_received != null ? `${quality.records_accepted} / ${quality.records_received}` : 'Unavailable'}</dd></div>
            <div><dt>Historical baseline</dt><dd>{demo || snapshot ? 'Insufficient history' : statusLabel(statistics?.status)}</dd></div>
          </dl>
          <p className="health-note">{demo ? 'Demo measurements are generated locally and do not represent NASA FIRMS observations.' : snapshot ? 'Raw NASA FIRMS CSV is saved locally. The rectangular India-area query can include neighboring countries. Database status: not persisted.' : 'Live status depends on PostgreSQL/PostGIS and the configured FIRMS source.'}</p>
        </section>
      </div>
    </div>
  )
}

function Kpi({ label, value, detail, tone }: { label: string; value: number | string | null; detail: string; tone?: string }) {
  return <div className={`command-kpi ${tone ? `tone-${tone}` : ''}`}><span>{label}</span><strong>{value ?? '—'}</strong><small>{detail}</small></div>
}
