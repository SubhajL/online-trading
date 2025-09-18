import type { Order, Position, OrderId, Symbol, Venue, OrderSide, OrderType } from '@/types'
import { ApiClient } from './api.client'

export type PlaceOrderRequest = {
  symbol: Symbol
  side: OrderSide
  type: OrderType
  quantity: number
  price?: number
  stopPrice?: number
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

export class TradingService {
  constructor(private apiClient: ApiClient) {}

  async placeOrder(order: PlaceOrderRequest): Promise<Order> {
    // Validate order parameters
    if (order.quantity <= 0) {
      throw new Error('Quantity must be positive')
    }

    if ((order.type === 'LIMIT' || order.type === 'STOP_LIMIT') && !order.price) {
      throw new Error(`${order.type} order requires price`)
    }

    if ((order.type === 'STOP_MARKET' || order.type === 'STOP_LIMIT') && !order.stopPrice) {
      throw new Error(`${order.type} order requires stopPrice`)
    }

    return this.apiClient.post<Order>('/trading/orders', order)
  }

  async getPositions(): Promise<Position[]> {
    return this.apiClient.get<Position[]>('/trading/positions')
  }

  async cancelOrder(orderId: OrderId, request: CancelOrderRequest): Promise<any> {
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
