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
