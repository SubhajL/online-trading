'use client'

import { useState, useEffect } from 'react'
import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { Dashboard } from '@/components/Dashboard/Dashboard'
import type { Position, Order, Balance, OrderFormValues, Symbol, OrderId } from '@/types'

export default function Home() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [balances, setBalances] = useState<Balance[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>()
  const [autoTradingEnabled, setAutoTradingEnabled] = useState(false)

  // Simulate loading data
  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true)

        // Simulate API calls
        await new Promise(resolve => setTimeout(resolve, 1000))

        // Mock data
        setPositions([
          {
            symbol: 'BTCUSDT' as Symbol,
            side: 'BUY',
            quantity: 0.1,
            entryPrice: 40000,
            markPrice: 42000,
            pnl: 200,
            pnlPercent: 5,
            venue: 'SPOT',
          },
        ])

        setOrders([
          {
            orderId: 'ORD001' as OrderId,
            symbol: 'BTCUSDT' as Symbol,
            side: 'BUY',
            type: 'MARKET',
            quantity: 0.1,
            status: 'FILLED',
            venue: 'SPOT',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            executedQuantity: 0.1,
            avgPrice: 40000,
          },
        ])

        setBalances([
          {
            asset: 'USDT',
            free: 10000,
            locked: 500,
            venue: 'SPOT',
          },
          {
            asset: 'BTC',
            free: 0.5,
            locked: 0,
            venue: 'SPOT',
            usdValue: 21000,
          },
        ])

        setLoading(false)
      } catch {
        setError('Failed to load data')
        setLoading(false)
      }
    }

    loadData()
  }, [])

  const handleSubmitOrder = (order: OrderFormValues) => {
    console.info('Submitting order:', order)
    // TODO: Implement order submission
  }

  const handleToggleAutoTrading = (enabled: boolean) => {
    setAutoTradingEnabled(enabled)
    console.info('Auto trading:', enabled ? 'enabled' : 'disabled')
  }

  const handleLogout = () => {
    console.info('Logging out...')
    // TODO: Implement logout
  }

  return (
    <div className="app-layout">
      <Header userName="Trader" onLogout={handleLogout} />

      <div className="app-body">
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main className="app-main">
          <Dashboard
            positions={positions}
            orders={orders}
            balances={balances}
            loading={loading}
            error={error}
            autoTradingEnabled={autoTradingEnabled}
            onSubmitOrder={handleSubmitOrder}
            onToggleAutoTrading={handleToggleAutoTrading}
          />
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

        @media (max-width: 768px) {
          .app-body {
            position: relative;
          }

          .app-main {
            width: 100%;
          }
        }
      `}</style>
    </div>
  )
}
