import { describe, it, expect } from 'vitest'
import {
  extractBaseAsset,
  extractQuoteAsset,
  computeOrderCost,
  computeBalanceDelta,
  applyOptimisticDelta,
  rollbackOptimistic,
  canAffordOrder,
} from './balanceCalculations'
import type { Balance, OrderFormValues } from '@/types'

describe('balanceCalculations', () => {
  describe('extractBaseAsset', () => {
    it('extracts BTC from BTCUSDT', () => {
      expect(extractBaseAsset('BTCUSDT')).toBe('BTC')
    })

    it('extracts ETH from ETHUSDT', () => {
      expect(extractBaseAsset('ETHUSDT')).toBe('ETH')
    })

    it('extracts SOL from SOLBUSD', () => {
      expect(extractBaseAsset('SOLBUSD')).toBe('SOL')
    })

    it('extracts DOGE from DOGEBTC', () => {
      expect(extractBaseAsset('DOGEBTC')).toBe('DOGE')
    })

    it('extracts BNB from BNBETH', () => {
      expect(extractBaseAsset('BNBETH')).toBe('BNB')
    })
  })

  describe('extractQuoteAsset', () => {
    it('extracts USDT from BTCUSDT', () => {
      expect(extractQuoteAsset('BTCUSDT')).toBe('USDT')
    })

    it('extracts BUSD from ETHBUSD', () => {
      expect(extractQuoteAsset('ETHBUSD')).toBe('BUSD')
    })

    it('extracts BTC from ETHBTC', () => {
      expect(extractQuoteAsset('ETHBTC')).toBe('BTC')
    })

    it('extracts BNB from DOGEBNB', () => {
      expect(extractQuoteAsset('DOGEBNB')).toBe('BNB')
    })
  })

  describe('computeOrderCost', () => {
    it('calculates BUY cost as qty × price', () => {
      const cost = computeOrderCost('BUY', 0.1, 50000)
      expect(cost).toBe(5000)
    })

    it('calculates SELL proceeds as qty × price', () => {
      const cost = computeOrderCost('SELL', 0.5, 3000)
      expect(cost).toBe(1500)
    })

    it('handles fractional quantities', () => {
      const cost = computeOrderCost('BUY', 0.001, 45000)
      expect(cost).toBe(45)
    })

    it('handles large quantities', () => {
      const cost = computeOrderCost('BUY', 100, 50)
      expect(cost).toBe(5000)
    })
  })

  describe('computeBalanceDelta', () => {
    it('BUY decreases USDT and increases base asset', () => {
      const order: OrderFormValues = {
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.1,
      }
      const deltas = computeBalanceDelta(order, 50000)

      expect(deltas).toHaveLength(2)
      expect(deltas).toContainEqual({ asset: 'USDT', delta: -5000 })
      expect(deltas).toContainEqual({ asset: 'BTC', delta: 0.1 })
    })

    it('SELL decreases base asset and increases USDT', () => {
      const order: OrderFormValues = {
        symbol: 'ETHUSDT',
        side: 'SELL',
        type: 'MARKET',
        quantity: 1,
      }
      const deltas = computeBalanceDelta(order, 3000)

      expect(deltas).toHaveLength(2)
      expect(deltas).toContainEqual({ asset: 'ETH', delta: -1 })
      expect(deltas).toContainEqual({ asset: 'USDT', delta: 3000 })
    })

    it('handles BTC quote pair correctly', () => {
      const order: OrderFormValues = {
        symbol: 'ETHBTC',
        side: 'BUY',
        type: 'LIMIT',
        quantity: 2,
        price: 0.05,
      }
      const deltas = computeBalanceDelta(order, 0.05)

      expect(deltas).toContainEqual({ asset: 'BTC', delta: -0.1 })
      expect(deltas).toContainEqual({ asset: 'ETH', delta: 2 })
    })
  })

  describe('applyOptimisticDelta', () => {
    const mockBalances: Balance[] = [
      { asset: 'USDT', free: 10000, locked: 0, total: 10000, venue: 'SPOT' },
      { asset: 'BTC', free: 0.5, locked: 0, total: 0.5, venue: 'SPOT' },
    ]

    it('updates balance immediately for BUY order', () => {
      const deltas = [
        { asset: 'USDT', delta: -5000 },
        { asset: 'BTC', delta: 0.1 },
      ]
      const { updatedBalances } = applyOptimisticDelta(mockBalances, deltas)

      const usdt = updatedBalances.find(b => b.asset === 'USDT')
      const btc = updatedBalances.find(b => b.asset === 'BTC')

      expect(usdt?.free).toBe(5000)
      expect(usdt?.total).toBe(5000)
      expect(btc?.free).toBe(0.6)
      expect(btc?.total).toBe(0.6)
    })

    it('returns token with snapshot for rollback', () => {
      const deltas = [{ asset: 'USDT', delta: -1000 }]
      const { token } = applyOptimisticDelta(mockBalances, deltas)

      expect(token.id).toMatch(/^opt-/)
      expect(token.snapshot).toHaveLength(2)
      expect(token.snapshot[0].free).toBe(10000)
      expect(token.deltas).toEqual(deltas)
      expect(token.timestamp).toBeGreaterThan(0)
    })

    it('clamps balance at zero for insufficient funds', () => {
      const deltas = [{ asset: 'USDT', delta: -20000 }]
      const { updatedBalances } = applyOptimisticDelta(mockBalances, deltas)

      const usdt = updatedBalances.find(b => b.asset === 'USDT')
      expect(usdt?.free).toBe(0)
      expect(usdt?.total).toBe(0)
    })

    it('does not modify original balances array', () => {
      const originalFree = mockBalances[0].free
      const deltas = [{ asset: 'USDT', delta: -5000 }]
      applyOptimisticDelta(mockBalances, deltas)

      expect(mockBalances[0].free).toBe(originalFree)
    })
  })

  describe('rollbackOptimistic', () => {
    it('restores exact prior values from snapshot', () => {
      const originalBalances: Balance[] = [
        { asset: 'USDT', free: 10000, locked: 0, total: 10000, venue: 'SPOT' },
        { asset: 'BTC', free: 0.5, locked: 0, total: 0.5, venue: 'SPOT' },
      ]

      const deltas = [{ asset: 'USDT', delta: -5000 }]
      const { updatedBalances, token } = applyOptimisticDelta(originalBalances, deltas)

      expect(updatedBalances.find(b => b.asset === 'USDT')?.free).toBe(5000)

      const restoredBalances = rollbackOptimistic(updatedBalances, token)

      expect(restoredBalances.find(b => b.asset === 'USDT')?.free).toBe(10000)
      expect(restoredBalances.find(b => b.asset === 'BTC')?.free).toBe(0.5)
    })

    it('returns new array, not reference to snapshot', () => {
      const originalBalances: Balance[] = [
        { asset: 'USDT', free: 1000, locked: 0, total: 1000, venue: 'SPOT' },
      ]

      const deltas = [{ asset: 'USDT', delta: -500 }]
      const { token } = applyOptimisticDelta(originalBalances, deltas)
      const restoredBalances = rollbackOptimistic([], token)

      expect(restoredBalances).not.toBe(token.snapshot)
      restoredBalances[0].free = 999
      expect(token.snapshot[0].free).toBe(1000)
    })
  })

  describe('canAffordOrder', () => {
    const balances: Balance[] = [
      { asset: 'USDT', free: 5000, locked: 0, total: 5000, venue: 'SPOT' },
      { asset: 'BTC', free: 0.1, locked: 0, total: 0.1, venue: 'SPOT' },
    ]

    it('returns true when BUY order is affordable', () => {
      const order: OrderFormValues = {
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.1,
      }
      expect(canAffordOrder(balances, order, 50000)).toBe(true)
    })

    it('returns false when BUY order exceeds balance', () => {
      const order: OrderFormValues = {
        symbol: 'BTCUSDT',
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.2,
      }
      expect(canAffordOrder(balances, order, 50000)).toBe(false)
    })

    it('returns true when SELL order is affordable', () => {
      const order: OrderFormValues = {
        symbol: 'BTCUSDT',
        side: 'SELL',
        type: 'MARKET',
        quantity: 0.1,
      }
      expect(canAffordOrder(balances, order, 50000)).toBe(true)
    })

    it('returns false when SELL order exceeds balance', () => {
      const order: OrderFormValues = {
        symbol: 'BTCUSDT',
        side: 'SELL',
        type: 'MARKET',
        quantity: 0.2,
      }
      expect(canAffordOrder(balances, order, 50000)).toBe(false)
    })

    it('returns false when asset not in balances', () => {
      const order: OrderFormValues = {
        symbol: 'ETHUSDT',
        side: 'SELL',
        type: 'MARKET',
        quantity: 1,
      }
      expect(canAffordOrder(balances, order, 3000)).toBe(false)
    })
  })
})
