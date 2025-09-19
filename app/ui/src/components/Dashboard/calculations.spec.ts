import { describe, it, expect } from 'vitest'
import { formatPercentageChange, calculateDailyPnL } from './calculations'
import type { Position, Order } from '@/types'

describe('formatPercentageChange', () => {
  it('formats positive percentage with plus sign', () => {
    expect(formatPercentageChange(5.25)).toBe('+5.25%')
  })

  it('formats negative percentage with minus sign', () => {
    expect(formatPercentageChange(-3.75)).toBe('-3.75%')
  })

  it('formats zero percentage', () => {
    expect(formatPercentageChange(0)).toBe('0.00%')
  })

  it('formats small positive percentage', () => {
    expect(formatPercentageChange(0.01)).toBe('+0.01%')
  })

  it('formats small negative percentage', () => {
    expect(formatPercentageChange(-0.01)).toBe('-0.01%')
  })

  it('rounds to 2 decimal places', () => {
    expect(formatPercentageChange(5.256)).toBe('+5.26%')
    expect(formatPercentageChange(-3.754)).toBe('-3.75%')
  })

  it('handles large percentages', () => {
    expect(formatPercentageChange(100.5)).toBe('+100.50%')
    expect(formatPercentageChange(-50.25)).toBe('-50.25%')
  })
})

describe('calculateDailyPnL', () => {
  const mockPositions: Position[] = [
    {
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      quantity: 0.1,
      entryPrice: 40000,
      markPrice: 42000,
      pnl: 200,
      pnlPercent: 5,
      venue: 'SPOT',
    },
    {
      symbol: 'ETHUSDT' as any,
      side: 'SELL',
      quantity: 1,
      entryPrice: 2500,
      markPrice: 2400,
      pnl: 100,
      pnlPercent: 4,
      venue: 'USD_M',
    },
  ]

  const todayStart = new Date()
  todayStart.setHours(0, 0, 0, 0)

  const mockTrades: Order[] = [
    {
      orderId: 'ORD001' as any,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.05,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      executedQuantity: 0.05,
      avgPrice: 41000,
    },
    {
      orderId: 'ORD002' as any,
      symbol: 'BTCUSDT' as any,
      side: 'SELL',
      type: 'MARKET',
      quantity: 0.05,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      executedQuantity: 0.05,
      avgPrice: 41500,
    },
  ]

  it('calculates P&L from positions and closed trades', () => {
    const result = calculateDailyPnL(mockPositions, mockTrades)

    // Position P&L: 200 + 100 = 300
    // Trade P&L: (41500 - 41000) * 0.05 = 25
    expect(result).toBe(325)
  })

  it('returns 0 when no positions or trades', () => {
    expect(calculateDailyPnL([], [])).toBe(0)
  })

  it('calculates P&L from positions only', () => {
    expect(calculateDailyPnL(mockPositions, [])).toBe(300)
  })

  it('calculates P&L from trades only', () => {
    expect(calculateDailyPnL([], mockTrades)).toBe(25)
  })

  it('ignores unfilled trades', () => {
    const unfilledTrade: Order = {
      orderId: 'ORD003' as any,
      symbol: 'ETHUSDT' as any,
      side: 'BUY',
      type: 'LIMIT',
      quantity: 1,
      price: 2000,
      status: 'NEW',
      venue: 'SPOT',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      executedQuantity: 0,
    }

    const result = calculateDailyPnL([], [unfilledTrade])
    expect(result).toBe(0)
  })

  it('ignores old trades from previous days', () => {
    const yesterday = new Date()
    yesterday.setDate(yesterday.getDate() - 1)

    const oldTrade: Order = {
      ...mockTrades[0]!,
      createdAt: yesterday.toISOString(),
      updatedAt: yesterday.toISOString(),
    }

    expect(calculateDailyPnL([], [oldTrade])).toBe(0)
  })

  it('calculates sell trade P&L correctly', () => {
    const buyTrade: Order = {
      orderId: 'BUY1' as any,
      symbol: 'ETHUSDT' as any,
      side: 'BUY',
      type: 'MARKET',
      quantity: 1,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      executedQuantity: 1,
      avgPrice: 2000,
    }

    const sellTrade: Order = {
      orderId: 'SELL1' as any,
      symbol: 'ETHUSDT' as any,
      side: 'SELL',
      type: 'MARKET',
      quantity: 1,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      executedQuantity: 1,
      avgPrice: 2100,
    }

    // P&L = (2100 - 2000) * 1 = 100
    expect(calculateDailyPnL([], [buyTrade, sellTrade])).toBe(100)
  })

  it('handles partial fills correctly', () => {
    const partialBuy: Order = {
      orderId: 'PARTIAL1' as any,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'LIMIT',
      quantity: 0.1,
      price: 40000,
      status: 'PARTIALLY_FILLED',
      venue: 'SPOT',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      executedQuantity: 0.05,
      avgPrice: 40000,
    }

    const partialSell: Order = {
      orderId: 'PARTIAL2' as any,
      symbol: 'BTCUSDT' as any,
      side: 'SELL',
      type: 'LIMIT',
      quantity: 0.1,
      price: 41000,
      status: 'PARTIALLY_FILLED',
      venue: 'SPOT',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      executedQuantity: 0.05,
      avgPrice: 41000,
    }

    // P&L = (41000 - 40000) * 0.05 = 50
    expect(calculateDailyPnL([], [partialBuy, partialSell])).toBe(50)
  })

  it('groups trades by symbol and venue', () => {
    const trades: Order[] = [
      {
        orderId: 'B1' as any,
        symbol: 'BTCUSDT' as any,
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.1,
        status: 'FILLED',
        venue: 'SPOT',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        executedQuantity: 0.1,
        avgPrice: 40000,
      },
      {
        orderId: 'S1' as any,
        symbol: 'BTCUSDT' as any,
        side: 'SELL',
        type: 'MARKET',
        quantity: 0.05,
        status: 'FILLED',
        venue: 'SPOT',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        executedQuantity: 0.05,
        avgPrice: 41000,
      },
      {
        orderId: 'B2' as any,
        symbol: 'ETHUSDT' as any,
        side: 'BUY',
        type: 'MARKET',
        quantity: 1,
        status: 'FILLED',
        venue: 'SPOT',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        executedQuantity: 1,
        avgPrice: 2000,
      },
    ]

    // BTC P&L: (41000 - 40000) * 0.05 = 50
    // ETH: no sell, so no realized P&L
    expect(calculateDailyPnL([], trades)).toBe(50)
  })
})
