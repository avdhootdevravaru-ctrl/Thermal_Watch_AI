import { useEffect, useState, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeft, MapPin, Activity, Calendar, AlertTriangle, Layers, TrendingUp, TrendingDown, Minus, Zap, Clock, Target, Database } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, ResponsiveContainer, Tooltip, CartesianGrid } from 'recharts'
import { api } from '@/api/client'
import type { ThermalEventDetail, EventHistoryPoint, ThermalProfileResponse } from '@/types'
import { formatTimelineDate, formatObservationDate } from '@/utils/timestampUtils'
import './EventDetailPage.css'

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [event, setEvent] = useState<ThermalEventDetail | null>(null)
  const [history, setHistory] = useState<EventHistoryPoint[]>([])
  const [profile, setProfile] = useState<ThermalProfileResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const eventId = Number(id)

  const load = useCallback(async () => {
    if (!Number.isFinite(eventId)) return
    setLoading(true)
    setError(null)
    try {
      const [detail, hist, prof] = await Promise.all([
        api.getEvent(eventId),
        api.getEventHistory(eventId).catch(() => [] as EventHistoryPoint[]),
        api.getEventProfile(eventId),
      ])
      setEvent(detail)
      setHistory(hist)
      setProfile(prof)
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to load event'
      setError(message)
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
    intensity: p.intensity ?? 0,
    observation_count: p.observation_count,
  }))

  const hasProfile = !!profile && profile.observation_count > 0

  return (
    <div className="event-detail">
      <div className="event-detail-header">
        <button className="back-btn" onClick={() => navigate(-1)}>
          <ArrowLeft size={14} />
          <span>Back</span>
        </button>
        <div className="event-id-block">
          <span className="event-label mono">EVENT</span>
          <span className="event-id mono">#{event.id}</span>
        </div>
        <div className={`status-pill-large status-${event.status.toLowerCase()}`}>
          {event.status}
        </div>
      </div>

      <div className="event-detail-body">
        {/* EVENT INFORMATION */}
        <section className="detail-panel">
          <header className="detail-panel-header">
            <MapPin size={14} />
            <h3>Event Information</h3>
          </header>
          <div className="detail-grid">
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
            <Field label="Avg Intensity" value={event.persistence?.average_intensity ? `${event.persistence.average_intensity.toFixed(1)} K` : '—'} mono />
            <Field label="Active Days" value={String(event.persistence?.active_days ?? 0)} mono />
            <Field label="Persistence Score" value={event.persistence?.persistence_score?.toFixed(2) ?? '—'} mono />
            <Field label="Intensity Variance" value={event.persistence?.intensity_variance ? `${event.persistence.intensity_variance.toFixed(2)}` : '—'} mono />
            <Field label="Spatial Stability" value={event.persistence?.spatial_stability ? `${event.persistence.spatial_stability.toFixed(4)}` : '—'} mono />
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
                <Field label="First Detection" value={profile.temporal_features.first_detection ?? '—'} mono />
                <Field label="Last Detection" value={profile.temporal_features.last_detection ?? '—'} mono />
                <Field label="Active Days" value={String(profile.temporal_features.active_days ?? 0)} mono />
                <Field label="Duration (hours)" value={profile.temporal_features.duration_hours !== null && profile.temporal_features.duration_hours !== undefined ? `${profile.temporal_features.duration_hours.toFixed(1)}` : '—'} mono />
                <Field label="Detection Frequency" value={profile.temporal_features.detection_frequency !== null && profile.temporal_features.detection_frequency !== undefined ? `${profile.temporal_features.detection_frequency.toFixed(2)} per day` : '—'} mono />
                <Field label="Temporal Trend" value={profile.temporal_features.trend ?? 'UNKNOWN'} mono />
              </div>

              <div className="profile-section">
                <h4>Intensity Features</h4>
                <Field label="Mean Brightness" value={profile.intensity_features.mean_brightness_temperature !== null && profile.intensity_features.mean_brightness_temperature !== undefined ? `${profile.intensity_features.mean_brightness_temperature.toFixed(1)} K` : '—'} mono />
                <Field label="Max Brightness" value={profile.intensity_features.max_brightness_temperature !== null && profile.intensity_features.max_brightness_temperature !== undefined ? `${profile.intensity_features.max_brightness_temperature.toFixed(1)} K` : '—'} mono />
                <Field label="Min Brightness" value={profile.intensity_features.min_brightness_temperature !== null && profile.intensity_features.min_brightness_temperature !== undefined ? `${profile.intensity_features.min_brightness_temperature.toFixed(1)} K` : '—'} mono />
                <Field label="Intensity Variance" value={profile.intensity_features.intensity_variance !== null && profile.intensity_features.intensity_variance !== undefined ? `${profile.intensity_features.intensity_variance.toFixed(2)}` : '—'} mono />
                <Field label="Intensity Trend" value={profile.intensity_features.intensity_trend ?? 'UNKNOWN'} mono />
                <Field label="FRP Mean" value={profile.intensity_features.frp_statistics?.mean !== null && profile.intensity_features.frp_statistics?.mean !== undefined ? `${profile.intensity_features.frp_statistics.mean.toFixed(1)}` : '—'} mono />
                <Field label="FRP Max" value={profile.intensity_features.frp_statistics?.max !== null && profile.intensity_features.frp_statistics?.max !== undefined ? `${profile.intensity_features.frp_statistics.max.toFixed(1)}` : '—'} mono />
              </div>

              <div className="profile-section">
                <h4>Spatial Features</h4>
                <Field label="Centroid Lat" value={profile.spatial_features.centroid_lat !== null && profile.spatial_features.centroid_lat !== undefined ? `${profile.spatial_features.centroid_lat.toFixed(4)}` : '—'} mono />
                <Field label="Centroid Lon" value={profile.spatial_features.centroid_lon !== null && profile.spatial_features.centroid_lon !== undefined ? `${profile.spatial_features.centroid_lon.toFixed(4)}` : '—'} mono />
                <Field label="Spatial Spread" value={profile.spatial_features.spatial_spread !== null && profile.spatial_features.spatial_spread !== undefined ? `${profile.spatial_features.spatial_spread.toFixed(2)}` : '—'} mono />
                <Field label="Distinct Detections" value={String(profile.spatial_features.distinct_detections ?? 0)} mono />
                <Field label="Spatial Stability" value={profile.spatial_features.spatial_stability !== null && profile.spatial_features.spatial_stability !== undefined ? `${profile.spatial_features.spatial_stability.toFixed(4)}` : '—'} mono />
              </div>

              <div className="profile-section">
                <h4>Persistence Features</h4>
                <Field label="Persistence Score" value={profile.persistence_features.persistence_score !== null && profile.persistence_features.persistence_score !== undefined ? `${profile.persistence_features.persistence_score.toFixed(2)}` : '—'} mono />
                <Field label="Consecutive Days" value={profile.persistence_features.consecutive_active_days !== null && profile.persistence_features.consecutive_active_days !== undefined ? String(profile.persistence_features.consecutive_active_days) : '—'} mono />
                <Field label="Persistence Type" value={profile.persistence_features.persistence_type ?? '—'} mono />
                <Field label="Recurrence Frequency" value={profile.persistence_features.recurrence_frequency !== null && profile.persistence_features.recurrence_frequency !== undefined ? `${profile.persistence_features.recurrence_frequency.toFixed(2)}` : '—'} mono />
              </div>

              <div className="profile-section">
                <h4>Data Quality</h4>
                <Field label="Observation Count" value={String(profile.observation_count)} mono />
                <Field label="Baseline Status" value={profile.baseline_status} mono />
                <Field label="Completeness" value={profile.data_quality.completeness !== null && profile.data_quality.completeness !== undefined ? `${(profile.data_quality.completeness * 100).toFixed(1)}%` : '—'} mono />
              </div>
            </div>
          </section>
        )}

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
                  {o.intensity?.toFixed(1) ?? '—'} K
                </span>
                <span className="obs-source">{o.source}</span>
              </div>
            ))}
            {event.observations.length > 10 && (
              <div className="obs-more">
                + {event.observations.length - 10} earlier observations
              </div>
            )}
          </div>
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
    HIGH: '#ff9500',
    MEDIUM: '#ffcc00',
    LOW: '#34c759',
  }

  const severityColor = severityColors[risk.severity?.toUpperCase()] ?? '#8b9eb0'

  // Determine methodology label
  const isStored = !risk.is_computed
  const isRuleBased = risk.methodology?.includes('rule-based') ?? risk.classification?.methodology?.includes('rule-based') ?? false
  const methodologyLabel = isStored ? 'RULE-BASED' : isRuleBased ? 'RULE-BASED' : 'Computed'

  return (
    <section className="detail-panel detail-panel-wide">
      <header className="detail-panel-header">
        <Target size={14} />
        <h3>Risk Assessment</h3>
        <span className="methodology-badge">
          {methodologyLabel}
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

        {/* Event Classification */}
        {risk.classification && (
          <div className="risk-classification-card">
            <div className="risk-card-header">
              <Zap size={14} />
              <span>Event Classification</span>
            </div>
            <div className="classification-type">
              {formatClassification(risk.classification.type)}
            </div>
            <div className="classification-confidence">
              Confidence: {(risk.classification.confidence * 100).toFixed(0)}%
            </div>
            <div className="classification-method">
              {risk.classification.methodology || 'Rule-based classification'}
            </div>
          </div>
        )}

        {/* Persistence Prediction */}
        {risk.persistence_prediction && (
          <div className="risk-persistence-card">
            <div className="risk-card-header">
              <Clock size={14} />
              <span>Persistence Prediction</span>
            </div>
            <div className="persistence-likelihood">
              {risk.persistence_prediction.likelihood}
            </div>
            <div className="persistence-horizon">
              ~{risk.persistence_prediction.time_horizon_days} days expected
            </div>
          </div>
        )}

        {/* Escalation Probability */}
        {risk.escalation_probability !== undefined && (
          <div className="risk-escalation-card">
            <div className="risk-card-header">
              {risk.escalation_probability > 0.3 ? <TrendingUp size={14} /> : <Minus size={14} />}
              <span>Escalation Probability</span>
            </div>
            <div className={`escalation-value ${risk.escalation_probability > 0.3 ? 'high' : 'low'}`}>
              {(risk.escalation_probability * 100).toFixed(0)}%
            </div>
          </div>
        )}
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

function formatClassification(type: string): string {
  const labels: Record<string, string> = {
    INDUSTRIAL_THERMAL_SOURCE: 'Industrial Thermal Source',
    INDUSTRIAL_FIRE: 'Industrial Fire',
    AGRICULTURAL_BURNING: 'Agricultural Burning',
    PERSISTENT_THERMAL_SOURCE: 'Persistent Thermal Source',
    NATURAL_SOURCE: 'Natural Thermal Source',
    TEMPORARY_THERMAL_EVENT: 'Temporary Thermal Event',
    OTHER: 'Other/Unknown',
    UNKNOWN: 'Unknown',
  }
  return labels[type] ?? type
}
