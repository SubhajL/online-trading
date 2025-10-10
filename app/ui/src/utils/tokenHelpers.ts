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
