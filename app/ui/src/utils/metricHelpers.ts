import type { DesignTokens } from '../types/tokens'

/**
 * Metric helper utilities for Dashboard components.
 * Provides token-based color derivation for metric trends and changes.
 */

/**
 * Computes trend color based on value comparison to threshold.
 *
 * @param value - Current metric value
 * @param threshold - Baseline threshold for comparison (default: 0)
 * @param tokens - Design tokens for color values
 * @returns Color string from tokens: text.success, text.danger, or text.muted
 */
export function computeMetricTrend(
  value: number,
  threshold: number = 0,
  tokens: DesignTokens,
): string {
  if (value > threshold) {
    return tokens.colors.text.success
  }
  if (value < threshold) {
    return tokens.colors.text.danger
  }
  return tokens.colors.text.muted
}

/**
 * Derives change class based on string prefix.
 *
 * @param changeValue - Change string with optional +/- prefix
 * @returns Token-based class name: 'change-positive', 'change-negative', or 'change-neutral'
 */
export function deriveChangeClass(changeValue: string): string {
  if (changeValue.startsWith('+')) {
    return 'change-positive'
  }
  if (changeValue.startsWith('-')) {
    return 'change-negative'
  }
  return 'change-neutral'
}
