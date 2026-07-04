import { useEffect, useRef, useState } from 'react'
import type { RefObject } from 'react'
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  CrosshairMode,
  type LineData,
  type HistogramData,
  type IPriceLine,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { SmcEvent, Zone } from '@/types'

type IndicatorType = 'EMA' | 'SMA' | 'RSI' | 'VOLUME' | 'MACD' | 'BB'

type IndicatorOptions = {
  color?: string
  lineWidth?: number
  priceScaleId?: string
}

export type UseChartReturn = {
  chart: IChartApi | null
  candlestickSeries: ISeriesApi<'Candlestick'> | null
  updateCandles: (candles: CandlestickData[]) => void
  addIndicator: (
    type: IndicatorType,
    data: (LineData | HistogramData)[],
    options?: IndicatorOptions,
  ) => ISeriesApi<'Line'> | ISeriesApi<'Histogram'> | null
  removeIndicator: (type: IndicatorType) => void
  fitContent: () => void
  setChartType: (type: string) => void
  addSmcOverlay: (events: SmcEvent[]) => void
  removeSmcOverlay: () => void
  addZoneOverlay: (zones: Zone[]) => void
  removeZoneOverlay: () => void
  addMarkers: (markers: Array<{ time: number | string; type: 'BUY' | 'SELL' }>) => void
  addPriceLevels: (levels: { entry?: number; stopLoss?: number; takeProfit?: number }) => void
  removePriceLevels: () => void
  cleanup: () => void
}

export function useChart(containerRef: RefObject<HTMLDivElement>): UseChartReturn {
  const [chart, setChart] = useState<IChartApi | null>(null)
  const [candlestickSeries, setCandlestickSeries] = useState<ISeriesApi<'Candlestick'> | null>(null)
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<'Line'> | ISeriesApi<'Histogram'>>>(
    new Map(),
  )
  const priceLinesRef = useRef<Map<string, IPriceLine>>(new Map())
  const candleSeedRef = useRef<{ length: number; firstTime: number | null }>({
    length: 0,
    firstTime: null,
  })

  useEffect(() => {
    if (!containerRef.current) {
      return
    }

    const container = containerRef.current
    const chartInstance = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        background: { color: '#161a1e' },
        textColor: '#d1d4dc',
      },
      grid: {
        vertLines: { color: '#2a2e39' },
        horzLines: { color: '#2a2e39' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: '#758696',
          width: 1,
          style: 3,
          labelBackgroundColor: '#2a2e39',
        },
        horzLine: {
          color: '#758696',
          width: 1,
          style: 3,
          labelBackgroundColor: '#2a2e39',
        },
      },
      timeScale: {
        borderColor: '#2a2e39',
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: '#2a2e39',
      },
    })

    // Create candlestick series
    const candleSeries = chartInstance.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
    })

    setChart(chartInstance)
    setCandlestickSeries(candleSeries)

    // Handle resize
    const handleResize = () => {
      if (container) {
        chartInstance.resize(container.clientWidth, container.clientHeight)
      }
    }

    window.addEventListener('resize', handleResize)

    // Store indicators ref for cleanup
    const indicators = indicatorSeriesRef.current

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize)
      // Clear indicators before chart removal
      indicators.clear()
      chartInstance.remove()
      setChart(null)
      setCandlestickSeries(null)
    }
  }, [containerRef])

  const updateCandles = (candles: CandlestickData[]) => {
    if (!candlestickSeries || candles.length === 0) return

    const firstBar = candles[0]
    if (!firstBar) return
    const firstTime = firstBar.time as number
    const seed = candleSeedRef.current
    const isAppendOrUpdate =
      seed.firstTime === firstTime && candles.length >= seed.length && seed.length > 0

    // Incremental tick: update only the newest bar. A full setData plus
    // fitContent on every tick is O(n) and resets the viewport; reserve it
    // for the initial load and reconnect-driven resets.
    const lastBar = candles[candles.length - 1]
    if (isAppendOrUpdate && lastBar) {
      candlestickSeries.update(lastBar)
    } else {
      candlestickSeries.setData(candles)
      chart?.timeScale().fitContent()
    }

    candleSeedRef.current = { length: candles.length, firstTime }
  }

  const addIndicator = (
    type: IndicatorType,
    data: (LineData | HistogramData)[],
    options: IndicatorOptions = {},
  ): ISeriesApi<'Line'> | ISeriesApi<'Histogram'> | null => {
    if (!chart) return null

    let series: ISeriesApi<'Line'> | ISeriesApi<'Histogram'>

    if (type === 'VOLUME' || type === 'RSI') {
      // Use histogram for volume and RSI
      series = chart.addHistogramSeries({
        color: options.color || '#26a69a',
        priceScaleId: options.priceScaleId || 'right',
        priceFormat: {
          type: 'volume',
        },
      })
    } else {
      // Use line series for moving averages
      series = chart.addLineSeries({
        color: options.color || '#2962ff',
        priceScaleId: options.priceScaleId || 'right',
        crosshairMarkerVisible: false,
      })
    }

    series.setData(data as LineData[])
    indicatorSeriesRef.current.set(`${type}-${Date.now()}`, series)

    return series
  }

  const fitContent = () => {
    chart?.timeScale().fitContent()
  }

  const removeIndicator = (type: IndicatorType) => {
    // Find and remove all indicators of this type
    const keysToRemove: string[] = []
    indicatorSeriesRef.current.forEach((series, key) => {
      if (key.startsWith(type)) {
        chart?.removeSeries(series)
        keysToRemove.push(key)
      }
    })
    keysToRemove.forEach(key => indicatorSeriesRef.current.delete(key))
  }

  const setChartType = (type: string) => {
    // Chart type change not implemented in current version
    // TODO: Implement chart type switching
    void type // Acknowledge parameter for future implementation
  }

  const addSmcOverlay = (events: SmcEvent[]) => {
    // SMC overlay not implemented in current version
    // TODO: Implement SMC overlay rendering
    void events // Acknowledge parameter for future implementation
  }

  const removeSmcOverlay = () => {
    // SMC overlay removal not implemented in current version
    // TODO: Implement SMC overlay removal
  }

  const addZoneOverlay = (zones: Zone[]) => {
    // Zone overlay not implemented in current version
    // TODO: Implement zone overlay rendering
    void zones // Acknowledge parameter for future implementation
  }

  const removeZoneOverlay = () => {
    // Zone overlay removal not implemented in current version
    // TODO: Implement zone overlay removal
  }

  const addMarkers = (markers: Array<{ time: number | string; type: 'BUY' | 'SELL' }>) => {
    if (!candlestickSeries || !markers || markers.length === 0) return

    const seriesMarkers = markers.map(marker => ({
      time: marker.time as UTCTimestamp,
      position: marker.type === 'BUY' ? ('belowBar' as const) : ('aboveBar' as const),
      shape: marker.type === 'BUY' ? ('arrowUp' as const) : ('arrowDown' as const),
      color: marker.type === 'BUY' ? '#26a69a' : '#ef5350',
      size: 2,
    }))

    candlestickSeries.setMarkers(seriesMarkers)
  }

  const addPriceLevels = (levels: { entry?: number; stopLoss?: number; takeProfit?: number }) => {
    if (!candlestickSeries) return

    // Remove existing price lines
    removePriceLevels()

    // Add entry line
    if (levels.entry) {
      const entryLine = candlestickSeries.createPriceLine({
        price: levels.entry,
        color: '#2196f3',
        lineWidth: 2,
        lineStyle: 0,
        axisLabelVisible: true,
        title: 'Entry',
      })
      priceLinesRef.current.set('entry', entryLine)
    }

    // Add stop loss line
    if (levels.stopLoss) {
      const slLine = candlestickSeries.createPriceLine({
        price: levels.stopLoss,
        color: '#ef5350',
        lineWidth: 2,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'SL',
      })
      priceLinesRef.current.set('stopLoss', slLine)
    }

    // Add take profit line
    if (levels.takeProfit) {
      const tpLine = candlestickSeries.createPriceLine({
        price: levels.takeProfit,
        color: '#26a69a',
        lineWidth: 2,
        lineStyle: 2,
        axisLabelVisible: true,
        title: 'TP',
      })
      priceLinesRef.current.set('takeProfit', tpLine)
    }
  }

  const removePriceLevels = () => {
    if (!candlestickSeries) return

    priceLinesRef.current.forEach(priceLine => {
      candlestickSeries.removePriceLine(priceLine)
    })
    priceLinesRef.current.clear()
  }

  const cleanup = () => {
    // Clear all indicators
    indicatorSeriesRef.current.forEach(series => {
      chart?.removeSeries(series)
    })
    indicatorSeriesRef.current.clear()

    // Clear price lines
    removePriceLevels()
  }

  return {
    chart,
    candlestickSeries,
    updateCandles,
    addIndicator,
    removeIndicator,
    fitContent,
    setChartType,
    addSmcOverlay,
    removeSmcOverlay,
    addZoneOverlay,
    removeZoneOverlay,
    addMarkers,
    addPriceLevels,
    removePriceLevels,
    cleanup,
  }
}
