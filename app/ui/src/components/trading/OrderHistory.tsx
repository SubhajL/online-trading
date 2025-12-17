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
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Type</th>
                <th>Qty</th>
                <th>Price</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedOrders.map(order => {
                const statusTheme = deriveOrderStatusTheme(order.status)
                return (
                  <tr key={order.orderId} data-testid={`order-row-${order.orderId}`}>
                    <td className="order-time-cell">
                      <div>{new Date(order.createdAt).toLocaleDateString()}</div>
                      <div className="order-time">{formatTime(order.createdAt)}</div>
                    </td>
                    <td className="symbol">{order.symbol}</td>
                    <td>
                      <span className={`side-badge ${order.side.toLowerCase()}`}>{order.side}</span>
                    </td>
                    <td className="order-type">{order.type}</td>
                    <td>{order.quantity}</td>
                    <td>{formatPrice(order)}</td>
                    <td>
                      <span className={`status-badge ${statusTheme.statusClass}`}>{order.status}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
