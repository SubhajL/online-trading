import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useRealtimeData } from './useRealtimeData'

// Mock the singleton module
const mockOnConnectionStateChange = vi.fn()
const mockIsConnected = vi.fn()
const mockOn = vi.fn()
const mockOff = vi.fn()
const mockReconnectWithAuth = vi.fn()

vi.mock('@/services/websocket', () => ({
  websocketService: {
    isConnected: () => mockIsConnected(),
    onConnectionStateChange: (callback: (state: unknown) => void) =>
      mockOnConnectionStateChange(callback),
    on: (event: string, handler: (data: unknown) => void) => mockOn(event, handler),
    off: (event: string, handler: (data: unknown) => void) => mockOff(event, handler),
    reconnectWithAuth: () => mockReconnectWithAuth(),
  },
}))

describe('useRealtimeData', () => {
  let connectionStateCallback: ((state: unknown) => void) | null = null

  beforeEach(() => {
    mockIsConnected.mockReturnValue(false)
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: false, connecting: true, reconnectAttempts: 0 })
      return vi.fn()
    })
    mockOn.mockClear()
    mockOff.mockClear()
  })

  afterEach(() => {
    vi.clearAllMocks()
    connectionStateCallback = null
  })

  it('subscribes to connection state on mount', () => {
    renderHook(() => useRealtimeData([]))

    expect(mockOnConnectionStateChange).toHaveBeenCalledTimes(1)
  })

  it('unsubscribes from connection state on unmount', () => {
    const mockUnsubscribe = vi.fn()
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: false, connecting: true, reconnectAttempts: 0 })
      return mockUnsubscribe
    })

    const { unmount } = renderHook(() => useRealtimeData([]))
    unmount()

    expect(mockUnsubscribe).toHaveBeenCalled()
  })

  it('sets up event handlers when connected', async () => {
    mockIsConnected.mockReturnValue(true)
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: true, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })

    const subscriptions = [
      { channel: 'ticker', symbol: 'BTCUSDT' },
      { channel: 'depth', symbol: 'ETHUSDT' },
    ]

    renderHook(() => useRealtimeData(subscriptions))

    await waitFor(() => {
      expect(mockOn).toHaveBeenCalledWith('ticker', expect.any(Function))
      expect(mockOn).toHaveBeenCalledWith('depth', expect.any(Function))
    })
  })

  it('handles data updates with symbol filtering', async () => {
    const onData = vi.fn()
    mockIsConnected.mockReturnValue(true)
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: true, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })

    let tickerHandler: ((data: unknown) => void) | null = null
    mockOn.mockImplementation((event: string, handler: (data: unknown) => void) => {
      if (event === 'ticker') {
        tickerHandler = handler
      }
    })

    const subscription = {
      channel: 'ticker',
      symbol: 'BTCUSDT',
      onData,
    }

    renderHook(() => useRealtimeData([subscription]))

    await waitFor(() => {
      expect(tickerHandler).not.toBeNull()
    })

    // Simulate data coming in
    act(() => {
      tickerHandler!({ symbol: 'BTCUSDT', price: '42000' })
      tickerHandler!({ symbol: 'ETHUSDT', price: '2500' }) // Should be filtered out
    })

    expect(onData).toHaveBeenCalledWith({ symbol: 'BTCUSDT', price: '42000' })
    expect(onData).not.toHaveBeenCalledWith({ symbol: 'ETHUSDT', price: '2500' })
  })

  it('returns connection state from singleton', async () => {
    mockIsConnected.mockReturnValue(false)
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: false, connecting: true, reconnectAttempts: 0 })
      return vi.fn()
    })

    const { result } = renderHook(() => useRealtimeData([]))

    expect(result.current.isConnected).toBe(false)
    expect(result.current.isLoading).toBe(true)

    // Simulate connection established
    act(() => {
      connectionStateCallback!({ connected: true, connecting: false, reconnectAttempts: 0 })
    })

    expect(result.current.isConnected).toBe(true)
    expect(result.current.isLoading).toBe(false)
  })

  it('sets error on connection loss', async () => {
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: true, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })

    const { result } = renderHook(() => useRealtimeData([]))

    expect(result.current.error).toBeNull()

    // Simulate connection lost with reconnect attempts
    act(() => {
      connectionStateCallback!({ connected: false, connecting: false, reconnectAttempts: 1 })
    })

    expect(result.current.error).toEqual(new Error('Connection lost'))
  })

  it('clears error on reconnection', async () => {
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: false, connecting: false, reconnectAttempts: 1 })
      return vi.fn()
    })

    const { result } = renderHook(() => useRealtimeData([]))

    expect(result.current.error).toEqual(new Error('Connection lost'))

    // Simulate reconnection
    act(() => {
      connectionStateCallback!({ connected: true, connecting: false, reconnectAttempts: 0 })
    })

    expect(result.current.error).toBeNull()
  })

  it('handles subscription changes', async () => {
    mockIsConnected.mockReturnValue(true)
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: true, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })

    const { rerender } = renderHook(({ subscriptions }) => useRealtimeData(subscriptions), {
      initialProps: {
        subscriptions: [{ channel: 'ticker', symbol: 'BTCUSDT' }],
      },
    })

    await waitFor(() => {
      expect(mockOn).toHaveBeenCalledWith('ticker', expect.any(Function))
    })

    // Change subscriptions
    rerender({
      subscriptions: [{ channel: 'depth', symbol: 'ETHUSDT' }],
    })

    await waitFor(() => {
      expect(mockOff).toHaveBeenCalledWith('ticker', expect.any(Function))
      expect(mockOn).toHaveBeenCalledWith('depth', expect.any(Function))
    })
  })

  it('cleans up event listeners on unmount', async () => {
    mockIsConnected.mockReturnValue(true)
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: true, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })

    const subscription = {
      channel: 'ticker',
      symbol: 'BTCUSDT',
      onData: vi.fn(),
    }

    const { unmount } = renderHook(() => useRealtimeData([subscription]))

    await waitFor(() => {
      expect(mockOn).toHaveBeenCalled()
    })

    unmount()

    expect(mockOff).toHaveBeenCalledWith('ticker', expect.any(Function))
  })

  it('calls reconnectWithAuth on reconnect', async () => {
    const { result } = renderHook(() => useRealtimeData([]))

    act(() => {
      result.current.reconnect()
    })

    expect(mockReconnectWithAuth).toHaveBeenCalled()
  })

  it('updates local isConnected state on disconnect', async () => {
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: true, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })

    const { result } = renderHook(() => useRealtimeData([]))

    expect(result.current.isConnected).toBe(true)

    act(() => {
      result.current.disconnect()
    })

    expect(result.current.isConnected).toBe(false)
  })

  it('handles multiple subscriptions to same channel with different symbols', async () => {
    const onDataBTC = vi.fn()
    const onDataETH = vi.fn()

    mockIsConnected.mockReturnValue(true)
    mockOnConnectionStateChange.mockImplementation(callback => {
      connectionStateCallback = callback
      callback({ connected: true, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })

    const handlers: ((data: unknown) => void)[] = []
    mockOn.mockImplementation((_event: string, handler: (data: unknown) => void) => {
      handlers.push(handler)
    })

    const subscriptions = [
      { channel: 'ticker', symbol: 'BTCUSDT', onData: onDataBTC },
      { channel: 'ticker', symbol: 'ETHUSDT', onData: onDataETH },
    ]

    renderHook(() => useRealtimeData(subscriptions))

    await waitFor(() => {
      expect(handlers.length).toBe(2)
    })

    // Simulate data coming in to all handlers
    act(() => {
      handlers.forEach(handler => {
        handler({ symbol: 'BTCUSDT', price: '42000' })
        handler({ symbol: 'ETHUSDT', price: '2500' })
      })
    })

    // BTC handler should only receive BTC data
    expect(onDataBTC).toHaveBeenCalledWith({ symbol: 'BTCUSDT', price: '42000' })
    expect(onDataBTC).not.toHaveBeenCalledWith({ symbol: 'ETHUSDT', price: '2500' })

    // ETH handler should only receive ETH data
    expect(onDataETH).toHaveBeenCalledWith({ symbol: 'ETHUSDT', price: '2500' })
    expect(onDataETH).not.toHaveBeenCalledWith({ symbol: 'BTCUSDT', price: '42000' })
  })
})
