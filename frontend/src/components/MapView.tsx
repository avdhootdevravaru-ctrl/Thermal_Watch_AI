import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import type { HotspotMarker } from '@/types'
import './MapView.css'

interface MapViewProps {
  markers: HotspotMarker[]
  selectedEventId: number | null
  onMarkerClick: (eventId: number) => void
  isLoading?: boolean
}

const RISK_COLORS: Record<string, string> = {
  high: '#ff3b30',
  medium: '#ff9500',
  low: '#34c759',
}

function createMarkerIcon(severity: string, selected: boolean) {
  const color = RISK_COLORS[severity] ?? '#8b9eb0'
  const size = selected ? 16 : 12
  const glow = selected ? `box-shadow: 0 0 12px ${color};` : ''
  return L.divIcon({
    className: '',
    html: `<div style="
      width:${size}px;height:${size}px;
      background:${color};
      border:2px solid ${selected ? '#fff' : color};
      border-radius:50%;
      ${glow}
      cursor:pointer;
      transition:all 0.2s ease;
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character] ?? character)
}

export default function MapView({ markers, selectedEventId, onMarkerClick, isLoading }: MapViewProps) {
  const mapRef = useRef<L.Map | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [mapReady, setMapReady] = useState(false)

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = L.map(containerRef.current, {
      center: [20.5937, 78.9629], // India center
      zoom: 5,
      zoomControl: true,
      attributionControl: true,
    })

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map)

    mapRef.current = map
    setMapReady(true)

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Update markers when data changes
  useEffect(() => {
    if (!mapRef.current || !mapReady) return

    // Clear existing markers
    mapRef.current.eachLayer((layer) => {
      if (layer instanceof L.Marker) {
        mapRef.current!.removeLayer(layer)
      }
    })

    // Add new markers
    markers.forEach((marker) => {
      // Use risk_severity from backend (computed from stored RiskAssessment)
      const severity = marker.risk_severity ?? 'medium'

      const selected = marker.event_id === selectedEventId
      const icon = createMarkerIcon(severity, selected)

      const markerLayer = L.marker([marker.latitude, marker.longitude], {
        icon, zIndexOffset: selected ? 1000 : 0,
        title: `Event ${marker.event_id}, ${severity} operational risk`,
      })
        .addTo(mapRef.current!)
        .bindPopup(`
          <div style="font-family:monospace;font-size:12px;min-width:160px;">
            <div style="font-weight:700;margin-bottom:4px;">Event #${marker.event_id}</div>
            <div style="color:#8b9eb0;">Status: <span style="color:${RISK_COLORS[severity]};font-weight:700;">${escapeHtml(marker.status)}</span></div>
            <div style="color:#8b9eb0;">Detections: ${marker.observation_count}</div>
            <div style="color:#8b9eb0;">Detection frequency: ${marker.persistence_score.toFixed(1)}/active day</div>
            <div style="color:#8b9eb0;">Risk: ${marker.risk_score?.toFixed(1) ?? 'unknown'}/100 (${severity.toUpperCase()})</div>
            <div style="color:#8b9eb0;">Trend: ${marker.trend ?? 'unknown'}</div>
            ${marker.last_detection ? `<div style="color:#5a6878;margin-top:4px;">Last: ${new Date(marker.last_detection).toLocaleDateString()}</div>` : ''}
            <div style="margin-top:8px;">
              <a href="/events/${marker.event_id}" style="color:#00d9ff;font-size:11px;">View Details →</a>
            </div>
          </div>
        `)
        .on('click', () => onMarkerClick(marker.event_id))
      void markerLayer
    })
  }, [markers, selectedEventId, mapReady, onMarkerClick])

  // Frame the returned events once data arrives; keep the India overview when empty.
  useEffect(() => {
    if (!mapRef.current || !mapReady || markers.length === 0) return
    const bounds = L.latLngBounds(markers.map((marker) => [marker.latitude, marker.longitude]))
    mapRef.current.fitBounds(bounds.pad(0.2), { maxZoom: 6 })
  }, [markers, mapReady])

  // Selecting a queue item or marker keeps the map and list on the same event.
  useEffect(() => {
    if (!mapRef.current || !mapReady || selectedEventId == null) return
    const marker = markers.find((item) => item.event_id === selectedEventId)
    if (marker) mapRef.current.flyTo([marker.latitude, marker.longitude], Math.max(mapRef.current.getZoom(), 7), { duration: 0.5 })
  }, [markers, mapReady, selectedEventId])

  return (
    <div className="map-container">
      <div ref={containerRef} className="map-view" />
      {isLoading && (
        <div className="map-loading">
          <div className="map-loading-inner">
            <div className="spinner" />
            <span>Loading hotspots…</span>
          </div>
        </div>
      )}
    </div>
  )
}
