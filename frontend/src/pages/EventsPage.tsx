import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowUpRight, Search } from 'lucide-react'
import { api } from '@/api/client'
import type { EventClassification, HotspotMarker, ThermalEventRead } from '@/types'
import { classificationLabel, detectionTime, locationLabel } from '@/utils/intelligence'
import './EventsPage.css'

export default function EventsPage() {
  const scrollRef = useRef<HTMLElement>(null)
  const [events, setEvents] = useState<ThermalEventRead[]>([])
  const [total, setTotal] = useState<number | null>(null)
  const [markers, setMarkers] = useState<Map<number, HotspotMarker>>(new Map())
  const [classes, setClasses] = useState<Record<number, EventClassification>>({})
  const [mode, setMode] = useState<string>('LOADING')
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('ALL')
  const [risk, setRisk] = useState('ALL')
  const [classification, setClassification] = useState('ALL')
  const [page, setPage] = useState(1)

  useEffect(() => {
    void (async () => {
      const loadAllEvents = async () => {
        const first = await api.listEvents({ page: 1, page_size: 100 })
        const pages = Math.ceil(first.total / 100)
        if (pages <= 1) return first
        const rest = await Promise.all(Array.from({ length: pages - 1 }, (_, index) =>
          api.listEvents({ page: index + 2, page_size: 100 })))
        return { ...first, items: [...first.items, ...rest.flatMap((page) => page.items)] }
      }
      const [health, listing, hotspots] = await Promise.allSettled([
        api.getHealth(), loadAllEvents(), api.getMapHotspots({ limit: 1000 }),
      ])
      if (health.status === 'fulfilled') setMode(health.value.data_mode)
      else setMode('OFFLINE')
      if (hotspots.status === 'fulfilled') setMarkers(new Map(hotspots.value.markers.map((marker) => [marker.event_id, marker])))
      if (listing.status === 'rejected') {
        setError('Event records are unavailable. Check backend and database status.')
        return
      }
      setEvents(listing.value.items)
      setTotal(listing.value.total)
      const missing = listing.value.items.filter((event) => !event.classification_type).slice(0, 30)
      const classified = await Promise.allSettled(missing.map((event) => api.getEventClassification(event.id)))
      const next: Record<number, EventClassification> = {}
      classified.forEach((result, index) => {
        if (result.status === 'fulfilled') next[missing[index].id] = result.value
      })
      setClasses(next)
    })()
  }, [])

  const [anomalyFilter, setAnomalyFilter] = useState('ALL')

  const classOptions = useMemo(() => [...new Set(events.map((event) => classes[event.id]?.type ?? event.classification_type).filter((item): item is string => !!item))].sort(), [events, classes])
  const filtered = useMemo(() => events.filter((event) => {
    const marker = markers.get(event.id)
    const model = classes[event.id]
    const type = model?.type ?? event.classification_type
    const anomalyScore = event.anomaly_score ?? model?.anomaly_score
    const isOutlier = (anomalyScore != null && anomalyScore < 0) || type === 'anomalous_thermal_pattern'
    const text = `${event.id} ${event.location_name ?? ''} ${event.latitude} ${event.longitude} ${classificationLabel(type)}`.toLowerCase()
    return (status === 'ALL' || event.status === status) &&
      (risk === 'ALL' || marker?.risk_severity?.toUpperCase() === risk) &&
      (classification === 'ALL' || type === classification) &&
      (anomalyFilter === 'ALL' || (anomalyFilter === 'OUTLIERS' && isOutlier) || (anomalyFilter === 'TYPICAL' && !isOutlier)) &&
      text.includes(query.trim().toLowerCase())
  }).sort((a, b) => (markers.get(b.id)?.risk_score ?? -1) - (markers.get(a.id)?.risk_score ?? -1)),
  [events, markers, classes, query, status, risk, classification, anomalyFilter])
  const pageSize = 36
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize))
  const visible = filtered.slice((page - 1) * pageSize, page * pageSize)
  const changePage = (next: number) => {
    setPage(next)
    scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  return <section className="events-page" ref={scrollRef}>
    <div className="events-heading">
      <div>
        <p className="events-eyebrow">THERMAL INTELLIGENCE · EVENT INVESTIGATIONS</p>
        <h1>Operational Events &amp; Anomaly Index</h1>
        <p>{total == null ? 'Loading spatial-temporal event clusters' : `${total} spatial-temporal event clusters`} from {mode === 'DEMO DATA' ? 'synthetic demonstration observations' : 'NASA FIRMS VIIRS observations in the India query area'}.</p>
      </div>
      <div className="events-count mono">{total ?? '—'} indexed</div>
    </div>
    {mode === 'DEMO DATA' && <div className="banner banner-partial"><strong>DEMO DATA</strong> · These are synthetic scenarios, not NASA FIRMS detections or confirmed fires.</div>}
    {mode === 'FIRMS SNAPSHOT' && <div className="banner banner-partial"><strong>REAL NASA FIRMS DATA</strong> · Validated VIIRS detections across India. Unsupervised Isolation Forest anomaly ranking; local SHA-256 evidence hashing. Satellite thermal detections do not confirm fire causes.</div>}
    {error && <div className="banner banner-error" role="status">{error}</div>}
    <div className="events-controls">
      <label className="events-search"><Search size={15} /><input aria-label="Search events" placeholder="Search ID, location, coordinates, classification" value={query} onChange={(event) => { setQuery(event.target.value); setPage(1) }} /></label>
      <select aria-label="Filter anomaly" value={anomalyFilter} onChange={(event) => { setAnomalyFilter(event.target.value); setPage(1) }}>
        <option value="ALL">All patterns</option>
        <option value="OUTLIERS">Outliers only (anomaly score &lt; 0)</option>
        <option value="TYPICAL">Within typical capture range</option>
      </select>
      <select aria-label="Filter risk" value={risk} onChange={(event) => { setRisk(event.target.value); setPage(1) }}>
        <option value="ALL">All risk levels</option><option value="HIGH">High risk (≥50)</option><option value="MEDIUM">Medium risk (25–49)</option><option value="LOW">Low risk (&lt;25)</option>
      </select>
      <select aria-label="Filter status" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1) }}>
        <option value="ALL">All statuses</option><option value="PERSISTENT">Persistent</option><option value="ACTIVE">Active</option><option value="RESOLVED">Resolved</option><option value="UNKNOWN">Unknown</option>
      </select>
      <select aria-label="Filter classification" value={classification} onChange={(event) => { setClassification(event.target.value); setPage(1) }}>
        <option value="ALL">All classifications</option>{classOptions.map((value) => <option key={value} value={value}>{classificationLabel(value)}</option>)}
      </select>
    </div>
    {!error && filtered.length === 0 && <div className="events-empty">{mode === 'LOADING' ? 'Loading events…' : 'No events match these filters.'}</div>}
    {pageCount > 1 && <div className="events-pagination" aria-label="Event pages"><span>{filtered.length} matching events · page {page} of {pageCount}</span><button type="button" disabled={page === 1} onClick={() => changePage(page - 1)}>Previous</button><button type="button" disabled={page === pageCount} onClick={() => changePage(page + 1)}>Next</button></div>}
    <div className="events-list">
      {visible.map((event) => {
        const marker = markers.get(event.id)
        const model = classes[event.id]
        const riskLevel = marker?.risk_severity?.toLowerCase() ?? 'unknown'
        const days = event.active_days ?? model?.features?.active_days ?? null
        const score = event.anomaly_score ?? model?.anomaly_score
        const isOutlier = (score != null && score < 0) || (model?.type ?? event.classification_type) === 'anomalous_thermal_pattern'
        return <Link className={`events-item risk-edge-${riskLevel}`} to={`/events/${event.id}`} key={event.id}>
          <div className="events-item-main">
            <strong>Event #{event.id}</strong>
            <span className={`risk-badge risk-${riskLevel}`}>{riskLevel.toUpperCase()} {marker?.risk_score != null ? `${marker.risk_score.toFixed(0)}/100` : ''}</span>
            {isOutlier && <span className="risk-badge risk-high">ML OUTLIER</span>}
            <span className={`status-pill status-${event.status.toLowerCase()}`}>{event.status}</span>
            <ArrowUpRight size={15} className="events-arrow" />
          </div>
          <div className="events-item-class">
            {classificationLabel(model?.type ?? event.classification_type)}
            <small> · {score != null ? `Anomaly decision score: ${score.toFixed(4)}` : 'Anomaly score unavailable'}</small>
          </div>
          <div className="events-item-meta">{locationLabel(event)} · {event.latitude.toFixed(4)}° N, {event.longitude.toFixed(4)}° E · {detectionTime(event.end_time ?? event.start_time)}</div>
          <div className="events-item-meta">
            {event.observation_count} satellite {event.observation_count === 1 ? 'detection' : 'detections'}
            {event.max_frp != null ? ` · Peak FRP: ${event.max_frp.toFixed(1)} MW` : ''}
            {event.confidence_category ? ` · VIIRS: ${event.confidence_category}` : ''}
            {days != null ? ` · ${days} ${days === 1 ? 'day' : 'days'} duration` : ''}
            {event.average_intensity != null ? ` · ${event.average_intensity.toFixed(1)} K mean brightness` : ''}
            {` · ${event.source === 'DEMO_SYNTHETIC' ? 'synthetic source' : event.source ?? 'source unavailable'}`}
          </div>
        </Link>
      })}
    </div>
    {pageCount > 1 && <div className="events-pagination" aria-label="Event pages"><span>{filtered.length} matching events · page {page} of {pageCount}</span><button type="button" disabled={page === 1} onClick={() => changePage(page - 1)}>Previous</button><button type="button" disabled={page === pageCount} onClick={() => changePage(page + 1)}>Next</button></div>}
  </section>
}
