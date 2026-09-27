import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, MapPin, Activity, Calendar, AlertTriangle, Layers, TrendingUp, TrendingDown, Minus, Zap, Target, Database, ShieldAlert } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from 'recharts'
import { api } from '@/api/client'
import MapView from '@/components/MapView'
import type { ThermalEventDetail, EventHistoryPoint, ThermalProfileResponse, WeakClassification } from '@/types'
import { formatTimelineDate, formatObservationDate } from '@/utils/timestampUtils'
import { classificationLabel, detectionTime, locationLabel, statusLabel } from '@/utils/intelligence'
import './EventDetailPage.css'

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [event, setEvent] = useState<ThermalEventDetail | null>(null)
  const [history, setHistory] = useState<EventHistoryPoint[]>([])
  const [profile, setProfile] = useState<ThermalProfileResponse | null>(null)
  const [evidence, setEvidence] = useState<Record<string, any> | null>(null)
  const [weak, setWeak] = useState<WeakClassification | null>(null)
  const [anchoring, setAnchoring] = useState(false)
  const [anchoringBlockchain, setAnchoringBlockchain] = useState(false)
  const [anchorError, setAnchorError] = useState<string | null>(null)
  const [nearby, setNearby] = useState<{ facilities: Array<{ name?: string; type?: string; distance_km?: number }>; note?: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const eventId = Number(id)

  const load = useCallback(async () => {
    if (!Number.isSafeInteger(eventId) || eventId <= 0) {
      setError('This event ID is invalid. Choose an event from the queue.')
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [detail, hist, prof, context, proof, weakResult] = await Promise.allSettled([
        api.getEvent(eventId),
        api.getEventHistory(eventId),
        api.getEventProfile(eventId),
        api.getNearbyFacilities(eventId),
        api.getEvidencePackage(eventId),
        api.getWeakClassification(eventId),
      ])
      if (detail.status === 'rejected') throw detail.reason
      setEvent(detail.value)
      setHistory(hist.status === 'fulfilled' ? hist.value : [])
      setProfile(prof.status === 'fulfilled' ? prof.value : null)
      setNearby(context.status === 'fulfilled' ? context.value as typeof nearby : null)
      setEvidence(proof.status === 'fulfilled' ? proof.value : null)
      setWeak(weakResult.status === 'fulfilled' ? weakResult.value : null)
    } catch (e) {
      setError('This event could not be loaded. It may no longer be in the current capture, or the API is unavailable.')
    } finally {
      setLoading(false)
    }
  }, [eventId])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) {
    return (
      <div className="event-detail">
        <div className="event-loading">
          <div className="spinner" />
          <span>Loading event…</span>
        </div>
      </div>
    )
  }

  if (error || !event) {
    return (
      <div className="event-detail">
        <div className="event-error">
          <AlertTriangle size={24} />
          <h2>Event not found</h2>
          <p>{error ?? `No thermal event with ID ${eventId}`}</p>
          <Link to="/" className="back-link">
            ← Back to map
          </Link>
        </div>
      </div>
    )
  }

  const chartData = history.map((p) => ({
    date: formatTimelineDate(p.timestamp),
    intensity: p.intensity,
    observation_count: p.observation_count,
  }))

  const hasProfile = !!profile && profile.observation_count > 0
  const classification = event.risk?.classification
  const risk = event.risk
  const why = [
    `${event.observation_count} ${event.observation_count === 1 ? 'detection' : 'detections'}`,
    event.persistence?.active_days != null ? `observed on ${event.persistence.active_days} ${event.persistence.active_days === 1 ? 'day' : 'days'}` : null,
    event.persistence?.average_intensity != null ? `mean brightness ${event.persistence.average_intensity.toFixed(1)} K` : null,
    risk?.score != null ? `${risk.severity.toLowerCase()} operational risk (${risk.score.toFixed(0)}/100)` : null,
  ].filter(Boolean).join(' · ')
  const eventMarker = [{
    event_id: event.id, latitude: event.latitude, longitude: event.longitude,
    status: event.status, observation_count: event.observation_count,
    persistence_score: event.persistence_score, trend: event.persistence?.trend ?? null,
    risk_score: risk?.score ?? null, risk_severity: risk?.severity?.toLowerCase() ?? null,
    last_detection: event.end_time,
  }]
  const anchorEvidence = async () => {
    setAnchoring(true)
    setAnchorError(null)
    try {
      await api.anchorLocalEvidence(eventId)
      setEvidence(await api.getEvidencePackage(eventId))
    } catch {
      setAnchorError('Could not write the local receipt. The evidence package remains available for inspection.')
    } finally {
      setAnchoring(false)
    }
  }

  const anchorOnBlockchain = async () => {
    setAnchoringBlockchain(true)
    setAnchorError(null)
    try {
      await api.anchorBlockchainEvidence(eventId)
      setEvidence(await api.getEvidencePackage(eventId))
    } catch {
      setAnchorError('Blockchain anchoring failed. Check testnet RPC connection and account balance.')
    } finally {
      setAnchoringBlockchain(false)
    }
  }

  return (
    <div className="event-detail">
      <div className="event-detail-header">
        <button className="back-btn" onClick={() => navigate('/events')} aria-label="Back to events">
          <ArrowLeft size={14} />
          <span>Back</span>
        </button>
        <div className="event-id-block">
          <span className="event-label mono">EVENT</span>
          <span className="event-id mono">#{event.id}</span>
        </div>
        <div className="detail-heading-meta">{locationLabel(event)} · {detectionTime(event.end_time ?? event.start_time)}</div>
        <div className={`status-pill-large status-${event.status.toLowerCase()}`}>
          {event.status}
        </div>
        {event.risk?.severity && <div className={`status-pill-large detail-risk-${event.risk.severity.toLowerCase()}`}>{event.risk.severity.toUpperCase()} RISK · {event.risk.score?.toFixed(0) ?? 'N/A'}/100</div>}
      </div>

      {event.observations.some((observation) => observation.source === 'DEMO_SYNTHETIC') && (
        <div className="banner banner-partial">
          <strong>DEMO DATA</strong> · Synthetic thermal observations. Classification is {classification?.model_status === 'WEAK_LABEL_PROTOTYPE' ? 'a weak-label ML prototype' : 'a rule-based fallback'}; historical baseline is not validated.
        </div>
      )}
      {!event.observations.some((observation) => observation.source === 'DEMO_SYNTHETIC') && <div className="banner banner-partial"><strong>NASA FIRMS capture</strong> · Source: {event.observations[0]?.source ?? 'Unknown'}. This event is built from satellite thermal detections; fire cause and historical baseline are unverified.</div>}

      <div className="event-detail-body">
        <section className="detail-panel detail-panel-wide investigation-summary">
          <header className="detail-panel-header"><ShieldAlert size={14} /><h3>Why this event matters</h3></header>
          <p>{why}. These measurements identify a thermal event; they do not confirm a fire or its cause.</p>
        </section>

        <section className="detail-panel detail-panel-wide event-location-panel">
          <header className="detail-panel-header"><MapPin size={14} /><h3>Location & surrounding map</h3><span className="methodology-badge">{event.latitude.toFixed(4)}° N · {event.longitude.toFixed(4)}° E</span></header>
          <div className="event-location-map"><MapView markers={eventMarker} selectedEventId={event.id} onMarkerClick={() => {}} /></div>
          <p className="context-message">Marker location is the centroid of the observed thermal event. OpenStreetMap provides geographic context; proximity does not establish cause.</p>
        </section>

        <section className="detail-panel detail-panel-wide">
          <header className="detail-panel-header"><Zap size={14} /><h3>Estimated classification</h3><span className="methodology-badge">{classification?.model_status?.replace(/_/g, ' ') ?? 'UNAVAILABLE'}</span></header>
          {classification ? <div className="classification-layout">
            <div><p className="classification-lead">{classificationLabel(classification.type)}</p>
              <p className="classification-caveat">{classification.methodology ?? 'Rule-based classification'}</p>
              <p className="classification-caveat">{classification.confidence != null ? `${classification.is_ml ? 'Prototype class vote' : 'Heuristic confidence'}: ${(classification.confidence * 100).toFixed(0)}%. This is separate from operational risk and is not a validated accuracy measure.` : classification.anomaly_score != null ? `Anomaly decision score: ${classification.anomaly_score.toFixed(4)}. Negative values mark outliers within this capture; this is not a fire probability.` : 'No calibrated confidence is available.'}</p>
              <div className="classification-evidence"><strong>What influenced this estimate</strong>
                {classification.top_contributing_features?.length ? classification.top_contributing_features.map((item) => <span key={item.feature}>{item.feature.replace(/_/g, ' ')}: {item.value.toFixed(2)}</span>) :
                  classification.reasoning?.map((reason) => <span key={reason}>{reason}</span>)}
              </div>
            </div>
            <div className="probability-list"><strong>{classification.model_status === 'UNSUPERVISED_PROTOTYPE' ? 'Model provenance' : classification.is_ml ? 'Prototype class votes' : 'Heuristic class scores'}</strong>
              {classification.model_status === 'UNSUPERVISED_PROTOTYPE' && <p className="classification-caveat">Isolation Forest · unlabelled FIRMS event clusters · no ground truth or calibrated probabilities</p>}
              {Object.entries(classification.probabilities ?? {}).sort((a, b) => b[1] - a[1]).map(([name, value]) => <div className="probability-row" key={name}><span>{classificationLabel(name)}</span><b>{(value * 100).toFixed(0)}%</b><div><i style={{ width: `${value * 100}%` }} /></div></div>)}
            </div>
          </div> : <p className="panel-empty">Classification unavailable.</p>}
        </section>

        <section className="detail-panel detail-panel-wide weak-classifier-panel">
          <header className="detail-panel-header"><Activity size={14} /><h3>Weakly supervised recurrence classifier</h3><span className="methodology-badge">SEPARATE FROM ANOMALY &amp; RISK</span></header>
          {weak ? <div className="weak-classifier-content">
            <div className="weak-prediction"><span>Model output</span><strong>{weak.prediction === 'multi_day_recurrence' ? 'Later-day re-detection pattern' : 'Single-day observed pattern'}</strong><small>{weak.model_name} · {weak.model_version}</small></div>
            <p className="classification-caveat">Target: {weak.target}. This model uses only first-day observations. Its class scores are uncalibrated and do not estimate fire probability.</p>
            <div className="weak-votes">{Object.entries(weak.uncalibrated_model_scores).map(([label, score]) => <span key={label}>{label.replace(/_/g, ' ')}: {(score * 100).toFixed(1)}% model score</span>)}</div>
            <div className="weak-features"><strong>Features contributing to this model output</strong>{weak.top_contributing_features.map((item) => <span key={item.feature}>{item.feature.replace(/_/g, ' ')}: {item.value.toFixed(2)} · score change {item.model_score_change >= 0 ? '+' : ''}{item.model_score_change.toFixed(3)} versus training median</span>)}</div>
            <div className="weak-provenance"><span>Artifact SHA-256: <code>{weak.model_provenance.artifact_hash}</code></span><span>Feature schema: {weak.model_provenance.feature_version}</span><span>Dataset fingerprint: <code>{weak.model_provenance.training_dataset_fingerprint}</code></span><span>Evaluation role: {weak.model_provenance.evaluation_role.replace(/_/g, ' ')}</span><span>Trained: {new Date(weak.model_provenance.trained_at).toLocaleString()}</span></div>
            {weak.warnings.map((warning) => <p className="classification-caveat" key={warning}>{warning}</p>)}
          </div> : <p className="panel-empty">A compatible real-FIRMS classifier is unavailable. Anomaly detection and rule-based risk remain independent.</p>}
        </section>

        <section className="detail-panel detail-panel-wide evidence-panel">
          <header className="detail-panel-header"><ShieldAlert size={14} /><h3>Evidence & integrity</h3></header>
          {evidence ? <div className="evidence-content">
            <Field label="Evidence ID" value={String(evidence.evidence_id)} mono />
            <Field label="SHA-256" value={String(evidence.sha256)} mono />
            <Field label="Current content" value={evidence.integrity?.content_hash_valid ? 'Hash verified' : 'Verification failed'} />
            <Field label="Local receipt" value={evidence.integrity?.local_anchor_valid ? 'Verified local receipt' : 'Not anchored locally'} />
            <Field label="Blockchain" value={
              evidence.integrity?.on_chain
                ? `Verified on-chain · ${String(evidence.integrity.blockchain?.network ?? 'testnet').toUpperCase()} (Block #${evidence.integrity.blockchain?.block_number})`
                : evidence.integrity?.blockchain?.status === 'CONNECTED'
                ? 'Ready to anchor on EVM testnet'
                : 'Blockchain unavailable — local evidence verification active'
            } />
            {evidence.integrity?.on_chain && evidence.integrity?.blockchain?.tx_hash && (
              <div className="field-group">
                <span className="field-label">Testnet Tx</span>
                <a
                  href={evidence.integrity.blockchain.explorer_link ?? `https://sepolia.etherscan.io/tx/${evidence.integrity.blockchain.tx_hash}`}
                  target="_blank"
                  rel="noreferrer"
                  style={{ color: 'var(--accent-primary)', textDecoration: 'underline', fontFamily: 'monospace', fontSize: '11px', wordBreak: 'break-all' }}
                >
                  {String(evidence.integrity.blockchain.tx_hash)} ↗
                </a>
              </div>
            )}
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '6px' }}>
              {!evidence.integrity?.local_anchor_valid && (
                <button className="primary-action" disabled={anchoring} onClick={() => void anchorEvidence()}>
                  {anchoring ? 'Saving local receipt…' : 'Anchor in local audit chain'}
                </button>
              )}
              {evidence.integrity?.blockchain?.status === 'CONNECTED' && !evidence.integrity?.on_chain && (
                <button className="primary-action" disabled={anchoringBlockchain} onClick={() => void anchorOnBlockchain()}>
                  {anchoringBlockchain ? 'Submitting to testnet…' : 'Anchor on EVM Testnet'}
                </button>
              )}
            </div>
            {anchorError && <p className="command-error" role="status">{anchorError}</p>}
            {evidence.integrity?.local_receipt && <details className="raw-evidence"><summary>Inspect linked receipt</summary>
              <Field label="Chain index" value={String(evidence.integrity.local_receipt.sequence)} />
              <Field label="Previous receipt SHA-256" value={String(evidence.integrity.local_receipt.previous_sha256)} mono />
              <Field label="Current receipt SHA-256" value={String(evidence.integrity.local_receipt.chain_sha256)} mono />
              <p>Local verification detects edits and truncation against the saved checkpoint. It is not an independent public timestamp.</p>
            </details>}
            <details className="raw-evidence"><summary>Inspect hashed evidence payload</summary><pre style={{ overflow: 'auto', maxHeight: 320 }}>{JSON.stringify(evidence.payload, null, 2)}</pre></details>
          </div> : <p className="panel-empty">Evidence package unavailable for this event.</p>}
        </section>

        {/* EVENT INFORMATION */}
        <section className="detail-panel">
          <header className="detail-panel-header">
            <MapPin size={14} />
            <h3>Event Information</h3>
          </header>
          <div className="detail-grid">
            <Field label="Location" value={locationLabel(event)} />
            <Field label="Latitude" value={event.latitude.toFixed(4)} mono />
            <Field label="Longitude" value={event.longitude.toFixed(4)} mono />
            <Field label="First Detection" value={formatTimelineDate(event.start_time)} />
            <Field label="Last Detection" value={event.end_time ? formatTimelineDate(event.end_time) : '—'} />
            <Field label="Total Observations" value={String(event.observation_count)} mono />
            <Field label="Status" value={event.status} />
          </div>
        </section>

        {/* OBSERVED THERMAL DATA */}
        <section className="detail-panel">
          <header className="detail-panel-header">
            <Activity size={14} />
            <h3>Observed Thermal Data</h3>
          </header>
          <div className="detail-grid">
            <Field label="Detection Count" value={String(event.observation_count)} mono />
            <Field label="Avg Intensity" value={event.persistence?.average_intensity != null ? `${event.persistence.average_intensity.toFixed(1)} K` : '—'} mono />
            <Field label="Peak FRP" value={event.max_frp != null ? `${event.max_frp.toFixed(1)} MW` : '—'} mono />
            <Field label="Mean FRP" value={event.mean_frp != null ? `${event.mean_frp.toFixed(1)} MW` : '—'} mono />
            <Field label="VIIRS Confidence" value={event.confidence_category ? `${event.confidence_category} category` : event.average_confidence != null ? `${event.average_confidence.toFixed(0)}%` : 'Unavailable'} mono />
            <Field label="Active Days" value={event.persistence?.active_days != null ? String(event.persistence.active_days) : 'Unavailable'} mono />
            <Field label="Persistence Score" value={event.persistence?.persistence_score?.toFixed(2) ?? '—'} mono />
            <Field label="Intensity Variance" value={event.persistence?.intensity_variance != null ? `${event.persistence.intensity_variance.toFixed(2)}` : '—'} mono />
            <Field label="Spatial Variance (°²)" value={event.persistence?.spatial_stability != null ? `${event.persistence.spatial_stability.toFixed(6)}` : '—'} mono />
          </div>
          <div className="trend-indicator">
            <span className="trend-label">Temporal Trend:</span>
            <TrendIcon trend={event.persistence?.trend ?? 'UNKNOWN'} />
            <span className={`trend-value trend-${event.persistence?.trend?.toLowerCase() ?? 'unknown'}`}>
              {event.persistence?.trend ?? 'UNKNOWN'}
            </span>
          </div>
        </section>

        {/* DETECTION TIMELINE */}
        <section className="detail-panel detail-panel-wide">
          <header className="detail-panel-header">
            <Calendar size={14} />
            <h3>Detection Timeline</h3>
          </header>
          {chartData.length === 0 ? (
            <div className="chart-empty">No history available.</div>
          ) : (
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={chartData} margin={{ top: 10, right: 16, bottom: 10, left: 0 }}>
                  <CartesianGrid stroke="rgba(120, 160, 200, 0.1)" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    stroke="#5a6878"
                    tick={{ fontSize: 10, fill: '#8b9eb0' }}
                    tickLine={false}
                  />
                  <YAxis
                    stroke="#5a6878"
                    tick={{ fontSize: 10, fill: '#8b9eb0' }}
                    tickLine={false}
                    width={40}
                  />
                  <Tooltip
                    contentStyle={{
                      background: '#1f2a3a',
                      border: '1px solid rgba(120, 160, 200, 0.2)',
                      borderRadius: 4,
                      fontSize: 11,
                    }}
                    labelStyle={{ color: '#e6edf3' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="intensity"
                    stroke="#ff9500"
                    strokeWidth={2}
                    dot={{ fill: '#ff9500', r: 3 }}
                    activeDot={{ r: 5 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>

        {/* THERMAL PROFILE */}
        {hasProfile && (
          <section className="detail-panel detail-panel-wide">
            <header className="detail-panel-header">
              <Database size={14} />
              <h3>Thermal DNA Profile</h3>
            </header>
            <div className="profile-grid">
              <div className="profile-section">
                <h4>Temporal Features</h4>
                <Field label="First Detection" value={profile.temporal_features.first_detection ? formatTimelineDate(profile.temporal_features.first_detection) : '—'} mono />
                <Field label="Last Detection" value={profile.temporal_features.last_detection ? formatTimelineDate(profile.temporal_features.last_detection) : '—'} mono />
                <Field label="Active Days" value={String(profile.temporal_features.active_days ?? 0)} mono />
                <Field label="Duration (hours)" value={(profile.temporal_features.event_duration_hours ?? profile.temporal_features.duration_hours) != null ? `${(profile.temporal_features.event_duration_hours ?? profile.temporal_features.duration_hours)!.toFixed(1)}` : '—'} mono />
                <Field label="Detection Frequency" value={profile.temporal_features.detection_frequency !== null && profile.temporal_features.detection_frequency !== undefined ? `${profile.temporal_features.detection_frequency.toFixed(2)} per day` : '—'} mono />
                <Field label="Temporal Trend" value={statusLabel(profile.temporal_features.temporal_trend ?? profile.temporal_features.trend)} />
              </div>

              <div className="profile-section">
                <h4>Intensity Features</h4>
                <Field label="Mean Brightness" value={profile.intensity_features.mean_brightness_temperature !== null && profile.intensity_features.mean_brightness_temperature !== undefined ? `${profile.intensity_features.mean_brightness_temperature.toFixed(1)} K` : '—'} mono />
                <Field label="Max Brightness" value={profile.intensity_features.max_brightness_temperature !== null && profile.intensity_features.max_brightness_temperature !== undefined ? `${profile.intensity_features.max_brightness_temperature.toFixed(1)} K` : '—'} mono />
                <Field label="Min Brightness" value={profile.intensity_features.min_brightness_temperature !== null && profile.intensity_features.min_brightness_temperature !== undefined ? `${profile.intensity_features.min_brightness_temperature.toFixed(1)} K` : '—'} mono />
                <Field label="Intensity Variance" value={profile.intensity_features.intensity_variance !== null && profile.intensity_features.intensity_variance !== undefined ? `${profile.intensity_features.intensity_variance.toFixed(2)}` : '—'} mono />
                <Field label="Intensity Trend" value={statusLabel(profile.intensity_features.intensity_trend)} />
                <Field label="FRP Mean" value={profile.intensity_features.frp_statistics?.mean !== null && profile.intensity_features.frp_statistics?.mean !== undefined ? `${profile.intensity_features.frp_statistics.mean.toFixed(1)}` : '—'} mono />
                <Field label="FRP Max" value={profile.intensity_features.frp_statistics?.max !== null && profile.intensity_features.frp_statistics?.max !== undefined ? `${profile.intensity_features.frp_statistics.max.toFixed(1)}` : '—'} mono />
              </div>

              <div className="profile-section">
                <h4>Spatial Features</h4>
                <Field label="Centroid Lat" value={profile.spatial_features.centroid_lat !== null && profile.spatial_features.centroid_lat !== undefined ? `${profile.spatial_features.centroid_lat.toFixed(4)}` : '—'} mono />
                <Field label="Centroid Lon" value={profile.spatial_features.centroid_lon !== null && profile.spatial_features.centroid_lon !== undefined ? `${profile.spatial_features.centroid_lon.toFixed(4)}` : '—'} mono />
                <Field label="Spatial Footprint (°²)" value={profile.spatial_features.spatial_spread !== null && profile.spatial_features.spatial_spread !== undefined ? `${profile.spatial_features.spatial_spread.toFixed(8)}` : 'Unavailable'} mono />
                <Field label="Spatial Variance (°²)" value={profile.spatial_features.spatial_variance !== null && profile.spatial_features.spatial_variance !== undefined ? `${profile.spatial_features.spatial_variance.toFixed(8)}` : 'Unavailable'} mono />
                <Field label="Distinct Detections" value={String(profile.spatial_features.distinct_detections ?? 0)} mono />
              </div>

              <div className="profile-section">
                <h4>Persistence Features</h4>
                <Field label="Persistence Score" value={profile.persistence_features.persistence_score !== null && profile.persistence_features.persistence_score !== undefined ? `${profile.persistence_features.persistence_score.toFixed(2)}` : '—'} mono />
                <Field label="Consecutive Days" value={profile.persistence_features.consecutive_active_days !== null && profile.persistence_features.consecutive_active_days !== undefined ? String(profile.persistence_features.consecutive_active_days) : '—'} mono />
                <Field label="Persistence Type" value={statusLabel(profile.persistence_features.persistence_type)} />
                <Field label="Recurrence Frequency" value={profile.persistence_features.recurrence_frequency !== null && profile.persistence_features.recurrence_frequency !== undefined ? `${profile.persistence_features.recurrence_frequency.toFixed(2)}` : '—'} mono />
              </div>

              <div className="profile-section">
                <h4>Data Quality</h4>
                <Field label="Observation Count" value={String(profile.observation_count)} mono />
                <Field label="Baseline Status" value={statusLabel(profile.baseline_status)} />
                <Field label="Completeness" value={profile.data_quality.completeness !== null && profile.data_quality.completeness !== undefined ? `${(profile.data_quality.completeness * 100).toFixed(1)}%` : '—'} mono />
              </div>
            </div>
          </section>
        )}

        <section className="detail-panel">
          <header className="detail-panel-header"><Database size={14} /><h3>Historical context</h3></header>
          <p className="context-message">{profile?.baseline_deviation ? 'Baseline comparison is available in the Thermal DNA profile.' : 'Not enough historical observations for a reliable baseline comparison.'}</p>
          <Field label="Baseline status" value={statusLabel(profile?.baseline_status)} />
        </section>

        <section className="detail-panel">
          <header className="detail-panel-header"><MapPin size={14} /><h3>Geospatial context</h3></header>
          {nearby?.facilities?.length ? nearby.facilities.map((facility, index) => <p className="context-message" key={index}>{facility.name ?? 'Unnamed facility'} · {facility.type ?? 'type unavailable'} · {facility.distance_km != null ? `${facility.distance_km.toFixed(1)} km` : 'distance unavailable'}</p>) : <p className="context-message">Nearby verified facility data unavailable. Proximity has not been used to infer a cause.</p>}
          {nearby?.note && <p className="context-message">{nearby.note}</p>}
        </section>

        {/* RISK ASSESSMENT */}
        <RiskAssessmentSection event={event} />

        {/* EVIDENCE / RECENT OBSERVATIONS */}
        <section className="detail-panel">
          <header className="detail-panel-header">
            <Layers size={14} />
            <h3>Recent Observations</h3>
          </header>
          <div className="obs-list">
            {event.observations.slice(0, 10).map((o) => (
              <div key={o.id} className="obs-row">
                <span className="mono obs-time">
                  {formatObservationDate(o.timestamp)}
                </span>
                <span className="mono obs-intensity">
                  {o.intensity != null ? `${o.intensity.toFixed(1)} K` : 'Unavailable'}
                </span>
                <span className="obs-frp mono">
                  {o.frp != null ? `FRP: ${o.frp.toFixed(1)} MW` : 'FRP: —'}
                </span>
                <span className="obs-source">
                  {o.satellite ? `${o.satellite} (${o.instrument ?? 'VIIRS'})` : o.source}
                </span>
                <span className="obs-source">
                  {o.confidence_category ? `VIIRS ${o.confidence_category}` : o.confidence != null ? `${o.confidence.toFixed(0)}% conf` : 'Confidence unavailable'}
                  {o.daynight ? ` · ${o.daynight === 'D' ? 'Day' : 'Night'}` : ''}
                </span>
              </div>
            ))}
            {event.observations.length > 10 && (
              <div className="obs-more">
                + {event.observations.length - 10} earlier observations
              </div>
            )}
          </div>
          <details className="raw-evidence">
            <summary>Observation provenance and coordinates</summary>
            <p>These records are {event.observations.some((observation) => observation.source === 'DEMO_SYNTHETIC') ? 'synthetic demonstration observations' : 'captured NASA FIRMS observations'}. The evidence package can be checked with SHA-256 and optionally anchored in the local audit chain.</p>
            {event.observations.slice(0, 10).map((observation) => <p key={observation.id}>#{observation.id} · {observation.source} · {observation.latitude.toFixed(4)}, {observation.longitude.toFixed(4)} · {detectionTime(observation.timestamp)}</p>)}
          </details>
        </section>
      </div>
    </div>
  )
}

// Risk Assessment Section Component
function RiskAssessmentSection({ event }: { event: ThermalEventDetail }) {
  const risk = event.risk

  if (!risk || Object.keys(risk).length === 0) {
    return (
      <section className="detail-panel">
        <header className="detail-panel-header">
          <Target size={14} />
          <h3>Risk Assessment</h3>
        </header>
        <div className="risk-empty">
          <AlertTriangle size={20} />
          <p>No risk assessment available for this event.</p>
        </div>
      </section>
    )
  }

  const severityColors: Record<string, string> = {
    CRITICAL: '#ff3b30',
    HIGH: '#ff3b30',
    MEDIUM: '#ff9500',
    LOW: '#34c759',
  }

  const severityColor = severityColors[risk.severity?.toUpperCase()] ?? '#8b9eb0'

  return (
    <section className="detail-panel detail-panel-wide">
      <header className="detail-panel-header">
        <Target size={14} />
        <h3>Risk Assessment</h3>
        <span className="methodology-badge">
          RULE-BASED OPERATIONAL PRIORITY
        </span>
      </header>

      <div className="risk-grid">
        {/* Risk Score Card */}
        <div className="risk-score-card" style={{ borderColor: severityColor }}>
          <div className="risk-score-label">Risk Level</div>
          <div className="risk-score-value" style={{ color: severityColor }}>
            {risk.severity?.toUpperCase() ?? 'UNKNOWN'}
          </div>
          <div className="risk-score-bar">
            <div
              className="risk-score-fill"
              style={{
                width: `${risk.score ?? 0}%`,
                backgroundColor: severityColor
              }}
            />
          </div>
          <div className="risk-score-number">{risk.score?.toFixed(1) ?? 0}/100</div>
        </div>

      </div>

      {/* Contributing Factors */}
      {risk.contributing_factors && risk.contributing_factors.length > 0 && (
        <div className="risk-factors">
          <div className="risk-factors-title">Contributing Factors</div>
          <div className="risk-factors-list">
            {Array.isArray(risk.contributing_factors)
              ? risk.contributing_factors.map((f: any, i: number) => (
                  <div key={i} className="risk-factor">
                    <span className="factor-score" style={{ color: severityColor }}>
                      {typeof f === 'string' ? '' : f.score?.toFixed(0)}
                    </span>
                    <span className="factor-name">
                      {typeof f === 'string' ? f : f.factor}
                    </span>
                  </div>
                ))
              : null}
          </div>
        </div>
      )}

      {/* Explanation */}
      {risk.explanation && (
        <div className="risk-explanation">
          <div className="explanation-title">Analysis</div>
          <div className="explanation-text">{risk.explanation}</div>
        </div>
      )}
      <p className="context-message">This score prioritizes investigation. It is separate from model confidence and does not establish fire cause or future escalation.</p>
    </section>
  )
}

// Helper Components
function Field({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="detail-field">
      <div className="detail-field-label">{label}</div>
      <div className={`detail-field-value ${mono ? 'mono' : ''}`}>{value}</div>
    </div>
  )
}

function TrendIcon({ trend }: { trend: string }) {
  if (trend === 'INCREASING') return <TrendingUp size={16} className="trend-icon trend-increasing" />
  if (trend === 'DECREASING') return <TrendingDown size={16} className="trend-icon trend-decreasing" />
  if (trend === 'STABLE') return <Minus size={16} className="trend-icon trend-stable" />
  return <Minus size={16} className="trend-icon trend-unknown" />
}
