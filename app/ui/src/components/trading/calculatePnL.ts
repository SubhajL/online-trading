import type { Position } from '@/types'

export function calculatePnL(
  position: Pick<Position, 'side' | 'quantity' | 'entryPrice'>,
  currentPrice: number,
): { pnl: number; pnlPercent: number } {
  let pnl: number
  let pnlPercent: number

  if (position.side === 'BUY') {
    // For long positions: (current - entry) * quantity
    pnl = (currentPrice - position.entryPrice) * position.quantity
    pnlPercent = ((currentPrice - position.entryPrice) / position.entryPrice) * 100
  } else {
    // For short positions: (entry - current) * quantity
    pnl = (position.entryPrice - currentPrice) * position.quantity
    pnlPercent = ((position.entryPrice - currentPrice) / position.entryPrice) * 100
  }

  return { pnl, pnlPercent }
}
