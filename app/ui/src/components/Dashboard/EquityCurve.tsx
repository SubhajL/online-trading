'use client'

import { useRef, useEffect, useState, useMemo, useCallback } from 'react'
import type { IChartApi, ISeriesApi, AreaData, UTCTimestamp } from 'lightweight-charts'
import { createChart, ColorType } from 'lightweight-charts'
import type { EquityPoint, EquityTimeRange } from '@/types/dashboard'
import { formatCurrency } from '@/utils/formatters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { MaterialIcon } from '@/components/common/MaterialIcon'

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
  if (!rangeConfig || rangeConfig.days === Infinity) return data
  const msPerDay = 24 * 60 * 60 * 1000
  const cutoffMs = now - rangeConfig.days * msPerDay
  return data.filter(point => new Date(point.timestamp).getTime() >= cutoffMs)
}

function sortDataByTimestamp(data: EquityPoint[]): EquityPoint[] {
  return data
    .map(point => ({ point, time: new Date(point.timestamp).getTime() }))
    .sort((a, b) => a.time - b.time)
    .map(({ point }) => point)
}

function toUTCTimestamp(isoString: string): UTCTimestamp {
  return Math.floor(new Date(isoString).getTime() / 1000) as UTCTimestamp
}

function convertToChartData(data: EquityPoint[]): AreaData<UTCTimestamp>[] {
  const result: AreaData<UTCTimestamp>[] = []
  for (const point of data) {
    const time = toUTCTimestamp(point.timestamp)
    const last = result[result.length - 1]
    if (last && last.time === time) {
      result[result.length - 1] = { time, value: point.equity }
      continue
    }
    result.push({ time, value: point.equity })
  }
  return result
}

function calculateChange(
  start: number,
  end: number,
): { amount: number; percent: number | null; isPositive: boolean; isNeutral: boolean } {
  const amount = end - start
  const isPositive = amount > 0
  const isNeutral = amount === 0
  if (start === 0) return { amount, percent: null, isPositive, isNeutral }
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

  const sortedData = useMemo(() => sortDataByTimestamp(data), [data])
  const filteredData = useMemo(
    () => filterDataByRange(sortedData, timeRange),
    [sortedData, timeRange],
  )

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
      rightPriceScale: { borderColor: 'var(--color-border)' },
      timeScale: { borderColor: 'var(--color-border)', timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    })
    chartRef.current = chart
    const series = chart.addAreaSeries({
      lineColor: 'var(--color-success)',
      topColor: 'rgba(16, 185, 129, 0.3)',
      bottomColor: 'rgba(16, 185, 129, 0.05)',
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    })
    seriesRef.current = series
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

  useEffect(() => {
    if (!seriesRef.current || !chartRef.current) return
    if (loading || error || filteredData.length < 2) return
    const chartData = convertToChartData(filteredData)
    if (chartData.length < 2) return
    const isPositive = summary.change.isPositive || summary.change.isNeutral
    seriesRef.current.applyOptions({
      lineColor: isPositive ? 'var(--color-success)' : 'var(--color-error)',
      topColor: isPositive ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)',
      bottomColor: isPositive ? 'rgba(16, 185, 129, 0.05)' : 'rgba(239, 68, 68, 0.05)',
    })
    seriesRef.current.setData(chartData)
    chartRef.current.timeScale().fitContent()
  }, [filteredData, loading, error, summary.change.isPositive, summary.change.isNeutral])

  if (loading) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border-slate-100 dark:border-slate-700 shadow-sm"
        data-testid="equity-curve-loading"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-wide">
            Equity Curve
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3" style={{ height }}>
            <Skeleton className="h-full w-full rounded-md" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 border-destructive/30 shadow-sm"
        data-testid="equity-curve-error"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-wide">
            Equity Curve
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 text-sm text-destructive" role="alert">
            <MaterialIcon name="error" size="sm" className="shrink-0" />
            {error}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (data.length === 0) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border-slate-100 dark:border-slate-700 shadow-sm"
        data-testid="equity-curve-empty"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-wide">
            Equity Curve
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500">No equity data available</p>
        </CardContent>
      </Card>
    )
  }

  if (filteredData.length < 2) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border-slate-100 dark:border-slate-700 shadow-sm"
        data-testid="equity-curve-empty"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-wide">
            Equity Curve
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500">Insufficient data for chart</p>
        </CardContent>
      </Card>
    )
  }

  const changeColor = summary.change.isNeutral
    ? 'text-slate-500'
    : summary.change.isPositive
      ? 'text-success'
      : 'text-danger'

  return (
    <Card
      className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-soft hover:shadow-md transition-all duration-200"
      data-testid="equity-curve"
    >
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <CardTitle className="text-sm font-medium text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-wide">
              Equity Curve
            </CardTitle>
            <div className="flex items-center gap-2 mt-1">
              <span className="text-xl font-bold font-mono" data-testid="current-equity">
                {formatCurrency(summary.currentEquity)}
              </span>
              <span
                className={`text-sm font-mono font-bold ${changeColor}`}
                data-testid="equity-change"
              >
                {formatChange(summary.change.amount)}
              </span>
              <span
                className={`text-xs font-mono ${changeColor}`}
                data-testid="equity-change-percent"
              >
                {formatPercentChange(summary.change.percent)}
              </span>
            </div>
          </div>

          <div className="flex bg-slate-100 p-1 rounded-lg" role="group" aria-label="Time range">
            {TIME_RANGES.map(({ value, label }) => (
              <button
                key={value}
                type="button"
                className={`px-3 py-1 text-xs rounded font-semibold transition-all duration-150 ${
                  timeRange === value
                    ? 'bg-white dark:bg-slate-800 text-indigo-600 shadow-sm'
                    : 'text-slate-500 dark:text-slate-400 dark:text-slate-500 hover:text-slate-700'
                }`}
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
      </CardHeader>

      <CardContent className="pt-0">
        <div
          ref={containerRef}
          className="rounded-xl overflow-hidden bg-slate-50 border border-slate-100"
          data-testid="equity-chart-container"
          style={{ height }}
        />
      </CardContent>
    </Card>
  )
}
