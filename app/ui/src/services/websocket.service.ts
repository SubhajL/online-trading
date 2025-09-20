import { io, type Socket } from 'socket.io-client'
import { MAX_RECONNECT_ATTEMPTS, RECONNECT_INTERVAL } from '@/config/constants'

export type ConnectionState = {
  connected: boolean
  connecting: boolean
  reconnectAttempts: number
}

type ConnectionStateCallback = (state: ConnectionState) => void

export class WebSocketService {
  private socket: Socket | null = null
  private reconnectAttempts = 0
  private reconnectTimer: NodeJS.Timeout | null = null
  private connectionStateCallbacks: ConnectionStateCallback[] = []
  private url = ''

  connect(url: string): void {
    if (this.socket) {
      return
    }

    this.url = url
    this.emitConnectionState({ connected: false, connecting: true, reconnectAttempts: 0 })

    this.socket = io(url, {
      autoConnect: true,
      reconnection: false, // We handle reconnection manually
    })

    this.setupEventHandlers()
  }

  disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }

    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }

    this.reconnectAttempts = 0
    this.emitConnectionState({ connected: false, connecting: false, reconnectAttempts: 0 })
  }

  subscribe<T = unknown>(event: string, callback: (data: T) => void): () => void {
    if (!this.socket) {
      throw new Error('WebSocket is not connected')
    }

    const handler = (data: T) => callback(data)
    this.socket.on(event, handler)

    return () => {
      this.socket?.off(event, handler)
    }
  }

  emit<T = unknown>(event: string, data: T): void {
    if (!this.socket || !this.socket.connected) {
      throw new Error('WebSocket is not connected')
    }

    this.socket.emit(event, data)
  }

  on<T = unknown>(event: string, callback: (data: T) => void): void {
    if (!this.socket) {
      throw new Error('WebSocket is not connected')
    }

    this.socket.on(event, callback)
  }

  off<T = unknown>(event: string, callback: (data: T) => void): void {
    if (!this.socket) {
      return
    }

    this.socket.off(event, callback)
  }

  unsubscribe(event: string): void {
    if (!this.socket) {
      return
    }

    this.socket.off(event)
  }

  isConnected(): boolean {
    return this.socket?.connected ?? false
  }

  onConnectionStateChange(callback: ConnectionStateCallback): () => void {
    this.connectionStateCallbacks.push(callback)

    // Emit current state immediately
    callback({
      connected: this.isConnected(),
      connecting: !!this.socket && !this.isConnected(),
      reconnectAttempts: this.reconnectAttempts,
    })

    return () => {
      const index = this.connectionStateCallbacks.indexOf(callback)
      if (index > -1) {
        this.connectionStateCallbacks.splice(index, 1)
      }
    }
  }

  private setupEventHandlers(): void {
    if (!this.socket) return

    this.socket.on('connect', () => {
      this.reconnectAttempts = 0
      this.emitConnectionState({ connected: true, connecting: false, reconnectAttempts: 0 })
    })

    this.socket.on('disconnect', (reason: string) => {
      this.emitConnectionState({
        connected: false,
        connecting: false,
        reconnectAttempts: this.reconnectAttempts,
      })

      if (reason !== 'io client disconnect') {
        this.attemptReconnect()
      }
    })

    this.socket.on('error', (error: Error) => {
      console.error('WebSocket error:', error)
    })
  }

  private attemptReconnect(): void {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      console.error('Max reconnection attempts reached')
      return
    }

    this.reconnectAttempts++

    this.reconnectTimer = setTimeout(() => {
      this.emitConnectionState({
        connected: false,
        connecting: true,
        reconnectAttempts: this.reconnectAttempts,
      })

      this.socket?.connect()
    }, RECONNECT_INTERVAL)
  }

  private emitConnectionState(state: ConnectionState): void {
    this.connectionStateCallbacks.forEach(callback => callback(state))
  }
}
