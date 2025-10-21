import { useEffect, useRef, useMemo } from 'react'
import type { SmcEvent } from '@/types'
import { getTokens } from '@/utils/getTokens'
import { getAbsoluteFillStyles, getSmcLabelStyles, getSmcLineStyles } from '@/utils/stylingHelpers'

type SmcOverlaysProps = {
  events: SmcEvent[]
  chartRef: React.RefObject<HTMLDivElement>
}

export function SmcOverlays({ events, chartRef }: SmcOverlaysProps) {
  const overlayRef = useRef<HTMLDivElement>(null)
  const tokens = useMemo(() => getTokens(), [])

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
      style={getAbsoluteFillStyles(tokens, 20, 'none')}
    />
  )
}

function createEventOverlay(event: SmcEvent): HTMLDivElement {
  const overlay = document.createElement('div')
  overlay.setAttribute('data-testid', `smc-overlay-${event.type}`)
  overlay.setAttribute('data-event-id', event.id)
  overlay.style.position = 'absolute'
  overlay.style.display = 'flex'
  overlay.style.alignItems = 'center'
  overlay.style.left = '0'
  overlay.style.top = '50%'
  overlay.style.transform = 'translateY(-50%)'

  const tokens = getTokens()

  // Create label
  const label = document.createElement('div')
  const labelStyles = getSmcLabelStyles(event as any, tokens)
  label.textContent = getEventLabel(event)
  Object.assign(label.style, labelStyles)

  // Create line
  const line = document.createElement('div')
  const lineStyles = getSmcLineStyles(event as any, tokens)
  Object.assign(line.style, lineStyles)

  overlay.appendChild(label)
  overlay.appendChild(line)

  return overlay
}

// Tailwind-based style mapping removed in favor of token helpers

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
