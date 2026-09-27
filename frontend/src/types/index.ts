// ThermalWatch AI — Shared TypeScript types (frontend only)
// These mirror the Pydantic models from backend/app/schemas/

export interface ObservationSummary {
  id: number
  timestamp: string
  latitude: number
  longitude: number
  intensity: number | null
  confidence: number | null
  confidence_category?: string | null
  source: string
  frp?: number | null
  satellite?: string | null
  instrument?: string | null
  daynight?: string | null
}

export interface PersistenceMetrics {
  total_detections: number
  active_days: number
  persistence_score: number
  average_intensity: number | null
  intensity_variance: number | null
  spatial_stability: number | null
  first_detection: string | null
  last_detection: string | null
  trend: 'INCREASING' | 'DECREASING' | 'STABLE' | 'UNKNOWN'
  persistence_type: string
}

export interface ThermalEventRead {
  id: number
  location_name?: string | null
  average_intensity?: number | null
  average_confidence?: number | null
  confidence_category?: string | null
  source?: string | null
  classification_type?: string | null
  classification_model_status?: string | null
  anomaly_score?: number | null
  risk_score?: number | null
  risk_severity?: string | null
  active_days?: number | null
  duration_hours?: number | null
  mean_frp?: number | null
  max_frp?: number | null
  latitude: number
  longitude: number
  start_time: string
  end_time: string | null
  observation_count: number
  persistence_score: number
  status: 'ACTIVE' | 'PERSISTENT' | 'RESOLVED' | 'UNKNOWN'
}

export interface ThermalEventDetail extends ThermalEventRead {
  observations: ObservationSummary[]
  persistence: PersistenceMetrics
  profile: Record<string, unknown>
  risk: RiskAssessment
}

export interface ThermalEventList {
  total: number
  page: number
  page_size: number
  items: ThermalEventRead[]
}

export interface HotspotMarker {
  event_id: number
  latitude: number
  longitude: number
  status: string
  observation_count: number
  persistence_score: number
  trend: string | null
  risk_score: number | null
  risk_severity: string | null
  last_detection: string | null
}

export interface MapHotspotsResponse {
  total: number
  risk_summary: { high: number; medium: number; low: number }
  markers: HotspotMarker[]
}

export interface IngestionResult {
  status: 'success' | 'partial' | 'failed'
  observations_fetched: number
  observations_stored: number
  observations_failed: number
  events_created: number
  events_updated: number
  persistent_sources: number
  started_at: string
  completed_at: string
  errors: string[]
}

export interface HealthStatus {
  status: 'ok'
  service: string
  version: string
  data_mode: 'DEMO DATA' | 'FIRMS SNAPSHOT' | 'LIVE MODE'
  source_status?: string
  classifier_status: 'TRAINED_MODEL' | 'UNSUPERVISED_PROTOTYPE' | 'WEAK_LABEL_PROTOTYPE' | 'RULE_BASED_FALLBACK'
}

export interface RiskAssessment {
  score: number
  severity: string
  contributing_factors: RiskFactor[]
  explanation: string
  created_at?: string
  is_computed?: boolean
  methodology?: string
  escalation_probability?: number | null
  persistence_prediction?: PersistencePrediction | null
  classification?: EventClassification
}

export interface RiskFactor {
  factor: string
  score: number
  weight: number
}

export interface PersistencePrediction {
  likelihood: 'HIGH' | 'MODERATE' | 'LOW'
  confidence: number
  time_horizon_days: number
}

export interface EventClassification {
  type: string
  confidence: number | null
  probabilities: Record<string, number>
  reasoning: string[]
  is_ml?: boolean
  model_status?: 'TRAINED_MODEL' | 'UNSUPERVISED_PROTOTYPE' | 'WEAK_LABEL_PROTOTYPE' | 'RULE_BASED_FALLBACK'
  anomaly_score?: number | null
  features?: Record<string, number | null>
  feature_importance?: Record<string, number> | null
  top_contributing_features?: Array<{ feature: string; value: number; probability_change: number }>
  model_version?: string
  methodology?: string
  data_mode?: 'DEMO DATA' | 'FIRMS SNAPSHOT' | 'LIVE MODE'
}

export interface EventHistoryPoint {
  timestamp: string
  intensity: number | null
  confidence: number | null
  observation_count: number
}

export type RiskSeverity = 'high' | 'medium' | 'low'

export type EventStatus = 'ACTIVE' | 'PERSISTENT' | 'RESOLVED' | 'UNKNOWN'

export type TrendDirection = 'INCREASING' | 'DECREASING' | 'STABLE' | 'UNKNOWN'

// --- Historical Intelligence Types ---

export interface DataQualityReport {
  records_received?: number
  records_accepted?: number
  records_rejected?: number
  invalid_timestamps?: number
  missing_values?: Record<string, number>
  capture_time?: string | null
  database_status?: string
  total_observations: number
  observations_by_date: Record<string, number>
  observations_by_source: Record<string, number>
  observations_by_region: Record<string, number>
  duplicate_count: number
  invalid_coordinates: number
  confidence_distribution: Record<string, number>
  events_by_date: Record<string, number>
  orphan_events: number
  observation_count_mismatches: number
  recurring_locations: number
  status: string
}

export interface HistoricalStatistics {
  total_observations?: number
  total_events?: number
  observation_count: number
  status: string
  observations_by_day: Record<string, number>
  observations_by_source: Record<string, number>
  average_intensity_by_day: Record<string, number | null>
  active_locations: number
  persistent_sources: number
}

export interface LocationStatistics {
  observation_count: number
  status: string
  average_intensity: number | null
  max_intensity: number | null
  min_intensity: number | null
  intensity_variance: number | null
  active_days: number
  detection_frequency: number | null
  persistence_type: string | null
  confidence_distribution: Record<string, number> | null
  source_distribution: Record<string, number> | null
  spatial_features: Record<string, number | null> | null
  temporal_features: Record<string, number | string | null> | null
}

export interface BaselineResult {
  status: string
  baseline: Record<string, number | null> | null
  observation_count: number
  note?: string
}

export interface BaselineComparison {
  status: string
  is_ml: boolean
  deviations: Record<string, number | null> | null
  baseline_status: string | null
}

export interface TemporalFeatures {
  first_detection: string | null
  last_detection: string | null
  active_days: number | null
  duration_hours: number | null
  event_duration_hours?: number | null
  detection_frequency: number | null
  recurrence: number | null
  temporal_pattern: string | null
  trend: string | null
  temporal_trend?: string | null
  status: string
}

export interface IntensityFeatures {
  mean_brightness_temperature: number | null
  max_brightness_temperature: number | null
  min_brightness_temperature: number | null
  intensity_variance: number | null
  intensity_trend: string | null
  frp_statistics: Record<string, number> | null
  status: string
}

export interface SpatialFeatures {
  centroid_lat: number | null
  centroid_lon: number | null
  spatial_spread: number | null
  spatial_variance: number | null
  spatial_stability: number | null
  distinct_detections: number | null
  status: string
}

export interface PersistenceFeatures {
  persistence_score: number | null
  consecutive_active_days: number | null
  persistence_type: string | null
  recurrence_frequency: number | null
  status: string
}

export interface DataQualityFeatures {
  observation_count: number
  confidence_distribution: Record<string, number> | null
  source_distribution: Record<string, number> | null
  completeness: number | null
  status: string
}

export interface ThermalProfileResponse {
  observation_count: number
  baseline_status: string
  temporal_features: TemporalFeatures
  intensity_features: IntensityFeatures
  spatial_features: SpatialFeatures
  persistence_features: PersistenceFeatures
  data_quality: DataQualityFeatures
  baseline: Record<string, unknown> | null
  baseline_deviation: Record<string, unknown> | null
}
