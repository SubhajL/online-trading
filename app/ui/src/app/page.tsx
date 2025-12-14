'use client'

import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { PageShell } from '@/components/Layout/PageShell'
import { Dashboard } from '@/components/Dashboard/Dashboard'
import { LogoutModal } from '@/components/common/LogoutModal'
import { useAuth } from '@/context/AuthContext'
import { useBalances } from '@/hooks/useBalances'
import { usePositions } from '@/hooks/usePositions'
import { useOrders } from '@/hooks/useOrders'
import type { OrderFormValues } from '@/types'

export default function Home() {
  const router = useRouter()
  const { state: authState, logout } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [autoTradingEnabled, setAutoTradingEnabled] = useState(false)
  const [showLogoutModal, setShowLogoutModal] = useState(false)

  // API hooks - must be called before any conditional return
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

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authState.isLoading && !authState.isAuthenticated) {
      router.push('/login')
    }
  }, [authState.isLoading, authState.isAuthenticated, router])

  const handleSubmitOrder = useCallback(async (order: OrderFormValues) => {
    try {
      await placeOrder(order)
    } catch (err) {
      console.error('Failed to place order:', err)
    }
  }, [placeOrder])

  const handleToggleAutoTrading = useCallback((enabled: boolean) => {
    setAutoTradingEnabled(enabled)
  }, [])

  const handleLogoutClick = useCallback(() => {
    if (positions.length > 0) {
      setShowLogoutModal(true)
    } else {
      logout()
    }
  }, [positions.length, logout])

  const handleLogoutConfirm = useCallback(() => {
    setShowLogoutModal(false)
    logout()
  }, [logout])

  const handleLogoutCancel = useCallback(() => {
    setShowLogoutModal(false)
  }, [])

  // Show loading while checking auth or if not authenticated
  if (authState.isLoading || !authState.isAuthenticated) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <p>Loading...</p>
      </div>
    )
  }

  const loading = balancesLoading || positionsLoading || ordersLoading
  const error = balancesError || positionsError || ordersError
  const userName = authState.user?.email ?? authState.user?.username

  return (
    <PageShell skipLinkTarget="dashboard-content" maxWidth="full">
      <Header userName={userName} onLogout={handleLogoutClick} />

      <div style={{ display: 'flex', flex: 1 }}>
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main id="main-content" tabIndex={-1} style={{ flex: 1, padding: '1rem' }}>
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

      {showLogoutModal && (
        <LogoutModal
          positions={positions}
          loading={positionsLoading}
          onCancel={handleLogoutCancel}
          onConfirm={handleLogoutConfirm}
        />
      )}
    </PageShell>
  )
}
