import type { Candle } from '@/types'

class MarketDataService {
  async getHistoricalCandles(
    symbol: string,
    timeframe: string,
    startTime: Date,
    endTime: Date,
  ): Promise<Candle[]> {
    // In a real implementation, this would fetch from the BFF API
    // For now, return empty array to satisfy the type checker
    // TODO: Implement API call using these parameters
    void symbol
    void timeframe
    void startTime
    void endTime
    return []
  }
}

export const marketDataService = new MarketDataService()
