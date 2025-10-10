/**
 * CSS helper utilities for dynamic class name generation
 */

/**
 * Converts order status enum to camelCase CSS module class name
 * @param status - Order status like "NEW", "PARTIALLY_FILLED", "CANCELED"
 * @returns CSS class name like "statusNew", "statusPartiallyFilled", "statusCanceled"
 */
export function mapStatusToClassName(status: string): string {
  const formatted =
    status.charAt(0) +
    status
      .slice(1)
      .toLowerCase()
      .replace(/_./g, (m: string) => m.charAt(1).toUpperCase())
  return `status${formatted}`
}
