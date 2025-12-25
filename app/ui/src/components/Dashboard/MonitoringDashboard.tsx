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
import './MonitoringDashboard.css'

type MonitoringDashboardProps = {
  // Safety data
  guardStatus: GuardStatusResponse | null
  guardStatusLoading?: boolean
  guardStatusError?: string

  // Exposure data
  exposure: ExposureSummary | null
  exposureLoading?: boolean
  exposureError?: string

  // KPIs
  kpis: TradingKPIsType | null
  kpisLoading?: boolean
  kpisError?: string

  // Equity curve
  equityCurve: EquityPoint[]
  equityCurveLoading?: boolean
  equityCurveError?: string

  // Pipeline health
  pipelineHealth: PipelineHealthResponse | null
  pipelineHealthLoading?: boolean
  pipelineHealthError?: string

  // Engine status
  engineStatus: EngineStatus | null
  engineStatusLoading?: boolean
  engineStatusError?: string
  activeSignals?: number
  onToggleAutoTrading?: (enabled: boolean) => void

  // Emergency controls
  onEmergencyClose: (
    scope: EmergencyCloseScope,
    stopEngine: boolean,
    idempotencyKey: string,
  ) => Promise<EmergencyCloseResult>

  // Positions
  positions: Position[]
  positionsLoading?: boolean

  // Balances
  balances: Balance[]
  balancesLoading?: boolean

  className?: string
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
    <div className={`monitoring-dashboard ${className}`} data-testid="monitoring-dashboard">
      {/* Top Section: Safety First */}
      <section className="safety-section" aria-label="Safety and Guards">
        <div className="safety-grid">
          <GuardStatusPanel
            status={guardStatus}
            loading={guardStatusLoading}
            error={guardStatusError}
          />
          <ExposurePanel exposure={exposure} loading={exposureLoading} error={exposureError} />
          <EmergencyControls exposure={exposure} onEmergencyClose={onEmergencyClose} />
        </div>
      </section>

      {/* Main Content Grid */}
      <div className="main-grid">
        {/* Left Column: KPIs + Equity Curve */}
        <section className="kpis-section" aria-label="Performance Metrics">
          <TradingKPIs kpis={kpis} loading={kpisLoading} error={kpisError} />
          <EquityCurve data={equityCurve} loading={equityCurveLoading} error={equityCurveError} />
        </section>

        {/* Right Column: Status + Pipeline Health */}
        <aside className="status-section" aria-label="System Status">
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

      {/* Bottom Section: Positions + Balances */}
      <section className="positions-section" aria-label="Positions and Balances">
        <div className="positions-grid">
          <div className="positions-panel">
            <PositionsList positions={positions} loading={positionsLoading} />
          </div>
          <div className="balances-panel">
            <AccountBalance balances={balances} loading={balancesLoading} />
          </div>
        </div>
      </section>
    </div>
  )
}
