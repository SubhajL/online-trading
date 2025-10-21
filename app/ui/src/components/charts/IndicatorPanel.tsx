import type { IndicatorType } from '@/types'
import { useMemo } from 'react'
import { getTokens } from '@/utils/getTokens'
import {
  getPanelContainerStyles,
  getPanelHeaderStyles,
  getPanelItemStyles,
  getIconButtonStyles,
} from '@/utils/stylingHelpers'

type IndicatorPanelProps = {
  activeIndicators: IndicatorType[]
  onToggleIndicator: (indicator: IndicatorType) => void
  onClose: () => void
}

const INDICATORS: { type: IndicatorType; name: string; description: string }[] = [
  { type: 'EMA', name: 'EMA', description: 'Exponential Moving Average' },
  { type: 'SMA', name: 'SMA', description: 'Simple Moving Average' },
  { type: 'RSI', name: 'RSI', description: 'Relative Strength Index' },
  { type: 'MACD', name: 'MACD', description: 'Moving Average Convergence Divergence' },
  { type: 'BB', name: 'BB', description: 'Bollinger Bands' },
  { type: 'VOLUME', name: 'Volume', description: 'Volume bars' },
]

export function IndicatorPanel({
  activeIndicators,
  onToggleIndicator,
  onClose,
}: IndicatorPanelProps) {
  const tokens = useMemo(() => getTokens(), [])
  const containerStyles = getPanelContainerStyles(tokens)
  const headerStyles = getPanelHeaderStyles(tokens)
  const listStyles = {
    padding: tokens.spacing[4],
    display: 'flex',
    flexDirection: 'column' as const,
    gap: tokens.spacing[2],
  }
  const handleToggle = (indicator: IndicatorType) => {
    if (onToggleIndicator) {
      onToggleIndicator(indicator)
    }
  }

  const handleClose = () => {
    if (onClose) {
      onClose()
    }
  }

  return (
    <div
      data-testid="indicator-panel"
      role="dialog"
      aria-label="Technical Indicators"
      style={{
        position: 'absolute',
        right: 0,
        top: 0,
        width: '320px',
        height: '100%',
        zIndex: 30,
        ...containerStyles,
      }}
    >
      {/* Header */}
      <div style={headerStyles}>
        <h3
          style={{
            fontSize: tokens.typography.fontSize.lg,
            fontWeight: tokens.typography.fontWeight.semibold,
            color: tokens.colors.text.primary,
            margin: 0,
          }}
        >
          Technical Indicators
        </h3>
        <button
          data-testid="close-button"
          onClick={handleClose}
          style={getIconButtonStyles(tokens)}
          aria-label="Close panel"
        >
          <svg
            style={{ width: tokens.spacing[4], height: tokens.spacing[4] }}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      {/* Indicators list */}
      <div style={listStyles}>
        {INDICATORS.map(indicator => {
          const isActive = activeIndicators.includes(indicator.type)
          return (
            <div
              key={indicator.type}
              data-testid={`indicator-item-${indicator.type}`}
              style={getPanelItemStyles(isActive, tokens)}
            >
              <label htmlFor={`indicator-${indicator.type}`} style={{ display: 'flex', flex: 1, alignItems: 'center', cursor: 'pointer' }}>
                <input
                  id={`indicator-${indicator.type}`}
                  type="checkbox"
                  checked={isActive}
                  onChange={() => handleToggle(indicator.type)}
                  aria-label={indicator.type}
                  style={{ width: '16px', height: '16px', margin: 0 }}
                />
                <div style={{ marginLeft: tokens.spacing[3], flex: 1 }}>
                  <div style={{ fontSize: tokens.typography.fontSize.sm, fontWeight: tokens.typography.fontWeight.medium, color: tokens.colors.text.primary }}>
                    {indicator.name}
                  </div>
                  <div style={{ fontSize: tokens.typography.fontSize.xs, color: tokens.colors.text.muted }}>
                    {indicator.description}
                  </div>
                </div>
              </label>
            </div>
          )
        })}
      </div>

      {/* Help text */}
      <div
        style={{
          position: 'absolute',
          bottom: tokens.spacing[4],
          left: tokens.spacing[4],
          right: tokens.spacing[4],
          padding: tokens.spacing[3],
          backgroundColor: tokens.colors.surface.overlay,
          borderRadius: tokens.radius.md,
        }}
      >
        <p style={{ fontSize: tokens.typography.fontSize.xs, color: tokens.colors.text.secondary }}>
          Select indicators to display on the chart. Some indicators may affect performance.
        </p>
      </div>
    </div>
  )
}
