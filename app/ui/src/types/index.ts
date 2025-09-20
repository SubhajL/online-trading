// Branded types for type safety
type Brand<K, T> = K & { __brand: T }

export type OrderId = Brand<string, 'OrderId'>
export type Symbol = Brand<string, 'Symbol'>
export type UserId = Brand<string, 'UserId'>

export type OrderSide = 'BUY' | 'SELL'
export type OrderType = 'MARKET' | 'LIMIT' | 'STOP_MARKET' | 'STOP_LIMIT'
export type OrderStatus =
  | 'NEW'
  | 'PARTIALLY_FILLED'
  | 'FILLED'
  | 'CANCELED'
  | 'REJECTED'
  | 'EXPIRED'
export type Venue = 'SPOT' | 'USD_M'
export type Timeframe =
  | '1m'
  | '3m'
  | '5m'
  | '15m'
  | '30m'
  | '1h'
  | '2h'
  | '4h'
  | '6h'
  | '8h'
  | '12h'
  | '1d'
  | '3d'
  | '1w'
  | '1M'

export type Candle = {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type Order = {
  orderId: OrderId
  symbol: Symbol
  side: OrderSide
  type: OrderType
  quantity: number
  price?: number
  stopPrice?: number
  status: OrderStatus
  venue: Venue
  createdAt: string
  updatedAt: string
  executedQuantity?: number
  avgPrice?: number
}

export type Position = {
  symbol: Symbol
  side: OrderSide
  quantity: number
  entryPrice: number
  markPrice: number
  pnl: number
  pnlPercent: number
  venue: Venue
}

export type MarketData = {
  symbol: Symbol
  price: number
  change24h: number
  volume24h: number
  high24h: number
  low24h: number
  timestamp: number
}

export type TechnicalIndicators = {
  ema?: number[]
  rsi?: number
  macd?: {
    macd: number
    signal: number
    histogram: number
  }
  bb?: {
    upper: number
    middle: number
    lower: number
  }
}

export type TradingDecision = {
  symbol: Symbol
  action: 'BUY' | 'SELL' | 'HOLD'
  confidence: number
  entry: number
  stopLoss: number
  takeProfit: number
  quantity: number
  reason: string
  timestamp: number
}

export type TimeFrame = '1m' | '5m' | '15m' | '1h' | '4h' | '1d'
export type ChartType = 'candlestick' | 'line' | 'area'
export type IndicatorType = 'EMA' | 'SMA' | 'RSI' | 'MACD' | 'BB' | 'VOLUME'

export type Indicator = {
  type: IndicatorType
  period?: number
  data: { time: number; value: number }[]
  color?: string
}

export type Balance = {
  asset: string
  free: number
  locked: number
  total: number
  venue: Venue
  usdValue?: number
}

export type OrderFormValues = {
  symbol: string
  side: OrderSide
  type: OrderType
  quantity: number
  price?: number
  stopPrice?: number
}
