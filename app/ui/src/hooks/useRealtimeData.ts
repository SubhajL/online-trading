import { useEffect, useState, useRef, useCallback } from 'react'
import { websocketService } from '@/services/websocket'
import type { Symbol } from '@/types'

export type Subscription = {
  channel: string
  symbol?: string | Symbol
  onData?: (data: unknown) => void
}

/**
 * Hook for managing real-time data subscriptions.
 * Uses the singleton WebSocket service for shared connection.
 */
export function useRealtimeData(subscriptions: Subscription[]) {
  const [isConnected, setIsConnected] = useState(websocketService.isConnected())
  const [isLoading, setIsLoading] = useState(!websocketService.isConnected())
  const [error, setError] = useState<Error | null>(null)
  const handlersRef = useRef<Map<string, (data: unknown) => void>>(new Map())
  const activeSubscriptionsRef = useRef<Set<string>>(new Set())

  // Subscribe to connection state changes from singleton
  useEffect(() => {
    const unsubscribe = websocketService.onConnectionStateChange(state => {
      setIsConnected(state.connected)
      setIsLoading(state.connecting)
      if (!state.connected && !state.connecting && state.reconnectAttempts > 0) {
        setError(new Error('Connection lost'))
      } else if (state.connected) {
        setError(null)
      }
    })

    return () => {
      unsubscribe()
    }
  }, [])

  // Manage subscriptions
  useEffect(() => {
    if (!isConnected) return

    const currentSubscriptions = new Set<string>()
    const newHandlers = new Map<string, (data: unknown) => void>()

    // Process current subscriptions
    subscriptions.forEach(sub => {
      const key = `${sub.channel}:${sub.symbol || 'all'}`
      currentSubscriptions.add(key)

      // Create handler for this subscription
      const handler = (data: unknown) => {
        // Filter by symbol if specified
        if (
          sub.symbol &&
          (data as { symbol?: string }).symbol &&
          (data as { symbol?: string }).symbol !== sub.symbol
        ) {
          return
        }
        sub.onData?.(data)
      }

      newHandlers.set(key, handler)

      // Subscribe if not already subscribed
      if (!activeSubscriptionsRef.current.has(key)) {
        websocketService.on(sub.channel, handler)
      }
    })

    // Unsubscribe from removed subscriptions
    activeSubscriptionsRef.current.forEach(key => {
      if (!currentSubscriptions.has(key)) {
        const [channel] = key.split(':')
        const handler = handlersRef.current.get(key)

        if (handler) {
          websocketService.off(channel!, handler)
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
          websocketService.off(channel!, handler)
        }
      })
    }
  }, [subscriptions, isConnected])

  // Note: These don't disconnect/reconnect the singleton - they just update local state
  // In a real implementation, you might want to trigger a reconnect via the service
  const disconnect = useCallback(() => {
    // Just update local state - don't actually disconnect the singleton
    // as other components may be using it
    setIsConnected(false)
  }, [])

  const reconnect = useCallback(() => {
    // Trigger reconnection via the service's reconnectWithAuth
    websocketService.reconnectWithAuth()
  }, [])

  return {
    isConnected,
    isLoading,
    error,
    disconnect,
    reconnect,
  }
}
