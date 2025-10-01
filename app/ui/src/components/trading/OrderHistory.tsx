import { useState } from 'react'
import type { Order, OrderStatus } from '@/types'
import { deriveOrderStatusTheme, isCancelableStatus } from '@/utils/tradingHelpers'
import './OrderHistory.css'

type OrderHistoryProps = {
  orders: Order[]
  onCancel: (order: Order) => void
  loading?: boolean
}

export function OrderHistory({ orders, onCancel, loading = false }: OrderHistoryProps) {
  const [symbolFilter, setSymbolFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState<OrderStatus | ''>('')

  // Filter orders
  const filteredOrders = orders.filter(order => {
    if (symbolFilter && !order.symbol.toLowerCase().includes(symbolFilter.toLowerCase())) {
      return false
    }
    if (statusFilter && order.status !== statusFilter) {
      return false
    }
    return true
  })

  // Sort by creation time (newest first)
  const sortedOrders = [...filteredOrders].sort((a, b) => {
    return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
  })

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleTimeString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  const formatPrice = (order: Order) => {
    if (order.type === 'MARKET' && order.avgPrice) {
      return `$${order.avgPrice.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`
    }

    const priceStr = order.price
      ? `$${order.price.toLocaleString(undefined, {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}`
      : '-'

    if (order.stopPrice) {
      return `${priceStr} (S: $${order.stopPrice.toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })})`
    }

    return priceStr
  }

  const formatQuantity = (order: Order) => {
    if (order.executedQuantity !== undefined && order.executedQuantity !== order.quantity) {
      return `${order.executedQuantity} / ${order.quantity}`
    }
    return order.quantity.toString()
  }

  if (loading) {
    return (
      <div className="order-history">
        <div className="order-history-loading" data-testid="loading-spinner">
          Loading orders...
        </div>
      </div>
    )
  }

  return (
    <div data-testid="order-history" className="order-history">
      <div className="order-history-header">
        <h3 className="order-history-title">Order History</h3>
        <div className="order-history-filter">
          <label htmlFor="status-filter">Status:</label>
          <select
            id="status-filter"
            data-testid="status-filter"
            value={statusFilter}
            onChange={e => setStatusFilter(e.target.value as OrderStatus | '')}
          >
            <option value="">All</option>
            <option value="NEW">New</option>
            <option value="PARTIALLY_FILLED">Partial</option>
            <option value="FILLED">Filled</option>
            <option value="CANCELED">Canceled</option>
            <option value="REJECTED">Rejected</option>
            <option value="EXPIRED">Expired</option>
          </select>
        </div>
      </div>

      {sortedOrders.length === 0 ? (
        <div className="empty-state">No orders yet</div>
      ) : (
        <div className="order-history-table">
          <div className="table-header">
            <span>Order ID</span>
            <span>Date/Time</span>
            <span>Symbol</span>
            <span>Type</span>
            <span>Side</span>
            <span>Price</span>
            <span>Amount</span>
            <span>Filled</span>
            <span>Total</span>
            <span>Status</span>
            <span>Venue</span>
          </div>

          {sortedOrders.map(order => {
            const statusTheme = deriveOrderStatusTheme(order.status)
            return (
              <div
                key={order.orderId}
                className="order-row"
                data-testid={`order-row-${order.orderId}`}
              >
                <span className="order-id">{order.orderId.slice(-8)}</span>
                <div className="order-date">
                  <span>{new Date(order.createdAt).toLocaleDateString()}</span>
                  <span className="order-time">{formatTime(order.createdAt)}</span>
                </div>
                <span className="symbol">{order.symbol}</span>
                <span className="order-type">{order.type}</span>
                <span className={`side-badge ${order.side.toLowerCase()}`}>{order.side}</span>
                <span>{formatPrice(order)}</span>
                <span>{order.quantity}</span>
                <span>
                  {order.executedQuantity ?? 0}
                  {order.executedQuantity && order.quantity && (
                    <span className="fill-percentage">
                      {' '}
                      ({Math.round((order.executedQuantity / order.quantity) * 100)}%)
                    </span>
                  )}
                </span>
                <span>
                  {order.avgPrice && order.executedQuantity
                    ? `$${(order.avgPrice * order.executedQuantity).toFixed(2)}`
                    : '-'}
                </span>
                <span className={`status-badge ${statusTheme.statusClass}`}>{order.status}</span>
                <span className="venue-badge">{order.venue}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
