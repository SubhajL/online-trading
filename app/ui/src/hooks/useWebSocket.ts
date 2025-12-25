import { useEffect, useState } from 'react'
import { websocketService } from '@/services/websocket'
import type { ConnectionState } from '@/services/websocket.service'

type UseWebSocketReturn = {
  service: typeof websocketService
  connected: boolean
  connecting: boolean
  reconnectAttempts: number
}

/**
 * Hook to access the singleton WebSocket service.
 * Uses a shared connection across all components.
 * The connection is managed by the websocket module - do not disconnect manually.
 */
export function useWebSocket(): UseWebSocketReturn {
  const [connectionState, setConnectionState] = useState<ConnectionState>({
    connected: websocketService.isConnected(),
    connecting: false,
    reconnectAttempts: 0,
  })

  useEffect(() => {
    // Subscribe to connection state changes
    const unsubscribe = websocketService.onConnectionStateChange(setConnectionState)

    return () => {
      unsubscribe()
      // Note: We don't disconnect here - the singleton stays connected
      // for use by other components
    }
  }, [])

  return {
    service: websocketService,
    connected: connectionState.connected,
    connecting: connectionState.connecting,
    reconnectAttempts: connectionState.reconnectAttempts,
  }
}
