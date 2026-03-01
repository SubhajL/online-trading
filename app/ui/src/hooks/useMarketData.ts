import { useState, useEffect } from 'react'
import type { Candle, Symbol, Timeframe, SmcEvent, Zone } from '@/types'
import { useWebSocket } from './useWebSocket'

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

type CandlesV1 = {
  symbol: string
  timeframe: string
  open_time: string
  close_time: string
  open: string
  high: string
  low: string
  close: string
  volume: string
}

type FeaturesV1 = {
  symbol: string
  timeframe: string
  close_time: string
  ema_short: number | null
  ema_long: number | null
  rsi: number | null
  macd: number | null
  bb_middle: number | null
  volume_ma: number | null
}

type SmcEventsV1 = {
  symbol: string
  timeframe: string
  event_time: string
  event_type: 'choch' | 'bos'
  direction: 'bullish' | 'bearish'
  price_level: string
}

type ZonesV1 = {
  symbol: string
  timeframe: string
  zone_id: string
  direction: 'demand' | 'supply'
  upper_bound: string
  lower_bound: string
  created_time: string
  strength: number
  touches: number
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

    service.emit('subscribe', { symbol: currentSymbol, timeframe: currentTimeframe })

    // Listen for candle updates
    const unsubscribeCandles = service.subscribe<CandlesV1>('candles.v1', data => {
      if (data.symbol !== currentSymbol || data.timeframe !== currentTimeframe) return
      setCandles(prev => [
        ...prev,
        {
          time: Date.parse(data.close_time),
          open: Number(data.open),
          high: Number(data.high),
          low: Number(data.low),
          close: Number(data.close),
          volume: Number(data.volume),
        },
      ])
      setLoading(false)
    })

    // Listen for indicator updates
    const unsubscribeFeatures = service.subscribe<FeaturesV1>('features.v1', data => {
      if (data.symbol !== currentSymbol || data.timeframe !== currentTimeframe) return
      const time = Date.parse(data.close_time)

      setIndicators(prev => ({
        ...prev,
        EMA: data.ema_short === null ? prev.EMA : [...prev.EMA, { time, value: data.ema_short }],
        RSI: data.rsi === null ? prev.RSI : [...prev.RSI, { time, value: data.rsi }],
        MACD: data.macd === null ? prev.MACD : [...prev.MACD, { time, value: data.macd }],
        BB: data.bb_middle === null ? prev.BB : [...prev.BB, { time, value: data.bb_middle }],
        VOLUME:
          data.volume_ma === null ? prev.VOLUME : [...prev.VOLUME, { time, value: data.volume_ma }],
      }))
      setLoading(false)
    })

    // Listen for SMC events
    const unsubscribeSmcEvents = service.subscribe<SmcEventsV1>('smc_events.v1', data => {
      if (data.symbol !== currentSymbol || data.timeframe !== currentTimeframe) return
      setSmcEvents(prev => [
        ...prev,
        {
          id: `${data.event_type}:${data.event_time}:${data.price_level}`,
          symbol: data.symbol,
          type: data.event_type === 'choch' ? 'CHOCH' : 'BOS',
          direction: data.direction,
          price: Number(data.price_level),
          timeframe: data.timeframe,
          timestamp: Date.parse(data.event_time),
        },
      ])
      setLoading(false)
    })

    // Listen for zone updates
    const unsubscribeZones = service.subscribe<ZonesV1>('zones.v1', data => {
      if (data.symbol !== currentSymbol || data.timeframe !== currentTimeframe) return
      setZones(prev => [
        ...prev,
        {
          id: data.zone_id,
          symbol: data.symbol,
          type: data.direction,
          priceFrom: Number(data.lower_bound),
          priceTo: Number(data.upper_bound),
          strength: data.strength,
          touches: data.touches,
          timeframe: data.timeframe,
          created: Date.parse(data.created_time),
        },
      ])
      setLoading(false)
    })

    // Cleanup
    return () => {
      service.emit('unsubscribe', { symbol: currentSymbol, timeframe: currentTimeframe })
      unsubscribeCandles()
      unsubscribeFeatures()
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
