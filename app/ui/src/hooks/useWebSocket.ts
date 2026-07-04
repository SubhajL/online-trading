import { useEffect, useState } from 'react'
import { websocketService } from '@/services/websocket'
import type { ConnectionState, WebSocketService } from '@/services/websocket.service'

type UseWebSocketReturn = {
  service: WebSocketService
  connected: boolean
  connecting: boolean
  reconnectAttempts: number
}

/**
 * Hook to access a singleton WebSocket service (the trading socket by
 * default). Uses a shared connection across all components.
 * The connection is managed by the websocket module - do not disconnect manually.
 */
export function useWebSocket(service: WebSocketService = websocketService): UseWebSocketReturn {
  const [connectionState, setConnectionState] = useState<ConnectionState>({
    connected: service.isConnected(),
    connecting: false,
    reconnectAttempts: 0,
  })

  useEffect(() => {
    // Subscribe to connection state changes
    const unsubscribe = service.onConnectionStateChange(setConnectionState)

    return () => {
      unsubscribe()
      // Note: We don't disconnect here - the singleton stays connected
      // for use by other components
    }
  }, [service])

  return {
    service,
    connected: connectionState.connected,
    connecting: connectionState.connecting,
    reconnectAttempts: connectionState.reconnectAttempts,
  }
}
