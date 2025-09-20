import type { Position, Order } from '@/types'

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
        // Calculate P&L for this match
        const pnl = (sell.avgPrice! - buy.avgPrice!) * matchQuantity
        realizedPnL += pnl

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
