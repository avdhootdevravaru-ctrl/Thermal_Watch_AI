export function classificationLabel(value?: string | null): string {
  if (!value) return 'Not classified'
  const names: Record<string, string> = {
    anomalous_thermal_pattern: 'Anomalous Thermal Pattern (Statistical Outlier)',
    within_capture_range: 'Within Typical Capture Range',
    industrial_thermal_source: 'Industrial thermal source candidate',
    persistent_thermal_source: 'Persistent thermal source pattern',
    industrial_fire: 'Industrial fire candidate',
    agricultural_burning: 'Agricultural burning candidate',
    natural_thermal_source: 'Natural thermal source candidate',
    temporary_thermal_event: 'Short-lived thermal anomaly',
    unknown: 'Uncertain thermal anomaly',
    other: 'Other / uncertain',
  }
  return names[value.toLowerCase()] ?? value.replace(/_/g, ' ')
}

export function statusLabel(value?: string | null): string {
  if (!value) return 'Unavailable'
  const names: Record<string, string> = {
    INSUFFICIENT_HISTORY: 'Not enough historical data',
    INSUFFICIENT_DATA: 'Not enough observations',
    DEMO_DATA: 'Demonstration scenario',
    NO_HISTORY: 'No historical observations',
    UNKNOWN: 'Unknown',
  }
  return names[value] ?? value.replace(/_/g, ' ').toLowerCase()
}

export function locationLabel(event: { location_name?: string | null; latitude: number; longitude: number }): string {
  return event.location_name || `${event.latitude.toFixed(3)}° N, ${event.longitude.toFixed(3)}° E`
}

export function detectionTime(value?: string | null): string {
  if (!value) return 'Time unavailable'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Time unavailable' : date.toLocaleString()
}
