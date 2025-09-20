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
} from 'lightweight-charts'

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
  fitContent: () => void
}

export function useChart(containerRef: RefObject<HTMLDivElement>): UseChartReturn {
  const [chart, setChart] = useState<IChartApi | null>(null)
  const [candlestickSeries, setCandlestickSeries] = useState<ISeriesApi<'Candlestick'> | null>(null)
  const indicatorSeriesRef = useRef<Map<string, ISeriesApi<'Line'> | ISeriesApi<'Histogram'>>>(new Map())

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

    // Cleanup
    return () => {
      window.removeEventListener('resize', handleResize)
      // Capture the current ref value to avoid stale closure issues
      const currentIndicators = indicatorSeriesRef.current
      currentIndicators.clear()
      chartInstance.remove()
      setChart(null)
      setCandlestickSeries(null)
    }
  }, [containerRef])

  const updateCandles = (candles: CandlestickData[]) => {
    if (!candlestickSeries) return
    candlestickSeries.setData(candles)
    chart?.timeScale().fitContent()
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

  return {
    chart,
    candlestickSeries,
    updateCandles,
    addIndicator,
    fitContent,
  }
}
