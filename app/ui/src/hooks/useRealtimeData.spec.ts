import { renderHook, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useRealtimeData } from './useRealtimeData'
import { WebSocketService } from '@/services/websocket.service'

// Mock WebSocketService
vi.mock('@/services/websocket.service')

describe('useRealtimeData', () => {
  let mockWebSocketService: any

  beforeEach(() => {
    mockWebSocketService = {
      connect: vi.fn().mockImplementation(async () => {
        mockWebSocketService.isConnected.mockReturnValue(true)
      }),
      disconnect: vi.fn(),
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
      on: vi.fn(),
      off: vi.fn(),
      isConnected: vi.fn().mockReturnValue(false),
    }

    vi.mocked(WebSocketService).mockImplementation(() => mockWebSocketService)
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('connects to WebSocket on mount', async () => {
    renderHook(() => useRealtimeData([]))

    await waitFor(() => {
      expect(mockWebSocketService.connect).toHaveBeenCalled()
    })
  })

  it('disconnects from WebSocket on unmount', async () => {
    const { unmount } = renderHook(() => useRealtimeData([]))

    await waitFor(() => {
      expect(mockWebSocketService.connect).toHaveBeenCalled()
    })

    unmount()

    expect(mockWebSocketService.disconnect).toHaveBeenCalled()
  })

  it('subscribes to specified channels', async () => {
    const subscriptions = [
      { channel: 'ticker', symbol: 'BTCUSDT' },
      { channel: 'depth', symbol: 'ETHUSDT' },
    ]

    renderHook(() => useRealtimeData(subscriptions))

    await waitFor(() => {
      expect(mockWebSocketService.subscribe).toHaveBeenCalledWith('ticker', {
        symbol: 'BTCUSDT',
      })
      expect(mockWebSocketService.subscribe).toHaveBeenCalledWith('depth', {
        symbol: 'ETHUSDT',
      })
    })
  })

  it('handles data updates', async () => {
    const onData = vi.fn()
    const subscription = {
      channel: 'ticker',
      symbol: 'BTCUSDT',
      onData,
    }

    // Set up event handler mock
    mockWebSocketService.on.mockImplementation((event: string, handler: any) => {
      if (event === 'ticker') {
        // Simulate data coming in
        setTimeout(() => {
          handler({
            symbol: 'BTCUSDT',
            price: '42000',
            volume: '1000',
          })
        }, 100)
      }
    })

    renderHook(() => useRealtimeData([subscription]))

    await waitFor(() => {
      expect(onData).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        price: '42000',
        volume: '1000',
      })
    })
  })

  it('returns connection state', async () => {
    const { result } = renderHook(() => useRealtimeData([]))

    // Initially should be false and loading
    expect(result.current.isConnected).toBe(false)
    expect(result.current.isLoading).toBe(true)

    // Wait for connection to complete
    await waitFor(() => {
      expect(result.current.isConnected).toBe(true)
      expect(result.current.isLoading).toBe(false)
    })
  })

  it('returns error state', async () => {
    const error = new Error('Connection failed')
    mockWebSocketService.connect.mockRejectedValueOnce(error)

    const { result } = renderHook(() => useRealtimeData([]))

    await waitFor(() => {
      expect(result.current.error).toEqual(error)
    })
  })

  it('returns loading state', async () => {
    const { result } = renderHook(() => useRealtimeData([]))

    expect(result.current.isLoading).toBe(true)

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })
  })

  it('handles subscription changes', async () => {
    const { rerender } = renderHook(
      ({ subscriptions }) => useRealtimeData(subscriptions),
      {
        initialProps: {
          subscriptions: [{ channel: 'ticker', symbol: 'BTCUSDT' }],
        },
      }
    )

    await waitFor(() => {
      expect(mockWebSocketService.subscribe).toHaveBeenCalledWith('ticker', {
        symbol: 'BTCUSDT',
      })
    })

    // Change subscriptions
    rerender({
      subscriptions: [{ channel: 'depth', symbol: 'ETHUSDT' }],
    })

    await waitFor(() => {
      expect(mockWebSocketService.unsubscribe).toHaveBeenCalledWith('ticker', {
        symbol: 'BTCUSDT',
      })
      expect(mockWebSocketService.subscribe).toHaveBeenCalledWith('depth', {
        symbol: 'ETHUSDT',
      })
    })
  })

  it('cleans up event listeners on unmount', async () => {
    const subscription = {
      channel: 'ticker',
      symbol: 'BTCUSDT',
      onData: vi.fn(),
    }

    const { unmount } = renderHook(() => useRealtimeData([subscription]))

    await waitFor(() => {
      expect(mockWebSocketService.on).toHaveBeenCalled()
    })

    unmount()

    expect(mockWebSocketService.off).toHaveBeenCalledWith('ticker', expect.any(Function))
  })

  it('handles multiple subscriptions to same channel', async () => {
    const onDataBTC = vi.fn()
    const onDataETH = vi.fn()

    const subscriptions = [
      { channel: 'ticker', symbol: 'BTCUSDT', onData: onDataBTC },
      { channel: 'ticker', symbol: 'ETHUSDT', onData: onDataETH },
    ]

    mockWebSocketService.on.mockImplementation((event: string, handler: any) => {
      if (event === 'ticker') {
        setTimeout(() => {
          handler({ symbol: 'BTCUSDT', price: '42000' })
          handler({ symbol: 'ETHUSDT', price: '2500' })
        }, 100)
      }
    })

    renderHook(() => useRealtimeData(subscriptions))

    await waitFor(() => {
      expect(onDataBTC).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        price: '42000',
      })
      expect(onDataETH).toHaveBeenCalledWith({
        symbol: 'ETHUSDT',
        price: '2500',
      })
    })
  })

  it('handles reconnection', async () => {
    const { result } = renderHook(() => useRealtimeData([]))

    await waitFor(() => {
      expect(mockWebSocketService.connect).toHaveBeenCalledTimes(1)
    })

    // Simulate reconnect
    await act(async () => {
      await result.current.reconnect()
    })

    expect(mockWebSocketService.disconnect).toHaveBeenCalled()
    expect(mockWebSocketService.connect).toHaveBeenCalledTimes(2)
  })

  it('provides manual disconnect method', async () => {
    const { result } = renderHook(() => useRealtimeData([]))

    await waitFor(() => {
      expect(mockWebSocketService.connect).toHaveBeenCalled()
    })

    act(() => {
      result.current.disconnect()
    })

    expect(mockWebSocketService.disconnect).toHaveBeenCalled()
  })

  it('filters data by symbol when onData provided', async () => {
    const onDataBTC = vi.fn()

    const subscription = {
      channel: 'ticker',
      symbol: 'BTCUSDT',
      onData: onDataBTC,
    }

    mockWebSocketService.on.mockImplementation((event: string, handler: any) => {
      if (event === 'ticker') {
        setTimeout(() => {
          // Send data for multiple symbols
          handler({ symbol: 'BTCUSDT', price: '42000' })
          handler({ symbol: 'ETHUSDT', price: '2500' })
        }, 100)
      }
    })

    renderHook(() => useRealtimeData([subscription]))

    await waitFor(() => {
      // Should only receive BTC data
      expect(onDataBTC).toHaveBeenCalledWith({
        symbol: 'BTCUSDT',
        price: '42000',
      })
      expect(onDataBTC).not.toHaveBeenCalledWith({
        symbol: 'ETHUSDT',
        price: '2500',
      })
    })
  })
})