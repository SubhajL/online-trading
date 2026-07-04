import { apiClient } from '@/services/api'
import type { Candle } from '@/types'

type CandleRow = {
  openTime?: string
  closeTime?: string
  open_time?: string
  close_time?: string
  open: string | number
  high: string | number
  low: string | number
  close: string | number
  volume: string | number
}

class MarketDataService {
  async getHistoricalCandles(
    symbol: string,
    timeframe: string,
    startTime: Date,
    endTime: Date,
  ): Promise<Candle[]> {
    const params = new URLSearchParams({
      symbol,
      tf: timeframe,
      startTime: startTime.toISOString(),
      endTime: endTime.toISOString(),
      limit: '1000',
    })
    const rows = await apiClient.get<CandleRow[]>(`/market-data/candles?${params.toString()}`)
    return rows
      .map(
        (row: CandleRow): Candle => ({
          time: Date.parse(row.closeTime ?? row.close_time ?? row.openTime ?? row.open_time ?? ''),
          open: Number(row.open),
          high: Number(row.high),
          low: Number(row.low),
          close: Number(row.close),
          volume: Number(row.volume),
        }),
      )
      .filter((candle: Candle) => Number.isFinite(candle.time))
      .sort((a: Candle, b: Candle) => a.time - b.time)
  }
}

export const marketDataService = new MarketDataService()
