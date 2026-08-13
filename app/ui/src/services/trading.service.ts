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

export type PlacementOperation = {
  readonly id: string
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
  private static readonly placementIdentityStoragePrefix = 'trading:placement:'
  private static readonly pendingPlacementOperationIdsStorageKey = 'trading:placement-operation-ids'
  private readonly pendingPlacementIdentities = new Map<
    string,
    { idempotencyKey: string; orderFingerprint: string }
  >()

  constructor(private apiClient: ApiClient) {}

  createPlacementOperation(): PlacementOperation {
    return { id: globalThis.crypto.randomUUID() }
  }

  private getStoredPlacementIdentity(storageKey: string): string | null {
    try {
      return globalThis.localStorage?.getItem(storageKey) ?? null
    } catch {
      return null
    }
  }

  private setStoredPlacementIdentity(
    storageKey: string,
    identity: { idempotencyKey: string; orderFingerprint: string },
  ): void {
    try {
      globalThis.localStorage?.setItem(storageKey, JSON.stringify(identity))
    } catch {
      return
    }
  }

  private removeStoredPlacementIdentity(storageKey: string): void {
    try {
      globalThis.localStorage?.removeItem(storageKey)
    } catch {
      return
    }
  }

  private pendingPlacementOperationIds(): string[] {
    const stored = this.getStoredPlacementIdentity(
      TradingService.pendingPlacementOperationIdsStorageKey,
    )
    if (!stored) {
      return []
    }
    try {
      const parsed = JSON.parse(stored) as unknown
      if (
        Array.isArray(parsed) &&
        parsed.every(operationId => typeof operationId === 'string' && operationId.length > 0)
      ) {
        return [...new Set(parsed)]
      }
    } catch {}
    this.removeStoredPlacementIdentity(TradingService.pendingPlacementOperationIdsStorageKey)
    return []
  }

  private storePendingPlacementOperationIds(operationIds: string[]): void {
    try {
      globalThis.localStorage?.setItem(
        TradingService.pendingPlacementOperationIdsStorageKey,
        JSON.stringify(operationIds),
      )
    } catch {
      return
    }
  }

  private registerPendingPlacementOperation(operationId: string): void {
    const operationIds = this.pendingPlacementOperationIds()
    if (!operationIds.includes(operationId)) {
      this.storePendingPlacementOperationIds([...operationIds, operationId])
    }
  }

  listPendingPlacementOperations(): PlacementOperation[] {
    return this.pendingPlacementOperationIds().map(id => ({ id }))
  }

  recoverPendingPlacementOperation(
    operationId: string,
    order: PlaceOrderRequest,
  ): PlacementOperation | null {
    if (!operationId.trim()) {
      throw new Error('Placement operation ID is required')
    }
    const storageKey = `${TradingService.placementIdentityStoragePrefix}${operationId}`
    const stored = this.getStoredPlacementIdentity(storageKey)
    if (!stored) {
      return null
    }
    try {
      const identity = JSON.parse(stored) as {
        idempotencyKey?: unknown
        orderFingerprint?: unknown
      }
      if (
        typeof identity.idempotencyKey !== 'string' ||
        typeof identity.orderFingerprint !== 'string'
      ) {
        throw new Error('Stored placement operation is invalid')
      }
      if (identity.orderFingerprint !== this.placementOrderFingerprint(order)) {
        throw new Error('Placement operation does not match this order')
      }
      this.pendingPlacementIdentities.set(operationId, {
        idempotencyKey: identity.idempotencyKey,
        orderFingerprint: identity.orderFingerprint,
      })
      return { id: operationId }
    } catch (error) {
      if (error instanceof Error && error.message.startsWith('Placement operation')) {
        throw error
      }
      this.removeStoredPlacementIdentity(storageKey)
      throw new Error('Stored placement operation is invalid')
    }
  }

  private placementOrderFingerprint(order: PlaceOrderRequest): string {
    return JSON.stringify([
      order.symbol,
      order.side,
      order.type,
      order.quantity,
      order.price ?? null,
      order.stopPrice ?? null,
      order.stopLossPrice ?? null,
      order.takeProfitPrice ?? null,
      order.venue,
    ])
  }

  private placementIdentity(
    operation: PlacementOperation,
    orderFingerprint: string,
  ): { idempotencyKey: string; orderFingerprint: string } {
    const storageKey = `${TradingService.placementIdentityStoragePrefix}${operation.id}`
    const stored = this.getStoredPlacementIdentity(storageKey)
    let prior = this.pendingPlacementIdentities.get(operation.id)
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as unknown
        if (
          typeof parsed === 'object' &&
          parsed !== null &&
          'idempotencyKey' in parsed &&
          typeof parsed.idempotencyKey === 'string' &&
          'orderFingerprint' in parsed &&
          typeof parsed.orderFingerprint === 'string'
        ) {
          prior = parsed as { idempotencyKey: string; orderFingerprint: string }
        }
      } catch {
        this.removeStoredPlacementIdentity(storageKey)
      }
    }
    if (prior && prior.orderFingerprint !== orderFingerprint) {
      throw new Error('Placement operation cannot be reused for a different order')
    }
    const identity = prior ?? {
      idempotencyKey: globalThis.crypto.randomUUID(),
      orderFingerprint,
    }
    this.pendingPlacementIdentities.set(operation.id, identity)
    this.setStoredPlacementIdentity(storageKey, identity)
    this.registerPendingPlacementOperation(operation.id)
    return identity
  }

  abandonPlacementOperation(operation: PlacementOperation): void {
    this.pendingPlacementIdentities.delete(operation.id)
    this.removeStoredPlacementIdentity(
      `${TradingService.placementIdentityStoragePrefix}${operation.id}`,
    )
    this.storePendingPlacementOperationIds(
      this.pendingPlacementOperationIds().filter(operationId => operationId !== operation.id),
    )
  }

  async placeOrder(order: PlaceOrderRequest, operation: PlacementOperation): Promise<Order> {
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

    const { idempotencyKey } = this.placementIdentity(
      operation,
      this.placementOrderFingerprint(order),
    )
    const result = await this.apiClient.post<Order>('/trading/orders', order, {
      headers: { 'X-Idempotency-Key': idempotencyKey },
    })
    this.abandonPlacementOperation(operation)
    return result
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
