'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { useState, useMemo } from 'react'
import { useOrders } from '@/hooks/useOrders'

export default function TradesPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [filter, setFilter] = useState<'all' | 'open' | 'filled' | 'canceled'>('all')

  // Use real API hook - fetch all orders without status filter
  const { orders, loading, error, cancelOrder } = useOrders({})

  const filteredOrders = useMemo(() => {
    return orders.filter(order => {
      if (filter === 'all') return true
      if (filter === 'open') return order.status === 'NEW' || order.status === 'PARTIALLY_FILLED'
      if (filter === 'filled') return order.status === 'FILLED'
      if (filter === 'canceled')
        return (
          order.status === 'CANCELED' || order.status === 'REJECTED' || order.status === 'EXPIRED'
        )
      return true
    })
  }, [orders, filter])

  const stats = useMemo(
    () => ({
      totalTrades: orders.length,
      openOrders: orders.filter(o => o.status === 'NEW' || o.status === 'PARTIALLY_FILLED').length,
      filledOrders: orders.filter(o => o.status === 'FILLED').length,
      canceledOrders: orders.filter(
        o => o.status === 'CANCELED' || o.status === 'REJECTED' || o.status === 'EXPIRED',
      ).length,
    }),
    [orders],
  )

  const handleCancelOrder = async (orderId: string) => {
    try {
      await cancelOrder(orderId)
      console.warn('Order canceled successfully:', orderId)
    } catch (error) {
      console.error('Failed to cancel order:', error)
    }
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <div className="app-layout">
      <Header userName="Trader" onLogout={() => console.warn('TODO: Implement logout')} />

      <div className="app-body">
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main className="app-main">
          <div className="page-container">
            <h1 className="page-title">Active Trades</h1>

            {error && (
              <div className="error-message">
                <p>Failed to load trades: {error}</p>
              </div>
            )}

            <div className="trades-summary">
              <div className="stat-card">
                <span className="stat-label">Total Trades</span>
                <span className="stat-value">{stats.totalTrades}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Open Orders</span>
                <span className="stat-value">{stats.openOrders}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Filled Orders</span>
                <span className="stat-value">{stats.filledOrders}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Canceled Orders</span>
                <span className="stat-value">{stats.canceledOrders}</span>
              </div>
            </div>

            <div className="trades-controls">
              <div className="filter-tabs">
                <button
                  className={`filter-tab ${filter === 'all' ? 'active' : ''}`}
                  onClick={() => setFilter('all')}
                >
                  All ({stats.totalTrades})
                </button>
                <button
                  className={`filter-tab ${filter === 'open' ? 'active' : ''}`}
                  onClick={() => setFilter('open')}
                >
                  Open ({stats.openOrders})
                </button>
                <button
                  className={`filter-tab ${filter === 'filled' ? 'active' : ''}`}
                  onClick={() => setFilter('filled')}
                >
                  Filled ({stats.filledOrders})
                </button>
                <button
                  className={`filter-tab ${filter === 'canceled' ? 'active' : ''}`}
                  onClick={() => setFilter('canceled')}
                >
                  Canceled ({stats.canceledOrders})
                </button>
              </div>
            </div>

            <div className="trades-table-container">
              {loading ? (
                <p className="loading-message">Loading trades...</p>
              ) : filteredOrders.length === 0 ? (
                <p className="empty-message">No trades found</p>
              ) : (
                <table className="trades-table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Symbol</th>
                      <th>Type</th>
                      <th>Side</th>
                      <th>Price</th>
                      <th>Quantity</th>
                      <th>Filled</th>
                      <th>Status</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredOrders.map(order => (
                      <tr key={order.orderId}>
                        <td>{formatDate(order.createdAt)}</td>
                        <td>{order.symbol}</td>
                        <td>{order.type}</td>
                        <td className={order.side === 'BUY' ? 'buy' : 'sell'}>{order.side}</td>
                        <td>
                          {order.type === 'MARKET'
                            ? 'Market'
                            : order.avgPrice && order.status === 'FILLED'
                              ? `$${order.avgPrice.toFixed(2)}`
                              : order.price
                                ? `$${order.price.toFixed(2)}`
                                : '-'}
                        </td>
                        <td>{order.quantity}</td>
                        <td>{order.executedQuantity || 0}</td>
                        <td>
                          <span className={`status status-${order.status.toLowerCase()}`}>
                            {order.status}
                          </span>
                        </td>
                        <td>
                          {(order.status === 'NEW' || order.status === 'PARTIALLY_FILLED') && (
                            <button
                              className="cancel-btn"
                              onClick={() => handleCancelOrder(String(order.orderId))}
                            >
                              Cancel
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </main>
      </div>

      <style jsx>{`
        .app-layout {
          display: flex;
          flex-direction: column;
          min-height: 100vh;
        }

        .app-body {
          display: flex;
          flex: 1;
        }

        .app-main {
          flex: 1;
          overflow-x: auto;
        }

        .page-container {
          padding: 2rem;
        }

        .page-title {
          margin-bottom: 2rem;
          color: #f0f0f0;
        }

        .trades-summary {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 1rem;
          margin-bottom: 2rem;
        }

        .stat-card {
          background: #2a2d3a;
          padding: 1rem;
          border-radius: 0.5rem;
          border: 1px solid #3a3d4a;
          display: flex;
          flex-direction: column;
          align-items: center;
        }

        .stat-label {
          font-size: 0.875rem;
          color: #9ca3af;
          margin-bottom: 0.25rem;
        }

        .stat-value {
          font-size: 1.5rem;
          font-weight: bold;
          color: #f0f0f0;
        }

        .trades-controls {
          margin-bottom: 2rem;
        }

        .filter-tabs {
          display: flex;
          gap: 1rem;
        }

        .filter-tab {
          padding: 0.5rem 1rem;
          background: transparent;
          border: 1px solid #3a3d4a;
          color: #9ca3af;
          border-radius: 0.25rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .filter-tab:hover {
          background: #3a3d4a;
          color: #f0f0f0;
        }

        .filter-tab.active {
          background: #4f46e5;
          border-color: #4f46e5;
          color: white;
        }

        .trades-table-container {
          background: #2a2d3a;
          border-radius: 0.5rem;
          border: 1px solid #3a3d4a;
          overflow: hidden;
        }

        .trades-table {
          width: 100%;
          border-collapse: collapse;
        }

        .trades-table th {
          text-align: left;
          padding: 1rem;
          background: #1a1d2a;
          color: #9ca3af;
          font-weight: 500;
          font-size: 0.875rem;
        }

        .trades-table td {
          padding: 1rem;
          border-top: 1px solid #3a3d4a;
          color: #f0f0f0;
          font-size: 0.875rem;
        }

        .loading-message,
        .empty-message {
          padding: 3rem;
          text-align: center;
          color: #9ca3af;
        }

        .buy {
          color: #10b981;
        }
        .sell {
          color: #ef4444;
        }

        .status {
          padding: 0.25rem 0.5rem;
          border-radius: 0.25rem;
          font-size: 0.75rem;
          font-weight: 500;
        }

        .status-new {
          background: #1e40af;
          color: #60a5fa;
        }

        .status-filled {
          background: #065f46;
          color: #34d399;
        }

        .status-partially_filled {
          background: #78350f;
          color: #fbbf24;
        }

        .status-canceled,
        .status-rejected,
        .status-expired {
          background: #7f1d1d;
          color: #fca5a5;
        }

        .cancel-btn {
          padding: 0.25rem 0.75rem;
          background: transparent;
          border: 1px solid #ef4444;
          color: #ef4444;
          border-radius: 0.25rem;
          font-size: 0.75rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .cancel-btn:hover {
          background: #ef4444;
          color: white;
        }

        .error-message {
          background: #dc2626;
          color: white;
          padding: 1rem;
          border-radius: 0.5rem;
          margin-bottom: 2rem;
        }
      `}</style>
    </div>
  )
}
