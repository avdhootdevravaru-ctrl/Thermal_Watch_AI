import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
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
  const [loading, setLoading] = useState(true)

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
      setLoading(false)
    })
    return () => { active = false }
  }, [])

  const title = section === 'analytics' ? 'Capture analytics' : section === 'model' ? 'Model transparency' : 'Evidence ledger'
  const daily = [...new Set([...Object.keys(statistics?.observations_by_day ?? {}), ...Object.keys(quality?.events_by_date ?? {})])].sort().map((date) => ({
    date, observations: statistics?.observations_by_day[date] ?? 0, events: quality?.events_by_date[date] ?? 0,
  }))
  const sourceRows = Object.entries(statistics?.observations_by_source ?? {}).map(([source, observations]) => ({ source, observations }))
  const weak = model?.weak_classifier as Record<string, unknown> | undefined
  const evaluation = weak?.evaluation_metrics as Record<string, unknown> | undefined
  return <div className="intelligence-page">
    <div className="command-eyebrow">IGNIS · {section.toUpperCase()}</div>
    <h1>{title}</h1>
    <p className="intelligence-intro">{section === 'analytics' ? 'Validated satellite observations, event formation, and activity across the saved FIRMS capture.' : section === 'model' ? 'What the current model uses and what its outputs can establish.' : 'Reproducible event hashes, local audit receipts, and current blockchain status.'}</p>
    {error && <div className="command-error">The backend is unavailable. Start the API and refresh this page.</div>}
    {loading && <p className="intelligence-loading">Loading {section} from the API…</p>}
    {section === 'analytics' && <div className="intelligence-grid">
      <article className="card-surface intelligence-card intelligence-chart-card"><span className="section-kicker">TEMPORAL ACTIVITY</span><h2>Satellite observations & formed events</h2>
        {daily.length ? <div className="intelligence-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={daily} margin={{ top: 8, right: 8, bottom: 4, left: -18 }}><CartesianGrid vertical={false} stroke="var(--border-default)" /><XAxis dataKey="date" tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} /><YAxis allowDecimals={false} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} /><Tooltip contentStyle={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-default)' }} /><Legend /><Bar dataKey="observations" name="FIRMS observations" fill="var(--accent-primary)" radius={[3, 3, 0, 0]} /><Bar dataKey="events" name="Event clusters" fill="var(--risk-medium)" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div> : <p>No daily observations are available.</p>}
      </article>
      <article className="card-surface intelligence-card intelligence-chart-card"><span className="section-kicker">SOURCE PROVENANCE</span><h2>Observations by satellite feed</h2>
        {sourceRows.length ? <div className="intelligence-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={sourceRows} layout="vertical" margin={{ top: 8, right: 20, bottom: 4, left: 54 }}><CartesianGrid horizontal={false} stroke="var(--border-default)" /><XAxis type="number" allowDecimals={false} tick={{ fill: 'var(--text-secondary)', fontSize: 11 }} /><YAxis type="category" dataKey="source" width={124} tick={{ fill: 'var(--text-secondary)', fontSize: 10 }} /><Tooltip contentStyle={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border-default)' }} /><Bar dataKey="observations" fill="var(--accent-secondary)" radius={[0, 3, 3, 0]} /></BarChart></ResponsiveContainer></div> : <p>Source distribution is unavailable.</p>}
      </article>
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
      <article className="card-surface intelligence-card intelligence-flow-card"><span className="section-kicker">FROM MEASUREMENT TO INTERPRETATION</span><h2>What the model does</h2>
        <div className="evidence-flow">{['Validated satellite detections', 'First-day thermal & spatial features', String(weak?.model_name ?? 'Model unavailable'), 'Later-day re-detection class', 'Research signal for operator review', 'No fire-cause or fire-probability claim'].map((step, index) => <div className="evidence-flow-step" key={step}><span>{String(index + 1).padStart(2, '0')}</span><strong>{step}</strong></div>)}</div>
      </article>
      <article className="card-surface intelligence-card weak-model-card"><span className="section-kicker">WEAKLY SUPERVISED CLASSIFIER · REAL FIRMS</span><h2>{String(weak?.model_name ?? 'Classifier unavailable')}</h2>
        <p>Target: later-day re-detection of an event first observed on an earlier day. Labels come from this capture's observed recurrence, not reviewed wildfire or industrial-fire cases.</p>
        <Metric label="Inference available" value={weak ? weak.inference_available === true ? 'Yes' : 'No' : 'Unavailable'} /><Metric label="Version" value={weak?.model_version} /><Metric label="Training / held-out events" value={weak?.training_samples != null ? `${weak.training_samples} / ${weak.holdout_samples}` : 'Unavailable'} /><Metric label="Training capture" value={weak?.training_dataset} /><Metric label="Feature count" value={Array.isArray(weak?.feature_names) ? weak.feature_names.length : 'Unavailable'} /><Metric label="Feature schema" value={weak?.feature_version} /><Metric label="Trained" value={weak?.trained_at ? new Date(String(weak.trained_at)).toLocaleString() : 'Unavailable'} /><Metric label="Artifact SHA-256" value={weak?.artifact_hash} />
        <p><strong>Inputs:</strong> {Array.isArray(weak?.feature_names) ? weak.feature_names.join(' · ').replace(/_/g, ' ') : 'Unavailable'}</p>
        <p><strong>Weak label:</strong> {String(weak?.label_strategy ?? 'Unavailable')}</p>
        <p><strong>Does not predict:</strong> wildfire, industrial cause, or calibrated fire probability.</p>
        <p>{String(weak?.note ?? 'No trained real-FIRMS artifact is loaded.')}</p>
      </article>
      <article className="card-surface intelligence-card weak-model-card"><span className="section-kicker">RESEARCH EVALUATION · NOT OPERATIONAL FIRE PREDICTION</span><h2>Measured weak-label agreement</h2>
        <Metric label="Holdout size" value={evaluation?.holdout_size} /><Metric label="Accuracy" value={typeof evaluation?.accuracy === 'number' ? `${(evaluation.accuracy * 100).toFixed(1)}%` : 'Unavailable'} /><Metric label="Balanced accuracy" value={typeof evaluation?.balanced_accuracy === 'number' ? `${(evaluation.balanced_accuracy * 100).toFixed(1)}%` : 'Unavailable'} /><Metric label="Recurrence precision" value={typeof evaluation?.precision_positive === 'number' ? `${(evaluation.precision_positive * 100).toFixed(1)}%` : 'Unavailable'} /><Metric label="Recurrence recall" value={typeof evaluation?.recall_positive === 'number' ? `${(evaluation.recall_positive * 100).toFixed(1)}%` : 'Unavailable'} /><Metric label="Recurrence F1" value={typeof evaluation?.f1_positive === 'number' ? evaluation.f1_positive.toFixed(3) : 'Unavailable'} />
        <p>These results come from a small same-capture holdout. They are not independent field accuracy and do not validate fire-cause identification.</p>
        <Metric label="Validation split" value={evaluation?.split_method} /><Metric label="Model selection" value={evaluation?.selection_method} />
        <Metric label="ROC-AUC" value={typeof evaluation?.roc_auc === 'number' ? evaluation.roc_auc.toFixed(3) : 'Unavailable'} />
        {evaluation?.model_comparison != null && typeof evaluation.model_comparison === 'object' && Object.entries(evaluation.model_comparison).map(([name, result]) => <Metric key={name} label={`${name} · training CV F1`} value={Number((result as { mean_training_cv_f1: number }).mean_training_cv_f1).toFixed(3)} />)}
        {Array.isArray(evaluation?.limitations) && evaluation.limitations.map((limitation) => <p key={String(limitation)}>{String(limitation)}</p>)}
      </article>
      <article className="card-surface intelligence-card"><span className="section-kicker">ANOMALY DETECTION</span><h2>{String(model?.model_type ?? 'Unavailable')}</h2>
        <Metric label="Inference status" value={model?.status} /><Metric label="Version" value={model?.version} /><Metric label="Training events" value={model?.training_samples} /><Metric label="Training type" value={model?.training_type} /><Metric label="Training timestamp" value={model?.trained_at ?? 'Unavailable'} /><Metric label="Evaluation metrics" value={model?.evaluation_metrics ?? 'Unavailable'} />
        <p>{String(model?.note ?? 'Model status unavailable.')}</p>
      </article>
      <article className="card-surface intelligence-card"><span className="section-kicker">PROVENANCE</span><h2>Training data</h2>
        <p>{String(model?.training_source ?? 'No eligible trained artifact loaded.')}</p>
        <Metric label="Calibrated" value={model ? model.calibrated === true ? 'Yes' : 'No' : 'Unavailable'} /><Metric label="Independent validation" value={model ? model.validated === true ? 'Yes' : 'No' : 'Unavailable'} />
        <p>An anomaly decision score ranks unusual feature combinations within the captured events. It is not a fire probability.</p>
      </article>
      <article className="card-surface intelligence-card"><span className="section-kicker">CLASSIFICATION & RISK</span><h2>Separate decisions</h2>
        <p>{Array.isArray(model?.feature_names) ? model.feature_names.join(' · ').replace(/_/g, ' ') : 'Unavailable'}</p>
        <Metric label="Event classification" value={model?.status === 'UNSUPERVISED_PROTOTYPE' ? 'Anomalous / typical thermal pattern' : model ? 'See event detail for active method' : 'Unavailable'} /><Metric label="Operational risk" value="Rule-based 0–100 priority" />
        <p>The anomaly score is an uncalibrated model decision value. The risk score comes from separate, inspectable rules. Neither is a fire probability.</p>
      </article>
    </div>}
    {section === 'evidence' && <div className="intelligence-grid">
      <article className="card-surface intelligence-card intelligence-flow-card"><span className="section-kicker">CHAIN OF CUSTODY</span><h2>From observation to verification</h2>
        <div className="evidence-flow">{['Satellite observation', 'Thermal event', 'Evidence package', 'SHA-256 digest', 'Local verification registry', chain?.on_chain === true ? 'EVM testnet anchor' : 'Blockchain fallback active'].map((step, index) => <div className="evidence-flow-step" key={step}><span>{String(index + 1).padStart(2, '0')}</span><strong>{step}</strong></div>)}</div>
        <p>Local hash verification and public blockchain anchoring are distinct audit tiers.</p>
      </article>
      <article className="card-surface intelligence-card"><span className="section-kicker">VERIFICATION</span><h2>Audit & chain status</h2>
        <Metric label="Blockchain status" value={chain?.status ?? 'Unavailable'} />
        <Metric label="On chain" value={chain?.on_chain === true ? 'Yes (Verified)' : 'No (Local only)'} />
        {chain?.configured === true && <Metric label="Network" value={String(chain.network ?? 'Sepolia testnet').toUpperCase()} />}
        {Boolean(chain?.contract_address) && <div className="intelligence-metric"><span>Contract</span><a href={`${String(chain?.explorer_address_url ?? 'https://sepolia.etherscan.io/address/')}${String(chain?.contract_address)}`} target="_blank" rel="noreferrer" style={{ color: 'var(--accent-primary)', textDecoration: 'underline', fontFamily: 'monospace', fontSize: '11px' }}>{String(chain?.contract_address).slice(0, 10)}…{String(chain?.contract_address).slice(-8)}</a></div>}
        <Metric label="Local receipts" value={(chain?.local_chain as Record<string, unknown> | undefined)?.receipt_count} />
        <Metric label="Local chain valid" value={(chain?.local_chain as Record<string, unknown> | undefined)?.valid === true ? 'Yes' : chain ? 'No' : 'Unavailable'} />
        <p>{String(chain?.note ?? 'Blockchain unavailable — local evidence verification active.')}</p>
      </article>
      <article className="card-surface intelligence-card evidence-list"><span className="section-kicker">INSPECT AN EVENT</span><h2>Recent evidence packages</h2>
        {events.map((event) => <Link key={event.id} to={`/events/${event.id}`}><strong>Event #{event.id}</strong><span>{locationLabel(event)} · {detectionTime(event.end_time)}</span></Link>)}
      </article>
    </div>}
  </div>
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return <div className="intelligence-metric"><span>{label}</span><strong>{value == null ? 'Unavailable' : String(value)}</strong></div>
}
