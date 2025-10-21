import type { OrderId, PositionId, BalanceId } from '../types/api'

/**
 * Generates stable key for Position items in lists
 * Uses symbol as the unique identifier for positions
 */
export function getPositionKey(symbol: string, index: number): string {
  return `position-${symbol}-${index}`
}

/**
 * Generates stable key for Balance items in lists
 * Uses asset as the unique identifier for balances
 */
export function getBalanceKey(asset: string, index: number): string {
  return `balance-${asset}-${index}`
}

/**
 * Generates stable key for Order items in lists
 * Uses orderId as the unique identifier for orders
 */
export function getOrderKey(orderId: OrderId): string {
  return `order-${orderId}`
}
