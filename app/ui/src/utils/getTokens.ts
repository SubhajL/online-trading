import { DEFAULT_TOKENS } from '../constants/defaultTokens'
import type {
  DesignTokens,
  ColorScale,
  SurfaceColors,
  TextColors,
  BorderColors,
  SpacingScale,
  RadiusScale,
  Typography,
  ChartColors,
} from '../types/tokens'

/**
 * Reads a color scale from CSS custom properties
 * Falls back to provided defaults when CSS variables are missing
 */
export function readColorScale(
  prefix: string,
  defaults: ColorScale,
  styles: CSSStyleDeclaration,
): ColorScale {
  return {
    50: styles.getPropertyValue(`--color-${prefix}-50`).trim() || defaults[50],
    100: styles.getPropertyValue(`--color-${prefix}-100`).trim() || defaults[100],
    200: styles.getPropertyValue(`--color-${prefix}-200`).trim() || defaults[200],
    300: styles.getPropertyValue(`--color-${prefix}-300`).trim() || defaults[300],
    400: styles.getPropertyValue(`--color-${prefix}-400`).trim() || defaults[400],
    500: styles.getPropertyValue(`--color-${prefix}-500`).trim() || defaults[500],
    600: styles.getPropertyValue(`--color-${prefix}-600`).trim() || defaults[600],
    700: styles.getPropertyValue(`--color-${prefix}-700`).trim() || defaults[700],
    800: styles.getPropertyValue(`--color-${prefix}-800`).trim() || defaults[800],
    900: styles.getPropertyValue(`--color-${prefix}-900`).trim() || defaults[900],
  }
}

/**
 * Reads surface colors from CSS custom properties
 */
export function readSurfaceColors(styles: CSSStyleDeclaration): SurfaceColors {
  return {
    base:
      styles.getPropertyValue('--color-surface-base').trim() || DEFAULT_TOKENS.colors.surface.base,
    raised:
      styles.getPropertyValue('--color-surface-raised').trim() ||
      DEFAULT_TOKENS.colors.surface.raised,
    overlay:
      styles.getPropertyValue('--color-surface-overlay').trim() ||
      DEFAULT_TOKENS.colors.surface.overlay,
    hover:
      styles.getPropertyValue('--color-surface-hover').trim() ||
      DEFAULT_TOKENS.colors.surface.hover,
    input:
      styles.getPropertyValue('--color-surface-input').trim() ||
      DEFAULT_TOKENS.colors.surface.input,
  }
}

/**
 * Reads text colors from CSS custom properties
 */
export function readTextColors(styles: CSSStyleDeclaration): TextColors {
  return {
    primary:
      styles.getPropertyValue('--color-text-primary').trim() || DEFAULT_TOKENS.colors.text.primary,
    secondary:
      styles.getPropertyValue('--color-text-secondary').trim() ||
      DEFAULT_TOKENS.colors.text.secondary,
    muted: styles.getPropertyValue('--color-text-muted').trim() || DEFAULT_TOKENS.colors.text.muted,
    disabled:
      styles.getPropertyValue('--color-text-disabled').trim() ||
      DEFAULT_TOKENS.colors.text.disabled,
    inverse:
      styles.getPropertyValue('--color-text-inverse').trim() || DEFAULT_TOKENS.colors.text.inverse,
    success:
      styles.getPropertyValue('--color-text-success').trim() || DEFAULT_TOKENS.colors.text.success,
    danger:
      styles.getPropertyValue('--color-text-danger').trim() || DEFAULT_TOKENS.colors.text.danger,
    warning:
      styles.getPropertyValue('--color-text-warning').trim() || DEFAULT_TOKENS.colors.text.warning,
    info: styles.getPropertyValue('--color-text-info').trim() || DEFAULT_TOKENS.colors.text.info,
  }
}

/**
 * Reads border colors from CSS custom properties
 */
export function readBorderColors(styles: CSSStyleDeclaration): BorderColors {
  return {
    subtle:
      styles.getPropertyValue('--color-border-subtle').trim() ||
      DEFAULT_TOKENS.colors.border.subtle,
    default:
      styles.getPropertyValue('--color-border-default').trim() ||
      DEFAULT_TOKENS.colors.border.default,
    strong:
      styles.getPropertyValue('--color-border-strong').trim() ||
      DEFAULT_TOKENS.colors.border.strong,
    focus:
      styles.getPropertyValue('--color-border-focus').trim() || DEFAULT_TOKENS.colors.border.focus,
  }
}

/**
 * Reads spacing scale from CSS custom properties
 */
export function readSpacing(styles: CSSStyleDeclaration): SpacingScale {
  return {
    0: styles.getPropertyValue('--space-0').trim() || DEFAULT_TOKENS.spacing[0],
    1: styles.getPropertyValue('--space-1').trim() || DEFAULT_TOKENS.spacing[1],
    2: styles.getPropertyValue('--space-2').trim() || DEFAULT_TOKENS.spacing[2],
    3: styles.getPropertyValue('--space-3').trim() || DEFAULT_TOKENS.spacing[3],
    4: styles.getPropertyValue('--space-4').trim() || DEFAULT_TOKENS.spacing[4],
    5: styles.getPropertyValue('--space-5').trim() || DEFAULT_TOKENS.spacing[5],
    6: styles.getPropertyValue('--space-6').trim() || DEFAULT_TOKENS.spacing[6],
    7: styles.getPropertyValue('--space-7').trim() || DEFAULT_TOKENS.spacing[7],
    8: styles.getPropertyValue('--space-8').trim() || DEFAULT_TOKENS.spacing[8],
    9: styles.getPropertyValue('--space-9').trim() || DEFAULT_TOKENS.spacing[9],
    10: styles.getPropertyValue('--space-10').trim() || DEFAULT_TOKENS.spacing[10],
  }
}

/**
 * Reads radius scale from CSS custom properties
 */
export function readRadius(styles: CSSStyleDeclaration): RadiusScale {
  return {
    none: styles.getPropertyValue('--radius-none').trim() || DEFAULT_TOKENS.radius.none,
    sm: styles.getPropertyValue('--radius-sm').trim() || DEFAULT_TOKENS.radius.sm,
    md: styles.getPropertyValue('--radius-md').trim() || DEFAULT_TOKENS.radius.md,
    lg: styles.getPropertyValue('--radius-lg').trim() || DEFAULT_TOKENS.radius.lg,
    full: styles.getPropertyValue('--radius-full').trim() || DEFAULT_TOKENS.radius.full,
  }
}

/**
 * Reads typography tokens from CSS custom properties
 */
export function readTypography(styles: CSSStyleDeclaration): Typography {
  return {
    fontSize: {
      xs: styles.getPropertyValue('--font-size-xs').trim() || DEFAULT_TOKENS.typography.fontSize.xs,
      sm: styles.getPropertyValue('--font-size-sm').trim() || DEFAULT_TOKENS.typography.fontSize.sm,
      base:
        styles.getPropertyValue('--font-size-base').trim() ||
        DEFAULT_TOKENS.typography.fontSize.base,
      lg: styles.getPropertyValue('--font-size-lg').trim() || DEFAULT_TOKENS.typography.fontSize.lg,
      xl: styles.getPropertyValue('--font-size-xl').trim() || DEFAULT_TOKENS.typography.fontSize.xl,
      '2xl':
        styles.getPropertyValue('--font-size-2xl').trim() ||
        DEFAULT_TOKENS.typography.fontSize['2xl'],
      '3xl':
        styles.getPropertyValue('--font-size-3xl').trim() ||
        DEFAULT_TOKENS.typography.fontSize['3xl'],
      '4xl':
        styles.getPropertyValue('--font-size-4xl').trim() ||
        DEFAULT_TOKENS.typography.fontSize['4xl'],
      '5xl':
        styles.getPropertyValue('--font-size-5xl').trim() ||
        DEFAULT_TOKENS.typography.fontSize['5xl'],
    },
    fontWeight: DEFAULT_TOKENS.typography.fontWeight,
    lineHeight: DEFAULT_TOKENS.typography.lineHeight,
  }
}

/**
 * Reads chart colors from CSS custom properties
 */
export function readChartColors(styles: CSSStyleDeclaration): ChartColors {
  return {
    bg: styles.getPropertyValue('--color-chart-bg').trim() || DEFAULT_TOKENS.chart.bg,
    text: styles.getPropertyValue('--color-chart-text').trim() || DEFAULT_TOKENS.chart.text,
    grid: styles.getPropertyValue('--color-chart-grid').trim() || DEFAULT_TOKENS.chart.grid,
    candleUp:
      styles.getPropertyValue('--color-chart-candle-up').trim() || DEFAULT_TOKENS.chart.candleUp,
    candleDown:
      styles.getPropertyValue('--color-chart-candle-down').trim() ||
      DEFAULT_TOKENS.chart.candleDown,
  }
}

/**
 * Reads design tokens from CSS custom properties at runtime.
 *
 * Requires browser DOM environment for runtime CSS variable reading.
 * Returns static defaults on server (typeof window === 'undefined').
 * Falls back to DEFAULT_TOKENS for any missing CSS variables.
 */
export function getTokens(): DesignTokens {
  if (typeof window === 'undefined') {
    return DEFAULT_TOKENS
  }

  const styles = getComputedStyle(document.documentElement)

  return {
    colors: {
      primary: readColorScale('primary', DEFAULT_TOKENS.colors.primary, styles),
      success: readColorScale('success', DEFAULT_TOKENS.colors.success, styles),
      warning: readColorScale('warning', DEFAULT_TOKENS.colors.warning, styles),
      error: readColorScale('error', DEFAULT_TOKENS.colors.error, styles),
      info: readColorScale('info', DEFAULT_TOKENS.colors.info, styles),
      gray: readColorScale('gray', DEFAULT_TOKENS.colors.gray, styles),
      surface: readSurfaceColors(styles),
      text: readTextColors(styles),
      border: readBorderColors(styles),
    },
    spacing: readSpacing(styles),
    radius: readRadius(styles),
    typography: readTypography(styles),
    chart: readChartColors(styles),
  }
}
