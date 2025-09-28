import { useState } from 'react'
import type { Order, OrderStatus } from '@/types'

type OrderHistoryProps = {
  orders: Order[]
  onCancel: (order: Order) => void
  loading?: boolean
}

const STATUS_COLORS: Record<OrderStatus, { bg: string; text: string }> = {
  NEW: { bg: 'bg-blue-500/10', text: 'text-blue-500' },
  PARTIALLY_FILLED: { bg: 'bg-yellow-500/10', text: 'text-yellow-500' },
  FILLED: { bg: 'bg-green-500/10', text: 'text-green-500' },
  CANCELED: { bg: 'bg-gray-500/10', text: 'text-gray-500' },
  REJECTED: { bg: 'bg-red-500/10', text: 'text-red-500' },
  EXPIRED: { bg: 'bg-gray-500/10', text: 'text-gray-500' },
}

const isCancelable = (status: OrderStatus) => {
  return status === 'NEW' || status === 'PARTIALLY_FILLED'
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
      <div className="bg-gray-900 rounded-lg p-4 flex justify-center items-center h-64">
        <div
          data-testid="loading-spinner"
          className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"
        />
      </div>
    )
  }

  return (
    <div data-testid="order-history" className="bg-gray-900 rounded-lg p-4">
      {/* Filters */}
      <div className="flex gap-4 mb-4">
        <input
          type="text"
          placeholder="Filter by symbol..."
          value={symbolFilter}
          onChange={e => setSymbolFilter(e.target.value)}
          className="flex-1 px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
        <select
          data-testid="status-filter"
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as OrderStatus | '')}
          className="px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        >
          <option value="">All Status</option>
          <option value="NEW">New</option>
          <option value="PARTIALLY_FILLED">Partial</option>
          <option value="FILLED">Filled</option>
          <option value="CANCELED">Canceled</option>
          <option value="REJECTED">Rejected</option>
          <option value="EXPIRED">Expired</option>
        </select>
      </div>

      {/* Orders table */}
      {sortedOrders.length === 0 ? (
        <div className="text-center text-gray-500 py-8">No orders yet</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-gray-400 border-b border-gray-800">
                <th className="pb-2">Time</th>
                <th className="pb-2">Symbol</th>
                <th className="pb-2">Side</th>
                <th className="pb-2">Type</th>
                <th className="pb-2">Price</th>
                <th className="pb-2">Quantity</th>
                <th className="pb-2">Status</th>
                <th className="pb-2">Venue</th>
                <th className="pb-2"></th>
              </tr>
            </thead>
            <tbody className="text-sm">
              {sortedOrders.map(order => (
                <tr
                  key={order.orderId}
                  data-testid={`order-row-${order.orderId}`}
                  className="border-b border-gray-800 hover:bg-gray-800/50"
                >
                  <td className="py-2">{formatTime(order.createdAt)}</td>
                  <td className="py-2">{order.symbol}</td>
                  <td
                    className={`py-2 ${order.side === 'BUY' ? 'text-green-500' : 'text-red-500'}`}
                  >
                    {order.side}
                  </td>
                  <td className="py-2">{order.type}</td>
                  <td className="py-2">{formatPrice(order)}</td>
                  <td className="py-2">{formatQuantity(order)}</td>
                  <td className="py-2">
                    <span
                      className={`px-2 py-1 text-xs rounded ${STATUS_COLORS[order.status].bg} ${STATUS_COLORS[order.status].text}`}
                    >
                      {order.status}
                    </span>
                  </td>
                  <td className="py-2">
                    <span
                      className={`px-2 py-1 text-xs rounded ${
                        order.venue === 'SPOT'
                          ? 'bg-blue-500/10 text-blue-500'
                          : 'bg-purple-500/10 text-purple-500'
                      }`}
                    >
                      {order.venue}
                    </span>
                  </td>
                  <td className="py-2">
                    {isCancelable(order.status) && (
                      <button
                        data-testid="cancel-order-button"
                        onClick={() => onCancel(order)}
                        className="text-xs text-red-500 hover:text-red-400"
                      >
                        Cancel
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
