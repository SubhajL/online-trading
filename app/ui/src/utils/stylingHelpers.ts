import type { DesignTokens } from '../types/tokens'
import type { IndicatorType } from '../types'

export type ToolbarVariant = 'primary' | 'secondary' | 'success' | 'error'
export type SpinnerSize = 'sm' | 'md' | 'lg'
export type BannerSeverity = 'error' | 'warning' | 'info'
export type MaxWidth = 'sm' | 'md' | 'lg' | 'xl' | 'full'

/**
 * Returns inline style object for toolbar variants
 */
export function getToolbarVariantStyles(
  variant: ToolbarVariant,
  tokens: DesignTokens,
): { backgroundColor: string; color: string } {
  switch (variant) {
    case 'primary':
      return {
        backgroundColor: tokens.colors.primary[500],
        color: tokens.colors.text.inverse,
      }
    case 'secondary':
      return {
        backgroundColor: tokens.colors.gray[200],
        color: tokens.colors.text.primary,
      }
    case 'success':
      return {
        backgroundColor: tokens.colors.success[500],
        color: tokens.colors.text.inverse,
      }
    case 'error':
      return {
        backgroundColor: tokens.colors.error[500],
        color: tokens.colors.text.inverse,
      }
    default:
      return {
        backgroundColor: tokens.colors.primary[500],
        color: tokens.colors.text.inverse,
      }
  }
}

/**
 * Returns inline style object for loading spinner
 */
export function getSpinnerStyle(
  size: SpinnerSize,
  tokens: DesignTokens,
  color?: string,
): { width: string; height: string; borderWidth: string; borderColor: string } {
  const spinnerColor = color ?? tokens.colors.primary[500]
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

/**
 * Returns inline style object for error/warning/info banner
 */
export function composeErrorBannerStyles(
  hasIcon: boolean,
  tokens: DesignTokens,
  severity: BannerSeverity = 'error',
): {
  backgroundColor: string
  color: string
  padding: string
  borderRadius: string
  border: string
  display: string
  alignItems: string | undefined
  gap: string | undefined
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
    padding: tokens.spacing[4],
    borderRadius: tokens.radius.md,
    border: `1px solid ${colors.border}`,
    display: hasIcon ? 'flex' : 'block',
    alignItems: hasIcon ? 'center' : undefined,
    gap: hasIcon ? tokens.spacing[3] : undefined,
  }
}

/**
 * Returns inline style object for page container with optional maxWidth
 */
export function buildPageContainerStyle(
  tokens: DesignTokens,
  paddingLevel: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 = 8,
  maxWidth?: MaxWidth,
): {
  padding: string
  backgroundColor: string
  maxWidth: string | undefined
  margin: string | undefined
} {
  const maxWidthMap: Record<MaxWidth, string> = {
    sm: '640px',
    md: '768px',
    lg: '1024px',
    xl: '1280px',
    full: '100%',
  }

  const width = maxWidth ? maxWidthMap[maxWidth] : undefined
  const margin = maxWidth && maxWidth !== 'full' ? '0 auto' : undefined

  return {
    padding: tokens.spacing[paddingLevel],
    backgroundColor: tokens.colors.surface.base,
    maxWidth: width,
    margin,
  }
}

export type AutoTradingToggleState = 'enabled' | 'disabled' | 'error'

/**
 * Returns inline style object for auto trading toggle based on state
 */
export function getAutoTradingToggleStyles(
  tokens: DesignTokens,
  state: AutoTradingToggleState,
): {
  backgroundColor: string
  color: string
  borderColor: string
  borderRadius: string
} {
  switch (state) {
    case 'enabled':
      return {
        backgroundColor: tokens.colors.success[50],
        color: tokens.colors.text.success,
        borderColor: tokens.colors.success[300],
        borderRadius: tokens.radius.md,
      }
    case 'error':
      return {
        backgroundColor: tokens.colors.error[50],
        color: tokens.colors.text.danger,
        borderColor: tokens.colors.error[300],
        borderRadius: tokens.radius.md,
      }
    case 'disabled':
    default:
      return {
        backgroundColor: tokens.colors.gray[100],
        color: tokens.colors.text.muted,
        borderColor: tokens.colors.gray[300],
        borderRadius: tokens.radius.md,
      }
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
 * Returns focus-visible outline styles using design tokens
 */
export function applyFocusVisible(
  tokens: DesignTokens,
  width: string = '2px',
  offset: string = '2px',
): { outline: string; outlineOffset: string } {
  return {
    outline: `${width} solid ${tokens.colors.border.focus}`,
    outlineOffset: offset,
  }
}
