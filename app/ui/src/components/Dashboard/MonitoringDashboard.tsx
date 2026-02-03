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
    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4 pl-1">
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
      {/* Section A — Safety & Guards */}
      <section aria-label="Safety and Guards">
        <SectionLabel>Safety &amp; Guards</SectionLabel>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <GuardStatusPanel
            status={guardStatus}
            loading={guardStatusLoading}
            error={guardStatusError}
          />
          <ExposurePanel exposure={exposure} loading={exposureLoading} error={exposureError} />
          <EmergencyControls exposure={exposure} onEmergencyClose={onEmergencyClose} />
        </div>
      </section>

      {/* Section B — Performance + System */}
      <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-6">
        <section className="flex flex-col gap-6" aria-label="Performance Metrics">
          <SectionLabel>Performance</SectionLabel>
          <TradingKPIs kpis={kpis} loading={kpisLoading} error={kpisError} />
          <EquityCurve data={equityCurve} loading={equityCurveLoading} error={equityCurveError} />
        </section>

        <aside className="flex flex-col gap-6" aria-label="System Status">
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

      {/* Section C — Positions & Balances */}
      <section aria-label="Positions and Balances">
        <SectionLabel>Positions &amp; Balances</SectionLabel>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <PositionsList positions={positions} loading={positionsLoading} />
          <AccountBalance balances={balances} loading={balancesLoading} />
        </div>
      </section>
    </div>
  )
}
