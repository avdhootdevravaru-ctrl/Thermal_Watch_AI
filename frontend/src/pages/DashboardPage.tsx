import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import MapView from '@/components/MapView'
import Sidebar from '@/components/Sidebar'
import { api } from '@/api/client'
import type { HotspotMarker, ThermalEventRead, IngestionResult, HistoricalStatistics, DataQualityReport } from '@/types'
import './DashboardPage.css'

export default function DashboardPage() {
  const navigate = useNavigate()
  const [markers, setMarkers] = useState<HotspotMarker[]>([])
  const [summary, setSummary] = useState<{ high: number; medium: number; low: number } | null>(null)
  const [recentEvents, setRecentEvents] = useState<ThermalEventRead[]>([])
  const [historicalStatistics, setHistoricalStatistics] = useState<HistoricalStatistics | null>(null)
  const [dataQualityReport, setDataQualityReport] = useState<DataQualityReport | null>(null)
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [ingesting, setIngesting] = useState(false)
  const [ingestionResult, setIngestionResult] = useState<IngestionResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    try {
      setError(null)
      const [hotspots, eventsList, historicalStats, dataQuality] = await Promise.all([
        api.getMapHotspots({ limit: 500 }),
        api.listEvents({ page: 1, page_size: 20 }),
        api.getHistoricalStatistics(),
        api.getDataQuality(),
      ])
      setMarkers(hotspots.markers)
      setSummary(hotspots.risk_summary)
      setRecentEvents(eventsList.items)
      setHistoricalStatistics(historicalStats)
      setDataQualityReport(dataQuality)
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to load data'
      setError(message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadData()
  }, [loadData])

  const handleRunIngestion = useCallback(async () => {
    setIngesting(true)
    setIngestionResult(null)
    try {
      const result = await api.runFirmsIngestion()
      setIngestionResult(result)
      await loadData()
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Ingestion failed'
      setError(message)
    } finally {
      setIngesting(false)
    }
  }, [loadData])

  const handleMarkerClick = useCallback((eventId: number) => {
    setSelectedEventId(eventId)
  }, [])

  const handleEventClick = useCallback(
    (eventId: number) => {
      navigate(`/events/${eventId}`)
    },
    [navigate],
  )

  return (
    <div className="dashboard">
      <Sidebar
        summary={summary}
        totalEvents={recentEvents.length}
        recentEvents={recentEvents}
        historicalStatistics={historicalStatistics}
        dataQualityReport={dataQualityReport}
        onEventClick={handleEventClick}
        onRunIngestion={handleRunIngestion}
        isIngesting={ingesting}
      />

      <div className="map-section">
        {error && (
          <div className="banner banner-error">
            <span className="banner-icon">⚠</span>
            <div>
              <strong>Backend unavailable.</strong> {error}
            </div>
          </div>
        )}

        {ingestionResult && (
          <div className={`banner banner-${ingestionResult.status}`}>
            <span className="banner-icon">
              {ingestionResult.status === 'success' ? '✓' : '!'}
            </span>
            <div>
              <strong>Ingestion {ingestionResult.status}.</strong>{' '}
              Fetched {ingestionResult.observations_fetched} · Stored {ingestionResult.observations_stored} · Events {ingestionResult.events_created} · Persistent {ingestionResult.persistent_sources}
            </div>
          </div>
        )}

        <MapView
          markers={markers}
          selectedEventId={selectedEventId}
          onMarkerClick={handleMarkerClick}
          isLoading={loading}
        />

        <MapLegend />
      </div>
    </div>
  )
}

function MapLegend() {
  return (
    <div className="map-legend">
      <div className="legend-title">RISK LEGEND</div>
      <div className="legend-row">
        <span className="legend-dot legend-high" />
        <span>HIGH (score ≥50)</span>
      </div>
      <div className="legend-row">
        <span className="legend-dot legend-medium" />
        <span>MEDIUM (score 25–49)</span>
      </div>
      <div className="legend-row">
        <span className="legend-dot legend-low" />
        <span>LOW (score &lt;25)</span>
      </div>
    </div>
  )
}
