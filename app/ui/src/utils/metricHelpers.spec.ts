import { describe, test, expect } from 'vitest'
import { DEFAULT_TOKENS } from '../constants/defaultTokens'
import { computeMetricTrend, deriveChangeClass } from './metricHelpers'
import type { DesignTokens } from '../types/tokens'

const mockTokens: DesignTokens = DEFAULT_TOKENS

describe('computeMetricTrend', () => {
  test('returns success color for values above threshold', () => {
    expect(computeMetricTrend(1000, 500, mockTokens)).toBe(mockTokens.colors.text.success)
    expect(computeMetricTrend(100, 0, mockTokens)).toBe(mockTokens.colors.text.success)
  })

  test('returns danger color for values below threshold', () => {
    expect(computeMetricTrend(-500, 0, mockTokens)).toBe(mockTokens.colors.text.danger)
    expect(computeMetricTrend(100, 200, mockTokens)).toBe(mockTokens.colors.text.danger)
  })

  test('returns muted color for values equal to threshold', () => {
    expect(computeMetricTrend(500, 500, mockTokens)).toBe(mockTokens.colors.text.muted)
    expect(computeMetricTrend(0, 0, mockTokens)).toBe(mockTokens.colors.text.muted)
  })

  test('handles edge case of zero comparison', () => {
    expect(computeMetricTrend(0, 1, mockTokens)).toBe(mockTokens.colors.text.danger)
    expect(computeMetricTrend(1, 0, mockTokens)).toBe(mockTokens.colors.text.success)
  })

  test('uses default threshold of 0 when not provided', () => {
    expect(computeMetricTrend(5, undefined, mockTokens)).toBe(mockTokens.colors.text.success)
    expect(computeMetricTrend(-5, undefined, mockTokens)).toBe(mockTokens.colors.text.danger)
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
