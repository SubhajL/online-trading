import { useRef, useEffect } from 'react'
import { useChart } from '@/hooks/useChart'
import type { Candle } from '@/types'
import type { HistogramData, Time } from 'lightweight-charts'
import './VolumeChart.css'

type VolumeChartProps = {
  candles: Candle[]
  loading?: boolean
  className?: string
}

export function VolumeChart({ candles, loading = false, className = '' }: VolumeChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const { addIndicator } = useChart(containerRef)

  useEffect(() => {
    if (candles.length > 0) {
      const volumeData: HistogramData[] = candles.map(candle => ({
        time: candle.time as Time,
        value: candle.volume,
        color: candle.close >= candle.open ? '#26a69a' : '#ef5350',
      }))

      addIndicator('VOLUME', volumeData, {
        priceScaleId: 'volume',
      })
    }
  }, [candles, addIndicator])

  return (
    <div className={`volume-chart ${className}`} data-testid="volume-chart">
      <div className="volume-header">
        <h4 className="volume-title">Volume</h4>
      </div>

      <div className="volume-container" ref={containerRef} data-testid="volume-container">
        {loading && (
          <div className="volume-loading" data-testid="volume-loading">
            Loading volume data...
          </div>
        )}

        {!loading && candles.length === 0 && (
          <div className="volume-no-data">No volume data available</div>
        )}
      </div>
    </div>
  )
}
