/**
 * Trading helper utilities for consistent order and position theming.
 * Provides token-based class name derivation for order statuses and P&L.
 */

import type { OrderStatus } from '@/types'

export type OrderStatusTheme = {
  statusClass: string
}

export type PositionDelta = {
  deltaClass: string
  displayValue: string
  formattedPnl: string
  formattedPnlPercent: string
}

/**
 * Derives theme class for order status badges.
 * Returns the status-specific class to be combined with .status-badge base class.
 *
 * @param status - Order status from exchange
 * @returns Object with CSS class name (e.g., 'new', 'filled') using design tokens
 *
 * @example
 * const theme = deriveOrderStatusTheme('NEW')
 * // Use as: <span className={`status-badge ${theme.statusClass}`}>NEW</span>
 */
export function deriveOrderStatusTheme(status: OrderStatus): OrderStatusTheme {
  const themes: Record<OrderStatus, OrderStatusTheme> = {
    NEW: { statusClass: 'new' },
    PARTIALLY_FILLED: { statusClass: 'partially-filled' },
    FILLED: { statusClass: 'filled' },
    CANCELED: { statusClass: 'canceled' },
    REJECTED: { statusClass: 'rejected' },
    EXPIRED: { statusClass: 'expired' },
  }

  return themes[status]
}

/**
 * Formats position P&L with appropriate styling class.
 *
 * @param pnl - Profit/loss dollar amount
 * @param pnlPercent - Profit/loss percentage
 * @returns Object with CSS class and formatted display string
 */
export function formatPositionDelta(pnl: number, pnlPercent: number): PositionDelta {
  const deltaClass = pnl > 0 ? 'delta-positive' : pnl < 0 ? 'delta-negative' : 'delta-neutral'

  const sign = pnl > 0 ? '+' : pnl < 0 ? '-' : ''
  const formattedPnl = `${sign}$${Math.abs(pnl).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`

  const percentSign = pnlPercent > 0 ? '+' : pnlPercent < 0 ? '' : ''
  const formattedPercent = `${percentSign}${pnlPercent.toFixed(2)}%`

  return {
    deltaClass,
    displayValue: `${formattedPnl} (${formattedPercent})`,
    formattedPnl,
    formattedPnlPercent: formattedPercent,
  }
}

/**
 * Determines if an order status allows cancellation.
 *
 * @param status - Order status from exchange
 * @returns True if order can be canceled (NEW or PARTIALLY_FILLED)
 */
export function isCancelableStatus(status: OrderStatus): boolean {
  return status === 'NEW' || status === 'PARTIALLY_FILLED'
}
