import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useMarketData } from './useMarketData'
import type { Symbol, Timeframe } from '@/types'

// Mock the useWebSocket hook
vi.mock('./useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    service: mockService,
    connected: true,
    connecting: false,
    reconnectAttempts: 0,
  })),
}))

const mockService = {
  emit: vi.fn(),
  subscribe: vi.fn(),
}

describe('useMarketData', () => {
  const symbol = 'BTCUSDT' as Symbol
  const timeframe = '5m' as Timeframe

  beforeEach(() => {
    vi.clearAllMocks()
    mockService.subscribe.mockReturnValue(() => {})
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('should subscribe to candles channel on mount', () => {
    renderHook(() => useMarketData(symbol, timeframe))

    expect(mockService.emit).toHaveBeenCalledWith('subscribe', {
      channel: 'candles',
      params: { symbol, timeframe },
    })
  })

  it('should subscribe to indicators channel on mount', () => {
    renderHook(() => useMarketData(symbol, timeframe))

    expect(mockService.emit).toHaveBeenCalledWith('subscribe', {
      channel: 'indicators',
      params: { symbol, timeframe },
    })
  })

  it('should subscribe to smc_events channel on mount', () => {
    renderHook(() => useMarketData(symbol, timeframe))

    expect(mockService.emit).toHaveBeenCalledWith('subscribe', {
      channel: 'smc_events',
      params: { symbol, timeframe },
    })
  })

  it('should subscribe to zones channel on mount', () => {
    renderHook(() => useMarketData(symbol, timeframe))

    expect(mockService.emit).toHaveBeenCalledWith('subscribe', {
      channel: 'zones',
      params: { symbol, timeframe },
    })
  })

  it('should update indicators when receiving indicator data', () => {
    const { result } = renderHook(() => useMarketData(symbol, timeframe))

    // Get the indicators subscription callback
    const indicatorsCallback = mockService.subscribe.mock.calls.find(
      call => call[0] === `indicators:${symbol}:${timeframe}`
    )?.[1]

    const indicatorData = {
      type: 'EMA',
      time: 1234567890,
      value: 50000,
    }

    act(() => {
      indicatorsCallback?.(indicatorData)
    })

    expect(result.current.indicators.EMA).toHaveLength(1)
    expect(result.current.indicators.EMA[0]).toEqual({
      time: indicatorData.time,
      value: indicatorData.value,
    })
  })

  it('should append SMC events when receiving new events', () => {
    const { result } = renderHook(() => useMarketData(symbol, timeframe))

    const smcCallback = mockService.subscribe.mock.calls.find(
      call => call[0] === `smc_events:${symbol}:${timeframe}`
    )?.[1]

    const smcEvent = {
      time: 1234567890,
      type: 'CHOCH' as const,
      price: 50000,
    }

    act(() => {
      smcCallback?.(smcEvent)
    })

    expect(result.current.smcEvents).toHaveLength(1)
    expect(result.current.smcEvents[0]).toEqual(smcEvent)

    // Add another event
    const smcEvent2 = {
      time: 1234567900,
      type: 'BOS' as const,
      price: 51000,
    }

    act(() => {
      smcCallback?.(smcEvent2)
    })

    expect(result.current.smcEvents).toHaveLength(2)
    expect(result.current.smcEvents[1]).toEqual(smcEvent2)
  })

  it('should replace zones when receiving zone updates', () => {
    const { result } = renderHook(() => useMarketData(symbol, timeframe))

    const zonesCallback = mockService.subscribe.mock.calls.find(
      call => call[0] === `zones:${symbol}:${timeframe}`
    )?.[1]

    const zones = [
      {
        id: 'zone1',
        type: 'ORDER_BLOCK' as const,
        startTime: 1234567890,
        endTime: 1234567900,
        highPrice: 51000,
        lowPrice: 50000,
      },
      {
        id: 'zone2',
        type: 'FVG' as const,
        startTime: 1234567900,
        endTime: 1234567910,
        highPrice: 52000,
        lowPrice: 51500,
      },
    ]

    act(() => {
      zonesCallback?.({ zones })
    })

    expect(result.current.zones).toEqual(zones)

    // Replace with new zones
    const newZones = [
      {
        id: 'zone3',
        type: 'ORDER_BLOCK' as const,
        startTime: 1234567920,
        endTime: 1234567930,
        highPrice: 53000,
        lowPrice: 52000,
      },
    ]

    act(() => {
      zonesCallback?.({ zones: newZones })
    })

    expect(result.current.zones).toEqual(newZones)
    expect(result.current.zones).toHaveLength(1)
  })

  it('should unsubscribe from all channels on cleanup', () => {
    const unsubCandles = vi.fn()
    const unsubIndicators = vi.fn()
    const unsubSmcEvents = vi.fn()
    const unsubZones = vi.fn()

    let callCount = 0
    mockService.subscribe.mockImplementation(() => {
      const unsubFns = [unsubCandles, unsubIndicators, unsubSmcEvents, unsubZones]
      return unsubFns[callCount++ % 4]
    })

    const { unmount } = renderHook(() => useMarketData(symbol, timeframe))

    unmount()

    expect(mockService.emit).toHaveBeenCalledWith('unsubscribe', {
      channel: 'candles',
      params: { symbol, timeframe },
    })
    expect(mockService.emit).toHaveBeenCalledWith('unsubscribe', {
      channel: 'indicators',
      params: { symbol, timeframe },
    })
    expect(mockService.emit).toHaveBeenCalledWith('unsubscribe', {
      channel: 'smc_events',
      params: { symbol, timeframe },
    })
    expect(mockService.emit).toHaveBeenCalledWith('unsubscribe', {
      channel: 'zones',
      params: { symbol, timeframe },
    })

    expect(unsubCandles).toHaveBeenCalled()
    expect(unsubIndicators).toHaveBeenCalled()
    expect(unsubSmcEvents).toHaveBeenCalled()
    expect(unsubZones).toHaveBeenCalled()
  })

  it('should handle indicator errors gracefully', () => {
    const { result } = renderHook(() => useMarketData(symbol, timeframe))

    const indicatorsCallback = mockService.subscribe.mock.calls.find(
      call => call[0] === `indicators:${symbol}:${timeframe}`
    )?.[1]

    act(() => {
      indicatorsCallback?.({ error: 'Failed to calculate indicators' })
    })

    expect(result.current.error).toBe('Failed to calculate indicators')
    expect(result.current.loading).toBe(false)
  })

  it('should handle multiple indicator types', () => {
    const { result } = renderHook(() => useMarketData(symbol, timeframe))

    const indicatorsCallback = mockService.subscribe.mock.calls.find(
      call => call[0] === `indicators:${symbol}:${timeframe}`
    )?.[1]

    const indicators = [
      { type: 'EMA', time: 1234567890, value: 50000 },
      { type: 'RSI', time: 1234567890, value: 65 },
      { type: 'MACD', time: 1234567890, value: 100 },
      { type: 'BB', time: 1234567890, value: 50500 },
    ]

    act(() => {
      indicators.forEach(indicator => indicatorsCallback?.(indicator))
    })

    expect(result.current.indicators.EMA).toHaveLength(1)
    expect(result.current.indicators.RSI).toHaveLength(1)
    expect(result.current.indicators.MACD).toHaveLength(1)
    expect(result.current.indicators.BB).toHaveLength(1)
  })

  it('should clear all data when symbol or timeframe changes', () => {
    const { result, rerender } = renderHook(
      ({ symbol, timeframe }) => useMarketData(symbol, timeframe),
      { initialProps: { symbol, timeframe } }
    )

    // Add some initial data
    const candlesCallback = mockService.subscribe.mock.calls.find(
      call => call[0] === `candles:${symbol}:${timeframe}`
    )?.[1]

    act(() => {
      candlesCallback?.({
        candle: {
          time: 1234567890,
          open: 50000,
          high: 51000,
          low: 49000,
          close: 50500,
          volume: 100,
        },
      })
    })

    expect(result.current.candles).toHaveLength(1)

    // Change symbol
    const newSymbol = 'ETHUSDT' as Symbol
    rerender({ symbol: newSymbol, timeframe })

    expect(result.current.candles).toHaveLength(0)
    expect(result.current.indicators.EMA).toHaveLength(0)
    expect(result.current.smcEvents).toHaveLength(0)
    expect(result.current.zones).toHaveLength(0)
  })
})