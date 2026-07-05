import { useRef, useState, useEffect, useMemo } from 'react'
import type { CSSProperties } from 'react'
import { useChart } from '@/hooks/useChart'
import { useMarketData } from '@/hooks/useMarketData'
import { IndicatorPanel } from './IndicatorPanel'
import { SmcOverlays } from './SmcOverlays'
import { ZoneOverlays } from './ZoneOverlays'
import { getTokens } from '@/utils/getTokens'
import {
  getIndicatorColor,
  getChartButtonStyles,
  getIconButtonStyles,
  getOverlayStyles,
  getSpinnerStyles,
  getIconSizeStyles,
} from '@/utils/stylingHelpers'
import type { Symbol, Timeframe, IndicatorType } from '@/types'
import type { UTCTimestamp } from 'lightweight-charts'

type ChartProps = {
  symbol: Symbol | string
  timeframe?: Timeframe
  activeIndicators?: IndicatorType[]
  showSmcOverlays?: boolean
  showZoneOverlays?: boolean
  markers?: Array<{ time: number | UTCTimestamp; type: 'BUY' | 'SELL' }>
  levels?: { entry?: number; stopLoss?: number; takeProfit?: number }
  onReady?: () => void
  className?: string
}

const TIMEFRAMES: Timeframe[] = ['1m', '5m', '15m', '1h', '4h', '1d']

export function Chart({
  symbol,
  timeframe = '15m',
  activeIndicators = [],
  showSmcOverlays = false,
  showZoneOverlays = false,
  markers,
  levels,
  onReady,
  className = '',
}: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [selectedTimeframe, setSelectedTimeframe] = useState<Timeframe>(timeframe)
  const [showIndicatorPanel, setShowIndicatorPanel] = useState(false)
  const [enabledIndicators, setEnabledIndicators] = useState<IndicatorType[]>(activeIndicators)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showSmc, setShowSmc] = useState(showSmcOverlays)
  const [showZones, setShowZones] = useState(showZoneOverlays)
  const tokens = useMemo(() => getTokens(), [])

  const {
    updateCandles,
    addIndicator,
    removeIndicator,
    fitContent,
    addMarkers,
    addPriceLevels,
    removePriceLevels,
    cleanup,
  } = useChart(containerRef)

  const { candles, indicators, smcEvents, zones, loading, error, setTimeframe, setSymbol } =
    useMarketData(symbol as Symbol, selectedTimeframe)

  // Update symbol when prop changes
  useEffect(() => {
    setSymbol(symbol as Symbol)
  }, [symbol, setSymbol])

  // Update candles
  useEffect(() => {
    if (candles.length > 0) {
      const candleData = candles.map(candle => ({
        ...candle,
        time: candle.time as UTCTimestamp,
      }))
      updateCandles(candleData)
    }
  }, [candles, updateCandles])

  // Update indicators
  useEffect(() => {
    enabledIndicators.forEach(indicatorType => {
      const indicatorData = indicators[indicatorType]
      if (indicatorData?.length > 0) {
        const formattedData = indicatorData.map(d => ({
          time: d.time as UTCTimestamp,
          value: d.value,
        }))
        addIndicator(indicatorType, formattedData, {
          color: getIndicatorColor(indicatorType, tokens),
        })
      }
    })
  }, [indicators, enabledIndicators, addIndicator, tokens])

  // Add markers
  useEffect(() => {
    if (markers && markers.length > 0) {
      addMarkers(markers)
    }
  }, [markers, addMarkers])

  // Add price levels
  useEffect(() => {
    if (levels) {
      addPriceLevels(levels)
    } else {
      removePriceLevels()
    }
  }, [levels, addPriceLevels, removePriceLevels])

  // Call onReady when chart is loaded
  useEffect(() => {
    if (candles.length > 0 && onReady) {
      onReady()
    }
  }, [candles, onReady])

  // Cleanup on unmount
  useEffect(() => {
    return cleanup
  }, [cleanup])

  const handleTimeframeChange = (tf: Timeframe) => {
    setSelectedTimeframe(tf)
    setTimeframe(tf)
  }

  const handleIndicatorToggle = (indicator: IndicatorType) => {
    if (enabledIndicators.includes(indicator)) {
      setEnabledIndicators(prev => prev.filter(i => i !== indicator))
      removeIndicator(indicator)
    } else {
      setEnabledIndicators(prev => [...prev, indicator])
    }
  }

  const toggleFullscreen = () => {
    setIsFullscreen(!isFullscreen)
  }

  const baseRootStyles: CSSProperties = {
    backgroundColor: tokens.colors.gray[900],
    borderRadius: tokens.radius.lg,
    display: 'flex',
    flexDirection: 'column',
  }

  const fullscreenStyles: CSSProperties = isFullscreen
    ? { position: 'fixed', inset: 0, zIndex: 50 }
    : { position: 'relative' }

  const rootStyles: CSSProperties = { ...baseRootStyles, ...fullscreenStyles }

  const headerStyles: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: `${tokens.spacing[2]} ${tokens.spacing[4]}`,
    borderBottom: `1px solid ${tokens.colors.border.subtle}`,
    gap: tokens.spacing[4],
  }

  const timeframeGroupStyles: CSSProperties = {
    display: 'flex',
    gap: tokens.spacing[1],
    alignItems: 'center',
  }

  const headerLeftStyles: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: tokens.spacing[4],
  }

  const headerRightStyles: CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: tokens.spacing[2],
  }

  const iconButtonStyle = getIconButtonStyles(tokens)
  const iconSvgStyle: CSSProperties = getIconSizeStyles('md', tokens)

  const chartAreaStyles: CSSProperties = {
    position: 'relative',
    height: '600px',
  }

  return (
    <div data-testid="chart-root" style={rootStyles} className={className}>
      {/* Header */}
      <div style={headerStyles}>
        <div style={headerLeftStyles}>
          <h3
            style={{
              fontSize: tokens.typography.fontSize.lg,
              fontWeight: tokens.typography.fontWeight.semibold,
              color: tokens.colors.text.primary,
              margin: 0,
            }}
          >
            {symbol}
          </h3>

          {/* Timeframe selector */}
          <div style={timeframeGroupStyles}>
            {TIMEFRAMES.map(tf => (
              <button
                key={tf}
                onClick={() => handleTimeframeChange(tf)}
                style={getChartButtonStyles(selectedTimeframe === tf, tokens)}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        <div style={headerRightStyles}>
          {/* Indicator toggle */}
          <button
            data-testid="indicator-panel-toggle"
            onClick={() => setShowIndicatorPanel(!showIndicatorPanel)}
            style={getChartButtonStyles(showIndicatorPanel, tokens)}
          >
            Indicators
          </button>

          {/* SMC overlay toggle */}
          <button
            data-testid="smc-overlay-toggle"
            onClick={() => setShowSmc(!showSmc)}
            style={getChartButtonStyles(showSmc, tokens)}
          >
            SMC
          </button>

          {/* Zone overlay toggle */}
          <button
            data-testid="zone-overlay-toggle"
            onClick={() => setShowZones(!showZones)}
            style={getChartButtonStyles(showZones, tokens)}
          >
            Zones
          </button>

          {/* Actions */}
          <button
            data-testid="fit-content-button"
            onClick={fitContent}
            style={iconButtonStyle}
            title="Fit content"
          >
            <svg style={iconSvgStyle} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 8V4m0 0h4M4 4l5 5m11-5h-4m4 0v4m0 0l-5-5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"
              />
            </svg>
          </button>

          <button
            data-testid="fullscreen-button"
            onClick={toggleFullscreen}
            style={iconButtonStyle}
            title="Toggle fullscreen"
          >
            <svg style={iconSvgStyle} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {isFullscreen ? (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              ) : (
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 8V4m0 0h4M4 4l4 4m12-4h-4m4 0v4m0 0l-4-4M4 16v4m0 0h4m-4 0l4-4m12 4l-4-4m4 4v-4m0 4h-4"
                />
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Chart container */}
      <div style={chartAreaStyles}>
        {loading && (
          <div data-testid="chart-loading" style={getOverlayStyles(tokens)}>
            <div
              style={{
                ...getSpinnerStyles('lg', tokens),
                borderTopColor: tokens.colors.primary[500],
                borderRightColor: tokens.colors.primary[500],
                borderBottomColor: tokens.colors.primary[500],
                borderLeftColor: 'transparent',
                animation: 'spin 1s linear infinite',
              }}
            ></div>
          </div>
        )}

        {error && (
          <div style={getOverlayStyles(tokens)}>
            <p
              style={{
                color: tokens.colors.text.danger,
                fontSize: tokens.typography.fontSize.sm,
                backgroundColor: tokens.colors.error[50],
                padding: `${tokens.spacing[2]} ${tokens.spacing[3]}`,
                borderRadius: tokens.radius.sm,
              }}
            >
              Error: {error}
            </p>
          </div>
        )}

        <div
          ref={containerRef}
          data-testid="chart-container"
          style={{ width: '100%', height: '100%' }}
        />

        {/* Overlays */}
        {showSmc && <SmcOverlays events={smcEvents} chartRef={containerRef} />}
        {showZones && <ZoneOverlays zones={zones} chartRef={containerRef} />}
      </div>

      {/* Indicator panel */}
      {showIndicatorPanel && (
        <IndicatorPanel
          data-testid="indicator-panel"
          activeIndicators={enabledIndicators}
          onToggleIndicator={handleIndicatorToggle}
          onClose={() => setShowIndicatorPanel(false)}
        />
      )}
    </div>
  )
}
