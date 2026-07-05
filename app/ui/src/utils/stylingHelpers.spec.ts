import { describe, expect, test } from 'vitest'
import type { DesignTokens } from '../types/tokens'
import { DEFAULT_TOKENS } from '../constants/defaultTokens'
import {
  getToolbarVariantStyles,
  getSpinnerStyle,
  composeErrorBannerStyles,
  buildPageContainerStyle,
  getAutoTradingToggleStyles,
  getIndicatorColor,
  applyFocusVisible,
  getChartButtonStyles,
  getIconButtonStyles,
  getOverlayStyles,
  getSpinnerStyles,
  getIconSizeStyles,
  getPanelContainerStyles,
  getPanelHeaderStyles,
  getPanelItemStyles,
  getSmcLabelStyles,
  getSmcLineStyles,
  getZoneOverlayStyles,
  getZoneLabelStyles,
  getZoneBadgeStyles,
  getAbsoluteFillStyles,
  getPageHeadingStyles,
  getTabButtonStyles,
} from './stylingHelpers'

const mockTokens: DesignTokens = DEFAULT_TOKENS

describe('getToolbarVariantStyles', () => {
  test('returns primary variant classes', () => {
    const result = getToolbarVariantStyles('primary', mockTokens)
    expect(result).toEqual({
      backgroundColor: mockTokens.colors.primary[500],
      color: mockTokens.colors.text.inverse,
    })
  })

  test('returns secondary variant classes', () => {
    const result = getToolbarVariantStyles('secondary', mockTokens)
    expect(result).toEqual({
      backgroundColor: mockTokens.colors.gray[200],
      color: mockTokens.colors.text.primary,
    })
  })

  test('returns success variant classes', () => {
    const result = getToolbarVariantStyles('success', mockTokens)
    expect(result).toEqual({
      backgroundColor: mockTokens.colors.success[500],
      color: mockTokens.colors.text.inverse,
    })
  })

  test('returns error variant classes', () => {
    const result = getToolbarVariantStyles('error', mockTokens)
    expect(result).toEqual({
      backgroundColor: mockTokens.colors.error[500],
      color: mockTokens.colors.text.inverse,
    })
  })

  test('defaults to primary for unknown variant', () => {
    const result = getToolbarVariantStyles('unknown' as any, mockTokens)
    expect(result).toEqual({
      backgroundColor: mockTokens.colors.primary[500],
      color: mockTokens.colors.text.inverse,
    })
  })
})

describe('getSpinnerStyle', () => {
  test('returns small spinner style', () => {
    const result = getSpinnerStyle('sm', mockTokens)
    expect(result).toEqual({
      width: '16px',
      height: '16px',
      borderWidth: '2px',
      borderColor: `${mockTokens.colors.primary[500]} transparent transparent transparent`,
    })
  })

  test('returns medium spinner style', () => {
    const result = getSpinnerStyle('md', mockTokens)
    expect(result).toEqual({
      width: '24px',
      height: '24px',
      borderWidth: '3px',
      borderColor: `${mockTokens.colors.primary[500]} transparent transparent transparent`,
    })
  })

  test('returns large spinner style', () => {
    const result = getSpinnerStyle('lg', mockTokens)
    expect(result).toEqual({
      width: '32px',
      height: '32px',
      borderWidth: '4px',
      borderColor: `${mockTokens.colors.primary[500]} transparent transparent transparent`,
    })
  })

  test('applies custom color', () => {
    const result = getSpinnerStyle('md', mockTokens, 'hsl(0, 70%, 50%)')
    expect(result.borderColor).toBe('hsl(0, 70%, 50%) transparent transparent transparent')
  })
})

describe('composeErrorBannerStyles', () => {
  test('returns error banner style with icon', () => {
    const result = composeErrorBannerStyles(true, mockTokens, 'error')
    expect(result).toEqual({
      backgroundColor: mockTokens.colors.error[50],
      color: mockTokens.colors.text.danger,
      padding: mockTokens.spacing[4],
      borderRadius: mockTokens.radius.md,
      border: `1px solid ${mockTokens.colors.error[200]}`,
      display: 'flex',
      alignItems: 'center',
      gap: mockTokens.spacing[3],
    })
  })

  test('returns error banner style without icon', () => {
    const result = composeErrorBannerStyles(false, mockTokens, 'error')
    expect(result).toEqual({
      backgroundColor: mockTokens.colors.error[50],
      color: mockTokens.colors.text.danger,
      padding: mockTokens.spacing[4],
      borderRadius: mockTokens.radius.md,
      border: `1px solid ${mockTokens.colors.error[200]}`,
      display: 'block',
      alignItems: undefined,
      gap: undefined,
    })
  })

  test('error severity returns danger palette', () => {
    const result = composeErrorBannerStyles(false, mockTokens, 'error')
    expect(result.backgroundColor).toBe(mockTokens.colors.error[50])
    expect(result.color).toBe(mockTokens.colors.text.danger)
    expect(result.border).toBe(`1px solid ${mockTokens.colors.error[200]}`)
  })

  test('warning severity returns warning palette', () => {
    const result = composeErrorBannerStyles(false, mockTokens, 'warning')
    expect(result.backgroundColor).toBe(mockTokens.colors.warning[50])
    expect(result.color).toBe(mockTokens.colors.text.warning)
    expect(result.border).toBe(`1px solid ${mockTokens.colors.warning[200]}`)
  })

  test('info severity returns info palette', () => {
    const result = composeErrorBannerStyles(false, mockTokens, 'info')
    expect(result.backgroundColor).toBe(mockTokens.colors.info[50])
    expect(result.color).toBe(mockTokens.colors.text.info)
    expect(result.border).toBe(`1px solid ${mockTokens.colors.info[200]}`)
  })

  test('defaults to error when severity omitted for backward compat', () => {
    const result = composeErrorBannerStyles(false, mockTokens)
    expect(result.backgroundColor).toBe(mockTokens.colors.error[50])
    expect(result.color).toBe(mockTokens.colors.text.danger)
  })
})

describe('buildPageContainerStyle', () => {
  test('returns page container with default padding', () => {
    const result = buildPageContainerStyle(mockTokens)
    expect(result).toEqual({
      padding: mockTokens.spacing[8],
      backgroundColor: mockTokens.colors.surface.base,
      maxWidth: undefined,
      margin: undefined,
    })
  })

  test('returns page container with custom padding', () => {
    const result = buildPageContainerStyle(mockTokens, 6)
    expect(result).toEqual({
      padding: mockTokens.spacing[6],
      backgroundColor: mockTokens.colors.surface.base,
      maxWidth: undefined,
      margin: undefined,
    })
  })

  test('returns page container with zero padding', () => {
    const result = buildPageContainerStyle(mockTokens, 0)
    expect(result).toEqual({
      padding: mockTokens.spacing[0],
      backgroundColor: mockTokens.colors.surface.base,
      maxWidth: undefined,
      margin: undefined,
    })
  })

  test('applies maxWidth sm with auto margin', () => {
    const result = buildPageContainerStyle(mockTokens, 8, 'sm')
    expect(result.maxWidth).toBe('640px')
    expect(result.margin).toBe('0 auto')
  })

  test('applies maxWidth md with auto margin', () => {
    const result = buildPageContainerStyle(mockTokens, 8, 'md')
    expect(result.maxWidth).toBe('768px')
    expect(result.margin).toBe('0 auto')
  })

  test('applies maxWidth lg with auto margin', () => {
    const result = buildPageContainerStyle(mockTokens, 8, 'lg')
    expect(result.maxWidth).toBe('1024px')
    expect(result.margin).toBe('0 auto')
  })

  test('applies maxWidth xl with auto margin', () => {
    const result = buildPageContainerStyle(mockTokens, 8, 'xl')
    expect(result.maxWidth).toBe('1280px')
    expect(result.margin).toBe('0 auto')
  })

  test('applies maxWidth full without auto margin', () => {
    const result = buildPageContainerStyle(mockTokens, 8, 'full')
    expect(result.maxWidth).toBe('100%')
    expect(result.margin).toBeUndefined()
  })
})

describe('getAutoTradingToggleStyles', () => {
  test('returns enabled palette from success tokens', () => {
    const result = getAutoTradingToggleStyles(mockTokens, 'enabled')
    expect(result.backgroundColor).toBe(mockTokens.colors.success[50])
    expect(result.color).toBe(mockTokens.colors.text.success)
    expect(result.borderColor).toBe(mockTokens.colors.success[300])
  })

  test('returns disabled palette from warning tokens', () => {
    const result = getAutoTradingToggleStyles(mockTokens, 'disabled')
    expect(result.backgroundColor).toBe(mockTokens.colors.gray[100])
    expect(result.color).toBe(mockTokens.colors.text.muted)
    expect(result.borderColor).toBe(mockTokens.colors.gray[300])
  })

  test('returns error palette from error tokens', () => {
    const result = getAutoTradingToggleStyles(mockTokens, 'error')
    expect(result.backgroundColor).toBe(mockTokens.colors.error[50])
    expect(result.color).toBe(mockTokens.colors.text.danger)
    expect(result.borderColor).toBe(mockTokens.colors.error[300])
  })

  test('applies shared border radius from tokens', () => {
    const result = getAutoTradingToggleStyles(mockTokens, 'enabled')
    expect(result.borderRadius).toBe(mockTokens.radius.md)
  })
})

describe('getIndicatorColor', () => {
  test('maps EMA to error token color', () => {
    const result = getIndicatorColor('EMA', mockTokens)
    expect(result).toBe(mockTokens.colors.error[500])
  })

  test('maps SMA to success token color', () => {
    const result = getIndicatorColor('SMA', mockTokens)
    expect(result).toBe(mockTokens.colors.success[500])
  })

  test('maps RSI to info token color', () => {
    const result = getIndicatorColor('RSI', mockTokens)
    expect(result).toBe(mockTokens.colors.info[500])
  })

  test('maps MACD to warning token color', () => {
    const result = getIndicatorColor('MACD', mockTokens)
    expect(result).toBe(mockTokens.colors.warning[500])
  })

  test('maps BB to primary token color', () => {
    const result = getIndicatorColor('BB', mockTokens)
    expect(result).toBe(mockTokens.colors.primary[500])
  })

  test('falls back to neutral token for unknown indicator', () => {
    const result = getIndicatorColor('UNKNOWN' as any, mockTokens)
    expect(result).toBe(mockTokens.colors.gray[500])
  })
})

describe('applyFocusVisible', () => {
  test('returns focus-visible styles with border focus color', () => {
    const result = applyFocusVisible(mockTokens)
    expect(result).toEqual({
      outline: `2px solid ${mockTokens.colors.border.focus}`,
      outlineOffset: '2px',
    })
  })

  test('uses custom outline width when provided', () => {
    const result = applyFocusVisible(mockTokens, '3px')
    expect(result.outline).toBe(`3px solid ${mockTokens.colors.border.focus}`)
  })

  test('uses custom outline offset when provided', () => {
    const result = applyFocusVisible(mockTokens, '2px', '4px')
    expect(result.outlineOffset).toBe('4px')
  })
})

describe('getChartButtonStyles', () => {
  test('returns active state with primary background and white text', () => {
    const result = getChartButtonStyles(true, mockTokens)
    expect(result).toEqual({
      backgroundColor: mockTokens.colors.primary[600],
      color: mockTokens.colors.text.inverse,
      padding: `${mockTokens.spacing[2]} ${mockTokens.spacing[3]}`,
      borderRadius: mockTokens.radius.md,
      border: 'none',
      cursor: 'pointer',
      transition: 'background-color 0.2s ease, color 0.2s ease',
    })
  })

  test('returns inactive state with gray background and muted text', () => {
    const result = getChartButtonStyles(false, mockTokens)
    expect(result).toEqual({
      backgroundColor: mockTokens.colors.gray[800],
      color: mockTokens.colors.gray[300],
      padding: `${mockTokens.spacing[2]} ${mockTokens.spacing[3]}`,
      borderRadius: mockTokens.radius.md,
      border: 'none',
      cursor: 'pointer',
      transition: 'background-color 0.2s ease, color 0.2s ease',
    })
  })

  test('includes padding from spacing tokens', () => {
    const result = getChartButtonStyles(false, mockTokens)
    expect(result.padding).toBe(`${mockTokens.spacing[2]} ${mockTokens.spacing[3]}`)
  })

  test('includes borderRadius from radius tokens', () => {
    const result = getChartButtonStyles(false, mockTokens)
    expect(result.borderRadius).toBe(mockTokens.radius.md)
  })

  test('includes transition for smooth state changes', () => {
    const result = getChartButtonStyles(false, mockTokens)
    expect(result.transition).toBe('background-color 0.2s ease, color 0.2s ease')
  })

  test('uses token values not hex literals', () => {
    const result = getChartButtonStyles(true, mockTokens)
    expect(result.backgroundColor).not.toMatch(/#[0-9a-fA-F]{6}/)
    expect(result.color).not.toMatch(/#[0-9a-fA-F]{6}/)
  })
})

describe('getIconButtonStyles', () => {
  test('returns default icon button styles using muted text', () => {
    const styles = getIconButtonStyles(mockTokens, 'default')
    expect(styles.color).toBe(mockTokens.colors.text.muted)
    expect(styles.backgroundColor).toBe('transparent')
    expect(styles.border).toBe('none')
  })

  test('returns hover icon button styles using primary token', () => {
    const styles = getIconButtonStyles(mockTokens, 'hover')
    expect(styles.color).toBe(mockTokens.colors.text.primary)
  })
})

describe('getOverlayStyles', () => {
  test('returns overlay styles with dark surface token and flex centering', () => {
    const styles = getOverlayStyles(mockTokens)
    expect(styles.backgroundColor).toBe(`${mockTokens.colors.surface.base}cc`)
    expect(styles.display).toBe('flex')
    expect(styles.alignItems).toBe('center')
    expect(styles.justifyContent).toBe('center')
  })
})

describe('getSpinnerStyles', () => {
  test('returns spinner size using spacing tokens', () => {
    const styles = getSpinnerStyles('sm', mockTokens)
    expect(styles.width).toBe(mockTokens.spacing[4])
    expect(styles.height).toBe(mockTokens.spacing[4])
  })

  test('returns spinner border color from primary tokens by default', () => {
    const styles = getSpinnerStyles('md', mockTokens)
    expect(styles.borderColor).toBe(mockTokens.colors.primary[500])
  })

  test('returns spinner border color from success tokens when variant provided', () => {
    const styles = getSpinnerStyles('lg', mockTokens, 'success')
    expect(styles.borderColor).toBe(mockTokens.colors.success[500])
  })
})

// New helpers
describe('getIconSizeStyles', () => {
  test('returns sm width/height from spacing tokens', () => {
    const styles = getIconSizeStyles('sm', mockTokens)
    expect(styles).toEqual({ width: mockTokens.spacing[3], height: mockTokens.spacing[3] })
  })

  test('returns md width/height from spacing tokens', () => {
    const styles = getIconSizeStyles('md', mockTokens)
    expect(styles).toEqual({ width: mockTokens.spacing[4], height: mockTokens.spacing[4] })
  })

  test('returns lg width/height from spacing tokens', () => {
    const styles = getIconSizeStyles('lg', mockTokens)
    expect(styles).toEqual({ width: mockTokens.spacing[5], height: mockTokens.spacing[5] })
  })
})

describe('panel styles', () => {
  test('getPanelContainerStyles uses surface and border tokens', () => {
    const s = getPanelContainerStyles(mockTokens)
    expect(s.backgroundColor).toBe(mockTokens.colors.surface.raised)
    expect(s.borderLeft).toBe(`1px solid ${mockTokens.colors.border.default}`)
    expect(s.borderRadius).toBe(mockTokens.radius.lg)
  })

  test('getPanelHeaderStyles uses border and padding tokens', () => {
    const s = getPanelHeaderStyles(mockTokens)
    expect(s.borderBottom).toBe(`1px solid ${mockTokens.colors.border.subtle}`)
    expect(s.padding).toBe(`${mockTokens.spacing[4]} ${mockTokens.spacing[4]}`)
  })

  test('getPanelItemStyles active/inactive token palettes', () => {
    const active = getPanelItemStyles(true, mockTokens)
    const inactive = getPanelItemStyles(false, mockTokens)
    expect(active.backgroundColor).not.toBe('transparent')
    expect(active.color).toBe(mockTokens.colors.text.primary)
    expect(inactive.color).toBe(mockTokens.colors.text.secondary)
  })
})

describe('SMC overlay styles', () => {
  test('label uses success tokens for bullish', () => {
    const s = getSmcLabelStyles({ direction: 'bullish', type: 'CHOCH' }, mockTokens)
    expect(s.backgroundColor).toBe(mockTokens.colors.success[600])
    expect(s.color).toBe(mockTokens.colors.text.inverse)
  })

  test('line uses error tokens for bearish', () => {
    const s = getSmcLineStyles({ direction: 'bearish', type: 'BOS' }, mockTokens)
    expect(s.backgroundColor).toBe(mockTokens.colors.error[500])
    expect(s.height).toBe('1px')
  })
})

describe('Zone overlay styles', () => {
  test('overlay uses tokens and computed opacity', () => {
    const s = getZoneOverlayStyles({ type: 'supply', strength: 3, touches: 1 }, mockTokens)
    expect(s.backgroundColor).toBe(mockTokens.colors.error[500])
    expect(typeof s.opacity).toBe('number')
    expect(s.border).toBe(`1px solid ${mockTokens.colors.error[500]}`)
  })

  test('label and badge token colors reflect type', () => {
    const label = getZoneLabelStyles({ type: 'demand' }, mockTokens)
    const badge = getZoneBadgeStyles({ type: 'demand' }, mockTokens)
    expect(label.color).toBe(mockTokens.colors.success[600])
    expect(badge.backgroundColor).toBe(mockTokens.colors.success[100])
  })
})

describe('layout helpers', () => {
  test('getAbsoluteFillStyles returns absolute inset and zIndex', () => {
    const s = getAbsoluteFillStyles(mockTokens, 20)
    expect(s.position).toBe('absolute')
    expect(s.top).toBe(0)
    expect(s.left).toBe(0)
    expect(s.zIndex).toBe(20)
    expect(s.pointerEvents).toBe('none')
  })

  test('getPageHeadingStyles uses typography and text tokens', () => {
    const s = getPageHeadingStyles(mockTokens)
    expect(s.fontSize).toBe(mockTokens.typography.fontSize.xl)
    expect(s.color).toBe(mockTokens.colors.text.primary)
    expect(s.margin).toContain(mockTokens.spacing[4])
  })

  test('getTabButtonStyles active/inactive use tokens', () => {
    const a = getTabButtonStyles(true, mockTokens)
    const i = getTabButtonStyles(false, mockTokens)
    expect(a.backgroundColor).toBe(mockTokens.colors.primary[600])
    expect(a.color).toBe(mockTokens.colors.text.inverse)
    expect(i.backgroundColor).toBe(mockTokens.colors.surface.overlay)
    expect(i.color).toBe(mockTokens.colors.text.secondary)
  })
})
