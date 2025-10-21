import { describe, expect, test } from 'vitest'
import {
  createChartThemeFromTokens,
  mapRouteToNavTokens,
  getVolumeBarColor,
  getTouchTargetPadding,
  getIndicatorColor,
  getErrorBannerStyles,
  ensureFocusVisibleStyles,
  getSpinnerStyles,
} from './tokenHelpers'
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

describe('getVolumeBarColor', () => {
  test('bullish candle maps to success color', () => {
    const candle = { open: 100, close: 110, high: 115, low: 95, volume: 1000 }
    const result = getVolumeBarColor(candle, DEFAULT_TOKENS)
    expect(result).toBe(DEFAULT_TOKENS.colors.success[500])
  })

  test('bearish candle maps to error color', () => {
    const candle = { open: 110, close: 100, high: 115, low: 95, volume: 1000 }
    const result = getVolumeBarColor(candle, DEFAULT_TOKENS)
    expect(result).toBe(DEFAULT_TOKENS.colors.error[500])
  })

  test('flat candle falls back to neutral', () => {
    const candle = { open: 100, close: 100, high: 105, low: 95, volume: 1000 }
    const result = getVolumeBarColor(candle, DEFAULT_TOKENS)
    expect(result).toBe(DEFAULT_TOKENS.colors.gray[400])
  })
})

describe('getTouchTargetPadding', () => {
  test('returns padding yielding forty four pixels', () => {
    const result = getTouchTargetPadding(DEFAULT_TOKENS)
    expect(result).toEqual({
      paddingTop: DEFAULT_TOKENS.spacing[3],
      paddingBottom: DEFAULT_TOKENS.spacing[3],
    })
  })
})

describe('getIndicatorColor', () => {
  test('maps EMA to error token', () => {
    const color = getIndicatorColor('EMA', DEFAULT_TOKENS)
    expect(color).toBe(DEFAULT_TOKENS.colors.error[500])
  })

  test('maps SMA to success token', () => {
    const color = getIndicatorColor('SMA', DEFAULT_TOKENS)
    expect(color).toBe(DEFAULT_TOKENS.colors.success[500])
  })

  test('maps RSI to info token', () => {
    const color = getIndicatorColor('RSI', DEFAULT_TOKENS)
    expect(color).toBe(DEFAULT_TOKENS.colors.info[500])
  })

  test('maps MACD to warning token', () => {
    const color = getIndicatorColor('MACD', DEFAULT_TOKENS)
    expect(color).toBe(DEFAULT_TOKENS.colors.warning[500])
  })

  test('maps BB to primary token', () => {
    const color = getIndicatorColor('BB', DEFAULT_TOKENS)
    expect(color).toBe(DEFAULT_TOKENS.colors.primary[500])
  })

  test('falls back to neutral token for unknown indicators', () => {
    const color = getIndicatorColor('VOLUME', DEFAULT_TOKENS)
    expect(color).toBe(DEFAULT_TOKENS.colors.gray[500])
  })
})

describe('getErrorBannerStyles', () => {
  test('returns danger palette for error severity', () => {
    const styles = getErrorBannerStyles('error', DEFAULT_TOKENS)
    expect(styles.backgroundColor).toBe(DEFAULT_TOKENS.colors.error[50])
    expect(styles.color).toBe(DEFAULT_TOKENS.colors.text.danger)
    expect(styles.borderColor).toBe(DEFAULT_TOKENS.colors.error[200])
  })

  test('returns warning palette for warning severity', () => {
    const styles = getErrorBannerStyles('warning', DEFAULT_TOKENS)
    expect(styles.backgroundColor).toBe(DEFAULT_TOKENS.colors.warning[50])
    expect(styles.color).toBe(DEFAULT_TOKENS.colors.text.warning)
    expect(styles.borderColor).toBe(DEFAULT_TOKENS.colors.warning[200])
  })

  test('returns info palette for info severity', () => {
    const styles = getErrorBannerStyles('info', DEFAULT_TOKENS)
    expect(styles.backgroundColor).toBe(DEFAULT_TOKENS.colors.info[50])
    expect(styles.color).toBe(DEFAULT_TOKENS.colors.text.info)
    expect(styles.borderColor).toBe(DEFAULT_TOKENS.colors.info[200])
  })

  test('includes padding from tokens', () => {
    const styles = getErrorBannerStyles('error', DEFAULT_TOKENS)
    expect(styles.padding).toBe(DEFAULT_TOKENS.spacing[4])
  })

  test('includes border radius from tokens', () => {
    const styles = getErrorBannerStyles('error', DEFAULT_TOKENS)
    expect(styles.borderRadius).toBe(DEFAULT_TOKENS.radius.md)
  })
})

describe('ensureFocusVisibleStyles', () => {
  test('provides outline using focus token', () => {
    const styles = ensureFocusVisibleStyles(DEFAULT_TOKENS)
    expect(styles.outline).toContain(DEFAULT_TOKENS.colors.border.focus)
  })

  test('includes default width of 2px', () => {
    const styles = ensureFocusVisibleStyles(DEFAULT_TOKENS)
    expect(styles.outline).toContain('2px')
  })

  test('includes default offset of 2px', () => {
    const styles = ensureFocusVisibleStyles(DEFAULT_TOKENS)
    expect(styles.outlineOffset).toBe('2px')
  })

  test('allows custom width', () => {
    const styles = ensureFocusVisibleStyles(DEFAULT_TOKENS, '3px')
    expect(styles.outline).toContain('3px')
  })

  test('allows custom offset', () => {
    const styles = ensureFocusVisibleStyles(DEFAULT_TOKENS, '2px', '4px')
    expect(styles.outlineOffset).toBe('4px')
  })
})

describe('getSpinnerStyles', () => {
  test('small size uses token spacing', () => {
    const styles = getSpinnerStyles('sm', 'primary', DEFAULT_TOKENS)
    expect(styles.width).toBe('16px')
    expect(styles.height).toBe('16px')
    expect(styles.borderWidth).toBe('2px')
  })

  test('medium size uses larger dimensions', () => {
    const styles = getSpinnerStyles('md', 'primary', DEFAULT_TOKENS)
    expect(styles.width).toBe('24px')
    expect(styles.height).toBe('24px')
    expect(styles.borderWidth).toBe('3px')
  })

  test('large size uses largest dimensions', () => {
    const styles = getSpinnerStyles('lg', 'primary', DEFAULT_TOKENS)
    expect(styles.width).toBe('32px')
    expect(styles.height).toBe('32px')
    expect(styles.borderWidth).toBe('4px')
  })

  test('primary variant uses success token', () => {
    const styles = getSpinnerStyles('md', 'primary', DEFAULT_TOKENS)
    expect(styles.borderColor).toContain(DEFAULT_TOKENS.colors.success[500])
  })

  test('secondary variant uses primary token', () => {
    const styles = getSpinnerStyles('md', 'secondary', DEFAULT_TOKENS)
    expect(styles.borderColor).toContain(DEFAULT_TOKENS.colors.primary[500])
  })

  test('white variant uses inverse text token', () => {
    const styles = getSpinnerStyles('md', 'white', DEFAULT_TOKENS)
    expect(styles.borderColor).toContain(DEFAULT_TOKENS.colors.text.inverse)
  })

  test('border color includes transparent segments', () => {
    const styles = getSpinnerStyles('md', 'primary', DEFAULT_TOKENS)
    expect(styles.borderColor).toContain('transparent')
  })
})
