'use client'

import { useMemo, useCallback, useState, useEffect } from 'react'
import { apiClient } from '@/services/api'
import { useEmergencySell } from './useEmergencySell'
import type { Position, Balance } from '@/types'
import type {
  GuardStatusResponse,
  ExposureSummary,
  TradingKPIs,
  EquityPoint,
  PipelineHealthResponse,
  EngineStatus,
  EmergencyCloseScope,
  DashboardSnapshot,
  EmergencyCloseResult,
} from '@/types/dashboard'

type UseDashboardDataReturn = {
  // Safety data
  guardStatus: GuardStatusResponse | null
  guardStatusLoading: boolean
  guardStatusError: string | undefined

  // Exposure data
  exposure: ExposureSummary | null
  exposureLoading: boolean
  exposureError: string | undefined

  // KPIs
  kpis: TradingKPIs | null
  kpisLoading: boolean
  kpisError: string | undefined

  // Equity curve
  equityCurve: EquityPoint[]
  equityCurveLoading: boolean
  equityCurveError: string | undefined

  // Pipeline health
  pipelineHealth: PipelineHealthResponse | null
  pipelineHealthLoading: boolean
  pipelineHealthError: string | undefined

  // Engine status
  engineStatus: EngineStatus | null
  engineStatusLoading: boolean
  engineStatusError: string | undefined
  activeSignals: number
  onToggleAutoTrading: (enabled: boolean) => void

  // Emergency controls
  onEmergencyClose: (
    scope: EmergencyCloseScope,
    stopEngine: boolean,
    idempotencyKey: string,
  ) => Promise<EmergencyCloseResult>

  // Positions
  positions: Position[]
  positionsLoading: boolean

  // Balances
  balances: Balance[]
  balancesLoading: boolean

  // Refresh
  refresh: () => Promise<void>
}

// Type for the BFF dashboard snapshot response
type DashboardSnapshotResponse = DashboardSnapshot & {
  guardStatus: GuardStatusResponse
  pipelineHealth: PipelineHealthResponse
  equityCurve: EquityPoint[]
}

export function useDashboardData(): UseDashboardDataReturn {
  const [snapshot, setSnapshot] = useState<DashboardSnapshotResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const { closePositions } = useEmergencySell()

  const fetchSnapshot = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await apiClient.get<DashboardSnapshotResponse>('/dashboard/snapshot')
      setSnapshot(data)
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to fetch dashboard data'
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch
  useEffect(() => {
    fetchSnapshot()
  }, [fetchSnapshot])

  // Auto-refresh every 5 seconds
  useEffect(() => {
    const interval = setInterval(fetchSnapshot, 5000)
    return () => clearInterval(interval)
  }, [fetchSnapshot])

  // Map snapshot data to Position type
  const positions: Position[] = useMemo(() => {
    if (!snapshot?.positions) return []
    return snapshot.positions.map(p => ({
      symbol: p.symbol as Position['symbol'],
      side: p.side,
      quantity: p.quantity,
      entryPrice: p.entryPrice,
      markPrice: p.markPrice,
      pnl: p.pnl,
      pnlPercent: p.pnlPercent,
      venue: p.venue as Position['venue'],
    }))
  }, [snapshot?.positions])

  // Map snapshot data to Balance type
  const balances: Balance[] = useMemo(() => {
    if (!snapshot?.balances) return []
    return snapshot.balances.map(b => ({
      asset: b.asset,
      free: b.free,
      locked: b.locked,
      total: b.total,
      venue: b.venue,
      usdValue: b.usdValue ?? undefined,
    }))
  }, [snapshot?.balances])

  // Handlers
  const onToggleAutoTrading = useCallback(
    async (enabled: boolean) => {
      try {
        await apiClient.post('/trading/auto-trading', { enabled })
        // Refresh snapshot to get updated state
        await fetchSnapshot()
      } catch (err) {
        console.error('Failed to toggle auto trading:', err)
      }
    },
    [fetchSnapshot],
  )

  const onEmergencyClose = useCallback(
    async (scope: EmergencyCloseScope, stopEngine: boolean, idempotencyKey: string) => {
      const response = await closePositions({ scope, stopEngine, idempotencyKey })
      // Refresh after emergency close
      await fetchSnapshot()
      return response
    },
    [closePositions, fetchSnapshot],
  )

  return {
    // Safety data
    guardStatus: snapshot?.guardStatus ?? null,
    guardStatusLoading: loading,
    guardStatusError: error ?? undefined,

    // Exposure data
    exposure: snapshot?.exposure ?? null,
    exposureLoading: loading,
    exposureError: error ?? undefined,

    // KPIs
    kpis: snapshot?.kpis ?? null,
    kpisLoading: loading,
    kpisError: error ?? undefined,

    // Equity curve
    equityCurve: snapshot?.equityCurve ?? [],
    equityCurveLoading: loading,
    equityCurveError: error ?? undefined,

    // Pipeline health
    pipelineHealth: snapshot?.pipelineHealth ?? null,
    pipelineHealthLoading: loading,
    pipelineHealthError: error ?? undefined,

    // Engine status
    engineStatus: snapshot?.engineStatus ?? null,
    engineStatusLoading: loading,
    engineStatusError: error ?? undefined,
    activeSignals: 0, // TODO: Add to snapshot response
    onToggleAutoTrading,

    // Emergency controls
    onEmergencyClose,

    // Positions
    positions,
    positionsLoading: loading,

    // Balances
    balances,
    balancesLoading: loading,

    // Refresh
    refresh: fetchSnapshot,
  }
}
