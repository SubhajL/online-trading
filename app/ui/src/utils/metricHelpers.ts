/**
 * Metric helper utilities for Dashboard components.
 * Provides token-based class name derivation for metric trends and changes.
 */

/**
 * Computes trend class based on value comparison to threshold.
 *
 * @param value - Current metric value
 * @param threshold - Baseline threshold for comparison (default: 0)
 * @returns Token-based class name: 'trend-up', 'trend-down', or 'trend-neutral'
 */
export function computeMetricTrend(value: number, threshold: number = 0): string {
  if (value > threshold) {
    return 'trend-up'
  }
  if (value < threshold) {
    return 'trend-down'
  }
  return 'trend-neutral'
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
