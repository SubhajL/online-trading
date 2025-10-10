import { describe, expect, test } from 'vitest'
import type { DesignTokens } from './tokens'

describe('DesignTokens', () => {
  test('type structure allows valid token objects', () => {
    const validTokens: DesignTokens = {
      colors: {
        primary: {
          50: 'hsl(220, 70%, 95%)',
          100: 'hsl(220, 70%, 90%)',
          200: 'hsl(220, 70%, 80%)',
          300: 'hsl(220, 70%, 70%)',
          400: 'hsl(220, 70%, 60%)',
          500: 'hsl(220, 70%, 50%)',
          600: 'hsl(220, 70%, 45%)',
          700: 'hsl(220, 70%, 40%)',
          800: 'hsl(220, 70%, 30%)',
          900: 'hsl(220, 70%, 20%)',
        },
        success: {
          50: 'hsl(142, 71%, 95%)',
          100: 'hsl(142, 71%, 85%)',
          200: 'hsl(142, 71%, 75%)',
          300: 'hsl(142, 71%, 65%)',
          400: 'hsl(142, 71%, 55%)',
          500: 'hsl(142, 71%, 45%)',
          600: 'hsl(142, 71%, 38%)',
          700: 'hsl(142, 71%, 32%)',
          800: 'hsl(142, 71%, 25%)',
          900: 'hsl(142, 71%, 18%)',
        },
        warning: {
          50: 'hsl(38, 92%, 95%)',
          100: 'hsl(38, 92%, 85%)',
          200: 'hsl(38, 92%, 75%)',
          300: 'hsl(38, 92%, 65%)',
          400: 'hsl(38, 92%, 55%)',
          500: 'hsl(38, 92%, 50%)',
          600: 'hsl(38, 92%, 45%)',
          700: 'hsl(38, 92%, 40%)',
          800: 'hsl(38, 92%, 32%)',
          900: 'hsl(38, 92%, 25%)',
        },
        error: {
          50: 'hsl(0, 84%, 95%)',
          100: 'hsl(0, 84%, 85%)',
          200: 'hsl(0, 84%, 75%)',
          300: 'hsl(0, 84%, 65%)',
          400: 'hsl(0, 84%, 60%)',
          500: 'hsl(0, 84%, 55%)',
          600: 'hsl(0, 84%, 50%)',
          700: 'hsl(0, 84%, 42%)',
          800: 'hsl(0, 84%, 35%)',
          900: 'hsl(0, 84%, 28%)',
        },
        info: {
          50: 'hsl(201, 90%, 95%)',
          100: 'hsl(201, 90%, 85%)',
          200: 'hsl(201, 90%, 75%)',
          300: 'hsl(201, 90%, 60%)',
          400: 'hsl(201, 90%, 52%)',
          500: 'hsl(201, 90%, 47%)',
          600: 'hsl(201, 90%, 42%)',
          700: 'hsl(201, 90%, 37%)',
          800: 'hsl(201, 90%, 30%)',
          900: 'hsl(201, 90%, 23%)',
        },
        gray: {
          50: 'hsl(220, 13%, 97%)',
          100: 'hsl(220, 13%, 94%)',
          200: 'hsl(220, 13%, 87%)',
          300: 'hsl(220, 13%, 78%)',
          400: 'hsl(220, 13%, 65%)',
          500: 'hsl(220, 13%, 52%)',
          600: 'hsl(220, 13%, 46%)',
          700: 'hsl(220, 13%, 38%)',
          800: 'hsl(220, 13%, 28%)',
          900: 'hsl(220, 13%, 13%)',
        },
        surface: {
          base: 'hsl(220, 20%, 7%)',
          raised: 'hsl(220, 16%, 13%)',
          overlay: 'hsl(220, 15%, 16%)',
          hover: 'hsl(220, 14%, 19%)',
          input: 'hsl(220, 18%, 9%)',
        },
        text: {
          primary: 'hsl(220, 13%, 85%)',
          secondary: 'hsl(220, 13%, 72%)',
          muted: 'hsl(220, 13%, 58%)',
          disabled: 'hsl(220, 13%, 42%)',
          inverse: 'hsl(220, 13%, 13%)',
          success: 'hsl(142, 71%, 55%)',
          danger: 'hsl(0, 84%, 60%)',
          warning: 'hsl(38, 92%, 55%)',
          info: 'hsl(201, 90%, 52%)',
        },
        border: {
          subtle: 'hsl(220, 15%, 16%)',
          default: 'hsl(220, 14%, 19%)',
          strong: 'hsl(220, 13%, 28%)',
          focus: 'hsl(220, 70%, 50%)',
        },
      },
      spacing: {
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
      },
      radius: {
        none: '0',
        sm: '4px',
        md: '8px',
        lg: '16px',
        full: '9999px',
      },
      typography: {
        fontSize: {
          xs: '0.75rem',
          sm: '0.875rem',
          base: '1rem',
          lg: '1.125rem',
          xl: '1.25rem',
          '2xl': '1.563rem',
          '3xl': '1.953rem',
          '4xl': '2.441rem',
          '5xl': '3.052rem',
        },
        fontWeight: {
          normal: 400,
          medium: 500,
          semibold: 600,
          bold: 700,
        },
        lineHeight: {
          tight: 1.2,
          normal: 1.5,
          relaxed: 1.7,
        },
      },
      chart: {
        bg: 'hsl(220, 18%, 9%)',
        text: 'hsl(220, 13%, 85%)',
        grid: 'hsl(220, 15%, 16%)',
        candleUp: 'hsl(142, 71%, 45%)',
        candleDown: 'hsl(0, 84%, 60%)',
      },
    }

    expect(validTokens.colors.primary[500]).toBe('hsl(220, 70%, 50%)')
    expect(validTokens.spacing[4]).toBe('16px')
    expect(validTokens.typography.fontSize.base).toBe('1rem')
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
})
