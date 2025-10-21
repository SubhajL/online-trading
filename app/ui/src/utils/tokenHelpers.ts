import type { DesignTokens } from '../types/tokens'
import type { ChartTheme } from '../types/chartTheme'

/**
 * Converts design tokens to Lightweight Charts theme configuration
 */
export function createChartThemeFromTokens(tokens: DesignTokens): ChartTheme {
  return {
    layout: {
      background: { color: tokens.chart.bg },
      textColor: tokens.chart.text,
    },
    grid: {
      vertLines: { color: tokens.chart.grid },
      horzLines: { color: tokens.chart.grid },
    },
    timeScale: {
      borderColor: tokens.colors.border.default,
    },
    rightPriceScale: {
      borderColor: tokens.colors.border.default,
    },
  }
}

/**
 * Returns inline style object for navigation item based on active state
 */
export function mapRouteToNavTokens(
  isActive: boolean,
  tokens: DesignTokens,
): { backgroundColor: string; color: string; borderLeft: string } {
  if (isActive) {
    return {
      backgroundColor: tokens.colors.primary[50],
      color: tokens.colors.primary[700],
      borderLeft: `3px solid ${tokens.colors.primary[500]}`,
    }
  }

  return {
    backgroundColor: 'transparent',
    color: tokens.colors.text.secondary,
    borderLeft: '3px solid transparent',
  }
}

export type Candle = {
  open: number
  close: number
  high: number
  low: number
  volume: number
}

/**
 * Returns color for volume bar based on candle direction
 */
export function getVolumeBarColor(candle: Candle, tokens: DesignTokens): string {
  if (candle.close > candle.open) {
    return tokens.colors.success[500]
  }
  if (candle.close < candle.open) {
    return tokens.colors.error[500]
  }
  return tokens.colors.gray[400]
}

/**
 * Returns padding that ensures 44px minimum touch target height
 */
export function getTouchTargetPadding(tokens: DesignTokens): {
  paddingTop: string
  paddingBottom: string
} {
  return {
    paddingTop: tokens.spacing[3],
    paddingBottom: tokens.spacing[3],
  }
}

export type IndicatorType = 'EMA' | 'SMA' | 'RSI' | 'MACD' | 'BB' | 'VOLUME'
export type BannerSeverity = 'error' | 'warning' | 'info'
export type SpinnerVariant = 'primary' | 'secondary' | 'white'
export type SpinnerSize = 'sm' | 'md' | 'lg'

/**
 * Returns inline styles for chart control buttons
 */
export function getChartButtonStyles(
  isActive: boolean,
  tokens: DesignTokens,
): { backgroundColor: string; color: string; padding: string; borderRadius: string } {
  if (isActive) {
    return {
      backgroundColor: tokens.colors.primary[600],
      color: tokens.colors.text.inverse,
      padding: `${tokens.spacing[1]} ${tokens.spacing[3]}`,
      borderRadius: tokens.radius.sm,
    }
  }

  return {
    backgroundColor: tokens.colors.gray[800],
    color: tokens.colors.gray[300],
    padding: `${tokens.spacing[1]} ${tokens.spacing[3]}`,
    borderRadius: tokens.radius.sm,
  }
}

/**
 * Maps chart indicator types to design token colors
 */
export function getIndicatorColor(indicator: IndicatorType, tokens: DesignTokens): string {
  switch (indicator) {
    case 'EMA':
      return tokens.colors.error[500]
    case 'SMA':
      return tokens.colors.success[500]
    case 'RSI':
      return tokens.colors.info[500]
    case 'MACD':
      return tokens.colors.warning[500]
    case 'BB':
      return tokens.colors.primary[500]
    case 'VOLUME':
      return tokens.colors.gray[500]
    default:
      return tokens.colors.gray[500]
  }
}

/**
 * Returns inline style object for error/warning/info banner
 */
export function getErrorBannerStyles(
  severity: BannerSeverity,
  tokens: DesignTokens,
): {
  backgroundColor: string
  color: string
  borderColor: string
  padding: string
  borderRadius: string
} {
  const colorMap = {
    error: {
      bg: tokens.colors.error[50],
      text: tokens.colors.text.danger,
      border: tokens.colors.error[200],
    },
    warning: {
      bg: tokens.colors.warning[50],
      text: tokens.colors.text.warning,
      border: tokens.colors.warning[200],
    },
    info: {
      bg: tokens.colors.info[50],
      text: tokens.colors.text.info,
      border: tokens.colors.info[200],
    },
  }

  const colors = colorMap[severity]

  return {
    backgroundColor: colors.bg,
    color: colors.text,
    borderColor: colors.border,
    padding: tokens.spacing[4],
    borderRadius: tokens.radius.md,
  }
}

/**
 * Returns focus-visible outline styles using design tokens
 */
export function ensureFocusVisibleStyles(
  tokens: DesignTokens,
  width: string = '2px',
  offset: string = '2px',
): { outline: string; outlineOffset: string } {
  return {
    outline: `${width} solid ${tokens.colors.border.focus}`,
    outlineOffset: offset,
  }
}

/**
 * Returns inline style object for loading spinner
 */
export function getSpinnerStyles(
  size: SpinnerSize,
  variant: SpinnerVariant,
  tokens: DesignTokens,
): { width: string; height: string; borderWidth: string; borderColor: string } {
  const variantColorMap: Record<SpinnerVariant, string> = {
    primary: tokens.colors.success[500],
    secondary: tokens.colors.primary[500],
    white: tokens.colors.text.inverse,
  }

  const spinnerColor = variantColorMap[variant]
  const borderColor = `${spinnerColor} transparent transparent transparent`

  switch (size) {
    case 'sm':
      return {
        width: '16px',
        height: '16px',
        borderWidth: '2px',
        borderColor,
      }
    case 'md':
      return {
        width: '24px',
        height: '24px',
        borderWidth: '3px',
        borderColor,
      }
    case 'lg':
      return {
        width: '32px',
        height: '32px',
        borderWidth: '4px',
        borderColor,
      }
  }
}
