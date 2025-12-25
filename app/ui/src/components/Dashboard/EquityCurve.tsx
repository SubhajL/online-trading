'use client'

import { useRef, useEffect, useState, useMemo, useCallback } from 'react'
import type { IChartApi, ISeriesApi, AreaData, UTCTimestamp } from 'lightweight-charts'
import { createChart, ColorType } from 'lightweight-charts'
import type { EquityPoint, EquityTimeRange } from '@/types/dashboard'
import { formatCurrency } from '@/utils/formatters'
import './EquityCurve.css'

type EquityCurveProps = {
  data: EquityPoint[]
  initialTimeRange?: EquityTimeRange
  onTimeRangeChange?: (range: EquityTimeRange) => void
  loading?: boolean
  error?: string
  height?: number
}

const TIME_RANGES: { value: EquityTimeRange; label: string; days: number }[] = [
  { value: '1D', label: '1 Day', days: 1 },
  { value: '1W', label: '1 Week', days: 7 },
  { value: '1M', label: '1 Month', days: 30 },
  { value: 'ALL', label: 'All Time', days: Infinity },
]

function filterDataByRange(
  data: EquityPoint[],
  range: EquityTimeRange,
  now: number = Date.now(),
): EquityPoint[] {
  const rangeConfig = TIME_RANGES.find(r => r.value === range)
  if (!rangeConfig || rangeConfig.days === Infinity) {
    return data
  }

  const msPerDay = 24 * 60 * 60 * 1000
  const cutoffMs = now - rangeConfig.days * msPerDay

  return data.filter(point => new Date(point.timestamp).getTime() >= cutoffMs)
}

function sortDataByTimestamp(data: EquityPoint[]): EquityPoint[] {
  // Decorate-sort-undecorate pattern to avoid repeated date parsing
  return data
    .map(point => ({ point, time: new Date(point.timestamp).getTime() }))
    .sort((a, b) => a.time - b.time)
    .map(({ point }) => point)
}

function toUTCTimestamp(isoString: string): UTCTimestamp {
  return Math.floor(new Date(isoString).getTime() / 1000) as UTCTimestamp
}

function convertToChartData(data: EquityPoint[]): AreaData<UTCTimestamp>[] {
  return data.map(point => ({
    time: toUTCTimestamp(point.timestamp),
    value: point.equity,
  }))
}

function calculateChange(
  start: number,
  end: number,
): { amount: number; percent: number | null; isPositive: boolean; isNeutral: boolean } {
  const amount = end - start
  const isPositive = amount > 0
  const isNeutral = amount === 0

  // Handle zero start (can't calculate percent)
  if (start === 0) {
    return { amount, percent: null, isPositive, isNeutral }
  }

  const percent = (amount / Math.abs(start)) * 100
  return { amount, percent, isPositive, isNeutral }
}

function formatChange(amount: number): string {
  const sign = amount >= 0 ? '+' : ''
  return `${sign}${formatCurrency(amount)}`
}

function formatPercentChange(percent: number | null): string {
  if (percent === null) return 'N/A'
  const sign = percent >= 0 ? '+' : ''
  return `${sign}${percent.toFixed(2)}%`
}

export function EquityCurve({
  data,
  initialTimeRange = '1M',
  onTimeRangeChange,
  loading = false,
  error,
  height = 300,
}: EquityCurveProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null)
  const [timeRange, setTimeRange] = useState<EquityTimeRange>(initialTimeRange)

  // Sort and process data
  const sortedData = useMemo(() => sortDataByTimestamp(data), [data])
  const filteredData = useMemo(
    () => filterDataByRange(sortedData, timeRange),
    [sortedData, timeRange],
  )

  // Calculate summary statistics
  const summary = useMemo(() => {
    if (filteredData.length === 0) {
      return {
        currentEquity: 0,
        change: { amount: 0, percent: null, isPositive: false, isNeutral: true },
      }
    }

    const first = filteredData[0]!
    const last = filteredData[filteredData.length - 1]!
    const currentEquity = last.equity
    const change = calculateChange(first.equity, currentEquity)

    return { currentEquity, change }
  }, [filteredData])

  const handleTimeRangeChange = useCallback(
    (range: EquityTimeRange) => {
      setTimeRange(range)
      onTimeRangeChange?.(range)
    },
    [onTimeRangeChange],
  )

  // Effect 1: Initialize chart ONCE - only recreate on height change
  useEffect(() => {
    if (!containerRef.current) return

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: 'var(--color-text-muted)',
      },
      grid: {
        vertLines: { color: 'var(--color-border)' },
        horzLines: { color: 'var(--color-border)' },
      },
      rightPriceScale: {
        borderColor: 'var(--color-border)',
      },
      timeScale: {
        borderColor: 'var(--color-border)',
        timeVisible: true,
        secondsVisible: false,
      },
      crosshair: {
        mode: 0,
      },
    })

    chartRef.current = chart

    // Create series with default colors (will be updated in data effect)
    const series = chart.addAreaSeries({
      lineColor: 'var(--color-success)',
      topColor: 'rgba(16, 185, 129, 0.3)',
      bottomColor: 'rgba(16, 185, 129, 0.05)',
      lineWidth: 2,
      priceFormat: {
        type: 'price',
        precision: 2,
        minMove: 0.01,
      },
    })

    seriesRef.current = series

    // Handle resize
    const handleResize = () => {
      if (containerRef.current && chartRef.current) {
        chartRef.current.resize(containerRef.current.clientWidth, height)
      }
    }

    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [height])

  // Effect 2: Update chart data and colors when data or colors change
  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return
    if (loading || error || filteredData.length < 2) return

    const isPositive = summary.change.isPositive || summary.change.isNeutral

    // Update series colors
    seriesRef.current.applyOptions({
      lineColor: isPositive ? 'var(--color-success)' : 'var(--color-error)',
      topColor: isPositive ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)',
      bottomColor: isPositive ? 'rgba(16, 185, 129, 0.05)' : 'rgba(239, 68, 68, 0.05)',
    })

    // Update data
    seriesRef.current.setData(convertToChartData(filteredData))
    chartRef.current.timeScale().fitContent()
  }, [filteredData, loading, error, summary.change.isPositive, summary.change.isNeutral])

  if (loading) {
    return (
      <div className="equity-curve" data-testid="equity-curve-loading">
        <div className="equity-curve-header">
          <h3>Equity Curve</h3>
        </div>
        <div className="equity-curve-skeleton" style={{ height }}>
          <div className="skeleton-line" />
          <div className="skeleton-line" />
          <div className="skeleton-line" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="equity-curve" data-testid="equity-curve-error">
        <div className="equity-curve-header">
          <h3>Equity Curve</h3>
        </div>
        <div className="equity-curve-error" role="alert">
          {error}
        </div>
      </div>
    )
  }

  if (data.length === 0) {
    return (
      <div className="equity-curve" data-testid="equity-curve-empty">
        <div className="equity-curve-header">
          <h3>Equity Curve</h3>
        </div>
        <div className="equity-curve-empty">No equity data available</div>
      </div>
    )
  }

  if (filteredData.length < 2) {
    return (
      <div className="equity-curve" data-testid="equity-curve-empty">
        <div className="equity-curve-header">
          <h3>Equity Curve</h3>
        </div>
        <div className="equity-curve-empty">Insufficient data for chart</div>
      </div>
    )
  }

  const changeClass = summary.change.isNeutral
    ? 'neutral'
    : summary.change.isPositive
      ? 'positive'
      : 'negative'

  return (
    <div className="equity-curve" data-testid="equity-curve">
      <div className="equity-curve-header">
        <div className="equity-curve-title-section">
          <h3>Equity Curve</h3>
          <div className="equity-curve-summary">
            <span className="current-equity" data-testid="current-equity">
              {formatCurrency(summary.currentEquity)}
            </span>
            <span className={`equity-change ${changeClass}`} data-testid="equity-change">
              {formatChange(summary.change.amount)}
            </span>
            <span
              className={`equity-change-percent ${changeClass}`}
              data-testid="equity-change-percent"
            >
              {formatPercentChange(summary.change.percent)}
            </span>
          </div>
        </div>

        <div className="time-range-selector" role="group" aria-label="Time range">
          {TIME_RANGES.map(({ value, label }) => (
            <button
              key={value}
              type="button"
              className={`time-range-btn ${timeRange === value ? 'active' : ''}`}
              onClick={() => handleTimeRangeChange(value)}
              aria-pressed={timeRange === value}
              aria-label={label}
              data-testid={`time-range-${value}`}
            >
              {value}
            </button>
          ))}
        </div>
      </div>

      <div
        ref={containerRef}
        className="equity-chart-container"
        data-testid="equity-chart-container"
        style={{ height }}
      />
    </div>
  )
}
