import { describe, expect, test } from 'vitest'
import { DEFAULT_TOKENS } from './defaultTokens'
import type { DesignTokens } from '../types/tokens'

describe('DEFAULT_TOKENS', () => {
  test('conforms to DesignTokens type', () => {
    const _typecheck: DesignTokens = DEFAULT_TOKENS
    expect(_typecheck).toBeDefined()
  })

  test('has all required color scales', () => {
    expect(DEFAULT_TOKENS.colors.primary).toBeDefined()
    expect(DEFAULT_TOKENS.colors.success).toBeDefined()
    expect(DEFAULT_TOKENS.colors.warning).toBeDefined()
    expect(DEFAULT_TOKENS.colors.error).toBeDefined()
    expect(DEFAULT_TOKENS.colors.info).toBeDefined()
    expect(DEFAULT_TOKENS.colors.gray).toBeDefined()
  })

  test('primary color scale has all values 50-900', () => {
    const scale = DEFAULT_TOKENS.colors.primary
    expect(scale[50]).toBe('hsl(220, 70%, 95%)')
    expect(scale[100]).toBe('hsl(220, 70%, 90%)')
    expect(scale[200]).toBe('hsl(220, 70%, 80%)')
    expect(scale[300]).toBe('hsl(220, 70%, 70%)')
    expect(scale[400]).toBe('hsl(220, 70%, 60%)')
    expect(scale[500]).toBe('hsl(220, 70%, 50%)')
    expect(scale[600]).toBe('hsl(220, 70%, 45%)')
    expect(scale[700]).toBe('hsl(220, 70%, 40%)')
    expect(scale[800]).toBe('hsl(220, 70%, 30%)')
    expect(scale[900]).toBe('hsl(220, 70%, 20%)')
  })

  test('surface colors are defined', () => {
    expect(DEFAULT_TOKENS.colors.surface.base).toBe('hsl(220, 20%, 7%)')
    expect(DEFAULT_TOKENS.colors.surface.raised).toBe('hsl(220, 16%, 13%)')
    expect(DEFAULT_TOKENS.colors.surface.overlay).toBe('hsl(220, 15%, 16%)')
    expect(DEFAULT_TOKENS.colors.surface.hover).toBe('hsl(220, 14%, 19%)')
    expect(DEFAULT_TOKENS.colors.surface.input).toBe('hsl(220, 18%, 9%)')
  })

  test('text colors are defined', () => {
    expect(DEFAULT_TOKENS.colors.text.primary).toBe('hsl(220, 13%, 85%)')
    expect(DEFAULT_TOKENS.colors.text.secondary).toBe('hsl(220, 13%, 72%)')
    expect(DEFAULT_TOKENS.colors.text.muted).toBe('hsl(220, 13%, 58%)')
    expect(DEFAULT_TOKENS.colors.text.disabled).toBe('hsl(220, 13%, 42%)')
    expect(DEFAULT_TOKENS.colors.text.success).toBe('hsl(142, 71%, 55%)')
    expect(DEFAULT_TOKENS.colors.text.danger).toBe('hsl(0, 84%, 60%)')
    expect(DEFAULT_TOKENS.colors.text.warning).toBe('hsl(38, 92%, 55%)')
    expect(DEFAULT_TOKENS.colors.text.info).toBe('hsl(201, 90%, 52%)')
  })

  test('spacing scale has all values 0-10', () => {
    expect(DEFAULT_TOKENS.spacing[0]).toBe('0')
    expect(DEFAULT_TOKENS.spacing[1]).toBe('4px')
    expect(DEFAULT_TOKENS.spacing[2]).toBe('8px')
    expect(DEFAULT_TOKENS.spacing[3]).toBe('12px')
    expect(DEFAULT_TOKENS.spacing[4]).toBe('16px')
    expect(DEFAULT_TOKENS.spacing[5]).toBe('24px')
    expect(DEFAULT_TOKENS.spacing[6]).toBe('32px')
    expect(DEFAULT_TOKENS.spacing[7]).toBe('48px')
    expect(DEFAULT_TOKENS.spacing[8]).toBe('64px')
    expect(DEFAULT_TOKENS.spacing[9]).toBe('96px')
    expect(DEFAULT_TOKENS.spacing[10]).toBe('128px')
  })

  test('border radius values are defined', () => {
    expect(DEFAULT_TOKENS.radius.none).toBe('0')
    expect(DEFAULT_TOKENS.radius.sm).toBe('4px')
    expect(DEFAULT_TOKENS.radius.md).toBe('8px')
    expect(DEFAULT_TOKENS.radius.lg).toBe('16px')
    expect(DEFAULT_TOKENS.radius.full).toBe('9999px')
  })

  test('typography font sizes follow modular scale', () => {
    expect(DEFAULT_TOKENS.typography.fontSize.xs).toBe('0.75rem')
    expect(DEFAULT_TOKENS.typography.fontSize.sm).toBe('0.875rem')
    expect(DEFAULT_TOKENS.typography.fontSize.base).toBe('1rem')
    expect(DEFAULT_TOKENS.typography.fontSize.lg).toBe('1.125rem')
    expect(DEFAULT_TOKENS.typography.fontSize.xl).toBe('1.25rem')
    expect(DEFAULT_TOKENS.typography.fontSize['2xl']).toBe('1.563rem')
    expect(DEFAULT_TOKENS.typography.fontSize['3xl']).toBe('1.953rem')
    expect(DEFAULT_TOKENS.typography.fontSize['4xl']).toBe('2.441rem')
    expect(DEFAULT_TOKENS.typography.fontSize['5xl']).toBe('3.052rem')
  })

  test('font weights are numeric', () => {
    expect(DEFAULT_TOKENS.typography.fontWeight.normal).toBe(400)
    expect(DEFAULT_TOKENS.typography.fontWeight.medium).toBe(500)
    expect(DEFAULT_TOKENS.typography.fontWeight.semibold).toBe(600)
    expect(DEFAULT_TOKENS.typography.fontWeight.bold).toBe(700)
  })

  test('line heights are numeric ratios', () => {
    expect(DEFAULT_TOKENS.typography.lineHeight.tight).toBe(1.2)
    expect(DEFAULT_TOKENS.typography.lineHeight.normal).toBe(1.5)
    expect(DEFAULT_TOKENS.typography.lineHeight.relaxed).toBe(1.7)
  })

  test('chart tokens are defined', () => {
    expect(DEFAULT_TOKENS.chart.bg).toBe('hsl(220, 18%, 9%)')
    expect(DEFAULT_TOKENS.chart.text).toBe('hsl(220, 13%, 85%)')
    expect(DEFAULT_TOKENS.chart.grid).toBe('hsl(220, 15%, 16%)')
    expect(DEFAULT_TOKENS.chart.candleUp).toBe('hsl(142, 71%, 45%)')
    expect(DEFAULT_TOKENS.chart.candleDown).toBe('hsl(0, 84%, 60%)')
  })
})
