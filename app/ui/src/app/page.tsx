'use client'

import { useState } from 'react'
import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { Dashboard } from '@/components/Dashboard/Dashboard'
import { useBalances } from '@/hooks/useBalances'
import { usePositions } from '@/hooks/usePositions'
import { useOrders } from '@/hooks/useOrders'
import type { OrderFormValues } from '@/types'
import './layout.css'

export default function Home() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [autoTradingEnabled, setAutoTradingEnabled] = useState(false)

  // Use real API hooks
  const { balances, loading: balancesLoading, error: balancesError } = useBalances()
  const { positions, loading: positionsLoading, error: positionsError } = usePositions()
  const {
    orders,
    loading: ordersLoading,
    error: ordersError,
    placeOrder,
  } = useOrders({
    status: 'NEW',
    limit: 10,
  })

  // Combine loading and error states
  const loading = balancesLoading || positionsLoading || ordersLoading
  const error = balancesError || positionsError || ordersError

  const handleSubmitOrder = async (order: OrderFormValues) => {
    try {
      await placeOrder(order)
      console.warn('Order placed successfully:', order)
    } catch (error) {
      console.error('Failed to place order:', error)
    }
  }

  const handleToggleAutoTrading = (enabled: boolean) => {
    setAutoTradingEnabled(enabled)
    console.warn('Auto trading:', enabled ? 'enabled' : 'disabled')
  }

  const handleLogout = () => {
    console.warn('TODO: Implement logout')
    // TODO: Implement logout
  }

  return (
    <div className="app-layout">
      <Header userName="Trader" onLogout={handleLogout} />

      <div className="app-body">
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main id="main-content" className="app-main" tabIndex={-1}>
          <Dashboard
            positions={positions}
            orders={orders}
            balances={balances}
            loading={loading}
            error={error || undefined}
            autoTradingEnabled={autoTradingEnabled}
            onSubmitOrder={handleSubmitOrder}
            onToggleAutoTrading={handleToggleAutoTrading}
          />
        </main>
      </div>
    </div>
  )
}
