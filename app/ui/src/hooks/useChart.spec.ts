import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { useChart } from './useChart'
import type { RefObject } from 'react'

// Mock lightweight-charts
const mockChart = {
  applyOptions: vi.fn(),
  resize: vi.fn(),
  timeScale: vi.fn(() => ({
    fitContent: vi.fn(),
    setVisibleRange: vi.fn(),
  })),
  remove: vi.fn(),
  addCandlestickSeries: vi.fn(() => ({
    setData: vi.fn(),
    update: vi.fn(),
  })),
  addLineSeries: vi.fn(() => ({
    setData: vi.fn(),
    update: vi.fn(),
  })),
  addHistogramSeries: vi.fn(() => ({
    setData: vi.fn(),
    update: vi.fn(),
  })),
}

vi.mock('lightweight-charts', () => {
  const createChart = vi.fn(() => mockChart)
  return {
    createChart,
    CrosshairMode: {
      Normal: 0,
      Magnet: 1,
    },
  }
})

describe('useChart', () => {
  let containerRef: RefObject<HTMLDivElement>

  beforeEach(() => {
    containerRef = { current: document.createElement('div') }
    // Set dimensions
    Object.defineProperty(containerRef.current, 'clientWidth', {
      value: 800,
      configurable: true,
    })
    Object.defineProperty(containerRef.current, 'clientHeight', {
      value: 600,
      configurable: true,
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('creates chart when container is available', () => {
    const { result } = renderHook(() => useChart(containerRef))

    expect(result.current.chart).toBeDefined()
    expect(result.current.candlestickSeries).toBeDefined()
  })

  it('does not create chart when container is null', () => {
    const nullRef = { current: null }
    const { result } = renderHook(() => useChart(nullRef))

    expect(result.current.chart).toBeNull()
    expect(result.current.candlestickSeries).toBeNull()
  })

  it('applies dark theme options', async () => {
    const { createChart } = await import('lightweight-charts')
    renderHook(() => useChart(containerRef))

    expect(createChart).toHaveBeenCalledWith(
      containerRef.current,
      expect.objectContaining({
        layout: expect.objectContaining({
          background: expect.objectContaining({ color: '#161a1e' }),
          textColor: '#d1d4dc',
        }),
        grid: expect.objectContaining({
          vertLines: expect.objectContaining({ color: '#2a2e39' }),
          horzLines: expect.objectContaining({ color: '#2a2e39' }),
        }),
      }),
    )
  })

  it('resizes chart when container dimensions change', () => {
    renderHook(() => useChart(containerRef))

    // Change container dimensions
    Object.defineProperty(containerRef.current, 'clientWidth', {
      value: 1000,
      configurable: true,
    })
    Object.defineProperty(containerRef.current, 'clientHeight', {
      value: 700,
      configurable: true,
    })

    // Trigger resize event
    act(() => {
      window.dispatchEvent(new Event('resize'))
    })

    expect(mockChart.resize).toHaveBeenCalledWith(1000, 700)
  })

  it('removes chart on unmount', () => {
    const { unmount } = renderHook(() => useChart(containerRef))

    unmount()

    expect(mockChart.remove).toHaveBeenCalled()
  })

  it('updates candle data', () => {
    const mockSetData = vi.fn()
    const mockUpdate = vi.fn()
    mockChart.addCandlestickSeries.mockReturnValueOnce({
      setData: mockSetData,
      update: mockUpdate,
    })

    const { result } = renderHook(() => useChart(containerRef))

    const candles = [
      { time: 1000 as any, open: 100, high: 110, low: 90, close: 105 },
      { time: 2000 as any, open: 105, high: 115, low: 100, close: 110 },
    ]

    act(() => {
      result.current.updateCandles(candles)
    })

    expect(mockSetData).toHaveBeenCalledWith(candles)
  })

  it('adds indicator series', () => {
    const { result } = renderHook(() => useChart(containerRef))

    const indicatorData = [
      { time: 1000 as any, value: 50 },
      { time: 2000 as any, value: 55 },
    ]

    act(() => {
      const series = result.current.addIndicator('EMA', indicatorData, {
        color: '#2962ff',
        lineWidth: 2,
      })
      expect(series).toBeDefined()
    })

    expect(mockChart.addLineSeries).toHaveBeenCalledWith(
      expect.objectContaining({
        color: '#2962ff',
        lineWidth: 2,
      }),
    )
  })

  it('fits content to screen', () => {
    const mockFitContent = vi.fn()
    mockChart.timeScale.mockReturnValue({
      fitContent: mockFitContent,
      setVisibleRange: vi.fn(),
    })

    const { result } = renderHook(() => useChart(containerRef))

    act(() => {
      result.current.fitContent()
    })

    expect(mockFitContent).toHaveBeenCalled()
  })

  it('handles container ref changes', () => {
    const { rerender } = renderHook(({ ref }) => useChart(ref), {
      initialProps: { ref: containerRef },
    })

    // Create new container
    const newContainerRef = { current: document.createElement('div') }
    Object.defineProperty(newContainerRef.current, 'clientWidth', {
      value: 900,
      configurable: true,
    })
    Object.defineProperty(newContainerRef.current, 'clientHeight', {
      value: 650,
      configurable: true,
    })

    rerender({ ref: newContainerRef })

    // Should create new chart
    expect(mockChart.remove).toHaveBeenCalled()
  })
})
