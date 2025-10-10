import { describe, test, expect } from 'vitest'
import { deriveOrderStatusTheme, formatPositionDelta, isCancelableStatus } from './tradingHelpers'

describe('deriveOrderStatusTheme', () => {
  test('returns theme for NEW status', () => {
    const theme = deriveOrderStatusTheme('NEW')
    expect(theme).toEqual({ statusClass: 'new' })
  })

  test('returns theme for PARTIALLY_FILLED status', () => {
    const theme = deriveOrderStatusTheme('PARTIALLY_FILLED')
    expect(theme).toEqual({ statusClass: 'partially-filled' })
  })

  test('returns theme for FILLED status', () => {
    const theme = deriveOrderStatusTheme('FILLED')
    expect(theme).toEqual({ statusClass: 'filled' })
  })

  test('returns theme for CANCELED status', () => {
    const theme = deriveOrderStatusTheme('CANCELED')
    expect(theme).toEqual({ statusClass: 'canceled' })
  })

  test('returns theme for REJECTED status', () => {
    const theme = deriveOrderStatusTheme('REJECTED')
    expect(theme).toEqual({ statusClass: 'rejected' })
  })

  test('returns theme for EXPIRED status', () => {
    const theme = deriveOrderStatusTheme('EXPIRED')
    expect(theme).toEqual({ statusClass: 'expired' })
  })
})

describe('formatPositionDelta', () => {
  test('returns positive class for profitable position', () => {
    const result = formatPositionDelta(1500, 12.5)
    expect(result).toEqual({
      deltaClass: 'delta-positive',
      displayValue: '+$1,500.00 (+12.50%)',
      formattedPnl: '+$1,500.00',
      formattedPnlPercent: '+12.50%',
    })
  })

  test('returns negative class for losing position', () => {
    const result = formatPositionDelta(-850.5, -5.75)
    expect(result).toEqual({
      deltaClass: 'delta-negative',
      displayValue: '-$850.50 (-5.75%)',
      formattedPnl: '-$850.50',
      formattedPnlPercent: '-5.75%',
    })
  })

  test('returns neutral class for breakeven position', () => {
    const result = formatPositionDelta(0, 0)
    expect(result).toEqual({
      deltaClass: 'delta-neutral',
      displayValue: '$0.00 (0.00%)',
      formattedPnl: '$0.00',
      formattedPnlPercent: '0.00%',
    })
  })

  test('handles small positive gains correctly', () => {
    const result = formatPositionDelta(0.25, 0.01)
    expect(result).toEqual({
      deltaClass: 'delta-positive',
      displayValue: '+$0.25 (+0.01%)',
      formattedPnl: '+$0.25',
      formattedPnlPercent: '+0.01%',
    })
  })

  test('handles large negative losses correctly', () => {
    const result = formatPositionDelta(-12345.67, -45.3)
    expect(result).toEqual({
      deltaClass: 'delta-negative',
      displayValue: '-$12,345.67 (-45.30%)',
      formattedPnl: '-$12,345.67',
      formattedPnlPercent: '-45.30%',
    })
  })
})

describe('isCancelableStatus', () => {
  test('returns true for NEW status', () => {
    expect(isCancelableStatus('NEW')).toBe(true)
  })

  test('returns true for PARTIALLY_FILLED status', () => {
    expect(isCancelableStatus('PARTIALLY_FILLED')).toBe(true)
  })

  test('returns false for FILLED status', () => {
    expect(isCancelableStatus('FILLED')).toBe(false)
  })

  test('returns false for CANCELED status', () => {
    expect(isCancelableStatus('CANCELED')).toBe(false)
  })

  test('returns false for REJECTED status', () => {
    expect(isCancelableStatus('REJECTED')).toBe(false)
  })

  test('returns false for EXPIRED status', () => {
    expect(isCancelableStatus('EXPIRED')).toBe(false)
  })
})
