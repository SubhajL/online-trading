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
  const needsCentering = maxWidth && maxWidth !== 'full'
  const margin = needsCentering ? '0 auto' : undefined

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

/**
 * Returns inline style object for chart button states (active/inactive)
 */
export function getChartButtonStyles(
  isActive: boolean,
  tokens: DesignTokens,
): {
  backgroundColor: string
  color: string
  padding: string
  borderRadius: string
  border: string
  cursor: string
  transition: string
} {
  return {
    backgroundColor: isActive ? tokens.colors.primary[600] : tokens.colors.gray[800],
    color: isActive ? tokens.colors.text.inverse : tokens.colors.gray[300],
    padding: `${tokens.spacing[2]} ${tokens.spacing[3]}`,
    borderRadius: tokens.radius.md,
    border: 'none',
    cursor: 'pointer',
    transition: 'background-color 0.2s ease, color 0.2s ease',
  }
}

/**
 * Returns inline styles for chart select control
 */
export function getChartSelectStyles(tokens: DesignTokens): {
  backgroundColor: string
  border: string
  color: string
  padding: string
  borderRadius: string
  fontSize: string
  appearance: 'none'
} {
  return {
    backgroundColor: tokens.colors.surface.overlay,
    border: `1px solid ${tokens.colors.border.subtle}`,
    color: tokens.colors.text.primary,
    padding: `${tokens.spacing[2]} ${tokens.spacing[3]}`,
    borderRadius: tokens.radius.sm,
    fontSize: tokens.typography.fontSize.sm,
    appearance: 'none',
  }
}

/**
 * Returns styles for icon-only chart toolbar buttons
 */
export function getIconButtonStyles(
  tokens: DesignTokens,
  state: 'default' | 'hover' = 'default',
): {
  backgroundColor: string
  border: string
  color: string
  padding: string
  borderRadius: string
  transition: string
} {
  const color = state === 'hover' ? tokens.colors.text.primary : tokens.colors.text.muted
  return {
    backgroundColor: 'transparent',
    border: 'none',
    color,
    padding: tokens.spacing[2],
    borderRadius: tokens.radius.sm,
    transition: 'color 0.2s ease',
  }
}

/**
 * Returns overlay styles for loading and error states
 */
export function getOverlayStyles(tokens: DesignTokens): {
  position: 'absolute'
  inset: number
  backgroundColor: string
  display: 'flex'
  alignItems: 'center'
  justifyContent: 'center'
  zIndex: number
} {
  return {
    position: 'absolute',
    inset: 0,
    backgroundColor: `${tokens.colors.surface.base}cc`,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10,
  }
}

/**
 * Returns spinner dimension and color styles using tokens
 */
export function getSpinnerStyles(
  size: 'sm' | 'md' | 'lg',
  tokens: DesignTokens,
  variant: 'primary' | 'success' | 'white' = 'primary',
): {
  width: string
  height: string
  borderWidth: string
  borderColor: string
  borderStyle: 'solid'
  borderRadius: string
} {
  const sizeMap = {
    sm: { dimension: tokens.spacing[4], borderWidth: '2px' },
    md: { dimension: tokens.spacing[5], borderWidth: '3px' },
    lg: { dimension: tokens.spacing[6], borderWidth: '4px' },
  }

  const colorMap = {
    primary: tokens.colors.primary[500],
    success: tokens.colors.success[500],
    white: tokens.colors.text.inverse,
  }

  const { dimension, borderWidth } = sizeMap[size]
  const borderColor = colorMap[variant]

  return {
    width: dimension,
    height: dimension,
    borderWidth,
    borderColor,
    borderStyle: 'solid',
    borderRadius: tokens.radius.full,
  }
}

// New helpers
export type IconSize = 'sm' | 'md' | 'lg'

export function getIconSizeStyles(size: IconSize, tokens: DesignTokens): {
  width: string
  height: string
} {
  const map: Record<IconSize, string> = {
    sm: tokens.spacing[3],
    md: tokens.spacing[4],
    lg: tokens.spacing[5],
  }
  const dimension = map[size]
  return { width: dimension, height: dimension }
}

export function getPanelContainerStyles(tokens: DesignTokens): {
  backgroundColor: string
  borderLeft: string
  borderRadius: string
} {
  return {
    backgroundColor: tokens.colors.surface.raised,
    borderLeft: `1px solid ${tokens.colors.border.default}`,
    borderRadius: tokens.radius.lg,
  }
}

export function getPanelHeaderStyles(tokens: DesignTokens): {
  display: 'flex'
  alignItems: 'center'
  justifyContent: 'space-between'
  padding: string
  borderBottom: string
} {
  return {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: `${tokens.spacing[4]} ${tokens.spacing[4]}`,
    borderBottom: `1px solid ${tokens.colors.border.subtle}`,
  }
}

export function getPanelItemStyles(isActive: boolean, tokens: DesignTokens): {
  display: 'flex'
  alignItems: 'center'
  padding: string
  borderRadius: string
  backgroundColor: string
  color: string
  transition: string
} {
  return {
    display: 'flex',
    alignItems: 'center',
    padding: tokens.spacing[3],
    borderRadius: tokens.radius.md,
    backgroundColor: isActive ? tokens.colors.surface.overlay : 'transparent',
    color: isActive ? tokens.colors.text.primary : tokens.colors.text.secondary,
    transition: 'background-color 0.2s ease, color 0.2s ease',
  }
}

export function getSmcLabelStyles(
  event: { direction: 'bullish' | 'bearish'; type: string },
  tokens: DesignTokens,
): {
  padding: string
  fontSize: string
  fontWeight: number
  borderRadius: string
  backgroundColor: string
  color: string
} {
  const isBullish = event.direction === 'bullish'
  return {
    padding: `${tokens.spacing[1]} ${tokens.spacing[2]}`,
    fontSize: tokens.typography.fontSize.xs,
    fontWeight: tokens.typography.fontWeight.medium,
    borderRadius: tokens.radius.md,
    backgroundColor: isBullish ? tokens.colors.success[600] : tokens.colors.error[600],
    color: tokens.colors.text.inverse,
  }
}

export function getSmcLineStyles(
  event: { direction: 'bullish' | 'bearish'; type: string },
  tokens: DesignTokens,
): {
  height: string
  width: string
  backgroundColor: string
} {
  const isBullish = event.direction === 'bullish'
  return {
    height: '1px',
    width: '100%',
    backgroundColor: isBullish ? tokens.colors.success[500] : tokens.colors.error[500],
  }
}

export function getZoneOverlayStyles(
  zone: { type: 'supply' | 'demand'; strength?: number; touches?: number },
  tokens: DesignTokens,
): {
  width: string
  backgroundColor: string
  opacity: number
  border: string
  borderRadius: string
} {
  const color = zone.type === 'supply' ? tokens.colors.error[500] : tokens.colors.success[500]
  const strength = zone.strength ?? 0
  const touches = zone.touches ?? 0
  const baseOpacity = Math.min(0.1 + strength * 0.08, 0.5)
  const finalOpacity = Math.max(baseOpacity - touches * 0.05, 0.1)
  return {
    width: '100%',
    backgroundColor: color,
    opacity: finalOpacity,
    border: `1px solid ${color}`,
    borderRadius: tokens.radius.md,
  }
}

export function getZoneLabelStyles(
  zone: { type: 'supply' | 'demand' },
  tokens: DesignTokens,
): {
  fontSize: string
  color: string
} {
  return {
    fontSize: tokens.typography.fontSize.xs,
    color: zone.type === 'supply' ? tokens.colors.error[600] : tokens.colors.success[600],
  }
}

export function getZoneBadgeStyles(
  zone: { type: 'supply' | 'demand' },
  tokens: DesignTokens,
): {
  backgroundColor: string
  color: string
  borderRadius: string
  padding: string
  fontSize: string
} {
  const bg = zone.type === 'supply' ? tokens.colors.error[100] : tokens.colors.success[100]
  const text = zone.type === 'supply' ? tokens.colors.error[700] : tokens.colors.success[700]
  return {
    backgroundColor: bg,
    color: text,
    borderRadius: tokens.radius.full,
    padding: `${tokens.spacing[0]} ${tokens.spacing[1]}`,
    fontSize: tokens.typography.fontSize.xs,
  }
}

export function getAbsoluteFillStyles(
  tokens: DesignTokens,
  zIndex: number,
  pointerEvents: 'auto' | 'none' = 'none',
): {
  position: 'absolute'
  top: number
  right: number
  bottom: number
  left: number
  zIndex: number
  pointerEvents: 'auto' | 'none'
} {
  return {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex,
    pointerEvents,
  }
}

export function getPageHeadingStyles(tokens: DesignTokens): {
  fontSize: string
  fontWeight: number
  color: string
  margin: string
} {
  return {
    fontSize: tokens.typography.fontSize.xl,
    fontWeight: tokens.typography.fontWeight.semibold,
    color: tokens.colors.text.primary,
    margin: `0 0 ${tokens.spacing[4]} 0`,
  }
}

export function getTabButtonStyles(isActive: boolean, tokens: DesignTokens): {
  backgroundColor: string
  color: string
  padding: string
  borderRadius: string
  border: string
  cursor: string
} {
  return {
    backgroundColor: isActive ? tokens.colors.primary[600] : tokens.colors.surface.overlay,
    color: isActive ? tokens.colors.text.inverse : tokens.colors.text.secondary,
    padding: `${tokens.spacing[2]} ${tokens.spacing[4]}`,
    borderRadius: tokens.radius.md,
    border: 'none',
    cursor: 'pointer',
  }
}
