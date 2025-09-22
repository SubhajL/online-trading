import { useRef, useState, useEffect } from 'react'
import { useChart } from '@/hooks/useChart'
import { useMarketData } from '@/hooks/useMarketData'
import { IndicatorPanel } from './IndicatorPanel'
import { SmcOverlays } from './SmcOverlays'
import { ZoneOverlays } from './ZoneOverlays'
import type { Symbol, Timeframe, ChartType, IndicatorType } from '@/types'
import type { UTCTimestamp } from 'lightweight-charts'

type ChartProps = {
  symbol: Symbol | string
  timeframe?: Timeframe
  activeIndicators?: IndicatorType[]
  showSmcOverlays?: boolean
  showZoneOverlays?: boolean
  className?: string
}

const TIMEFRAMES: Timeframe[] = ['1m', '5m', '15m', '1h', '4h', '1d']
const CHART_TYPES: ChartType[] = ['candlestick', 'line', 'area']

export function Chart({
  symbol,
  timeframe = '15m',
  activeIndicators = [],
  showSmcOverlays = false,
  showZoneOverlays = false,
  className = '',
}: ChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [selectedTimeframe, setSelectedTimeframe] = useState<Timeframe>(timeframe)
  const [chartType, setChartType] = useState<ChartType>('candlestick')
  const [showIndicatorPanel, setShowIndicatorPanel] = useState(false)
  const [enabledIndicators, setEnabledIndicators] = useState<IndicatorType[]>(activeIndicators)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [showSmc, setShowSmc] = useState(showSmcOverlays)
  const [showZones, setShowZones] = useState(showZoneOverlays)

  const {
    updateCandles,
    addIndicator,
    removeIndicator,
    fitContent,
    setChartType: updateChartType,
    addSmcOverlay,
    removeSmcOverlay,
    addZoneOverlay,
    removeZoneOverlay,
    cleanup,
  } = useChart(containerRef)

  const { candles, indicators, smcEvents, zones, loading, error, setTimeframe, setSymbol } = useMarketData(
    symbol as Symbol,
    selectedTimeframe
  )

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
          color: getIndicatorColor(indicatorType),
        })
      }
    })
  }, [indicators, enabledIndicators, addIndicator])

  // Update SMC overlays
  useEffect(() => {
    if (showSmc && smcEvents.length > 0) {
      addSmcOverlay(smcEvents)
    } else {
      removeSmcOverlay()
    }
  }, [showSmc, smcEvents, addSmcOverlay, removeSmcOverlay])

  // Update zone overlays
  useEffect(() => {
    if (showZones && zones.length > 0) {
      addZoneOverlay(zones)
    } else {
      removeZoneOverlay()
    }
  }, [showZones, zones, addZoneOverlay, removeZoneOverlay])

  // Cleanup on unmount
  useEffect(() => {
    return cleanup
  }, [cleanup])

  const handleTimeframeChange = (tf: Timeframe) => {
    setSelectedTimeframe(tf)
    setTimeframe(tf)
  }

  const handleChartTypeChange = (type: ChartType) => {
    setChartType(type)
    updateChartType(type)
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

  return (
    <div
      className={`relative bg-gray-900 rounded-lg ${
        isFullscreen ? 'fixed inset-0 z-50 fullscreen' : ''
      } ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-700">
        <div className="flex items-center gap-4">
          <h3 className="text-lg font-semibold text-white">{symbol}</h3>

          {/* Timeframe selector */}
          <div className="flex gap-1">
            {TIMEFRAMES.map(tf => (
              <button
                key={tf}
                onClick={() => handleTimeframeChange(tf)}
                className={`px-3 py-1 text-sm rounded transition-colors ${
                  selectedTimeframe === tf
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Chart type selector */}
          <select
            data-testid="chart-type-selector"
            value={chartType}
            onChange={(e) => handleChartTypeChange(e.target.value as ChartType)}
            className="bg-gray-800 text-white text-sm px-3 py-1 rounded border border-gray-700"
          >
            {CHART_TYPES.map(type => (
              <option key={type} value={type}>
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </option>
            ))}
          </select>

          {/* Indicator toggle */}
          <button
            data-testid="indicator-panel-toggle"
            onClick={() => setShowIndicatorPanel(!showIndicatorPanel)}
            className="px-3 py-1 text-sm bg-gray-800 text-gray-300 rounded hover:bg-gray-700"
          >
            Indicators
          </button>

          {/* SMC overlay toggle */}
          <button
            data-testid="smc-overlay-toggle"
            onClick={() => setShowSmc(!showSmc)}
            className={`px-3 py-1 text-sm rounded transition-colors ${
              showSmc
                ? 'bg-green-600 text-white'
                : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            SMC
          </button>

          {/* Zone overlay toggle */}
          <button
            data-testid="zone-overlay-toggle"
            onClick={() => setShowZones(!showZones)}
            className={`px-3 py-1 text-sm rounded transition-colors ${
              showZones
                ? 'bg-purple-600 text-white'
                : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            Zones
          </button>

          {/* Actions */}
          <button
            data-testid="fit-content-button"
            onClick={fitContent}
            className="p-1 text-gray-400 hover:text-white"
            title="Fit content"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-5h-4m4 0v4m0 0l-5-5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
            </svg>
          </button>

          <button
            data-testid="fullscreen-button"
            onClick={toggleFullscreen}
            className="p-1 text-gray-400 hover:text-white"
            title="Toggle fullscreen"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {isFullscreen ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l4 4m12-4h-4m4 0v4m0 0l-4-4M4 16v4m0 0h4m-4 0l4-4m12 4l-4-4m4 4v-4m0 4h-4" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Chart container */}
      <div className="relative h-[600px]">
        {loading && (
          <div
            data-testid="chart-loading"
            className="absolute inset-0 flex items-center justify-center bg-gray-900 bg-opacity-75 z-10"
          >
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-900 bg-opacity-75 z-10">
            <p className="text-red-500">Error: {error}</p>
          </div>
        )}

        <div ref={containerRef} data-testid="chart-container" className="w-full h-full" />

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

function getIndicatorColor(indicator: IndicatorType): string {
  const colors: Record<IndicatorType, string> = {
    EMA: '#3B82F6',
    SMA: '#10B981',
    RSI: '#F59E0B',
    MACD: '#8B5CF6',
    BB: '#EC4899',
    VOLUME: '#6B7280',
  }
  return colors[indicator] || '#6B7280'
}