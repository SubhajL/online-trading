import { useRef, useEffect } from 'react'
import { useChart } from '@/hooks/useChart'
import type { Candle, Indicator } from '@/types'
import './CandlestickChart.css'

type CandlestickChartProps = {
  symbol: string
  candles: Candle[]
  indicators?: Indicator[]
  loading?: boolean
  error?: string
  className?: string
}

export function CandlestickChart({
  symbol,
  candles,
  indicators = [],
  loading = false,
  error,
  className = '',
}: CandlestickChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { updateCandles, addIndicator, fitContent } = useChart(containerRef)

  useEffect(() => {
    if (candles.length > 0) {
      const candleData = candles.map(candle => ({
        ...candle,
        time: candle.time as any
      }))
      updateCandles(candleData)
    }
  }, [candles, updateCandles])

  useEffect(() => {
    indicators.forEach(indicator => {
      if (indicator.data.length > 0) {
        const indicatorData = indicator.data.map(d => ({
          ...d,
          time: d.time as any
        }))
        addIndicator(indicator.type, indicatorData, {
          color: indicator.color,
        })
      }
    })
  }, [indicators, addIndicator])

  const handleFitToScreen = () => {
    fitContent()
  }

  return (
    <div className={`candlestick-chart ${className}`} data-testid="candlestick-chart">
      <div className="chart-header">
        <h3 className="chart-symbol">{symbol}</h3>
        <button
          className="chart-action"
          onClick={handleFitToScreen}
          title="Fit to screen"
          type="button"
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
            <path d="M1.5 1h6v6h-6zM8.5 1h6v6h-6zM1.5 8h6v6h-6zM8.5 8h6v6h-6z" />
          </svg>
        </button>
      </div>

      <div className="chart-container" data-testid="chart-container" ref={containerRef}>
        {loading && (
          <div className="chart-loading" data-testid="chart-loading">
            Loading chart data...
          </div>
        )}

        {error && (
          <div className="chart-error" data-testid="chart-error">
            {error}
          </div>
        )}

        {!loading && !error && candles.length === 0 && (
          <div className="chart-no-data">No data available</div>
        )}
      </div>
    </div>
  )
}
