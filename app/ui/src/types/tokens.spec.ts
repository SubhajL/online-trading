import { describe, expect, test } from 'vitest'
import { DEFAULT_TOKENS } from '../constants/defaultTokens'
import type { DesignTokens } from './tokens'

describe('DesignTokens', () => {
  test('type structure allows valid token objects', () => {
    const validTokens: DesignTokens = DEFAULT_TOKENS

    expect(validTokens.colors.primary[500]).toBe('hsl(220, 70%, 50%)')
    expect(validTokens.spacing[4]).toBe('16px')
    expect(validTokens.typography.fontSize.base).toBe('1rem')
    expect(validTokens.breakpoints.tablet).toBe('768px')
    expect(validTokens.constraints.maxScrollHeight).toBe('300px')
  })

  test('requires all color scale values 50-900', () => {
    const tokens: DesignTokens['colors']['primary'] = {
      50: 'test',
      100: 'test',
      200: 'test',
      300: 'test',
      400: 'test',
      500: 'test',
      600: 'test',
      700: 'test',
      800: 'test',
      900: 'test',
    }

    expect(Object.keys(tokens)).toHaveLength(10)
  })

  test('requires all spacing keys 0-10', () => {
    const spacing: DesignTokens['spacing'] = {
      0: '0',
      1: '4px',
      2: '8px',
      3: '12px',
      4: '16px',
      5: '24px',
      6: '32px',
      7: '48px',
      8: '64px',
      9: '96px',
      10: '128px',
    }

    expect(Object.keys(spacing)).toHaveLength(11)
  })

  test('chart tokens are all strings', () => {
    const chart: DesignTokens['chart'] = {
      bg: 'hsl(220, 18%, 9%)',
      text: 'hsl(220, 13%, 85%)',
      grid: 'hsl(220, 15%, 16%)',
      candleUp: 'hsl(142, 71%, 45%)',
      candleDown: 'hsl(0, 84%, 60%)',
    }

    expect(typeof chart.bg).toBe('string')
    expect(typeof chart.text).toBe('string')
    expect(typeof chart.grid).toBe('string')
    expect(typeof chart.candleUp).toBe('string')
    expect(typeof chart.candleDown).toBe('string')
  })

  test('breakpoints are all strings with px unit', () => {
    const breakpoints: DesignTokens['breakpoints'] = DEFAULT_TOKENS.breakpoints

    expect(breakpoints.mobile).toMatch(/^\d+px$/)
    expect(breakpoints.tablet).toMatch(/^\d+px$/)
    expect(breakpoints.desktop).toMatch(/^\d+px$/)
    expect(breakpoints.wide).toMatch(/^\d+px$/)
  })

  test('constraints are all strings with px unit', () => {
    const constraints: DesignTokens['constraints'] = DEFAULT_TOKENS.constraints

    expect(constraints.maxScrollHeight).toMatch(/^\d+px$/)
    expect(constraints.minTouchTarget).toMatch(/^\d+px$/)
  })
})
