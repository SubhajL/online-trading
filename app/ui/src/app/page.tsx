'use client'

import { useState, useCallback, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { AppShell } from '@/components/shell'
import { MonitoringDashboard } from '@/components/Dashboard/MonitoringDashboard'
import { LogoutModal } from '@/components/common/LogoutModal'
import { useAuth } from '@/context/AuthContext'
import { useDashboardData } from '@/hooks/useDashboardData'

export default function Home() {
  const router = useRouter()
  const { state: authState, logout } = useAuth()

  const [showLogoutModal, setShowLogoutModal] = useState(false)

  const dashboardData = useDashboardData()

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

  if (authState.isLoading || !authState.isAuthenticated) {
    return (
      <div className="flex items-center justify-center h-screen bg-[#FAFBFC]">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 border-3 border-slate-200 border-t-indigo-500 rounded-full animate-spin" />
          <p className="text-sm text-slate-400">Loading...</p>
        </div>
      </div>
    )
  }

  return (
    <AppShell onLogout={handleLogoutClick}>
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

      {showLogoutModal && (
        <LogoutModal
          positions={dashboardData.positions}
          loading={dashboardData.positionsLoading}
          onCancel={handleLogoutCancel}
          onConfirm={handleLogoutConfirm}
        />
      )}
    </AppShell>
  )
}
