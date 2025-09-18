import { describe, it, expect } from 'vitest'
import { formatCurrency, formatPercentage, formatNumber } from './formatters'

describe('formatCurrency', () => {
  it('formats positive numbers with USD symbol', () => {
    expect(formatCurrency(1234.56)).toBe('$1,234.56')
    expect(formatCurrency(1000000)).toBe('$1,000,000.00')
    expect(formatCurrency(0.99)).toBe('$0.99')
  })

  it('formats negative numbers', () => {
    expect(formatCurrency(-1234.56)).toBe('-$1,234.56')
    expect(formatCurrency(-0.99)).toBe('-$0.99')
  })

  it('handles zero', () => {
    expect(formatCurrency(0)).toBe('$0.00')
  })

  it('formats with custom currency', () => {
    expect(formatCurrency(1234.56, 'EUR')).toBe('€1,234.56')
    expect(formatCurrency(1234.56, 'GBP')).toBe('£1,234.56')
  })

  it('handles custom decimal places', () => {
    expect(formatCurrency(1234.567, 'USD', 3)).toBe('$1,234.567')
    expect(formatCurrency(1234.5, 'USD', 0)).toBe('$1,235')
  })
})

describe('formatPercentage', () => {
  it('formats positive percentages', () => {
    expect(formatPercentage(0.1234)).toBe('12.34%')
    expect(formatPercentage(1.5)).toBe('150.00%')
    expect(formatPercentage(0.001)).toBe('0.10%')
  })

  it('formats negative percentages', () => {
    expect(formatPercentage(-0.1234)).toBe('-12.34%')
    expect(formatPercentage(-1.5)).toBe('-150.00%')
  })

  it('handles zero', () => {
    expect(formatPercentage(0)).toBe('0.00%')
  })

  it('handles custom decimal places', () => {
    expect(formatPercentage(0.12345, 3)).toBe('12.345%')
    expect(formatPercentage(0.12345, 0)).toBe('12%')
  })
})

describe('formatNumber', () => {
  it('formats numbers with commas', () => {
    expect(formatNumber(1234567)).toBe('1,234,567')
    expect(formatNumber(1000)).toBe('1,000')
    expect(formatNumber(999)).toBe('999')
  })

  it('preserves decimal places', () => {
    expect(formatNumber(1234.56)).toBe('1,234.56')
    expect(formatNumber(1234.5)).toBe('1,234.5')
    expect(formatNumber(1234.0)).toBe('1,234')
  })

  it('handles negative numbers', () => {
    expect(formatNumber(-1234567)).toBe('-1,234,567')
    expect(formatNumber(-1234.56)).toBe('-1,234.56')
  })

  it('handles custom decimal places', () => {
    expect(formatNumber(1234.567, 2)).toBe('1,234.57')
    expect(formatNumber(1234, 2)).toBe('1,234.00')
    expect(formatNumber(1234.999, 0)).toBe('1,235')
  })
})
