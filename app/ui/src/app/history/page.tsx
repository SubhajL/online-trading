'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { useState } from 'react'
import { useOrderHistory } from '@/hooks/useOrderHistory'
import styles from './history.module.css'

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
    <div className={styles.appLayout}>
      <Header userName="Trader" onLogout={() => console.warn('TODO: Implement logout')} />

      <div className={styles.appBody}>
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main id="main-content" className={styles.appMain} tabIndex={-1}>
          <div className={styles.pageContainer}>
            <h1 className={styles.pageTitle}>Trade History</h1>

            {error && (
              <div className={styles.errorMessage}>
                <p>Failed to load trade history: {error}</p>
              </div>
            )}

            <div className={styles.historyStats}>
              <div className={styles.statCard}>
                <span className={styles.statLabel}>Total Trades</span>
                <span className={styles.statValue}>{stats.totalTrades}</span>
              </div>
              <div className={styles.statCard}>
                <span className={styles.statLabel}>Buy Orders</span>
                <span className={`${styles.statValue} ${styles.buy}`}>{stats.buyOrders}</span>
              </div>
              <div className={styles.statCard}>
                <span className={styles.statLabel}>Sell Orders</span>
                <span className={`${styles.statValue} ${styles.sell}`}>{stats.sellOrders}</span>
              </div>
              <div className={styles.statCard}>
                <span className={styles.statLabel}>Total Volume</span>
                <span className={styles.statValue}>
                  ${stats.totalVolume.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </span>
              </div>
            </div>

            <div className={styles.historyControls}>
              <div className={styles.dateRangeSelector}>
                <button
                  className={`${styles.rangeBtn} ${dateRange === '1d' ? styles.active : ''}`}
                  onClick={() => setDateRange('1d')}
                >
                  24H
                </button>
                <button
                  className={`${styles.rangeBtn} ${dateRange === '7d' ? styles.active : ''}`}
                  onClick={() => setDateRange('7d')}
                >
                  7D
                </button>
                <button
                  className={`${styles.rangeBtn} ${dateRange === '30d' ? styles.active : ''}`}
                  onClick={() => setDateRange('30d')}
                >
                  30D
                </button>
                <button
                  className={`${styles.rangeBtn} ${dateRange === 'all' ? styles.active : ''}`}
                  onClick={() => setDateRange('all')}
                >
                  All
                </button>
              </div>
            </div>

            <div className={styles.historyTableContainer}>
              {loading ? (
                <p className={styles.loadingMessage}>Loading history...</p>
              ) : filteredOrders.length === 0 ? (
                <p className={styles.emptyMessage}>No trades found in selected period</p>
              ) : (
                <table className={styles.historyTable}>
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
                        <td className={order.side === 'BUY' ? styles.buy : styles.sell}>
                          {order.side}
                        </td>
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
                          <span className={`${styles.status} ${styles.statusFilled}`}>
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
