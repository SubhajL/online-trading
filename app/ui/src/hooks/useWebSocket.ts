import { useEffect, useState, useRef } from 'react'
import { WebSocketService } from '@/services/websocket.service'
import type { ConnectionState } from '@/services/websocket.service'
import { getWebSocketUrl } from '@/config/constants'

type UseWebSocketReturn = {
  service: WebSocketService
  connected: boolean
  connecting: boolean
  reconnectAttempts: number
}

export function useWebSocket(url?: string): UseWebSocketReturn {
  const serviceRef = useRef<WebSocketService | null>(null)
  const [connectionState, setConnectionState] = useState<ConnectionState>({
    connected: false,
    connecting: false,
    reconnectAttempts: 0,
  })

  useEffect(() => {
    const wsUrl = url || getWebSocketUrl()

    // Create service if it doesn't exist
    if (!serviceRef.current) {
      serviceRef.current = new WebSocketService()
    }

    const service = serviceRef.current

    // Connect to WebSocket
    service.connect(wsUrl)

    // Subscribe to connection state changes
    const unsubscribe = service.onConnectionStateChange(setConnectionState)

    return () => {
      unsubscribe()
      service.disconnect()
    }
  }, [url])

  return {
    service: serviceRef.current!,
    connected: connectionState.connected,
    connecting: connectionState.connecting,
    reconnectAttempts: connectionState.reconnectAttempts,
  }
}
