// ThermalWatch AI — API client
// All requests go through Vite proxy in dev (/api -> http://localhost:8000/8001)
// In production, the same paths work behind a reverse proxy.

import axios from 'axios'
import type {
  HealthStatus,
  ThermalEventList,
  ThermalEventDetail,
  MapHotspotsResponse,
  IngestionResult,
  EventHistoryPoint,
  RiskAssessment,
  DataQualityReport,
  HistoricalStatistics,
  LocationStatistics,
  BaselineResult,
  BaselineComparison,
  ThermalProfileResponse,
} from '@/types'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '/api'

const client = axios.create({
  baseURL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Separate client for long-running requests (e.g., FIRMS ingestion)
// FIRMS ingestion fetches satellite data, normalizes, stores, and clusters
// observations — with thousands of detections and existing DB data, this can
// take several minutes. Use a generous timeout to avoid false failures.
const longRunningClient = axios.create({
  baseURL,
  timeout: 600000, // 10 minutes — accommodates large ingestion runs
  headers: {
    'Content-Type': 'application/json',
  },
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response) {
      console.error('API error:', error.response.status, error.response.data)
    } else if (error.request) {
      console.error('Network error: backend not reachable at', baseURL)
    } else {
      console.error('Request error:', error.message)
    }
    return Promise.reject(error)
  },
)

export const api = {
  // Health
  getHealth: async (): Promise<HealthStatus> => {
    const { data } = await client.get<HealthStatus>('/health')
    return data
  },

  // Ingestion
  runFirmsIngestion: async (params?: { area?: string; days?: number; satellite?: string }): Promise<IngestionResult> => {
    const { data } = await longRunningClient.post<IngestionResult>('/ingestion/firms/run', params ?? {})
    return data
  },

  // Events
  listEvents: async (params?: { page?: number; page_size?: number; status?: string }): Promise<ThermalEventList> => {
    const { data } = await client.get<ThermalEventList>('/thermal-events', { params })
    return data
  },

  getEvent: async (eventId: number): Promise<ThermalEventDetail> => {
    const { data } = await client.get<ThermalEventDetail>(`/thermal-events/${eventId}`)
    return data
  },

  getEventHistory: async (eventId: number): Promise<EventHistoryPoint[]> => {
    const { data } = await client.get<EventHistoryPoint[]>(`/thermal-events/${eventId}/history`)
    return data
  },

  getEventRisk: async (eventId: number): Promise<RiskAssessment> => {
    const { data } = await client.get<RiskAssessment>(`/thermal-events/${eventId}/risk`)
    return data
  },

  getEventEvidence: async (eventId: number): Promise<Record<string, unknown>> => {
    const { data } = await client.get(`/thermal-events/${eventId}/evidence`)
    return data
  },

  getEventThermalDna: async (eventId: number): Promise<Record<string, unknown>> => {
    const { data } = await client.get(`/thermal-events/${eventId}/thermal-dna`)
    return data
  },

  // Map / hotspots
  getMapHotspots: async (params?: { risk_severity?: string; limit?: number }): Promise<MapHotspotsResponse> => {
    const { data } = await client.get<MapHotspotsResponse>('/map/hotspots', { params })
    return data
  },

  getNearbyFacilities: async (eventId: number, radiusKm: number = 5): Promise<unknown> => {
    const { data } = await client.get('/map/facilities/nearby', {
      params: { event_id: eventId, radius_km: radiusKm },
    })
    return data
  },

  // Historical intelligence
  getDataQuality: async (params?: { start_date?: string; end_date?: string }): Promise<DataQualityReport> => {
    const { data } = await client.get<DataQualityReport>('/history/data-quality', { params })
    return data
  },

  getHistoricalStatistics: async (params?: { start_date?: string; end_date?: string }): Promise<HistoricalStatistics> => {
    const { data } = await client.get<HistoricalStatistics>('/history/statistics', { params })
    return data
  },

  getLocationStatistics: async (lat: number, lon: number, radiusKm?: number): Promise<LocationStatistics> => {
    const { data } = await client.get<LocationStatistics>(`/history/location/${lat}/${lon}/statistics`, {
      params: { radius_km: radiusKm },
    })
    return data
  },

  getLocationBaseline: async (lat: number, lon: number, radiusKm?: number): Promise<BaselineResult> => {
    const { data } = await client.get<BaselineResult>(`/history/location/${lat}/${lon}/baseline`, {
      params: { radius_km: radiusKm },
    })
    return data
  },

  compareLocationToBaseline: async (lat: number, lon: number, radiusKm?: number): Promise<BaselineComparison> => {
    const { data } = await client.post<BaselineComparison>(`/history/location/${lat}/${lon}/compare`, {
      radius_km: radiusKm,
    })
    return data
  },

  getEventProfile: async (eventId: number): Promise<ThermalProfileResponse> => {
    const { data } = await client.get<ThermalProfileResponse>(`/history/event/${eventId}/profile`)
    return data
  },

  computeEventProfile: async (eventId: number): Promise<ThermalProfileResponse> => {
    const { data } = await client.post<ThermalProfileResponse>(`/history/event/${eventId}/profile`)
    return data
  },
}
