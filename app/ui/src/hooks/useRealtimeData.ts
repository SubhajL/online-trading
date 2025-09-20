import { useEffect, useState, useRef, useCallback } from 'react'
import { WebSocketService } from '@/services/websocket.service'
import { getWebSocketUrl } from '@/config/constants'
import type { Symbol } from '@/types'

export type Subscription = {
  channel: string
  symbol?: string | Symbol
  onData?: (data: unknown) => void
}

export function useRealtimeData(subscriptions: Subscription[]) {
  const [isConnected, setIsConnected] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const wsRef = useRef<WebSocketService | null>(null)
  const handlersRef = useRef<Map<string, (data: unknown) => void>>(new Map())
  const activeSubscriptionsRef = useRef<Set<string>>(new Set())

  // Initialize WebSocket connection
  useEffect(() => {
    const ws = new WebSocketService()
    wsRef.current = ws

    const connect = async () => {
      try {
        setIsLoading(true)
        setError(null)
        ws.connect(getWebSocketUrl())
        const connected = ws.isConnected()
        setIsConnected(connected)
      } catch (err) {
        setError(err as Error)
      } finally {
        setIsLoading(false)
      }
    }

    connect()

    return () => {
      ws.disconnect()
    }
  }, [])

  // Manage subscriptions
  useEffect(() => {
    if (!wsRef.current || !isConnected) return

    const ws = wsRef.current
    const currentSubscriptions = new Set<string>()
    const newHandlers = new Map<string, (data: unknown) => void>()

    // Process current subscriptions
    subscriptions.forEach(sub => {
      const key = `${sub.channel}:${sub.symbol || 'all'}`
      currentSubscriptions.add(key)

      // Create handler for this subscription
      const handler = (data: unknown) => {
        // Filter by symbol if specified
        if (sub.symbol && (data as { symbol?: string }).symbol && (data as { symbol?: string }).symbol !== sub.symbol) {
          return
        }
        sub.onData?.(data)
      }

      newHandlers.set(key, handler)

      // Subscribe if not already subscribed
      if (!activeSubscriptionsRef.current.has(key)) {
        ws.on(sub.channel, handler)
      }
    })

    // Unsubscribe from removed subscriptions
    activeSubscriptionsRef.current.forEach(key => {
      if (!currentSubscriptions.has(key)) {
        const [channel] = key.split(':')
        const handler = handlersRef.current.get(key)

        if (handler) {
          ws.off(channel!, handler)
        }
      }
    })

    // Update refs
    activeSubscriptionsRef.current = currentSubscriptions
    handlersRef.current = newHandlers

    // Cleanup function
    return () => {
      // This cleanup runs when subscriptions change
      currentSubscriptions.forEach(key => {
        const [channel] = key.split(':')
        const handler = newHandlers.get(key)
        if (handler) {
          ws.off(channel!, handler)
        }
      })
    }
  }, [subscriptions, isConnected])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.disconnect()
      setIsConnected(false)
    }
  }, [])

  const reconnect = useCallback(async () => {
    if (wsRef.current) {
      wsRef.current.disconnect()
      setIsConnected(false)
      setIsLoading(true)
      setError(null)

      try {
        wsRef.current.connect(getWebSocketUrl())
        setIsConnected(wsRef.current.isConnected())
      } catch (err) {
        setError(err as Error)
      } finally {
        setIsLoading(false)
      }
    }
  }, [])

  return {
    isConnected,
    isLoading,
    error,
    disconnect,
    reconnect,
  }
}
