import type { Brand } from './index'

export type AlertId = Brand<string, 'AlertId'>
export type AlertType = 'order' | 'position' | 'decision' | 'smc' | 'error' | 'info'
export type AlertPriority = 'low' | 'medium' | 'high' | 'critical'

export type Alert = {
  id: AlertId
  type: AlertType
  priority: AlertPriority
  title: string
  message: string
  data?: any
  imageUrl?: string
  read: boolean
  createdAt: string
  updatedAt?: string
}

export type SmcEventType = 'CHOCH' | 'BOS' | 'ORDER_BLOCK' | 'FVG'
export type SmcDirection = 'bullish' | 'bearish'

export type SmcEvent = {
  id: string
  symbol: string
  type: SmcEventType
  direction: SmcDirection
  price: number
  timeframe: string
  timestamp: number
}

export type ZoneType = 'supply' | 'demand'

export type Zone = {
  id: string
  symbol: string
  type: ZoneType
  priceFrom: number
  priceTo: number
  strength: number
  touches: number
  timeframe: string
  created: number
  lastTested?: number
}

export type OrderBlock = Zone & {
  orderType: 'bullish' | 'bearish'
  volume: number
}

export type FairValueGap = {
  id: string
  symbol: string
  priceFrom: number
  priceTo: number
  timestamp: number
  filled: boolean
}

export type AlertFilters = {
  type?: AlertType
  priority?: AlertPriority
  read?: boolean
  fromDate?: string
  toDate?: string
  search?: string
}

export type AlertStats = {
  total: number
  unread: number
  byType: Record<AlertType, number>
  byPriority: Record<AlertPriority, number>
}