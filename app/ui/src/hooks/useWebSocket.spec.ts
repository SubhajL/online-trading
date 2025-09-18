import { renderHook, act } from '@testing-library/react'
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { useWebSocket } from './useWebSocket'
import { WebSocketService } from '@/services/websocket.service'

vi.mock('@/services/websocket.service')

describe('useWebSocket', () => {
  let mockService: WebSocketService

  beforeEach(() => {
    mockService = new WebSocketService()
    vi.mocked(WebSocketService).mockImplementation(() => mockService)

    // Setup default mock implementations
    mockService.connect = vi.fn()
    mockService.disconnect = vi.fn()
    mockService.isConnected = vi.fn().mockReturnValue(false)
    mockService.onConnectionStateChange = vi.fn().mockImplementation(callback => {
      callback({ connected: false, connecting: false, reconnectAttempts: 0 })
      return vi.fn()
    })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('connects to WebSocket on mount', () => {
    const { result } = renderHook(() => useWebSocket())

    expect(mockService.connect).toHaveBeenCalledWith('ws://localhost:3000')
    expect(result.current.connected).toBe(false)
    expect(result.current.connecting).toBe(false)
  })

  it('disconnects on unmount', () => {
    const { unmount } = renderHook(() => useWebSocket())

    unmount()

    expect(mockService.disconnect).toHaveBeenCalled()
  })

  it('tracks connection state changes', () => {
    let stateChangeCallback: any

    mockService.onConnectionStateChange = vi.fn().mockImplementation(callback => {
      stateChangeCallback = callback
      callback({ connected: false, connecting: true, reconnectAttempts: 0 })
      return vi.fn()
    })

    const { result } = renderHook(() => useWebSocket())

    expect(result.current.connected).toBe(false)
    expect(result.current.connecting).toBe(true)

    act(() => {
      stateChangeCallback({ connected: true, connecting: false, reconnectAttempts: 0 })
    })

    expect(result.current.connected).toBe(true)
    expect(result.current.connecting).toBe(false)
  })

  it('returns the WebSocket service instance', () => {
    const { result } = renderHook(() => useWebSocket())

    expect(result.current.service).toBe(mockService)
  })

  it('reconnects when URL changes', () => {
    const { rerender } = renderHook(({ url }) => useWebSocket(url), {
      initialProps: { url: 'ws://localhost:3000' },
    })

    expect(mockService.connect).toHaveBeenCalledWith('ws://localhost:3000')
    expect(mockService.connect).toHaveBeenCalledTimes(1)

    rerender({ url: 'ws://localhost:4000' })

    expect(mockService.disconnect).toHaveBeenCalled()
    expect(mockService.connect).toHaveBeenCalledWith('ws://localhost:4000')
    expect(mockService.connect).toHaveBeenCalledTimes(2)
  })

  it('uses default URL from constants when not provided', () => {
    renderHook(() => useWebSocket())

    expect(mockService.connect).toHaveBeenCalledWith('ws://localhost:3000')
  })

  it('uses custom URL when provided', () => {
    renderHook(() => useWebSocket('wss://custom.server.com'))

    expect(mockService.connect).toHaveBeenCalledWith('wss://custom.server.com')
  })
})
