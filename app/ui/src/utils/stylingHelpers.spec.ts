import { describe, expect, test } from 'vitest'
import type { DesignTokens } from '../types/tokens'
import {
  getToolbarVariantStyles,
  getSpinnerStyle,
  composeErrorBannerStyles,
  buildPageContainerStyle,
  getAutoTradingToggleStyles,
  getIndicatorColor,
  applyFocusVisible,
} from './stylingHelpers'

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
