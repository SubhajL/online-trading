import type { Balance, Order, OrderId, Symbol } from '@/types'
import type { Alert } from '@/types/alerts'

/**
 * Create a mock Balance object with all required fields
 * The total field is automatically calculated from free + locked
 */
export function createMockBalance(overrides?: Partial<Balance>): Balance {
  const defaults: Balance = {
    asset: 'USDT',
    free: 1000,
    locked: 0,
    total: 1000,
    venue: 'SPOT',
    usdValue: 1000,
  }

  const balance = { ...defaults, ...overrides }

  // Ensure total is always calculated correctly
  balance.total = balance.free + balance.locked

  return balance
}

/**
 * Create a mock Alert object with all required fields
 */
export function createMockAlert(overrides?: Partial<Alert>): Alert {
  const defaults: Alert = {
    id: 'alert-1' as Alert['id'],
    type: 'info',
    priority: 'medium',
    title: 'Test Alert',
    message: 'This is a test alert',
    data: { symbol: 'BTCUSDT' as Symbol, venue: 'SPOT' },
    createdAt: new Date().toISOString(),
    read: false,
  }

  return { ...defaults, ...overrides }
}

/**
 * Create a mock Order object with all required fields
 */
export function createMockOrder(overrides?: Partial<Order>): Order {
  const defaults: Order = {
    orderId: '123' as OrderId,
    symbol: 'BTCUSDT' as Symbol,
    side: 'BUY',
    type: 'LIMIT',
    quantity: 0.001,
    price: 50000,
    status: 'NEW',
    venue: 'SPOT',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }

  return { ...defaults, ...overrides }
}
