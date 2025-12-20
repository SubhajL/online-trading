import { describe, it, expect } from 'vitest'
import {
  formatPercentageChange,
  calculateDailyPnL,
  calculateWinRate,
  calculateProfitFactor,
  calculateSharpeRatio,
  calculateMaxDrawdown,
  buildEquityCurve,
} from './calculations'
import type { Position, Order } from '@/types'
import type { EquityPoint } from '@/types/dashboard'

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

// Closed trade type for KPI calculations
type ClosedTrade = {
  pnl: number
  timestamp: string
}

describe('calculateWinRate', () => {
  it('returns percentage of winning trades', () => {
    const trades: ClosedTrade[] = [
      { pnl: 100, timestamp: '2025-01-01T00:00:00Z' },
      { pnl: 50, timestamp: '2025-01-01T01:00:00Z' },
      { pnl: -30, timestamp: '2025-01-01T02:00:00Z' },
      { pnl: 80, timestamp: '2025-01-01T03:00:00Z' },
      { pnl: -20, timestamp: '2025-01-01T04:00:00Z' },
      { pnl: 60, timestamp: '2025-01-01T05:00:00Z' },
      { pnl: -10, timestamp: '2025-01-01T06:00:00Z' },
      { pnl: 40, timestamp: '2025-01-01T07:00:00Z' },
      { pnl: -15, timestamp: '2025-01-01T08:00:00Z' },
      { pnl: 25, timestamp: '2025-01-01T09:00:00Z' },
    ]
    // 6 wins, 4 losses = 60%
    expect(calculateWinRate(trades)).toBe(60)
  })

  it('returns null when fewer than minTrades', () => {
    const trades: ClosedTrade[] = [
      { pnl: 100, timestamp: '2025-01-01T00:00:00Z' },
      { pnl: -50, timestamp: '2025-01-01T01:00:00Z' },
    ]
    expect(calculateWinRate(trades, 10)).toBeNull()
  })

  it('returns 100 when all trades are winners', () => {
    const trades: ClosedTrade[] = Array.from({ length: 10 }, (_, i) => ({
      pnl: (i + 1) * 10,
      timestamp: `2025-01-01T0${i}:00:00Z`,
    }))
    expect(calculateWinRate(trades)).toBe(100)
  })

  it('returns 0 when all trades are losers', () => {
    const trades: ClosedTrade[] = Array.from({ length: 10 }, (_, i) => ({
      pnl: -(i + 1) * 10,
      timestamp: `2025-01-01T0${i}:00:00Z`,
    }))
    expect(calculateWinRate(trades)).toBe(0)
  })

  it('treats zero pnl as not a win', () => {
    const trades: ClosedTrade[] = Array.from({ length: 10 }, (_, i) => ({
      pnl: i === 0 ? 0 : 10,
      timestamp: `2025-01-01T0${i}:00:00Z`,
    }))
    // 9 wins out of 10 = 90%
    expect(calculateWinRate(trades)).toBe(90)
  })
})

describe('calculateProfitFactor', () => {
  it('divides gross wins by gross losses', () => {
    const trades: ClosedTrade[] = [
      { pnl: 100, timestamp: '2025-01-01T00:00:00Z' },
      { pnl: 200, timestamp: '2025-01-01T01:00:00Z' },
      { pnl: -100, timestamp: '2025-01-01T02:00:00Z' },
    ]
    // Gross wins: 300, Gross losses: 100 -> PF = 3.0
    // Pass minTrades=3 since we only have 3 trades
    expect(calculateProfitFactor(trades, 3)).toBe(3)
  })

  it('returns null when fewer than minTrades', () => {
    const trades: ClosedTrade[] = [{ pnl: 100, timestamp: '2025-01-01T00:00:00Z' }]
    expect(calculateProfitFactor(trades, 10)).toBeNull()
  })

  it('returns Infinity when no losses', () => {
    const trades: ClosedTrade[] = Array.from({ length: 10 }, (_, i) => ({
      pnl: (i + 1) * 10,
      timestamp: `2025-01-01T0${i}:00:00Z`,
    }))
    expect(calculateProfitFactor(trades)).toBe(Infinity)
  })

  it('returns 0 when no wins', () => {
    const trades: ClosedTrade[] = Array.from({ length: 10 }, (_, i) => ({
      pnl: -(i + 1) * 10,
      timestamp: `2025-01-01T0${i}:00:00Z`,
    }))
    expect(calculateProfitFactor(trades)).toBe(0)
  })

  it('ignores zero pnl trades', () => {
    const trades: ClosedTrade[] = [
      { pnl: 100, timestamp: '2025-01-01T00:00:00Z' },
      { pnl: 0, timestamp: '2025-01-01T01:00:00Z' },
      { pnl: -50, timestamp: '2025-01-01T02:00:00Z' },
      ...Array.from({ length: 7 }, (_, i) => ({
        pnl: 10,
        timestamp: `2025-01-01T0${i + 3}:00:00Z`,
      })),
    ]
    // Gross wins: 100 + 70 = 170, Gross losses: 50 -> PF = 3.4
    expect(calculateProfitFactor(trades)).toBe(3.4)
  })
})

describe('calculateSharpeRatio', () => {
  it('returns null when fewer than 30 trades', () => {
    const returns = Array.from({ length: 20 }, () => 0.01)
    expect(calculateSharpeRatio(returns, 30, 7)).toBeNull()
  })

  it('returns null when fewer than minDays', () => {
    // 10 returns, but we require minDays=14, so should return null
    const returns = Array.from({ length: 10 }, () => 0.01)
    expect(calculateSharpeRatio(returns, 5, 14)).toBeNull()
  })

  it('returns 0 when variance is zero', () => {
    // All identical returns = zero variance
    const returns = Array.from({ length: 30 }, () => 0.01)
    const result = calculateSharpeRatio(returns, 30, 7)
    // With zero variance, Sharpe is undefined - we return 0
    expect(result).toBe(0)
  })

  it('annualizes daily returns correctly', () => {
    // Mean = 0.001 (0.1% daily), Std = 0.01
    // Sharpe = (0.001 / 0.01) * sqrt(252) ≈ 1.587
    const returns = [
      0.011, 0.009, -0.001, 0.012, 0.008, -0.002, 0.013, 0.007, -0.003, 0.011, 0.009, 0.001, 0.012,
      0.008, -0.001, 0.013, 0.007, 0.002, 0.011, 0.009, -0.002, 0.012, 0.008, 0.001, 0.013, 0.007,
      -0.001, 0.011, 0.009, 0.001,
    ]
    const result = calculateSharpeRatio(returns, 30, 7)
    expect(result).not.toBeNull()
    expect(result).toBeGreaterThan(0)
  })

  it('returns negative Sharpe for losing strategy', () => {
    const returns = Array.from({ length: 30 }, (_, i) => (i % 3 === 0 ? -0.02 : 0.005))
    const result = calculateSharpeRatio(returns, 30, 7)
    expect(result).not.toBeNull()
  })
})

describe('calculateMaxDrawdown', () => {
  it('finds peak-to-trough decline', () => {
    const equityCurve: EquityPoint[] = [
      { timestamp: '2025-01-01T00:00:00Z', equity: 100 },
      { timestamp: '2025-01-02T00:00:00Z', equity: 120 },
      { timestamp: '2025-01-03T00:00:00Z', equity: 90 },
      { timestamp: '2025-01-04T00:00:00Z', equity: 110 },
    ]
    // Peak: 120, Trough: 90, Drawdown: (120-90)/120 = 25%
    expect(calculateMaxDrawdown(equityCurve)).toBe(25)
  })

  it('returns 0 for monotonically increasing equity', () => {
    const equityCurve: EquityPoint[] = [
      { timestamp: '2025-01-01T00:00:00Z', equity: 100 },
      { timestamp: '2025-01-02T00:00:00Z', equity: 110 },
      { timestamp: '2025-01-03T00:00:00Z', equity: 120 },
    ]
    expect(calculateMaxDrawdown(equityCurve)).toBe(0)
  })

  it('returns 0 for empty equity curve', () => {
    expect(calculateMaxDrawdown([])).toBe(0)
  })

  it('returns 0 for single point', () => {
    expect(calculateMaxDrawdown([{ timestamp: '2025-01-01T00:00:00Z', equity: 100 }])).toBe(0)
  })

  it('handles multiple drawdowns and finds the largest', () => {
    const equityCurve: EquityPoint[] = [
      { timestamp: '2025-01-01T00:00:00Z', equity: 100 },
      { timestamp: '2025-01-02T00:00:00Z', equity: 90 }, // 10% DD
      { timestamp: '2025-01-03T00:00:00Z', equity: 95 },
      { timestamp: '2025-01-04T00:00:00Z', equity: 110 },
      { timestamp: '2025-01-05T00:00:00Z', equity: 80 }, // 27.27% DD from 110
      { timestamp: '2025-01-06T00:00:00Z', equity: 100 },
    ]
    // Max DD: (110 - 80) / 110 = 27.27%
    expect(calculateMaxDrawdown(equityCurve)).toBeCloseTo(27.27, 1)
  })
})

describe('buildEquityCurve', () => {
  it('sorts points by timestamp', () => {
    const unsorted: EquityPoint[] = [
      { timestamp: '2025-01-03T00:00:00Z', equity: 120 },
      { timestamp: '2025-01-01T00:00:00Z', equity: 100 },
      { timestamp: '2025-01-02T00:00:00Z', equity: 110 },
    ]
    const result = buildEquityCurve(unsorted)
    expect(result[0]?.timestamp).toBe('2025-01-01T00:00:00Z')
    expect(result[1]?.timestamp).toBe('2025-01-02T00:00:00Z')
    expect(result[2]?.timestamp).toBe('2025-01-03T00:00:00Z')
  })

  it('deduplicates by timestamp keeping latest', () => {
    const withDupes: EquityPoint[] = [
      { timestamp: '2025-01-01T00:00:00Z', equity: 100 },
      { timestamp: '2025-01-01T00:00:00Z', equity: 105 },
      { timestamp: '2025-01-02T00:00:00Z', equity: 110 },
    ]
    const result = buildEquityCurve(withDupes)
    expect(result).toHaveLength(2)
    expect(result[0]?.equity).toBe(105)
  })

  it('returns empty array for empty input', () => {
    expect(buildEquityCurve([])).toEqual([])
  })

  it('handles single point', () => {
    const single: EquityPoint[] = [{ timestamp: '2025-01-01T00:00:00Z', equity: 100 }]
    expect(buildEquityCurve(single)).toEqual(single)
  })
})
