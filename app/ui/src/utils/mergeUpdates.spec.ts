import { describe, it, expect } from 'vitest'
import { mergeOrderUpdate } from './mergeUpdates'
import type { Order, OrderId } from '@/types'

describe('mergeOrderUpdate', () => {
  const mockOrders: Order[] = [
    {
      orderId: 'ORD001' as OrderId,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.1,
      price: 40000,
      status: 'NEW',
      venue: 'SPOT',
      createdAt: '2024-01-15T10:00:00Z',
      updatedAt: '2024-01-15T10:00:00Z',
      executedQuantity: 0,
    },
    {
      orderId: 'ORD002' as OrderId,
      symbol: 'ETHUSDT' as any,
      side: 'SELL',
      type: 'MARKET',
      quantity: 1,
      status: 'FILLED',
      venue: 'USD_M',
      createdAt: '2024-01-15T11:00:00Z',
      updatedAt: '2024-01-15T11:00:05Z',
      executedQuantity: 1,
      avgPrice: 2500,
    },
  ]

  it('updates existing order status', () => {
    const update: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD001' as OrderId,
      status: 'FILLED',
      executedQuantity: 0.1,
      avgPrice: 40100,
      updatedAt: '2024-01-15T10:05:00Z',
    }

    const result = mergeOrderUpdate(mockOrders, update)

    expect(result).toHaveLength(2)
    expect(result[0]).toEqual({
      ...mockOrders[0],
      status: 'FILLED',
      executedQuantity: 0.1,
      avgPrice: 40100,
      updatedAt: '2024-01-15T10:05:00Z',
    })
    expect(result[1]).toEqual(mockOrders[1])
  })

  it('maintains order of items', () => {
    const update: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD002' as OrderId,
      status: 'PARTIALLY_FILLED',
      executedQuantity: 0.5,
    }

    const result = mergeOrderUpdate(mockOrders, update)

    expect(result[0]!.orderId).toBe('ORD001')
    expect(result[1]!.orderId).toBe('ORD002')
  })

  it('handles non-existent order gracefully', () => {
    const update: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD999' as OrderId,
      status: 'FILLED',
    }

    const result = mergeOrderUpdate(mockOrders, update)

    expect(result).toEqual(mockOrders)
  })

  it('preserves immutability', () => {
    const update: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD001' as OrderId,
      status: 'CANCELED',
    }

    const result = mergeOrderUpdate(mockOrders, update)

    expect(result).not.toBe(mockOrders)
    expect(result[0]).not.toBe(mockOrders[0])
    expect(result[1]).toBe(mockOrders[1]) // Unchanged item should be the same reference
    expect(mockOrders[0]!.status).toBe('NEW') // Original unchanged
  })

  it('merges multiple fields', () => {
    const update: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD001' as OrderId,
      status: 'PARTIALLY_FILLED',
      executedQuantity: 0.05,
      avgPrice: 40050,
      updatedAt: '2024-01-15T10:02:00Z',
    }

    const result = mergeOrderUpdate(mockOrders, update)

    expect(result[0]).toMatchObject({
      orderId: 'ORD001',
      status: 'PARTIALLY_FILLED',
      executedQuantity: 0.05,
      avgPrice: 40050,
      updatedAt: '2024-01-15T10:02:00Z',
      // Original fields preserved
      symbol: 'BTCUSDT',
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.1,
      price: 40000,
    })
  })

  it('handles empty orders array', () => {
    const update: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD001' as OrderId,
      status: 'FILLED',
    }

    const result = mergeOrderUpdate([], update)

    expect(result).toEqual([])
  })

  it('handles partial updates correctly', () => {
    const update: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD001' as OrderId,
      executedQuantity: 0.03,
    }

    const result = mergeOrderUpdate(mockOrders, update)

    expect(result[0]!.executedQuantity).toBe(0.03)
    expect(result[0]!.status).toBe('NEW') // Other fields unchanged
  })

  it('updates timestamps correctly', () => {
    const newTimestamp = '2024-01-15T10:10:00Z'
    const update: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD001' as OrderId,
      status: 'FILLED',
      updatedAt: newTimestamp,
    }

    const result = mergeOrderUpdate(mockOrders, update)

    expect(result[0]!.updatedAt).toBe(newTimestamp)
    expect(result[0]!.createdAt).toBe(mockOrders[0]!.createdAt) // createdAt unchanged
  })

  it('handles status transitions correctly', () => {
    const orders: Order[] = [
      {
        ...mockOrders[0]!,
        status: 'NEW',
      },
    ]

    // NEW -> PARTIALLY_FILLED
    let result = mergeOrderUpdate(orders, {
      orderId: 'ORD001' as OrderId,
      status: 'PARTIALLY_FILLED',
      executedQuantity: 0.05,
    })
    expect(result[0]!.status).toBe('PARTIALLY_FILLED')

    // PARTIALLY_FILLED -> FILLED
    result = mergeOrderUpdate(result, {
      orderId: 'ORD001' as OrderId,
      status: 'FILLED',
      executedQuantity: 0.1,
    })
    expect(result[0]!.status).toBe('FILLED')
  })

  it('handles concurrent updates to different orders', () => {
    const update1: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD001' as OrderId,
      status: 'FILLED',
    }
    const update2: Partial<Order> & { orderId: OrderId } = {
      orderId: 'ORD002' as OrderId,
      status: 'CANCELED',
    }

    let result = mergeOrderUpdate(mockOrders, update1)
    result = mergeOrderUpdate(result, update2)

    expect(result[0]!.status).toBe('FILLED')
    expect(result[1]!.status).toBe('CANCELED')
  })
})
