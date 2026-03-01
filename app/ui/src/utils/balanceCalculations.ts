import type { Balance, OrderFormValues, OrderSide } from '@/types'

export type BalanceDelta = {
  asset: string
  delta: number
}

export type OptimisticToken = {
  id: string
  snapshot: Balance[]
  deltas: BalanceDelta[]
  timestamp: number
}

function generateOptimisticId(): string {
  return `opt-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export function extractBaseAsset(symbol: string): string {
  const quoteAssets = ['USDT', 'BUSD', 'USDC', 'BTC', 'ETH', 'BNB']
  for (const quote of quoteAssets) {
    if (symbol.endsWith(quote)) {
      return symbol.slice(0, -quote.length)
    }
  }
  return symbol.slice(0, 3)
}

export function extractQuoteAsset(symbol: string): string {
  const quoteAssets = ['USDT', 'BUSD', 'USDC', 'BTC', 'ETH', 'BNB']
  for (const quote of quoteAssets) {
    if (symbol.endsWith(quote)) {
      return quote
    }
  }
  return 'USDT'
}

export function computeOrderCost(side: OrderSide, quantity: number, price: number): number {
  return quantity * price
}

export function computeBalanceDelta(order: OrderFormValues, price: number): BalanceDelta[] {
  const baseAsset = extractBaseAsset(order.symbol)
  const quoteAsset = extractQuoteAsset(order.symbol)
  const cost = computeOrderCost(order.side, order.quantity, price)

  if (order.side === 'BUY') {
    return [
      { asset: quoteAsset, delta: -cost },
      { asset: baseAsset, delta: order.quantity },
    ]
  } else {
    return [
      { asset: baseAsset, delta: -order.quantity },
      { asset: quoteAsset, delta: cost },
    ]
  }
}

export function applyOptimisticDelta(
  balances: Balance[],
  deltas: BalanceDelta[],
): { updatedBalances: Balance[]; token: OptimisticToken } {
  const snapshot = balances.map(b => ({ ...b }))

  const updatedBalances = balances.map(balance => {
    const delta = deltas.find(d => d.asset === balance.asset)
    if (!delta) return balance

    const newFree = Math.max(0, balance.free + delta.delta)
    return {
      ...balance,
      free: newFree,
      total: newFree + balance.locked,
    }
  })

  const token: OptimisticToken = {
    id: generateOptimisticId(),
    snapshot,
    deltas,
    timestamp: Date.now(),
  }

  return { updatedBalances, token }
}

export function rollbackOptimistic(_currentBalances: Balance[], token: OptimisticToken): Balance[] {
  return token.snapshot.map(b => ({ ...b }))
}

export function canAffordOrder(
  balances: Balance[],
  order: OrderFormValues,
  price: number,
): boolean {
  const deltas = computeBalanceDelta(order, price)

  for (const delta of deltas) {
    if (delta.delta < 0) {
      const balance = balances.find(b => b.asset === delta.asset)
      const available = balance?.free ?? 0
      if (available < Math.abs(delta.delta)) {
        return false
      }
    }
  }

  return true
}
