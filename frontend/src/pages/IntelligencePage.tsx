import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '@/api/client'
import type { DataQualityReport, HistoricalStatistics, ThermalEventRead } from '@/types'
import { detectionTime, locationLabel } from '@/utils/intelligence'
import './IntelligencePage.css'

type Section = 'analytics' | 'model' | 'evidence'

export default function IntelligencePage({ section }: { section: Section }) {
  const [quality, setQuality] = useState<DataQualityReport | null>(null)
  const [statistics, setStatistics] = useState<HistoricalStatistics | null>(null)
  const [model, setModel] = useState<Record<string, unknown> | null>(null)
  const [chain, setChain] = useState<Record<string, unknown> | null>(null)
  const [events, setEvents] = useState<ThermalEventRead[]>([])
  const [error, setError] = useState(false)

  useEffect(() => {
    let active = true
    void Promise.allSettled([
      api.getDataQuality(), api.getHistoricalStatistics(), api.getModelStatus(),
      api.getBlockchainStatus(), api.listEvents({ page: 1, page_size: 10 }),
    ]).then((results) => {
      if (!active) return
      if (results[0].status === 'fulfilled') setQuality(results[0].value)
      if (results[1].status === 'fulfilled') setStatistics(results[1].value)
      if (results[2].status === 'fulfilled') setModel(results[2].value)
      if (results[3].status === 'fulfilled') setChain(results[3].value)
      if (results[4].status === 'fulfilled') setEvents(results[4].value.items)
      setError(results.every((result) => result.status === 'rejected'))
    })
    return () => { active = false }
  }, [])

  const title = section === 'analytics' ? 'Capture analytics' : section === 'model' ? 'Model transparency' : 'Evidence ledger'
  return <div className="intelligence-page">
    <div className="command-eyebrow">THERMALWATCH · {section.toUpperCase()}</div>
    <h1>{title}</h1>
    <p className="intelligence-intro">{section === 'analytics' ? 'Validated satellite observations, event formation, and activity across the saved FIRMS capture.' : section === 'model' ? 'What the current model uses and what its outputs can establish.' : 'Reproducible event hashes and a local audit chain. No blockchain provider is configured.'}</p>
    {error && <div className="command-error">The backend is unavailable. Start the API and refresh this page.</div>}
    {section === 'analytics' && <div className="intelligence-grid">
      <article className="card-surface intelligence-card"><span className="section-kicker">INGESTION</span><h2>Validation report</h2>
        <Metric label="Rows received" value={quality?.records_received} /><Metric label="Accepted" value={quality?.records_accepted} /><Metric label="Rejected" value={quality?.records_rejected} /><Metric label="Duplicates removed" value={quality?.duplicate_count} /><Metric label="Invalid coordinates" value={quality?.invalid_coordinates} /><Metric label="Invalid timestamps" value={quality?.invalid_timestamps} /><Metric label="Missing values" value={quality?.missing_values ? Object.entries(quality.missing_values).map(([key, value]) => `${key}: ${value}`).join(', ') : 'Unavailable'} />
        <p>Captured: {quality?.capture_time ? new Date(quality.capture_time).toLocaleString() : 'Unknown'}</p>
      </article>
      <article className="card-surface intelligence-card"><span className="section-kicker">EVENT FORMATION</span><h2>Observed activity</h2>
        <Metric label="Event clusters" value={statistics?.total_events} /><Metric label="Active locations" value={statistics?.active_locations} /><Metric label="Persistent sources" value={statistics?.persistent_sources} />
        <p>Clustering uses distance and acquisition time. Persistence reflects repeated detections in this capture.</p>
      </article>
      <article className="card-surface intelligence-card"><span className="section-kicker">PROVENANCE</span><h2>Source and limits</h2>
        {Object.entries(statistics?.observations_by_source ?? {}).map(([source, count]) => <Metric key={source} label={source} value={count} />)}
        <Metric label="Database" value={quality?.database_status ?? 'Unknown'} />
        <p>A short capture cannot establish a historical baseline or confirm a fire cause.</p>
      </article>
    </div>}
    {section === 'model' && <div className="intelligence-grid">
      <article className="card-surface intelligence-card"><span className="section-kicker">CURRENT METHOD</span><h2>{String(model?.model_type ?? 'Rules')}</h2>
        <Metric label="Status" value={model?.status} /><Metric label="Version" value={model?.version} /><Metric label="Training events" value={model?.training_samples} /><Metric label="Training type" value={model?.training_type} />
        <p>{String(model?.note ?? 'Model status unavailable.')}</p>
      </article>
      <article className="card-surface intelligence-card"><span className="section-kicker">PROVENANCE</span><h2>Training data</h2>
        <p>{String(model?.training_source ?? 'No eligible trained artifact loaded.')}</p>
        <Metric label="Calibrated" value={model?.calibrated === true ? 'Yes' : 'No'} /><Metric label="Independent validation" value={model?.validated === true ? 'Yes' : 'No'} />
        <p>An anomaly decision score ranks unusual feature combinations within the captured events. It is not a fire probability.</p>
      </article>
      <article className="card-surface intelligence-card"><span className="section-kicker">FEATURES</span><h2>Inputs</h2>
        <p>{Array.isArray(model?.feature_names) ? model.feature_names.join(' · ').replace(/_/g, ' ') : 'Unavailable'}</p>
        <p>Operational priority comes from separate, inspectable risk rules.</p>
      </article>
    </div>}
    {section === 'evidence' && <div className="intelligence-grid">
      <article className="card-surface intelligence-card"><span className="section-kicker">VERIFICATION</span><h2>Local audit chain</h2>
        <Metric label="Blockchain" value={chain?.status ?? 'Unavailable'} /><Metric label="On chain" value="No" /><Metric label="Local receipts" value={(chain?.local_chain as Record<string, unknown> | undefined)?.receipt_count} /><Metric label="Local chain valid" value={(chain?.local_chain as Record<string, unknown> | undefined)?.valid === true ? 'Yes' : 'No'} />
        <p>Each event package hashes source measurements, derived features, risk, and model output with SHA-256. Local receipts link to the previous receipt.</p>
      </article>
      <article className="card-surface intelligence-card evidence-list"><span className="section-kicker">INSPECT AN EVENT</span><h2>Recent evidence</h2>
        {events.map((event) => <Link key={event.id} to={`/events/${event.id}`}><strong>Event #{event.id}</strong><span>{locationLabel(event)} · {detectionTime(event.end_time)}</span></Link>)}
      </article>
    </div>}
  </div>
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return <div className="intelligence-metric"><span>{label}</span><strong>{value == null ? 'Unavailable' : String(value)}</strong></div>
}
