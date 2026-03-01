import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { WebSocketService } from './websocket.service'

// Mock socket.io-client
vi.mock('socket.io-client', () => ({
  io: vi.fn(() => ({
    connect: vi.fn(),
    disconnect: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
    emit: vi.fn(),
    connected: false,
  })),
}))

describe('WebSocketService', () => {
  let service: WebSocketService

  beforeEach(() => {
    service = new WebSocketService()
  })

  afterEach(() => {
    service.disconnect()
    vi.clearAllMocks()
  })

  describe('connect', () => {
    it('establishes connection to WebSocket server', () => {
      service.connect('ws://localhost:3000')

      expect(service.isConnected()).toBe(false) // Not connected until connect event
    })

    it('does not create multiple connections when called multiple times', () => {
      service.connect('ws://localhost:3000')
      const firstSocket = service['socket']

      service.connect('ws://localhost:3000')
      const secondSocket = service['socket']

      expect(firstSocket).toBe(secondSocket)
    })

    it('sets up event handlers for connection lifecycle', () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any

      expect(socket.on).toHaveBeenCalledWith('connect', expect.any(Function))
      expect(socket.on).toHaveBeenCalledWith('disconnect', expect.any(Function))
      expect(socket.on).toHaveBeenCalledWith('error', expect.any(Function))
    })
  })

  describe('subscribe', () => {
    it('subscribes to specific events', () => {
      const callback = vi.fn()
      service.connect('ws://localhost:3000')

      const unsubscribe = service.subscribe('test-event', callback)

      expect(unsubscribe).toBeInstanceOf(Function)
    })

    it('calls callback when event is received', () => {
      const callback = vi.fn()
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any

      service.subscribe('test-event', callback)

      // Simulate event
      const onCall = socket.on.mock.calls.find((call: any[]) => call[0] === 'test-event')
      const handler = onCall?.[1]
      handler?.({ data: 'test' })

      expect(callback).toHaveBeenCalledWith({ data: 'test' })
    })

    it('unsubscribes when unsubscribe function is called', () => {
      const callback = vi.fn()
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any

      const unsubscribe = service.subscribe('test-event', callback)
      unsubscribe()

      expect(socket.off).toHaveBeenCalledWith('test-event', expect.any(Function))
    })
  })

  describe('emit', () => {
    it('emits events with data', () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any

      // Simulate connected state
      socket.connected = true

      service.emit('test-event', { data: 'test' })

      expect(socket.emit).toHaveBeenCalledWith('test-event', { data: 'test' })
    })

    it('throws error when not connected', () => {
      expect(() => {
        service.emit('test-event', { data: 'test' })
      }).toThrow('WebSocket is not connected')
    })
  })

  describe('disconnect', () => {
    it('disconnects from WebSocket server', () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any

      service.disconnect()

      expect(socket.disconnect).toHaveBeenCalled()
    })

    it('handles disconnect when not connected', () => {
      expect(() => {
        service.disconnect()
      }).not.toThrow()
    })
  })

  describe('reconnection', () => {
    it('attempts to reconnect on disconnect', () => {
      vi.useFakeTimers()
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any

      // Simulate disconnect
      const disconnectHandler = socket.on.mock.calls.find(
        (call: any[]) => call[0] === 'disconnect',
      )?.[1]

      disconnectHandler?.('transport error')

      expect(service['reconnectAttempts']).toBe(1)

      vi.advanceTimersByTime(3000)

      expect(socket.connect).toHaveBeenCalled()

      vi.useRealTimers()
    })

    it('stops reconnection after max attempts', () => {
      vi.useFakeTimers()
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any

      // Simulate multiple disconnects
      const disconnectHandler = socket.on.mock.calls.find(
        (call: any[]) => call[0] === 'disconnect',
      )?.[1]

      for (let i = 0; i < 11; i++) {
        disconnectHandler?.('transport error')
        vi.advanceTimersByTime(3000)
      }

      expect(service['reconnectAttempts']).toBe(10)

      vi.useRealTimers()
    })
  })

  describe('connection state', () => {
    it('tracks connection state correctly', () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any

      expect(service.isConnected()).toBe(false)

      // Simulate connect event
      const connectHandler = socket.on.mock.calls.find((call: any[]) => call[0] === 'connect')?.[1]

      socket.connected = true
      connectHandler?.()

      expect(service.isConnected()).toBe(true)
    })

    it('emits connection state changes', () => {
      const stateCallback = vi.fn()
      service.onConnectionStateChange(stateCallback)

      service.connect('ws://localhost:3000')

      expect(stateCallback).toHaveBeenCalledWith({
        connected: false,
        connecting: true,
        reconnectAttempts: 0,
      })
    })
  })

  describe('emitWithAck', () => {
    it('resolves with response when success is true', async () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any
      socket.connected = true

      const orderData = { orderId: 'order-123', status: 'NEW' }
      const response = { success: true, data: orderData }

      socket.timeout = vi.fn().mockReturnValue({
        emit: vi.fn(
          (_event: string, _data: unknown, callback: (err: Error | null, res: unknown) => void) => {
            callback(null, response)
          },
        ),
      })

      const result = await service.emitWithAck('placeOrder', { symbol: 'BTCUSDT' })

      expect(result).toEqual(response)
      expect(result.data).toEqual(orderData)
    })

    it('rejects with error when success is false', async () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any
      socket.connected = true

      const response = { success: false, error: 'Insufficient balance' }

      socket.timeout = vi.fn().mockReturnValue({
        emit: vi.fn(
          (_event: string, _data: unknown, callback: (err: Error | null, res: unknown) => void) => {
            callback(null, response)
          },
        ),
      })

      await expect(service.emitWithAck('placeOrder', { symbol: 'BTCUSDT' })).rejects.toThrow(
        'Insufficient balance',
      )
    })

    it('rejects on socket timeout', async () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any
      socket.connected = true

      socket.timeout = vi.fn().mockReturnValue({
        emit: vi.fn(
          (_event: string, _data: unknown, callback: (err: Error | null, res: unknown) => void) => {
            callback(new Error('operation has timed out'), null)
          },
        ),
      })

      await expect(service.emitWithAck('placeOrder', { symbol: 'BTCUSDT' }, 1000)).rejects.toThrow(
        'operation has timed out',
      )
    })

    it('throws when socket is not connected', async () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any
      socket.connected = false

      await expect(service.emitWithAck('placeOrder', { symbol: 'BTCUSDT' })).rejects.toThrow(
        'WebSocket is not connected',
      )
    })

    it('throws when socket is null', async () => {
      await expect(service.emitWithAck('placeOrder', { symbol: 'BTCUSDT' })).rejects.toThrow(
        'WebSocket is not connected',
      )
    })

    it('uses default timeout of 10000ms', async () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any
      socket.connected = true

      const response = { success: true, data: {} }

      socket.timeout = vi.fn().mockReturnValue({
        emit: vi.fn(
          (_event: string, _data: unknown, callback: (err: Error | null, res: unknown) => void) => {
            callback(null, response)
          },
        ),
      })

      await service.emitWithAck('placeOrder', { symbol: 'BTCUSDT' })

      expect(socket.timeout).toHaveBeenCalledWith(10000)
    })

    it('uses custom timeout when provided', async () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any
      socket.connected = true

      const response = { success: true, data: {} }

      socket.timeout = vi.fn().mockReturnValue({
        emit: vi.fn(
          (_event: string, _data: unknown, callback: (err: Error | null, res: unknown) => void) => {
            callback(null, response)
          },
        ),
      })

      await service.emitWithAck('placeOrder', { symbol: 'BTCUSDT' }, 5000)

      expect(socket.timeout).toHaveBeenCalledWith(5000)
    })
  })

  describe('isReady', () => {
    it('returns true when socket is connected', () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any
      socket.connected = true

      expect(service.isReady()).toBe(true)
    })

    it('returns false when socket is not connected', () => {
      service.connect('ws://localhost:3000')
      const socket = service['socket'] as any
      socket.connected = false

      expect(service.isReady()).toBe(false)
    })

    it('returns false when socket is null', () => {
      expect(service.isReady()).toBe(false)
    })
  })
})
