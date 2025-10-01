'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { useState } from 'react'
import { useOrderHistory } from '@/hooks/useOrderHistory'

export default function HistoryPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Use real API hook with historical orders
  const { filteredOrders, loading, error, stats, dateRange, setDateRange } = useOrderHistory({
    status: 'FILLED',
    limit: 100,
  })

  // Map dateRange values to match component's expected values
  // const mapDateRange = (range: string) => {
  //   switch (range) {
  //     case '1d':
  //       return '1d'
  //     case '7d':
  //       return '7d'
  //     case '30d':
  //       return '30d'
  //     case '90d':
  //       return '90d'
  //     default:
  //       return 'all'
  //   }
  // }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    })
  }

  const formatTime = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <div className="app-layout">
      <Header userName="Trader" onLogout={() => console.warn('TODO: Implement logout')} />

      <div className="app-body">
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main id="main-content" className="app-main" tabIndex={-1}>
          <div className="page-container">
            <h1 className="page-title">Trade History</h1>

            {error && (
              <div className="error-message">
                <p>Failed to load trade history: {error}</p>
              </div>
            )}

            <div className="history-stats">
              <div className="stat-card">
                <span className="stat-label">Total Trades</span>
                <span className="stat-value">{stats.totalTrades}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Buy Orders</span>
                <span className="stat-value buy">{stats.buyOrders}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Sell Orders</span>
                <span className="stat-value sell">{stats.sellOrders}</span>
              </div>
              <div className="stat-card">
                <span className="stat-label">Total Volume</span>
                <span className="stat-value">
                  ${stats.totalVolume.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </span>
              </div>
            </div>

            <div className="history-controls">
              <div className="date-range-selector">
                <button
                  className={`range-btn ${dateRange === '1d' ? 'active' : ''}`}
                  onClick={() => setDateRange('1d')}
                >
                  24H
                </button>
                <button
                  className={`range-btn ${dateRange === '7d' ? 'active' : ''}`}
                  onClick={() => setDateRange('7d')}
                >
                  7D
                </button>
                <button
                  className={`range-btn ${dateRange === '30d' ? 'active' : ''}`}
                  onClick={() => setDateRange('30d')}
                >
                  30D
                </button>
                <button
                  className={`range-btn ${dateRange === 'all' ? 'active' : ''}`}
                  onClick={() => setDateRange('all')}
                >
                  All
                </button>
              </div>
            </div>

            <div className="history-table-container">
              {loading ? (
                <p className="loading-message">Loading history...</p>
              ) : filteredOrders.length === 0 ? (
                <p className="empty-message">No trades found in selected period</p>
              ) : (
                <table className="history-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Time</th>
                      <th>Symbol</th>
                      <th>Type</th>
                      <th>Side</th>
                      <th>Price</th>
                      <th>Quantity</th>
                      <th>Total</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredOrders.map(order => (
                      <tr key={order.orderId}>
                        <td>{formatDate(order.createdAt)}</td>
                        <td>{formatTime(order.createdAt)}</td>
                        <td>{order.symbol}</td>
                        <td>{order.type}</td>
                        <td className={order.side === 'BUY' ? 'buy' : 'sell'}>{order.side}</td>
                        <td>${(order.avgPrice || order.price || 0).toFixed(2)}</td>
                        <td>{(order.executedQuantity || 0).toFixed(4)}</td>
                        <td>
                          $
                          {(
                            (order.avgPrice || order.price || 0) * (order.executedQuantity || 0)
                          ).toLocaleString('en-US', {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </td>
                        <td>
                          <span className={`status status-${order.status.toLowerCase()}`}>
                            {order.status}
                          </span>
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
    </div>
  )
}
