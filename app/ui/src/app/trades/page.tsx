'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { PageShell } from '@/components/Layout/PageShell'
import { useState, useMemo } from 'react'
import { useOrders } from '@/hooks/useOrders'
import { mapStatusToClassName } from '@/utils/cssHelpers'
import styles from './trades.module.css'

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

  const handleCancelOrder = async (orderId: string, symbol: string, venue: 'SPOT' | 'USD_M') => {
    try {
      await cancelOrder(orderId, symbol, venue)
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
    <PageShell skipLinkTarget="trades-content" maxWidth="xl">
      <Header userName="Trader" onLogout={() => console.warn('TODO: Implement logout')} />

      <div style={{ display: 'flex', flex: 1 }}>
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main id="main-content" tabIndex={-1} style={{ flex: 1, padding: '1rem' }}>
          <h1 className={styles.pageTitle}>Active Trades</h1>

          {error && (
            <div className={styles.errorMessage}>
              <p>Failed to load trades: {error}</p>
            </div>
          )}

          <div className={styles.tradesSummary}>
            <div className={styles.statCard}>
              <span className={styles.statLabel}>Total Trades</span>
              <span className={styles.statValue}>{stats.totalTrades}</span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statLabel}>Open Orders</span>
              <span className={styles.statValue}>{stats.openOrders}</span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statLabel}>Filled Orders</span>
              <span className={styles.statValue}>{stats.filledOrders}</span>
            </div>
            <div className={styles.statCard}>
              <span className={styles.statLabel}>Canceled Orders</span>
              <span className={styles.statValue}>{stats.canceledOrders}</span>
            </div>
          </div>

          <div className={styles.tradesControls}>
            <div className={styles.filterTabs}>
              <button
                className={`${styles.filterTab} ${filter === 'all' ? styles.active : ''}`}
                onClick={() => setFilter('all')}
              >
                All ({stats.totalTrades})
              </button>
              <button
                className={`${styles.filterTab} ${filter === 'open' ? styles.active : ''}`}
                onClick={() => setFilter('open')}
              >
                Open ({stats.openOrders})
              </button>
              <button
                className={`${styles.filterTab} ${filter === 'filled' ? styles.active : ''}`}
                onClick={() => setFilter('filled')}
              >
                Filled ({stats.filledOrders})
              </button>
              <button
                className={`${styles.filterTab} ${filter === 'canceled' ? styles.active : ''}`}
                onClick={() => setFilter('canceled')}
              >
                Canceled ({stats.canceledOrders})
              </button>
            </div>
          </div>

          <div className={styles.tradesTableContainer}>
            {loading ? (
              <p className={styles.loadingMessage}>Loading trades...</p>
            ) : filteredOrders.length === 0 ? (
              <p className={styles.emptyMessage}>No trades found</p>
            ) : (
              <table className={styles.tradesTable}>
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
                      <td className={order.side === 'BUY' ? styles.buy : styles.sell}>
                        {order.side}
                      </td>
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
                        <span
                          className={`${styles.status} ${styles[mapStatusToClassName(order.status)] || ''}`}
                        >
                          {order.status}
                        </span>
                      </td>
                      <td>
                        {(order.status === 'NEW' || order.status === 'PARTIALLY_FILLED') && (
                          <button
                            className={styles.cancelBtn}
                            onClick={() =>
                              handleCancelOrder(String(order.orderId), order.symbol, order.venue)
                            }
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
        </main>
      </div>
    </PageShell>
  )
}
