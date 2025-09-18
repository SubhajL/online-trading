import { useState, useEffect } from 'react'
import type { Candle, Symbol, Timeframe } from '@/types'
import { useWebSocket } from './useWebSocket'

type MarketDataEvent = {
  candle?: Candle
  error?: string
}

type UseMarketDataReturn = {
  candles: Candle[]
  loading: boolean
  error: string | null
}

export function useMarketData(symbol: Symbol, timeframe: Timeframe): UseMarketDataReturn {
  const { service, connected } = useWebSocket()
  const [candles, setCandles] = useState<Candle[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!connected) {
      return
    }

    setLoading(true)
    setError(null)
    setCandles([])

    // Subscribe to market data
    service.emit('subscribe', {
      channel: 'candles',
      params: { symbol, timeframe },
    })

    // Listen for candle updates
    const unsubscribe = service.subscribe<MarketDataEvent>(
      `candles:${symbol}:${timeframe}`,
      data => {
        if (data.error) {
          setError(data.error)
          setLoading(false)
          return
        }

        if (data.candle) {
          setCandles(prev => [...prev, data.candle!])
          setLoading(false)
        }
      },
    )

    // Cleanup
    return () => {
      service.emit('unsubscribe', {
        channel: 'candles',
        params: { symbol, timeframe },
      })
      unsubscribe()
    }
  }, [symbol, timeframe, service, connected])

  return {
    candles,
    loading,
    error,
  }
}
