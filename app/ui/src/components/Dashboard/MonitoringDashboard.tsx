'use client'

import type { Position, Balance } from '@/types'
import type {
  GuardStatusResponse,
  ExposureSummary,
  TradingKPIs as TradingKPIsType,
  EquityPoint,
  PipelineHealthResponse,
  EngineStatus,
  EmergencyCloseScope,
  EmergencyCloseResult,
} from '@/types/dashboard'
import { GuardStatusPanel } from './GuardStatusPanel'
import { ExposurePanel } from './ExposurePanel'
import { TradingKPIs } from './TradingKPIs'
import { EquityCurve } from './EquityCurve'
import { PipelineHealth } from './PipelineHealth'
import { AutoTradingStatus } from './AutoTradingStatus'
import { EmergencyControls } from './EmergencyControls'
import { PositionsList } from '../trading/PositionsList'
import { AccountBalance } from '../trading/AccountBalance'

type MonitoringDashboardProps = {
  guardStatus: GuardStatusResponse | null
  guardStatusLoading?: boolean
  guardStatusError?: string
  exposure: ExposureSummary | null
  exposureLoading?: boolean
  exposureError?: string
  kpis: TradingKPIsType | null
  kpisLoading?: boolean
  kpisError?: string
  equityCurve: EquityPoint[]
  equityCurveLoading?: boolean
  equityCurveError?: string
  pipelineHealth: PipelineHealthResponse | null
  pipelineHealthLoading?: boolean
  pipelineHealthError?: string
  engineStatus: EngineStatus | null
  engineStatusLoading?: boolean
  engineStatusError?: string
  activeSignals?: number
  onToggleAutoTrading?: (enabled: boolean) => void
  onEmergencyClose: (
    scope: EmergencyCloseScope,
    stopEngine: boolean,
    idempotencyKey: string,
  ) => Promise<EmergencyCloseResult>
  positions: Position[]
  positionsLoading?: boolean
  balances: Balance[]
  balancesLoading?: boolean
  className?: string
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4 pl-1">
      {children}
    </h3>
  )
}

export function MonitoringDashboard({
  guardStatus,
  guardStatusLoading,
  guardStatusError,
  exposure,
  exposureLoading,
  exposureError,
  kpis,
  kpisLoading,
  kpisError,
  equityCurve,
  equityCurveLoading,
  equityCurveError,
  pipelineHealth,
  pipelineHealthLoading,
  pipelineHealthError,
  engineStatus,
  engineStatusLoading,
  engineStatusError,
  activeSignals,
  onToggleAutoTrading,
  onEmergencyClose,
  positions,
  positionsLoading,
  balances,
  balancesLoading,
  className = '',
}: MonitoringDashboardProps) {
  return (
    <div className={`flex flex-col gap-6 ${className}`} data-testid="monitoring-dashboard">
      {/* Row 1 — Safety & Guards (Spec §6.1: 3-6-3 columns) */}
      <section aria-label="Safety and Guards">
        <SectionLabel>Safety &amp; Guards</SectionLabel>
        <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
          <div className="md:col-span-3">
            <GuardStatusPanel
              status={guardStatus}
              loading={guardStatusLoading}
              error={guardStatusError}
            />
          </div>
          <div className="md:col-span-6">
            <ExposurePanel exposure={exposure} loading={exposureLoading} error={exposureError} />
          </div>
          <div className="md:col-span-3">
            <EmergencyControls exposure={exposure} onEmergencyClose={onEmergencyClose} />
          </div>
        </div>
      </section>

      {/* Row 2 — Performance + System (Spec §6.1: 8-4 columns) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <section className="lg:col-span-8 flex flex-col gap-6" aria-label="Performance Metrics">
          <SectionLabel>Performance</SectionLabel>
          <TradingKPIs kpis={kpis} loading={kpisLoading} error={kpisError} />
          <EquityCurve data={equityCurve} loading={equityCurveLoading} error={equityCurveError} />
        </section>

        <aside className="lg:col-span-4 flex flex-col gap-6" aria-label="System Status">
          <SectionLabel>System Status</SectionLabel>
          <AutoTradingStatus
            status={engineStatus}
            loading={engineStatusLoading}
            error={engineStatusError}
            activeSignals={activeSignals}
            onToggle={onToggleAutoTrading}
          />
          <PipelineHealth
            data={pipelineHealth}
            loading={pipelineHealthLoading}
            error={pipelineHealthError}
          />
        </aside>
      </div>

      {/* Row 3 — Positions & Balances (Spec §6.1: 8-4 columns) */}
      <section aria-label="Positions and Balances">
        <SectionLabel>Positions &amp; Balances</SectionLabel>
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <div className="lg:col-span-8">
            <PositionsList positions={positions} loading={positionsLoading} />
          </div>
          <div className="lg:col-span-4">
            <AccountBalance balances={balances} loading={balancesLoading} />
          </div>
        </div>
      </section>
    </div>
  )
}
