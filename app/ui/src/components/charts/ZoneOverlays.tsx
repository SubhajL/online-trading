import { useEffect, useRef } from 'react'
import type { Zone } from '@/types'

type ZoneOverlaysProps = {
  zones: Zone[]
  chartRef: React.RefObject<HTMLDivElement>
}

export function ZoneOverlays({ zones, chartRef }: ZoneOverlaysProps) {
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!chartRef.current || !overlayRef.current || zones.length === 0) return

    // Clear previous overlays
    if (overlayRef.current) {
      overlayRef.current.innerHTML = ''
    }

    // Create overlay elements for each zone
    zones.forEach(zone => {
      const overlay = createZoneOverlay(zone)
      overlayRef.current?.appendChild(overlay)
    })
  }, [zones, chartRef])

  return (
    <div
      ref={overlayRef}
      data-testid="zone-overlays"
      className="absolute inset-0 pointer-events-none z-10"
    />
  )
}

function createZoneOverlay(zone: Zone): HTMLDivElement {
  const overlay = document.createElement('div')
  overlay.className = 'absolute'
  overlay.setAttribute('data-testid', `zone-overlay-${zone.type}`)
  overlay.setAttribute('data-zone-id', zone.id)
  overlay.setAttribute('data-strength', zone.strength.toString())

  // Calculate zone dimensions based on price range
  const height = Math.abs(zone.priceTo - zone.priceFrom)
  const opacity = getZoneOpacity(zone.strength, zone.touches)

  // Style the zone rectangle
  overlay.style.width = '100%'
  overlay.style.height = `${height}px` // This would be calculated based on chart scale
  overlay.style.backgroundColor = zone.type === 'supply'
    ? `rgba(239, 68, 68, ${opacity})` // red-500
    : `rgba(34, 197, 94, ${opacity})` // green-500
  overlay.style.border = `1px solid ${zone.type === 'supply' ? 'rgb(239, 68, 68)' : 'rgb(34, 197, 94)'}`

  // Create label
  const label = document.createElement('div')
  label.className = 'absolute top-1 left-2 flex items-center gap-1'

  const text = document.createElement('span')
  text.className = `text-xs font-medium ${zone.type === 'supply' ? 'text-red-600' : 'text-green-600'}`
  text.textContent = `${zone.type === 'supply' ? 'Supply' : 'Demand'} (S${zone.strength})`

  // Add touch count badge
  if (zone.touches > 0) {
    const badge = document.createElement('span')
    badge.className = `px-1 py-0.5 text-xs rounded-full ${
      zone.type === 'supply'
        ? 'bg-red-100 text-red-700'
        : 'bg-green-100 text-green-700'
    }`
    badge.textContent = `${zone.touches}x`
    label.appendChild(text)
    label.appendChild(badge)
  } else {
    label.appendChild(text)
  }

  // Add last tested indicator if available
  if (zone.lastTested) {
    const tested = document.createElement('span')
    tested.className = 'ml-1 text-xs text-gray-500'
    tested.textContent = `✓`
    tested.title = `Last tested: ${new Date(zone.lastTested).toLocaleString()}`
    label.appendChild(tested)
  }

  overlay.appendChild(label)

  return overlay
}

function getZoneOpacity(strength: number, touches: number): number {
  // Base opacity on strength
  const baseOpacity = Math.min(0.1 + (strength * 0.08), 0.5)

  // Reduce opacity based on touches (zones get weaker with more touches)
  const touchPenalty = touches * 0.05

  return Math.max(baseOpacity - touchPenalty, 0.1)
}