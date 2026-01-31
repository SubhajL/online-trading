import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useMarketData } from './useMarketData'
import type { Candle, Symbol, Timeframe } from '@/types'

// Mock useWebSocket hook
const mockSubscribe = vi.fn()
const mockEmit = vi.fn()
const mockService = {
  subscribe: mockSubscribe,
  emit: mockEmit,
} as any

vi.mock('./useWebSocket', () => ({
  useWebSocket: vi.fn(() => ({
    service: mockService,
    connected: true,
    connecting: false,
    reconnectAttempts: 0,
  })),
}))

describe('useMarketData', () => {
  const mockSymbol = 'BTCUSDT' as Symbol
  const mockTimeframe = '1m' as Timeframe

  beforeEach(() => {
    vi.clearAllMocks()
    mockSubscribe.mockReturnValue(vi.fn()) // Return unsubscribe function
  })

  it('subscribes to candle data on mount', () => {
    renderHook(() => useMarketData(mockSymbol, mockTimeframe))

    expect(mockEmit).toHaveBeenCalledWith('subscribe', {
      symbol: mockSymbol,
      timeframe: mockTimeframe,
    })

    expect(mockSubscribe).toHaveBeenCalledWith('candles.v1', expect.any(Function))
  })

  it('unsubscribes on unmount', () => {
    const unsubscribeFn = vi.fn()
    mockSubscribe.mockReturnValue(unsubscribeFn)

    const { unmount } = renderHook(() => useMarketData(mockSymbol, mockTimeframe))

    unmount()

    expect(mockEmit).toHaveBeenCalledWith('unsubscribe', {
      symbol: mockSymbol,
      timeframe: mockTimeframe,
    })

    expect(unsubscribeFn).toHaveBeenCalledTimes(4)
  })

  it('updates candles when data is received', async () => {
    let capturedCallback: ((data: any) => void) | null = null

    mockSubscribe.mockImplementation((event, callback) => {
      if (event === 'candles.v1') {
        capturedCallback = callback
      }
      return vi.fn()
    })

    const { result } = renderHook(() => useMarketData(mockSymbol, mockTimeframe))

    expect(result.current.candles).toEqual([])
    expect(result.current.loading).toBe(true)

    const closeTime = '2026-01-31T00:00:00.000Z'
    const expected: Candle = {
      time: Date.parse(closeTime),
      open: 50000,
      high: 50100,
      low: 49900,
      close: 50050,
      volume: 100,
    }

    act(() => {
      capturedCallback?.({
        symbol: mockSymbol,
        timeframe: mockTimeframe,
        open_time: '2026-01-30T23:59:00.000Z',
        close_time: closeTime,
        open: '50000',
        high: '50100',
        low: '49900',
        close: '50050',
        volume: '100',
      })
    })

    await waitFor(() => {
      expect(result.current.candles).toEqual([expected])
      expect(result.current.loading).toBe(false)
    })
  })

  it('appends new candles to existing data', async () => {
    let capturedCallback: ((data: any) => void) | null = null

    mockSubscribe.mockImplementation((event, callback) => {
      if (event === 'candles.v1') {
        capturedCallback = callback
      }
      return vi.fn()
    })

    const { result } = renderHook(() => useMarketData(mockSymbol, mockTimeframe))

    const close1 = '2026-01-31T00:00:00.000Z'
    const close2 = '2026-01-31T00:01:00.000Z'
    const candle1: Candle = {
      time: Date.parse(close1),
      open: 49000,
      high: 49100,
      low: 48900,
      close: 49050,
      volume: 50,
    }

    const candle2: Candle = {
      time: Date.parse(close2),
      open: 50000,
      high: 50100,
      low: 49900,
      close: 50050,
      volume: 100,
    }

    act(() => {
      capturedCallback?.({
        symbol: mockSymbol,
        timeframe: mockTimeframe,
        open_time: '2026-01-30T23:59:00.000Z',
        close_time: close1,
        open: '49000',
        high: '49100',
        low: '48900',
        close: '49050',
        volume: '50',
      })
    })

    act(() => {
      capturedCallback?.({
        symbol: mockSymbol,
        timeframe: mockTimeframe,
        open_time: '2026-01-31T00:00:00.000Z',
        close_time: close2,
        open: '50000',
        high: '50100',
        low: '49900',
        close: '50050',
        volume: '100',
      })
    })

    await waitFor(() => {
      expect(result.current.candles).toEqual([candle1, candle2])
    })
  })

  it('resubscribes when symbol or timeframe changes', () => {
    const { rerender } = renderHook(({ symbol, timeframe }) => useMarketData(symbol, timeframe), {
      initialProps: {
        symbol: 'BTCUSDT' as Symbol,
        timeframe: '1m' as Timeframe,
      },
    })

    expect(mockSubscribe).toHaveBeenCalledTimes(4)

    rerender({
      symbol: 'ETHUSDT' as Symbol,
      timeframe: '5m' as Timeframe,
    })

    expect(mockEmit).toHaveBeenCalledWith('unsubscribe', {
      symbol: 'BTCUSDT',
      timeframe: '1m',
    })

    expect(mockEmit).toHaveBeenCalledWith('subscribe', {
      symbol: 'ETHUSDT',
      timeframe: '5m',
    })
  })

  it('does not subscribe when not connected', async () => {
    const { useWebSocket } = await import('./useWebSocket')
    vi.mocked(useWebSocket).mockReturnValue({
      service: mockService,
      connected: false,
      connecting: false,
      reconnectAttempts: 0,
    })

    renderHook(() => useMarketData(mockSymbol, mockTimeframe))

    expect(mockEmit).not.toHaveBeenCalled()
    expect(mockSubscribe).not.toHaveBeenCalled()
  })
})
