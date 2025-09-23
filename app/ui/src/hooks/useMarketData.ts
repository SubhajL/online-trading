import { useState, useEffect } from 'react'
import type { Candle, Symbol, Timeframe, SmcEvent, Zone } from '@/types'
import { useWebSocket } from './useWebSocket'

type MarketDataEvent = {
  candle?: Candle
  error?: string
}

type IndicatorData = {
  time: number
  value: number
}

type Indicators = {
  EMA: IndicatorData[]
  SMA: IndicatorData[]
  RSI: IndicatorData[]
  MACD: IndicatorData[]
  BB: IndicatorData[]
  VOLUME: IndicatorData[]
}

type UseMarketDataReturn = {
  candles: Candle[]
  indicators: Indicators
  smcEvents: SmcEvent[]
  zones: Zone[]
  loading: boolean
  error: string | null
  setTimeframe: (timeframe: Timeframe) => void
  setSymbol: (symbol: Symbol) => void
}

export function useMarketData(symbol: Symbol, timeframe: Timeframe): UseMarketDataReturn {
  const { service, connected } = useWebSocket()
  const [currentSymbol, setCurrentSymbol] = useState<Symbol>(symbol)
  const [currentTimeframe, setCurrentTimeframe] = useState<Timeframe>(timeframe)
  const [candles, setCandles] = useState<Candle[]>([])
  const [indicators, setIndicators] = useState<Indicators>({
    EMA: [],
    SMA: [],
    RSI: [],
    MACD: [],
    BB: [],
    VOLUME: [],
  })
  const [smcEvents, setSmcEvents] = useState<SmcEvent[]>([])
  const [zones, setZones] = useState<Zone[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Update internal state when props change
  useEffect(() => {
    setCurrentSymbol(symbol)
  }, [symbol])

  useEffect(() => {
    setCurrentTimeframe(timeframe)
  }, [timeframe])

  useEffect(() => {
    if (!connected) {
      return
    }

    setLoading(true)
    setError(null)
    setCandles([])
    setIndicators({
      EMA: [],
      SMA: [],
      RSI: [],
      MACD: [],
      BB: [],
      VOLUME: [],
    })
    setSmcEvents([])
    setZones([])

    // Subscribe to all market data channels
    const channels = ['candles', 'indicators', 'smc_events', 'zones']
    channels.forEach(channel => {
      service.emit('subscribe', {
        channel,
        params: { symbol: currentSymbol, timeframe: currentTimeframe },
      })
    })

    // Listen for candle updates
    const unsubscribeCandles = service.subscribe<MarketDataEvent>(
      `candles:${currentSymbol}:${currentTimeframe}`,
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

    // Listen for indicator updates
    const unsubscribeIndicators = service.subscribe<any>(
      `indicators:${currentSymbol}:${currentTimeframe}`,
      data => {
        if (data.error) {
          setError(data.error)
          setLoading(false)
          return
        }

        if (data.type && data.time && data.value !== undefined) {
          setIndicators(prev => ({
            ...prev,
            [data.type]: [...(prev[data.type as keyof Indicators] || []), { time: data.time, value: data.value }],
          }))
          setLoading(false)
        }
      },
    )

    // Listen for SMC events
    const unsubscribeSmcEvents = service.subscribe<SmcEvent>(
      `smc_events:${currentSymbol}:${currentTimeframe}`,
      data => {
        if ('error' in data) {
          setError((data as any).error)
          setLoading(false)
          return
        }

        setSmcEvents(prev => [...prev, data])
        setLoading(false)
      },
    )

    // Listen for zone updates
    const unsubscribeZones = service.subscribe<{ zones?: Zone[]; error?: string }>(
      `zones:${currentSymbol}:${currentTimeframe}`,
      data => {
        if (data.error) {
          setError(data.error)
          setLoading(false)
          return
        }

        if (data.zones) {
          setZones(data.zones)
          setLoading(false)
        }
      },
    )

    // Cleanup
    return () => {
      channels.forEach(channel => {
        service.emit('unsubscribe', {
          channel,
          params: { symbol: currentSymbol, timeframe: currentTimeframe },
        })
      })
      unsubscribeCandles()
      unsubscribeIndicators()
      unsubscribeSmcEvents()
      unsubscribeZones()
    }
  }, [currentSymbol, currentTimeframe, service, connected])

  const setTimeframe = (tf: Timeframe) => {
    setCurrentTimeframe(tf)
  }

  const setSymbol = (sym: Symbol) => {
    setCurrentSymbol(sym)
  }

  return {
    candles,
    indicators,
    smcEvents,
    zones,
    loading,
    error,
    setTimeframe,
    setSymbol,
  }
}
