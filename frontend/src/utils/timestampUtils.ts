const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * Format a timestamp for display in the Detection Timeline.
 * Format: "Sep 6, 2026 · 7:03 PM"
 *
 * Handles ISO 8601 timestamps with timezone offsets correctly.
 * Displays the time as recorded (in the original timezone).
 */
export function formatTimelineDate(timestamp: string | Date): string {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp

  if (isNaN(date.getTime())) {
    return 'Invalid date'
  }

  const month = months[date.getMonth()]
  const day = date.getDate()
  const year = date.getFullYear()
  const hours = date.getHours()
  const minutes = date.getMinutes()
  const ampm = hours >= 12 ? 'PM' : 'AM'
  const displayHours = hours % 12 || 12
  const displayMinutes = minutes < 10 ? `0${minutes}` : minutes

  return `${month} ${day}, ${year} · ${displayHours}:${displayMinutes} ${ampm}`
}

/**
 * Format a timestamp for the observations section.
 * Format: "Sep 6, 2026, 7:03 PM"
 */
export function formatObservationDate(timestamp: string | Date): string {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp

  if (isNaN(date.getTime())) {
    return 'Invalid date'
  }

  const month = months[date.getMonth()]
  const day = date.getDate()
  const year = date.getFullYear()
  const hours = date.getHours()
  const minutes = date.getMinutes()
  const ampm = hours >= 12 ? 'PM' : 'AM'
  const displayHours = hours % 12 || 12
  const displayMinutes = minutes < 10 ? `0${minutes}` : minutes

  return `${month} ${day}, ${year}, ${displayHours}:${displayMinutes} ${ampm}`
}

/**
 * Format a timestamp for compact display.
 * Format: "Sep 6, 2026"
 */
export function formatSidebarDate(timestamp: string | Date): string {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp

  if (isNaN(date.getTime())) {
    return 'Invalid date'
  }

  const month = months[date.getMonth()]
  const day = date.getDate()
  const year = date.getFullYear()

  return `${month} ${day}, ${year}`
}
