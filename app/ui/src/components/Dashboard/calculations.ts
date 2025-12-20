import type { Position, Order } from '@/types'
import type { EquityPoint } from '@/types/dashboard'

// Type for closed trades with P&L
export type ClosedTrade = {
  pnl: number
  timestamp: string
}

export function formatPercentageChange(value: number): string {
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(2)}%`
}

export function calculateDailyPnL(positions: Position[], trades: Order[]): number {
  // Calculate unrealized P&L from open positions
  const positionPnL = positions.reduce((sum, position) => sum + position.pnl, 0)

  // Calculate realized P&L from today's trades
  const todayStart = new Date()
  todayStart.setHours(0, 0, 0, 0)

  // Filter today's filled trades
  const todayTrades = trades.filter(trade => {
    if (trade.status !== 'FILLED' && trade.status !== 'PARTIALLY_FILLED') {
      return false
    }
    const tradeDate = new Date(trade.updatedAt)
    return tradeDate >= todayStart
  })

  // Group trades by symbol and venue to match buys with sells
  const tradeGroups: Record<string, { buys: Order[]; sells: Order[] }> = {}

  todayTrades.forEach(trade => {
    const key = `${trade.symbol}-${trade.venue}`
    if (!tradeGroups[key]) {
      tradeGroups[key] = { buys: [], sells: [] }
    }

    if (trade.side === 'BUY') {
      tradeGroups[key]!.buys.push(trade)
    } else {
      tradeGroups[key]!.sells.push(trade)
    }
  })

  // Calculate realized P&L by matching buys with sells
  let realizedPnL = 0

  Object.values(tradeGroups).forEach(group => {
    // Sort buys by time (FIFO)
    const buys = [...group.buys].sort(
      (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    )
    const sells = [...group.sells].sort(
      (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    )

    let buyIndex = 0
    let sellIndex = 0
    let buyRemaining = buys[buyIndex]?.executedQuantity || 0
    let sellRemaining = sells[sellIndex]?.executedQuantity || 0

    while (buyIndex < buys.length && sellIndex < sells.length) {
      const buy = buys[buyIndex]!
      const sell = sells[sellIndex]!

      // Calculate the quantity to match
      const matchQuantity = Math.min(buyRemaining, sellRemaining)

      if (matchQuantity > 0) {
        // Guard: skip if avgPrice is missing (avoid NaN)
        const buyPrice = buy.avgPrice ?? 0
        const sellPrice = sell.avgPrice ?? 0
        if (buyPrice > 0 && sellPrice > 0) {
          const pnl = (sellPrice - buyPrice) * matchQuantity
          realizedPnL += pnl
        }

        buyRemaining -= matchQuantity
        sellRemaining -= matchQuantity
      }

      // Move to next order if current is exhausted
      if (buyRemaining === 0 && ++buyIndex < buys.length) {
        buyRemaining = buys[buyIndex]!.executedQuantity || 0
      }
      if (sellRemaining === 0 && ++sellIndex < sells.length) {
        sellRemaining = sells[sellIndex]!.executedQuantity || 0
      }
    }
  })

  return positionPnL + realizedPnL
}

export function calculateWinRate(trades: ClosedTrade[], minTrades: number = 10): number | null {
  if (trades.length < minTrades) {
    return null
  }

  const wins = trades.filter(t => t.pnl > 0).length
  return (wins / trades.length) * 100
}

export function calculateProfitFactor(
  trades: ClosedTrade[],
  minTrades: number = 10,
): number | null {
  if (trades.length < minTrades) {
    return null
  }

  const grossWins = trades.filter(t => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0)
  const grossLosses = Math.abs(trades.filter(t => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0))

  if (grossLosses === 0) {
    return grossWins > 0 ? Infinity : 0
  }

  return grossWins / grossLosses
}

const EPSILON = 1e-10

export function calculateSharpeRatio(
  returns: number[],
  minTrades: number = 30,
  minDays: number = 7,
): number | null {
  if (returns.length < minTrades || returns.length < minDays) {
    return null
  }

  const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length
  const squaredDiffs = returns.map(r => (r - mean) ** 2)
  const variance = squaredDiffs.reduce((sum, d) => sum + d, 0) / returns.length
  const stdDev = Math.sqrt(variance)

  // Handle zero/near-zero variance (all identical returns)
  if (stdDev < EPSILON) {
    return 0
  }

  const annualizationFactor = Math.sqrt(252)
  return (mean / stdDev) * annualizationFactor
}

export function calculateMaxDrawdown(equityCurve: EquityPoint[]): number {
  if (equityCurve.length < 2) {
    return 0
  }

  let peak = equityCurve[0]!.equity
  let maxDrawdown = 0

  for (const point of equityCurve) {
    if (point.equity > peak) {
      peak = point.equity
    }

    // Guard: avoid division by zero or negative peak
    if (peak <= 0) {
      continue
    }

    const drawdown = ((peak - point.equity) / peak) * 100
    if (drawdown > maxDrawdown) {
      maxDrawdown = drawdown
    }
  }

  return maxDrawdown
}

export function buildEquityCurve(points: EquityPoint[]): EquityPoint[] {
  if (points.length === 0) {
    return []
  }

  const byTimestamp = new Map<string, EquityPoint>()

  for (const point of points) {
    byTimestamp.set(point.timestamp, point)
  }

  const deduped = Array.from(byTimestamp.values())

  return deduped.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
}
