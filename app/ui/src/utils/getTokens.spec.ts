import { beforeEach, describe, expect, test, vi } from 'vitest'
import {
  getTokens,
  readColorScale,
  readSurfaceColors,
  readTextColors,
  readBorderColors,
  readSpacing,
  readRadius,
  readTypography,
  readChartColors,
} from './getTokens'
import { DEFAULT_TOKENS } from '../constants/defaultTokens'
import type { DesignTokens } from '../types/tokens'

describe('getTokens', () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
  })

  test('returns DEFAULT_TOKENS when window is undefined', () => {
    vi.stubGlobal('window', undefined)
    const tokens = getTokens()
    expect(tokens).toEqual(DEFAULT_TOKENS)
  })

  test('reads color-primary-500 from CSS variables on client', () => {
    const mockGetComputedStyle = vi.fn(() => ({
      getPropertyValue: (prop: string) => {
        if (prop === '--color-primary-500') return 'hsl(220, 70%, 50%)'
        return ''
      },
    }))
    vi.stubGlobal('window', { getComputedStyle: mockGetComputedStyle })
    vi.stubGlobal('document', { documentElement: {} })

    const tokens = getTokens()
    expect(tokens.colors.primary[500]).toBe('hsl(220, 70%, 50%)')
  })

  test('reads spacing-4 from CSS variables on client', () => {
    const mockGetComputedStyle = vi.fn(() => ({
      getPropertyValue: (prop: string) => {
        if (prop === '--space-4') return '16px'
        return ''
      },
    }))
    vi.stubGlobal('window', { getComputedStyle: mockGetComputedStyle })
    vi.stubGlobal('document', { documentElement: {} })

    const tokens = getTokens()
    expect(tokens.spacing[4]).toBe('16px')
  })

  test('returns all required color scales', () => {
    vi.stubGlobal('window', undefined)
    const tokens = getTokens()
    expect(tokens.colors.primary).toBeDefined()
    expect(tokens.colors.success).toBeDefined()
    expect(tokens.colors.warning).toBeDefined()
    expect(tokens.colors.error).toBeDefined()
    expect(tokens.colors.info).toBeDefined()
    expect(tokens.colors.gray).toBeDefined()
  })

  test('returns all required spacing values 0-10', () => {
    vi.stubGlobal('window', undefined)
    const tokens = getTokens()
    expect(Object.keys(tokens.spacing)).toHaveLength(11)
    expect(tokens.spacing[0]).toBeDefined()
    expect(tokens.spacing[10]).toBeDefined()
  })

  test('returns chart tokens with valid color strings', () => {
    vi.stubGlobal('window', undefined)
    const tokens = getTokens()
    expect(tokens.chart.bg).toBeTruthy()
    expect(tokens.chart.text).toBeTruthy()
    expect(tokens.chart.grid).toBeTruthy()
    expect(tokens.chart.candleUp).toBeTruthy()
    expect(tokens.chart.candleDown).toBeTruthy()
  })

  test('returned object conforms to DesignTokens type', () => {
    vi.stubGlobal('window', undefined)
    const tokens = getTokens()
    const _typecheck: DesignTokens = tokens
    expect(_typecheck).toBeDefined()
  })
})

describe('readColorScale', () => {
  test('uses correct defaults for success scale', () => {
    const mockStyles = {
      getPropertyValue: vi.fn().mockReturnValue(''),
    } as unknown as CSSStyleDeclaration

    const result = readColorScale('success', DEFAULT_TOKENS.colors.success, mockStyles)
    expect(result).toEqual(DEFAULT_TOKENS.colors.success)
  })

  test('uses correct defaults for error scale', () => {
    const mockStyles = {
      getPropertyValue: vi.fn().mockReturnValue(''),
    } as unknown as CSSStyleDeclaration

    const result = readColorScale('error', DEFAULT_TOKENS.colors.error, mockStyles)
    expect(result).toEqual(DEFAULT_TOKENS.colors.error)
  })

  test('uses correct defaults for warning scale', () => {
    const mockStyles = {
      getPropertyValue: vi.fn().mockReturnValue(''),
    } as unknown as CSSStyleDeclaration

    const result = readColorScale('warning', DEFAULT_TOKENS.colors.warning, mockStyles)
    expect(result).toEqual(DEFAULT_TOKENS.colors.warning)
  })

  test('reads CSS variables when available', () => {
    const mockStyles = {
      getPropertyValue: vi.fn((prop: string) => {
        if (prop === '--color-primary-500') return 'hsl(220, 70%, 50%)'
        return ''
      }),
    } as unknown as CSSStyleDeclaration

    const result = readColorScale('primary', DEFAULT_TOKENS.colors.primary, mockStyles)
    expect(result[500]).toBe('hsl(220, 70%, 50%)')
  })
})

describe('readSurfaceColors', () => {
  test('falls back to defaults when CSS vars missing', () => {
    const mockStyles = {
      getPropertyValue: vi.fn().mockReturnValue(''),
    } as unknown as CSSStyleDeclaration

    const result = readSurfaceColors(mockStyles)
    expect(result).toEqual(DEFAULT_TOKENS.colors.surface)
  })

  test('reads CSS variables when available', () => {
    const mockStyles = {
      getPropertyValue: vi.fn((prop: string) => {
        if (prop === '--color-surface-base') return 'hsl(0, 0%, 100%)'
        return ''
      }),
    } as unknown as CSSStyleDeclaration

    const result = readSurfaceColors(mockStyles)
    expect(result.base).toBe('hsl(0, 0%, 100%)')
  })
})

describe('readTextColors', () => {
  test('falls back to defaults when CSS vars missing', () => {
    const mockStyles = {
      getPropertyValue: vi.fn().mockReturnValue(''),
    } as unknown as CSSStyleDeclaration

    const result = readTextColors(mockStyles)
    expect(result).toEqual(DEFAULT_TOKENS.colors.text)
  })

  test('reads CSS variables when available', () => {
    const mockStyles = {
      getPropertyValue: vi.fn((prop: string) => {
        if (prop === '--color-text-primary') return 'hsl(0, 0%, 10%)'
        return ''
      }),
    } as unknown as CSSStyleDeclaration

    const result = readTextColors(mockStyles)
    expect(result.primary).toBe('hsl(0, 0%, 10%)')
  })
})

describe('readBorderColors', () => {
  test('falls back to defaults when CSS vars missing', () => {
    const mockStyles = {
      getPropertyValue: vi.fn().mockReturnValue(''),
    } as unknown as CSSStyleDeclaration

    const result = readBorderColors(mockStyles)
    expect(result).toEqual(DEFAULT_TOKENS.colors.border)
  })

  test('reads CSS variables when available', () => {
    const mockStyles = {
      getPropertyValue: vi.fn((prop: string) => {
        if (prop === '--color-border-focus') return 'hsl(220, 70%, 50%)'
        return ''
      }),
    } as unknown as CSSStyleDeclaration

    const result = readBorderColors(mockStyles)
    expect(result.focus).toBe('hsl(220, 70%, 50%)')
  })
})

describe('readSpacing', () => {
  test('falls back to defaults when CSS vars missing', () => {
    const mockStyles = {
      getPropertyValue: vi.fn().mockReturnValue(''),
    } as unknown as CSSStyleDeclaration

    const result = readSpacing(mockStyles)
    expect(result).toEqual(DEFAULT_TOKENS.spacing)
  })

  test('reads CSS variables when available', () => {
    const mockStyles = {
      getPropertyValue: vi.fn((prop: string) => {
        if (prop === '--space-4') return '16px'
        return ''
      }),
    } as unknown as CSSStyleDeclaration

    const result = readSpacing(mockStyles)
    expect(result[4]).toBe('16px')
  })
})

describe('readRadius', () => {
  test('falls back to defaults when CSS vars missing', () => {
    const mockStyles = {
      getPropertyValue: vi.fn().mockReturnValue(''),
    } as unknown as CSSStyleDeclaration

    const result = readRadius(mockStyles)
    expect(result).toEqual(DEFAULT_TOKENS.radius)
  })

  test('reads CSS variables when available', () => {
    const mockStyles = {
      getPropertyValue: vi.fn((prop: string) => {
        if (prop === '--radius-md') return '8px'
        return ''
      }),
    } as unknown as CSSStyleDeclaration

    const result = readRadius(mockStyles)
    expect(result.md).toBe('8px')
  })
})

describe('readTypography', () => {
  test('falls back to defaults when CSS vars missing', () => {
    const mockStyles = {
      getPropertyValue: vi.fn().mockReturnValue(''),
    } as unknown as CSSStyleDeclaration

    const result = readTypography(mockStyles)
    expect(result).toEqual(DEFAULT_TOKENS.typography)
  })

  test('reads CSS variables when available', () => {
    const mockStyles = {
      getPropertyValue: vi.fn((prop: string) => {
        if (prop === '--font-size-base') return '16px'
        return ''
      }),
    } as unknown as CSSStyleDeclaration

    const result = readTypography(mockStyles)
    expect(result.fontSize.base).toBe('16px')
  })
})

describe('readChartColors', () => {
  test('falls back to defaults when CSS vars missing', () => {
    const mockStyles = {
      getPropertyValue: vi.fn().mockReturnValue(''),
    } as unknown as CSSStyleDeclaration

    const result = readChartColors(mockStyles)
    expect(result).toEqual(DEFAULT_TOKENS.chart)
  })

  test('reads CSS variables when available', () => {
    const mockStyles = {
      getPropertyValue: vi.fn((prop: string) => {
        if (prop === '--color-chart-bg') return 'hsl(0, 0%, 100%)'
        return ''
      }),
    } as unknown as CSSStyleDeclaration

    const result = readChartColors(mockStyles)
    expect(result.bg).toBe('hsl(0, 0%, 100%)')
  })
})
