import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { useWebSocket } from './useWebSocket'

// Mock the singleton module
const mockOnConnectionStateChange = vi.fn()
const mockIsConnected = vi.fn()

vi.mock('@/services/websocket', () => ({
  websocketService: {
    isConnected: () => mockIsConnected(),
    onConnectionStateChange: (callback: (state: unknown) => void) =>
      mockOnConnectionStateChange(callback),
    connect: vi.fn(),
    disconnect: vi.fn(),
    subscribe: vi.fn(),
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

describe('useWebSocket', () => {
  beforeEach(() => {
    mockIsConnected.mockReturnValue(false)
    mockOnConnectionStateChange.mockImplementation(callback => {
      callback({ connected: false, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('returns connection state from singleton service', () => {
    const { result } = renderHook(() => useWebSocket())

    expect(result.current.connected).toBe(false)
    expect(result.current.connecting).toBe(false)
    expect(result.current.reconnectAttempts).toBe(0)
  })

  it('returns the singleton WebSocket service', () => {
    const { result } = renderHook(() => useWebSocket())

    expect(result.current.service).toBeDefined()
    expect(result.current.service.isConnected).toBeDefined()
    expect(result.current.service.onConnectionStateChange).toBeDefined()
  })

  it('subscribes to connection state changes on mount', () => {
    renderHook(() => useWebSocket())

    expect(mockOnConnectionStateChange).toHaveBeenCalledTimes(1)
    expect(mockOnConnectionStateChange).toHaveBeenCalledWith(expect.any(Function))
  })

  it('unsubscribes from connection state on unmount', () => {
    const mockUnsubscribe = vi.fn()
    mockOnConnectionStateChange.mockImplementation(callback => {
      callback({ connected: false, connecting: false, reconnectAttempts: 0 })
      return mockUnsubscribe
    })

    const { unmount } = renderHook(() => useWebSocket())
    unmount()

    expect(mockUnsubscribe).toHaveBeenCalled()
  })

  it('tracks connection state changes', () => {
    let stateChangeCallback: ((state: unknown) => void) | null = null

    mockOnConnectionStateChange.mockImplementation(callback => {
      stateChangeCallback = callback
      callback({ connected: false, connecting: true, reconnectAttempts: 0 })
      return vi.fn()
    })

    const { result } = renderHook(() => useWebSocket())

    expect(result.current.connected).toBe(false)
    expect(result.current.connecting).toBe(true)

    act(() => {
      stateChangeCallback!({ connected: true, connecting: false, reconnectAttempts: 0 })
    })

    expect(result.current.connected).toBe(true)
    expect(result.current.connecting).toBe(false)
  })

  it('tracks reconnect attempts', () => {
    let stateChangeCallback: ((state: unknown) => void) | null = null

    mockOnConnectionStateChange.mockImplementation(callback => {
      stateChangeCallback = callback
      callback({ connected: false, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })

    const { result } = renderHook(() => useWebSocket())

    expect(result.current.reconnectAttempts).toBe(0)

    act(() => {
      stateChangeCallback!({ connected: false, connecting: true, reconnectAttempts: 3 })
    })

    expect(result.current.reconnectAttempts).toBe(3)
  })

  it('does not disconnect on unmount (singleton pattern)', () => {
    const { unmount, result } = renderHook(() => useWebSocket())

    const disconnectSpy = vi.spyOn(result.current.service, 'disconnect')

    unmount()

    // Singleton should NOT be disconnected when component unmounts
    expect(disconnectSpy).not.toHaveBeenCalled()
  })

  it('initializes with current connection state', () => {
    mockIsConnected.mockReturnValue(true)
    mockOnConnectionStateChange.mockImplementation(callback => {
      callback({ connected: true, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })

    const { result } = renderHook(() => useWebSocket())

    expect(result.current.connected).toBe(true)
  })
})
