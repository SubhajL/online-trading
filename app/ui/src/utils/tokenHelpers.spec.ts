import { describe, expect, test } from 'vitest'
import { createChartThemeFromTokens, mapRouteToNavTokens } from './tokenHelpers'
import { DEFAULT_TOKENS } from '../constants/defaultTokens'
import type { ChartTheme } from '../types/chartTheme'

describe('createChartThemeFromTokens', () => {
  test('sets layout background from chart.bg token', () => {
    const theme = createChartThemeFromTokens(DEFAULT_TOKENS)
    expect(theme.layout.background.color).toBe(DEFAULT_TOKENS.chart.bg)
  })

  test('sets grid vertLines color from chart.grid', () => {
    const theme = createChartThemeFromTokens(DEFAULT_TOKENS)
    expect(theme.grid.vertLines.color).toBe(DEFAULT_TOKENS.chart.grid)
  })

  test('sets grid horzLines color from chart.grid', () => {
    const theme = createChartThemeFromTokens(DEFAULT_TOKENS)
    expect(theme.grid.horzLines.color).toBe(DEFAULT_TOKENS.chart.grid)
  })

  test('sets timeScale borderColor from border.default', () => {
    const theme = createChartThemeFromTokens(DEFAULT_TOKENS)
    expect(theme.timeScale.borderColor).toBe(DEFAULT_TOKENS.colors.border.default)
  })

  test('sets rightPriceScale borderColor from border.default', () => {
    const theme = createChartThemeFromTokens(DEFAULT_TOKENS)
    expect(theme.rightPriceScale.borderColor).toBe(DEFAULT_TOKENS.colors.border.default)
  })

  test('uses chart.text for layout textColor', () => {
    const theme = createChartThemeFromTokens(DEFAULT_TOKENS)
    expect(theme.layout.textColor).toBe(DEFAULT_TOKENS.chart.text)
  })

  test('returns valid ChartTheme object', () => {
    const theme = createChartThemeFromTokens(DEFAULT_TOKENS)
    const _typecheck: ChartTheme = theme
    expect(_typecheck).toBeDefined()
  })
})

describe('mapRouteToNavTokens', () => {
  test('returns active nav styles with primary colors', () => {
    const result = mapRouteToNavTokens(true, DEFAULT_TOKENS)
    expect(result.backgroundColor).toBe(DEFAULT_TOKENS.colors.primary[50])
  })

  test('returns active nav styles with border accent', () => {
    const result = mapRouteToNavTokens(true, DEFAULT_TOKENS)
    expect(result.borderLeft).toBe(`3px solid ${DEFAULT_TOKENS.colors.primary[500]}`)
  })

  test('returns active nav styles with primary text', () => {
    const result = mapRouteToNavTokens(true, DEFAULT_TOKENS)
    expect(result.color).toBe(DEFAULT_TOKENS.colors.primary[700])
  })

  test('returns inactive nav styles with transparent background', () => {
    const result = mapRouteToNavTokens(false, DEFAULT_TOKENS)
    expect(result.backgroundColor).toBe('transparent')
  })

  test('returns inactive nav styles with secondary text', () => {
    const result = mapRouteToNavTokens(false, DEFAULT_TOKENS)
    expect(result.color).toBe(DEFAULT_TOKENS.colors.text.secondary)
  })

  test('returns inactive nav styles with transparent border', () => {
    const result = mapRouteToNavTokens(false, DEFAULT_TOKENS)
    expect(result.borderLeft).toBe('3px solid transparent')
  })
})
