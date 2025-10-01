import { describe, test, expect } from 'vitest'
import { computeMetricTrend, deriveChangeClass } from './metricHelpers'

describe('computeMetricTrend', () => {
  test('returns positive class for values above threshold', () => {
    expect(computeMetricTrend(1000, 500)).toBe('trend-up')
    expect(computeMetricTrend(100, 0)).toBe('trend-up')
  })

  test('returns negative class for values below threshold', () => {
    expect(computeMetricTrend(-500, 0)).toBe('trend-down')
    expect(computeMetricTrend(100, 200)).toBe('trend-down')
  })

  test('returns neutral class for values equal to threshold', () => {
    expect(computeMetricTrend(500, 500)).toBe('trend-neutral')
    expect(computeMetricTrend(0, 0)).toBe('trend-neutral')
  })

  test('handles edge case of zero comparison', () => {
    expect(computeMetricTrend(0, 1)).toBe('trend-down')
    expect(computeMetricTrend(1, 0)).toBe('trend-up')
  })
})

describe('deriveChangeClass', () => {
  test('returns change-positive for strings starting with plus', () => {
    expect(deriveChangeClass('+5.2%')).toBe('change-positive')
    expect(deriveChangeClass('+0.01%')).toBe('change-positive')
  })

  test('returns change-negative for strings starting with minus', () => {
    expect(deriveChangeClass('-3.4%')).toBe('change-negative')
    expect(deriveChangeClass('-10%')).toBe('change-negative')
  })

  test('returns change-neutral for strings without sign', () => {
    expect(deriveChangeClass('0%')).toBe('change-neutral')
    expect(deriveChangeClass('No change')).toBe('change-neutral')
  })

  test('handles empty string as neutral', () => {
    expect(deriveChangeClass('')).toBe('change-neutral')
  })
})
