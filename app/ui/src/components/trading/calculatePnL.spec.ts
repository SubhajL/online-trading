import { describe, it, expect } from 'vitest'
import { calculatePnL } from './calculatePnL'

describe('calculatePnL', () => {
  describe('long positions (BUY)', () => {
    it('calculates profit for price increase', () => {
      const position = {
        side: 'BUY' as const,
        quantity: 0.1,
        entryPrice: 40000,
      }

      const result = calculatePnL(position, 42000)

      expect(result.pnl).toBe(200) // (42000 - 40000) * 0.1
      expect(result.pnlPercent).toBe(5) // ((42000 - 40000) / 40000) * 100
    })

    it('calculates loss for price decrease', () => {
      const position = {
        side: 'BUY' as const,
        quantity: 0.1,
        entryPrice: 40000,
      }

      const result = calculatePnL(position, 38000)

      expect(result.pnl).toBe(-200) // (38000 - 40000) * 0.1
      expect(result.pnlPercent).toBe(-5) // ((38000 - 40000) / 40000) * 100
    })

    it('calculates zero PnL when price unchanged', () => {
      const position = {
        side: 'BUY' as const,
        quantity: 1,
        entryPrice: 50000,
      }

      const result = calculatePnL(position, 50000)

      expect(result.pnl).toBe(0)
      expect(result.pnlPercent).toBe(0)
    })

    it('handles large quantities', () => {
      const position = {
        side: 'BUY' as const,
        quantity: 10,
        entryPrice: 40000,
      }

      const result = calculatePnL(position, 44000)

      expect(result.pnl).toBe(40000) // (44000 - 40000) * 10
      expect(result.pnlPercent).toBe(10) // ((44000 - 40000) / 40000) * 100
    })
  })

  describe('short positions (SELL)', () => {
    it('calculates profit for price decrease', () => {
      const position = {
        side: 'SELL' as const,
        quantity: 1,
        entryPrice: 2500,
      }

      const result = calculatePnL(position, 2400)

      expect(result.pnl).toBe(100) // (2500 - 2400) * 1
      expect(result.pnlPercent).toBe(4) // ((2500 - 2400) / 2500) * 100
    })

    it('calculates loss for price increase', () => {
      const position = {
        side: 'SELL' as const,
        quantity: 1,
        entryPrice: 2500,
      }

      const result = calculatePnL(position, 2600)

      expect(result.pnl).toBe(-100) // (2500 - 2600) * 1
      expect(result.pnlPercent).toBe(-4) // ((2500 - 2600) / 2500) * 100
    })

    it('handles fractional quantities', () => {
      const position = {
        side: 'SELL' as const,
        quantity: 0.5,
        entryPrice: 100,
      }

      const result = calculatePnL(position, 90)

      expect(result.pnl).toBe(5) // (100 - 90) * 0.5
      expect(result.pnlPercent).toBe(10) // ((100 - 90) / 100) * 100
    })
  })

  describe('edge cases', () => {
    it('handles very small price differences', () => {
      const position = {
        side: 'BUY' as const,
        quantity: 100,
        entryPrice: 0.001,
      }

      const result = calculatePnL(position, 0.0011)

      expect(result.pnl).toBeCloseTo(0.01, 6)
      expect(result.pnlPercent).toBeCloseTo(10, 6)
    })

    it('handles large price values', () => {
      const position = {
        side: 'BUY' as const,
        quantity: 0.001,
        entryPrice: 1000000,
      }

      const result = calculatePnL(position, 1100000)

      expect(result.pnl).toBe(100)
      expect(result.pnlPercent).toBe(10)
    })

    it('handles zero quantity edge case', () => {
      const position = {
        side: 'BUY' as const,
        quantity: 0,
        entryPrice: 100,
      }

      const result = calculatePnL(position, 110)

      expect(result.pnl).toBe(0)
      expect(result.pnlPercent).toBe(10)
    })
  })
})
