import { useEffect, useRef } from 'react'
import type { SmcEvent } from '@/types'

type SmcOverlaysProps = {
  events: SmcEvent[]
  chartRef: React.RefObject<HTMLDivElement>
}

export function SmcOverlays({ events, chartRef }: SmcOverlaysProps) {
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!chartRef.current || !overlayRef.current || events.length === 0) return

    // Clear previous overlays
    if (overlayRef.current) {
      overlayRef.current.innerHTML = ''
    }

    // Create overlay elements for each event
    events.forEach(event => {
      const overlay = createEventOverlay(event)
      overlayRef.current?.appendChild(overlay)
    })
  }, [events, chartRef])

  return (
    <div
      ref={overlayRef}
      data-testid="smc-overlays"
      className="absolute inset-0 pointer-events-none z-20"
    />
  )
}

function createEventOverlay(event: SmcEvent): HTMLDivElement {
  const overlay = document.createElement('div')
  overlay.className = 'absolute flex items-center'
  overlay.setAttribute('data-testid', `smc-overlay-${event.type}`)
  overlay.setAttribute('data-event-id', event.id)

  // Position will be calculated based on chart coordinates
  overlay.style.left = '0'
  overlay.style.top = '50%'
  overlay.style.transform = 'translateY(-50%)'

  // Create label
  const label = document.createElement('div')
  label.className = `px-2 py-1 text-xs font-medium rounded ${getEventStyles(event)}`
  label.textContent = getEventLabel(event)

  // Create line
  const line = document.createElement('div')
  line.className = `h-px ${event.direction === 'bullish' ? 'bg-green-500' : 'bg-red-500'}`
  line.style.width = '100%'

  overlay.appendChild(label)
  overlay.appendChild(line)

  return overlay
}

function getEventStyles(event: SmcEvent): string {
  const baseStyles = 'shadow-md'

  if (event.direction === 'bullish') {
    switch (event.type) {
      case 'CHOCH':
        return `${baseStyles} bg-green-600 text-white`
      case 'BOS':
        return `${baseStyles} bg-green-500 text-white`
      case 'ORDER_BLOCK':
        return `${baseStyles} bg-green-400 text-green-900`
      case 'FVG':
        return `${baseStyles} bg-green-300 text-green-900`
      default:
        return `${baseStyles} bg-green-500 text-white`
    }
  } else {
    switch (event.type) {
      case 'CHOCH':
        return `${baseStyles} bg-red-600 text-white`
      case 'BOS':
        return `${baseStyles} bg-red-500 text-white`
      case 'ORDER_BLOCK':
        return `${baseStyles} bg-red-400 text-red-900`
      case 'FVG':
        return `${baseStyles} bg-red-300 text-red-900`
      default:
        return `${baseStyles} bg-red-500 text-white`
    }
  }
}

function getEventLabel(event: SmcEvent): string {
  const prefix = event.direction === 'bullish' ? '↑' : '↓'

  switch (event.type) {
    case 'CHOCH':
      return `${prefix} CHoCH`
    case 'BOS':
      return `${prefix} BoS`
    case 'ORDER_BLOCK':
      return `${prefix} OB`
    case 'FVG':
      return `${prefix} FVG`
    default:
      return `${prefix} ${event.type}`
  }
}