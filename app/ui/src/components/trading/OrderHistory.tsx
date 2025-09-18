import { useState, useMemo } from 'react'
import type { Order, OrderStatus } from '@/types'
import { formatNumber } from '@/utils/formatters'
import './OrderHistory.css'

type OrderHistoryProps = {
  orders: Order[]
  loading?: boolean
  error?: string
  pageSize?: number
  className?: string
}

const STATUS_FILTER_OPTIONS: { value: OrderStatus | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'All Statuses' },
  { value: 'NEW', label: 'New' },
  { value: 'PARTIALLY_FILLED', label: 'Partially Filled' },
  { value: 'FILLED', label: 'Filled' },
  { value: 'CANCELED', label: 'Canceled' },
  { value: 'REJECTED', label: 'Rejected' },
  { value: 'EXPIRED', label: 'Expired' },
]

export function OrderHistory({
  orders,
  loading = false,
  error,
  pageSize = 20,
  className = '',
}: OrderHistoryProps) {
  const [statusFilter, setStatusFilter] = useState<OrderStatus | 'ALL'>('ALL')
  const [currentPage, setCurrentPage] = useState(0)

  const filteredOrders = useMemo(() => {
    let filtered = orders
    if (statusFilter !== 'ALL') {
      filtered = orders.filter(order => order.status === statusFilter)
    }
    // Sort by date descending (newest first) - create a copy to avoid mutating
    return [...filtered].sort((a, b) =>
      new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
    )
  }, [orders, statusFilter])

  const paginatedOrders = useMemo(() => {
    const start = currentPage * pageSize
    return filteredOrders.slice(start, start + pageSize)
  }, [filteredOrders, currentPage, pageSize])

  const totalPages = Math.ceil(filteredOrders.length / pageSize)

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return {
      date: date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      }),
      time: date.toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      })
    }
  }

  const getStatusClass = (status: OrderStatus) => {
    return status.toLowerCase().replace('_', '-')
  }

  if (loading) {
    return (
      <div className={`order-history ${className}`} data-testid="order-history">
        <h3 className="order-history-title">Order History</h3>
        <div className="order-history-loading" data-testid="order-history-loading">
          Loading order history...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`order-history ${className}`} data-testid="order-history">
        <h3 className="order-history-title">Order History</h3>
        <div className="order-history-error" data-testid="order-history-error">
          {error}
        </div>
      </div>
    )
  }

  return (
    <div className={`order-history ${className}`} data-testid="order-history">
      <div className="order-history-header">
        <h3 className="order-history-title">Order History</h3>
        <div className="order-history-filter">
          <label htmlFor="status-filter">Filter by status</label>
          <select
            id="status-filter"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value as OrderStatus | 'ALL')
              setCurrentPage(0) // Reset to first page on filter change
            }}
          >
            {STATUS_FILTER_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {filteredOrders.length === 0 ? (
        <div className="empty-state">No order history</div>
      ) : (
        <>
          <div className="order-history-table">
            <div className="table-header">
              <span>Order ID</span>
              <span>Date/Time</span>
              <span>Symbol</span>
              <span>Type</span>
              <span>Side</span>
              <span>Price</span>
              <span>Avg Price</span>
              <span>Quantity</span>
              <span>Filled</span>
              <span>Status</span>
              <span>Venue</span>
            </div>

            {paginatedOrders.map((order) => {
              const { date, time } = formatDate(order.createdAt)
              const fillPercentage = order.executedQuantity
                ? Math.round((order.executedQuantity / order.quantity) * 100)
                : 0

              return (
                <div key={order.orderId} className="order-row">
                  <span className="order-id" data-testid={`order-id-${order.orderId}`}>
                    {order.orderId}
                  </span>
                  <span className="order-date">
                    <div>{date}</div>
                    <div className="order-time">{time}</div>
                  </span>
                  <span className="symbol">{order.symbol}</span>
                  <span className="order-type">{order.type}</span>
                  <span className={`side-badge ${order.side.toLowerCase()}`}>
                    {order.side}
                  </span>
                  <span>
                    {order.type === 'MARKET' ? 'N/A' : formatNumber(order.price || 0)}
                  </span>
                  <span>
                    {order.avgPrice ? formatNumber(order.avgPrice) : 'N/A'}
                  </span>
                  <span>{order.quantity}</span>
                  <span>
                    {order.executedQuantity || 0} / {order.quantity}
                    {fillPercentage > 0 && fillPercentage < 100 && (
                      <span className="fill-percentage"> ({fillPercentage}%)</span>
                    )}
                  </span>
                  <span className={`status-badge ${getStatusClass(order.status)}`}>
                    {order.status}
                  </span>
                  <span className="venue-badge">{order.venue}</span>
                </div>
              )
            })}
          </div>

          {totalPages > 1 && (
            <div className="pagination">
              <button
                onClick={() => setCurrentPage(prev => Math.max(0, prev - 1))}
                disabled={currentPage === 0}
                aria-label="Previous page"
              >
                Previous
              </button>
              <span className="page-info">
                Page {currentPage + 1} of {totalPages}
              </span>
              <button
                onClick={() => setCurrentPage(prev => Math.min(totalPages - 1, prev + 1))}
                disabled={currentPage === totalPages - 1}
                aria-label="Next page"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}