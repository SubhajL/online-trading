'use client'

import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { PageShell } from '@/components/Layout/PageShell'
import { MonitoringDashboard } from '@/components/Dashboard/MonitoringDashboard'
import { LogoutModal } from '@/components/common/LogoutModal'
import { useAuth } from '@/context/AuthContext'
import { useDashboardData } from '@/hooks/useDashboardData'

export default function Home() {
  const router = useRouter()
  const { state: authState, logout } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [showLogoutModal, setShowLogoutModal] = useState(false)

  // Aggregated dashboard data hook
  const dashboardData = useDashboardData()

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!authState.isLoading && !authState.isAuthenticated) {
      router.push('/login')
    }
  }, [authState.isLoading, authState.isAuthenticated, router])

  const handleLogoutClick = useCallback(() => {
    if (dashboardData.positions.length > 0) {
      setShowLogoutModal(true)
    } else {
      logout()
    }
  }, [dashboardData.positions.length, logout])

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
      <div
        style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}
      >
        <p>Loading...</p>
      </div>
    )
  }

  const userName = authState.user?.email ?? authState.user?.username

  return (
    <PageShell skipLinkTarget="dashboard-content" maxWidth="full">
      <Header userName={userName} onLogout={handleLogoutClick} />

      <div style={{ display: 'flex', flex: 1 }}>
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main id="main-content" tabIndex={-1} style={{ flex: 1, padding: '1rem' }}>
          <MonitoringDashboard
            guardStatus={dashboardData.guardStatus}
            guardStatusLoading={dashboardData.guardStatusLoading}
            guardStatusError={dashboardData.guardStatusError}
            exposure={dashboardData.exposure}
            exposureLoading={dashboardData.exposureLoading}
            exposureError={dashboardData.exposureError}
            kpis={dashboardData.kpis}
            kpisLoading={dashboardData.kpisLoading}
            kpisError={dashboardData.kpisError}
            equityCurve={dashboardData.equityCurve}
            equityCurveLoading={dashboardData.equityCurveLoading}
            equityCurveError={dashboardData.equityCurveError}
            pipelineHealth={dashboardData.pipelineHealth}
            pipelineHealthLoading={dashboardData.pipelineHealthLoading}
            pipelineHealthError={dashboardData.pipelineHealthError}
            engineStatus={dashboardData.engineStatus}
            engineStatusLoading={dashboardData.engineStatusLoading}
            engineStatusError={dashboardData.engineStatusError}
            activeSignals={dashboardData.activeSignals}
            onToggleAutoTrading={dashboardData.onToggleAutoTrading}
            onEmergencyClose={dashboardData.onEmergencyClose}
            positions={dashboardData.positions}
            positionsLoading={dashboardData.positionsLoading}
            balances={dashboardData.balances}
            balancesLoading={dashboardData.balancesLoading}
          />
        </main>
      </div>

      {showLogoutModal && (
        <LogoutModal
          positions={dashboardData.positions}
          loading={dashboardData.positionsLoading}
          onCancel={handleLogoutCancel}
          onConfirm={handleLogoutConfirm}
        />
      )}
    </PageShell>
  )
}
