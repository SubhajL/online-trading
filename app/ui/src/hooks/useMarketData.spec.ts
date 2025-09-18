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
      channel: 'candles',
      params: { symbol: mockSymbol, timeframe: mockTimeframe },
    })

    expect(mockSubscribe).toHaveBeenCalledWith(
      `candles:${mockSymbol}:${mockTimeframe}`,
      expect.any(Function),
    )
  })

  it('unsubscribes on unmount', () => {
    const unsubscribeFn = vi.fn()
    mockSubscribe.mockReturnValue(unsubscribeFn)

    const { unmount } = renderHook(() => useMarketData(mockSymbol, mockTimeframe))

    unmount()

    expect(mockEmit).toHaveBeenCalledWith('unsubscribe', {
      channel: 'candles',
      params: { symbol: mockSymbol, timeframe: mockTimeframe },
    })

    expect(unsubscribeFn).toHaveBeenCalled()
  })

  it('updates candles when data is received', async () => {
    let capturedCallback: ((data: any) => void) | null = null

    mockSubscribe.mockImplementation((event, callback) => {
      capturedCallback = callback
      return vi.fn()
    })

    const { result } = renderHook(() => useMarketData(mockSymbol, mockTimeframe))

    expect(result.current.candles).toEqual([])
    expect(result.current.loading).toBe(true)

    const mockCandle: Candle = {
      time: Date.now(),
      open: 50000,
      high: 50100,
      low: 49900,
      close: 50050,
      volume: 100,
    }

    act(() => {
      capturedCallback?.({ candle: mockCandle })
    })

    await waitFor(() => {
      expect(result.current.candles).toEqual([mockCandle])
      expect(result.current.loading).toBe(false)
    })
  })

  it('appends new candles to existing data', async () => {
    let capturedCallback: ((data: any) => void) | null = null

    mockSubscribe.mockImplementation((event, callback) => {
      capturedCallback = callback
      return vi.fn()
    })

    const { result } = renderHook(() => useMarketData(mockSymbol, mockTimeframe))

    const candle1: Candle = {
      time: Date.now() - 60000,
      open: 49000,
      high: 49100,
      low: 48900,
      close: 49050,
      volume: 50,
    }

    const candle2: Candle = {
      time: Date.now(),
      open: 50000,
      high: 50100,
      low: 49900,
      close: 50050,
      volume: 100,
    }

    act(() => {
      capturedCallback?.({ candle: candle1 })
    })

    act(() => {
      capturedCallback?.({ candle: candle2 })
    })

    await waitFor(() => {
      expect(result.current.candles).toEqual([candle1, candle2])
    })
  })

  it('handles errors gracefully', async () => {
    let capturedCallback: ((data: any) => void) | null = null

    mockSubscribe.mockImplementation((event, callback) => {
      capturedCallback = callback
      return vi.fn()
    })

    const { result } = renderHook(() => useMarketData(mockSymbol, mockTimeframe))

    const errorMessage = 'Failed to fetch market data'

    act(() => {
      capturedCallback?.({ error: errorMessage })
    })

    await waitFor(() => {
      expect(result.current.error).toBe(errorMessage)
      expect(result.current.loading).toBe(false)
    })
  })

  it('resubscribes when symbol or timeframe changes', () => {
    const { rerender } = renderHook(({ symbol, timeframe }) => useMarketData(symbol, timeframe), {
      initialProps: {
        symbol: 'BTCUSDT' as Symbol,
        timeframe: '1m' as Timeframe,
      },
    })

    expect(mockSubscribe).toHaveBeenCalledTimes(1)

    rerender({
      symbol: 'ETHUSDT' as Symbol,
      timeframe: '5m' as Timeframe,
    })

    expect(mockEmit).toHaveBeenCalledWith('unsubscribe', {
      channel: 'candles',
      params: { symbol: 'BTCUSDT', timeframe: '1m' },
    })

    expect(mockEmit).toHaveBeenCalledWith('subscribe', {
      channel: 'candles',
      params: { symbol: 'ETHUSDT', timeframe: '5m' },
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
