import type { DesignTokens } from '../types/tokens'

export type ToolbarVariant = 'primary' | 'secondary' | 'success' | 'error'
export type SpinnerSize = 'sm' | 'md' | 'lg'

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
 * Returns inline style object for error banner
 */
export function composeErrorBannerStyles(
  hasIcon: boolean,
  tokens: DesignTokens,
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
  return {
    backgroundColor: tokens.colors.error[50],
    color: tokens.colors.text.danger,
    padding: tokens.spacing[4],
    borderRadius: tokens.radius.md,
    border: `1px solid ${tokens.colors.error[200]}`,
    display: hasIcon ? 'flex' : 'block',
    alignItems: hasIcon ? 'center' : undefined,
    gap: hasIcon ? tokens.spacing[3] : undefined,
  }
}

/**
 * Returns inline style object for page container
 */
export function buildPageContainerStyle(
  tokens: DesignTokens,
  paddingLevel: 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 = 8,
): { padding: string; backgroundColor: string } {
  return {
    padding: tokens.spacing[paddingLevel],
    backgroundColor: tokens.colors.surface.base,
  }
}
