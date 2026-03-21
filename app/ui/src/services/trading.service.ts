import type { Order, Position, OrderId, Symbol, Venue, OrderSide, OrderType } from '@/types'
import type { ApiClient } from './api.client'

export type PlaceOrderRequest = {
  symbol: Symbol
  side: OrderSide
  type: OrderType
  quantity: number
  price?: number
  stopPrice?: number
  stopLossPrice?: number
  takeProfitPrice?: number
  venue: Venue
}

export type CancelOrderRequest = {
  symbol: Symbol
  venue: Venue
}

export type AutoTradingResponse = {
  enabled: boolean
  message: string
}

export type AutoTradingStatus = {
  enabled: boolean
}

type BffPosition = {
  symbol: Symbol
  side: Position['side']
  quantity: number
  entryPrice: number
  currentPrice: number
  pnl: number
  pnlPercent: number
  venue: Venue
  timestamp?: number
}

export class TradingService {
  constructor(private apiClient: ApiClient) {}

  async placeOrder(order: PlaceOrderRequest): Promise<Order> {
    // Validate order parameters
    if (order.quantity <= 0) {
      throw new Error('Quantity must be positive')
    }

    if (!['MARKET', 'LIMIT'].includes(order.type)) {
      throw new Error('Only MARKET and LIMIT entries are supported')
    }

    if (order.type === 'LIMIT' && !order.price) {
      throw new Error(`${order.type} order requires price`)
    }

    if (!order.stopLossPrice) {
      throw new Error('Order requires stopLossPrice')
    }

    if (!order.takeProfitPrice) {
      throw new Error('Order requires takeProfitPrice')
    }

    return this.apiClient.post<Order>('/trading/orders', order)
  }

  async getPositions(): Promise<Position[]> {
    const positions = await this.apiClient.get<BffPosition[]>('/trading/positions')
    return positions.map(position => ({
      symbol: position.symbol,
      side: position.side,
      quantity: position.quantity,
      entryPrice: position.entryPrice,
      markPrice: position.currentPrice,
      pnl: position.pnl,
      pnlPercent: position.pnlPercent,
      venue: position.venue,
    }))
  }

  async cancelOrder(orderId: OrderId, request: CancelOrderRequest): Promise<void> {
    return this.apiClient.delete(`/trading/orders/${orderId}`, {
      body: request,
    })
  }

  async getOrderStatus(orderId: OrderId, venue: Venue): Promise<Order> {
    return this.apiClient.get<Order>(`/trading/orders/${orderId}`, {
      params: { venue },
    })
  }

  async getActiveOrders(): Promise<Order[]> {
    return this.apiClient.get<Order[]>('/trading/orders')
  }

  async setAutoTrading(enabled: boolean): Promise<AutoTradingResponse> {
    return this.apiClient.post<AutoTradingResponse>('/trading/auto-trading', {
      enabled,
    })
  }

  async getAutoTradingStatus(): Promise<AutoTradingStatus> {
    return this.apiClient.get<AutoTradingStatus>('/trading/auto-trading')
  }
}
