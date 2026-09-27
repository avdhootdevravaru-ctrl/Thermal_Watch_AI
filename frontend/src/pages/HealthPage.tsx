import { useEffect, useState } from 'react'
import { Activity, Database, Fingerprint, Radio, ShieldCheck } from 'lucide-react'
import { api } from '@/api/client'
import type { DataQualityReport, FirmsStatus, HealthStatus, HistoricalStatistics } from '@/types'
import './IntelligencePage.css'

type HealthData = {
  health: HealthStatus | null
  firms: FirmsStatus | null
  ingestion: Record<string, unknown> | null
  quality: DataQualityReport | null
  statistics: HistoricalStatistics | null
  database: Record<string, unknown> | null
  model: Record<string, unknown> | null
  chain: Record<string, unknown> | null
}

const empty: HealthData = { health: null, firms: null, ingestion: null, quality: null, statistics: null, database: null, model: null, chain: null }

export default function HealthPage() {
  const [data, setData] = useState<HealthData>(empty)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    const refresh = () => void Promise.allSettled([
      api.getHealth(), api.getIngestionStatus(), api.getDataQuality(), api.getHistoricalStatistics(),
      api.getDatabaseHealth(), api.getModelStatus(), api.getBlockchainStatus(), api.getFirmsStatus(),
    ]).then((results) => {
      if (!active) return
      const value = <T,>(index: number): T | null => results[index].status === 'fulfilled' ? results[index].value as T : null
      setData({ health: value(0), ingestion: value(1), quality: value(2), statistics: value(3), database: value(4), model: value(5), chain: value(6), firms: value(7) })
      setLoading(false)
    })
    refresh()
    const timer = window.setInterval(refresh, 30000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  const ingestion = data.ingestion
  const chain = data.chain
  const localChain = chain?.local_chain as Record<string, unknown> | undefined
  const weak = data.model?.weak_classifier as Record<string, unknown> | undefined
  const accepted = data.quality?.records_accepted
  const received = data.quality?.records_received
  const databaseState = String(data.database?.status ?? 'UNAVAILABLE')
  const rows = [
    { icon: <Radio size={17} />, name: 'NASA FIRMS / VIIRS', state: data.firms?.status === 'SAVED_CAPTURE' ? 'SAVED CAPTURE' : data.firms?.status?.replace(/_/g, ' ') ?? String(ingestion?.status ?? 'UNAVAILABLE'), detail: data.firms?.capture_timestamp ? `${String(data.firms.source ?? 'FIRMS')} · captured ${new Date(data.firms.capture_timestamp).toLocaleString()} · ${String(data.firms.freshness).toLowerCase()} observations` : 'Capture timestamp unavailable' },
    { icon: <Radio size={17} />, name: 'Capture records', state: data.firms?.validation_status?.replace(/_/g, ' ') ?? 'UNAVAILABLE', detail: data.firms?.observation_count != null ? `${data.firms.observation_count} validated observations · ${data.firms.event_count ?? 0} event clusters · ${data.firms.records_rejected ?? 0} rejected · ${data.firms.duplicates_removed ?? 0} duplicates` : 'Record counts unavailable' },
    { icon: <ShieldCheck size={17} />, name: 'Validation', state: accepted != null ? 'AVAILABLE' : 'UNAVAILABLE', detail: received != null ? `${accepted} accepted / ${received} received · ${data.quality?.records_rejected ?? 'N/A'} rejected · ${data.quality?.duplicate_count ?? 'N/A'} duplicates` : 'Report unavailable' },
    { icon: <Activity size={17} />, name: 'Preprocessing & clustering', state: data.statistics?.total_events != null ? 'AVAILABLE' : 'UNAVAILABLE', detail: data.statistics?.total_events != null ? `${data.statistics.total_events} event clusters · ${data.statistics.persistent_sources} persistent sources` : 'Statistics unavailable' },
    { icon: <Database size={17} />, name: 'PostgreSQL / PostGIS', state: String(data.database?.database ?? 'UNAVAILABLE').replace(/_/g, ' '), detail: data.database?.database === 'CONNECTED' ? `PostGIS ${String(data.database?.postgis_version ?? 'available')} · ${String(data.database?.persisted_observations ?? 0)} observations · ${String(data.database?.persisted_events ?? 0)} events persisted${data.database?.note ? ' · ' + data.database.note : ''}` : databaseState === 'snapshot' ? `Real FIRMS capture served from local files. ${String(data.database?.note ?? 'Install PostgreSQL + PostGIS to enable persistence.')}` : String(data.database?.error ?? 'Database check unavailable') },
    { icon: <Activity size={17} />, name: 'ML anomaly detection', state: String(data.model?.status ?? 'UNAVAILABLE').replace(/_/g, ' '), detail: `${String(data.model?.model_type ?? 'Model unavailable')} · ${String(data.model?.training_samples ?? 'N/A')} training events` },
    { icon: <Activity size={17} />, name: 'Weak recurrence classifier', state: weak?.model_loaded === true ? 'AVAILABLE' : 'UNAVAILABLE', detail: weak?.model_loaded === true ? `${String(weak.model_name)} · ${String(weak.training_samples)} real-FIRMS training events · same-capture weak-label evaluation` : 'Compatible real-FIRMS artifact unavailable' },
    { icon: <Fingerprint size={17} />, name: 'Evidence & SHA-256', state: localChain?.valid === true ? 'AVAILABLE' : 'UNAVAILABLE', detail: localChain ? `${String(localChain.receipt_count ?? 0)} local receipts · chain ${localChain.valid === true ? 'valid' : 'unverified'}` : 'Local chain status unavailable' },
    { icon: <Fingerprint size={17} />, name: 'On-chain anchor', state: chain?.configured === true ? String(chain.status ?? 'AVAILABLE') : 'NOT CONFIGURED', detail: chain?.on_chain === true ? `${String(chain.network ?? 'Sepolia').toUpperCase()} testnet active · Contract ${String(chain.contract_address).slice(0, 10)}… · Block #${chain.current_block ?? 'latest'}` : chain?.configured === true ? `${String(chain.note ?? 'Blockchain configured but RPC unavailable · local evidence active.')}` : 'No blockchain transaction is claimed; local evidence verification active.' },
  ]

  return <div className="intelligence-page">
    <div className="command-eyebrow">IGNIS · OPERATIONS</div>
    <h1>System health</h1>
    <p className="intelligence-intro">Connection checks update every 30 seconds. Captured data, local evidence, database persistence, and blockchain each retain their own provenance.</p>
    {loading ? <p className="health-loading">Checking data pipeline…</p> : <div className="health-grid">
      {rows.map((row) => <article className="card-surface health-card" key={row.name}>
        <div className="health-card-icon">{row.icon}</div>
        <div><h2>{row.name}</h2><p>{row.detail}</p></div>
        <strong className={`health-state ${/UNAVAILABLE|NOT PERSISTED|NOT CONFIGURED|DEMO/.test(row.state) ? 'health-state-warn' : ''}`}>{row.state}</strong>
      </article>)}
    </div>}
    {!loading && !data.health && <div className="command-error" role="status">The backend is unavailable. Start the API and refresh this page.</div>}
  </div>
}
