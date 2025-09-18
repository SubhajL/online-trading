import { useState, useRef, useEffect } from 'react'
import type { TimeFrame, ChartType, IndicatorType } from '@/types'
import './ChartToolbar.css'

type ChartToolbarProps = {
  timeframe: TimeFrame
  chartType: ChartType
  indicators: IndicatorType[]
  onTimeframeChange: (timeframe: TimeFrame) => void
  onChartTypeChange: (chartType: ChartType) => void
  onIndicatorToggle: (indicator: IndicatorType) => void
  className?: string
  disabled?: boolean
}

const TIMEFRAMES: TimeFrame[] = ['1m', '5m', '15m', '1h', '4h', '1d']
const CHART_TYPES: { value: ChartType; label: string }[] = [
  { value: 'candlestick', label: 'Candlestick' },
  { value: 'line', label: 'Line' },
  { value: 'area', label: 'Area' },
]
const AVAILABLE_INDICATORS: IndicatorType[] = ['EMA', 'SMA', 'RSI', 'MACD', 'BB']

export function ChartToolbar({
  timeframe,
  chartType,
  indicators,
  onTimeframeChange,
  onChartTypeChange,
  onIndicatorToggle,
  className = '',
  disabled = false,
}: ChartToolbarProps) {
  const [showTimeframeMenu, setShowTimeframeMenu] = useState(false)
  const [showChartTypeMenu, setShowChartTypeMenu] = useState(false)
  const timeframeRef = useRef<HTMLDivElement>(null)
  const chartTypeRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (timeframeRef.current && !timeframeRef.current.contains(event.target as Node)) {
        setShowTimeframeMenu(false)
      }
      if (chartTypeRef.current && !chartTypeRef.current.contains(event.target as Node)) {
        setShowChartTypeMenu(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const getChartTypeLabel = () => {
    return CHART_TYPES.find(ct => ct.value === chartType)?.label || 'Candlestick'
  }

  return (
    <div className={`chart-toolbar ${className}`} data-testid="chart-toolbar">
      <div className="toolbar-group">
        <div className="toolbar-dropdown" ref={timeframeRef}>
          <button
            className="toolbar-button dropdown-trigger"
            onClick={() => setShowTimeframeMenu(!showTimeframeMenu)}
            disabled={disabled}
            aria-label="Select timeframe"
            type="button"
          >
            {timeframe}
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
              <path d="M3 4.5L6 7.5L9 4.5" />
            </svg>
          </button>
          {showTimeframeMenu && (
            <div className="dropdown-menu">
              {TIMEFRAMES.map(tf => (
                <button
                  key={tf}
                  className={`dropdown-item ${tf === timeframe ? 'active' : ''}`}
                  onClick={() => {
                    onTimeframeChange(tf)
                    setShowTimeframeMenu(false)
                  }}
                  type="button"
                >
                  {tf}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="toolbar-dropdown" ref={chartTypeRef}>
          <button
            className="toolbar-button dropdown-trigger"
            onClick={() => setShowChartTypeMenu(!showChartTypeMenu)}
            disabled={disabled}
            aria-label="Select chart type"
            type="button"
          >
            {getChartTypeLabel()}
            <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor">
              <path d="M3 4.5L6 7.5L9 4.5" />
            </svg>
          </button>
          {showChartTypeMenu && (
            <div className="dropdown-menu">
              {CHART_TYPES.map(ct => (
                <button
                  key={ct.value}
                  className={`dropdown-item ${ct.value === chartType ? 'active' : ''}`}
                  onClick={() => {
                    onChartTypeChange(ct.value)
                    setShowChartTypeMenu(false)
                  }}
                  type="button"
                >
                  {ct.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="toolbar-separator" />

      <div className="toolbar-group indicators-group">
        {AVAILABLE_INDICATORS.map(indicator => (
          <label key={indicator} className="indicator-toggle">
            <input
              type="checkbox"
              checked={indicators.includes(indicator)}
              onChange={() => onIndicatorToggle(indicator)}
              disabled={disabled}
              aria-label={indicator}
            />
            <span className="indicator-label">{indicator}</span>
          </label>
        ))}
      </div>
    </div>
  )
}
