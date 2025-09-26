'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { useState, useEffect } from 'react'
import type { Order } from '@/types'

export default function HistoryPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [orders, setOrders] = useState<Order[]>([])
  const [loading, setLoading] = useState(true)
  const [dateRange, setDateRange] = useState('7d')

  useEffect(() => {
    // TODO: Fetch real historical data from BFF
    const loadData = async () => {
      try {
        setLoading(true)
        await new Promise(resolve => setTimeout(resolve, 500))

        // Mock historical data
        const historicalOrders: Order[] = []
        const symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT']
        const sides = ['BUY', 'SELL'] as const
        const types = ['MARKET', 'LIMIT'] as const

        // Generate 50 mock historical orders
        for (let i = 0; i < 50; i++) {
          const symbol = symbols[Math.floor(Math.random() * symbols.length)]
          const side = sides[Math.floor(Math.random() * sides.length)]
          const type = types[Math.floor(Math.random() * types.length)]
          const quantity = Math.random() * 2 + 0.1
          const price = symbol === 'BTCUSDT' ? 40000 + Math.random() * 5000
            : symbol === 'ETHUSDT' ? 2500 + Math.random() * 500
            : symbol === 'BNBUSDT' ? 300 + Math.random() * 100
            : 1 + Math.random() * 0.5

          historicalOrders.push({
            orderId: `HIST${String(i + 1).padStart(3, '0')}`,
            symbol,
            side,
            type,
            quantity,
            price,
            status: 'FILLED',
            venue: 'SPOT',
            createdAt: new Date(Date.now() - (i + 1) * 24 * 60 * 60 * 1000).toISOString(),
            updatedAt: new Date(Date.now() - (i + 1) * 24 * 60 * 60 * 1000).toISOString(),
            executedQuantity: quantity,
            avgPrice: price,
          })
        }

        setOrders(historicalOrders)
        setLoading(false)
      } catch (error) {
        console.error('Failed to load history:', error)
        setLoading(false)
      }
    }

    loadData()
  }, [dateRange])

  const filteredOrders = orders.filter(order => {
    const orderDate = new Date(order.createdAt)
    const now = new Date()
    const daysDiff = (now.getTime() - orderDate.getTime()) / (1000 * 60 * 60 * 24)

    switch (dateRange) {
      case '1d': return daysDiff <= 1
      case '7d': return daysDiff <= 7
      case '30d': return daysDiff <= 30
      case '90d': return daysDiff <= 90
      default: return true
    }
  })

  const calculateStats = () => {
    const buyOrders = filteredOrders.filter(o => o.side === 'BUY')
    const sellOrders = filteredOrders.filter(o => o.side === 'SELL')
    const totalVolume = filteredOrders.reduce((sum, o) => {
      const vol = (o.avgPrice || o.price || 0) * (o.executedQuantity || 0)
      return sum + vol
    }, 0)

    return {
      totalTrades: filteredOrders.length,
      buyOrders: buyOrders.length,
      sellOrders: sellOrders.length,
      totalVolume,
    }
  }

  const stats = calculateStats()

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

        <main className="app-main">
          <div className="page-container">
            <h1 className="page-title">Trade History</h1>

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
                <span className="stat-value">${stats.totalVolume.toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
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
                  className={`range-btn ${dateRange === '90d' ? 'active' : ''}`}
                  onClick={() => setDateRange('90d')}
                >
                  90D
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
                    {filteredOrders.map((order) => (
                      <tr key={order.orderId}>
                        <td>{formatDate(order.createdAt)}</td>
                        <td>{formatTime(order.createdAt)}</td>
                        <td>{order.symbol}</td>
                        <td>{order.type}</td>
                        <td className={order.side === 'BUY' ? 'buy' : 'sell'}>{order.side}</td>
                        <td>${(order.avgPrice || order.price || 0).toFixed(2)}</td>
                        <td>{(order.executedQuantity || 0).toFixed(4)}</td>
                        <td>
                          ${((order.avgPrice || order.price || 0) * (order.executedQuantity || 0)).toLocaleString('en-US', {
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

        .history-stats {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 1rem;
          margin-bottom: 2rem;
        }

        .stat-card {
          background: #2a2d3a;
          padding: 1.5rem;
          border-radius: 0.5rem;
          border: 1px solid #3a3d4a;
          display: flex;
          flex-direction: column;
        }

        .stat-label {
          font-size: 0.875rem;
          color: #9ca3af;
          margin-bottom: 0.5rem;
        }

        .stat-value {
          font-size: 1.5rem;
          font-weight: bold;
          color: #f0f0f0;
        }

        .history-controls {
          margin-bottom: 2rem;
        }

        .date-range-selector {
          display: flex;
          gap: 0.5rem;
        }

        .range-btn {
          padding: 0.5rem 1rem;
          background: transparent;
          border: 1px solid #3a3d4a;
          color: #9ca3af;
          border-radius: 0.25rem;
          cursor: pointer;
          transition: all 0.2s;
        }

        .range-btn:hover {
          background: #3a3d4a;
          color: #f0f0f0;
        }

        .range-btn.active {
          background: #4f46e5;
          border-color: #4f46e5;
          color: white;
        }

        .history-table-container {
          background: #2a2d3a;
          border-radius: 0.5rem;
          border: 1px solid #3a3d4a;
          overflow-x: auto;
        }

        .history-table {
          width: 100%;
          border-collapse: collapse;
          min-width: 800px;
        }

        .history-table th {
          text-align: left;
          padding: 1rem;
          background: #1a1d2a;
          color: #9ca3af;
          font-weight: 500;
          font-size: 0.875rem;
          white-space: nowrap;
        }

        .history-table td {
          padding: 0.75rem 1rem;
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

        .buy { color: #10b981; }
        .sell { color: #ef4444; }

        .status {
          padding: 0.25rem 0.5rem;
          border-radius: 0.25rem;
          font-size: 0.75rem;
          font-weight: 500;
        }

        .status-filled {
          background: #065f46;
          color: #34d399;
        }
      `}</style>
    </div>
  )
}