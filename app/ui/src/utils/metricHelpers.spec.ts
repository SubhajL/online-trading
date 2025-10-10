import { describe, test, expect } from 'vitest'
import { computeMetricTrend, deriveChangeClass } from './metricHelpers'
import type { DesignTokens } from '../types/tokens'

const mockTokens: DesignTokens = {
  colors: {
    primary: {
      50: 'hsl(220, 70%, 95%)',
      100: 'hsl(220, 70%, 90%)',
      200: 'hsl(220, 70%, 80%)',
      300: 'hsl(220, 70%, 70%)',
      400: 'hsl(220, 70%, 60%)',
      500: 'hsl(220, 70%, 50%)',
      600: 'hsl(220, 70%, 40%)',
      700: 'hsl(220, 70%, 30%)',
      800: 'hsl(220, 70%, 20%)',
      900: 'hsl(220, 70%, 10%)',
    },
    success: {
      50: 'hsl(140, 70%, 95%)',
      100: 'hsl(140, 70%, 90%)',
      200: 'hsl(140, 70%, 80%)',
      300: 'hsl(140, 70%, 70%)',
      400: 'hsl(140, 70%, 60%)',
      500: 'hsl(140, 70%, 50%)',
      600: 'hsl(140, 70%, 40%)',
      700: 'hsl(140, 70%, 30%)',
      800: 'hsl(140, 70%, 20%)',
      900: 'hsl(140, 70%, 10%)',
    },
    warning: {
      50: 'hsl(40, 90%, 95%)',
      100: 'hsl(40, 90%, 90%)',
      200: 'hsl(40, 90%, 80%)',
      300: 'hsl(40, 90%, 70%)',
      400: 'hsl(40, 90%, 60%)',
      500: 'hsl(40, 90%, 50%)',
      600: 'hsl(40, 90%, 40%)',
      700: 'hsl(40, 90%, 30%)',
      800: 'hsl(40, 90%, 20%)',
      900: 'hsl(40, 90%, 10%)',
    },
    error: {
      50: 'hsl(0, 70%, 95%)',
      100: 'hsl(0, 70%, 90%)',
      200: 'hsl(0, 70%, 80%)',
      300: 'hsl(0, 70%, 70%)',
      400: 'hsl(0, 70%, 60%)',
      500: 'hsl(0, 70%, 50%)',
      600: 'hsl(0, 70%, 40%)',
      700: 'hsl(0, 70%, 30%)',
      800: 'hsl(0, 70%, 20%)',
      900: 'hsl(0, 70%, 10%)',
    },
    info: {
      50: 'hsl(200, 70%, 95%)',
      100: 'hsl(200, 70%, 90%)',
      200: 'hsl(200, 70%, 80%)',
      300: 'hsl(200, 70%, 70%)',
      400: 'hsl(200, 70%, 60%)',
      500: 'hsl(200, 70%, 50%)',
      600: 'hsl(200, 70%, 40%)',
      700: 'hsl(200, 70%, 30%)',
      800: 'hsl(200, 70%, 20%)',
      900: 'hsl(200, 70%, 10%)',
    },
    gray: {
      50: 'hsl(0, 0%, 95%)',
      100: 'hsl(0, 0%, 90%)',
      200: 'hsl(0, 0%, 80%)',
      300: 'hsl(0, 0%, 70%)',
      400: 'hsl(0, 0%, 60%)',
      500: 'hsl(0, 0%, 50%)',
      600: 'hsl(0, 0%, 40%)',
      700: 'hsl(0, 0%, 30%)',
      800: 'hsl(0, 0%, 20%)',
      900: 'hsl(0, 0%, 10%)',
    },
    surface: {
      base: 'hsl(0, 0%, 100%)',
      raised: 'hsl(0, 0%, 98%)',
      overlay: 'hsl(0, 0%, 96%)',
      hover: 'hsl(0, 0%, 94%)',
      input: 'hsl(0, 0%, 97%)',
    },
    text: {
      primary: 'hsl(0, 0%, 10%)',
      secondary: 'hsl(0, 0%, 30%)',
      muted: 'hsl(0, 0%, 50%)',
      disabled: 'hsl(0, 0%, 70%)',
      inverse: 'hsl(0, 0%, 100%)',
      success: 'hsl(140, 70%, 30%)',
      danger: 'hsl(0, 70%, 40%)',
      warning: 'hsl(40, 90%, 30%)',
      info: 'hsl(200, 70%, 30%)',
    },
    border: {
      subtle: 'hsl(0, 0%, 90%)',
      default: 'hsl(0, 0%, 80%)',
      strong: 'hsl(0, 0%, 60%)',
      focus: 'hsl(220, 70%, 50%)',
    },
  },
  spacing: {
    0: '0',
    1: '4px',
    2: '8px',
    3: '12px',
    4: '16px',
    5: '20px',
    6: '24px',
    7: '28px',
    8: '32px',
    9: '36px',
    10: '40px',
  },
  radius: {
    none: '0',
    sm: '4px',
    md: '8px',
    lg: '12px',
    full: '9999px',
  },
  typography: {
    fontSize: {
      xs: '12px',
      sm: '14px',
      base: '16px',
      lg: '18px',
      xl: '20px',
      '2xl': '24px',
      '3xl': '30px',
      '4xl': '36px',
      '5xl': '48px',
    },
    fontWeight: {
      normal: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },
    lineHeight: {
      tight: 1.25,
      normal: 1.5,
      relaxed: 1.75,
    },
  },
  chart: {
    bg: 'hsl(0, 0%, 100%)',
    text: 'hsl(0, 0%, 10%)',
    grid: 'hsl(0, 0%, 90%)',
    candleUp: 'hsl(140, 70%, 50%)',
    candleDown: 'hsl(0, 70%, 50%)',
  },
}

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
