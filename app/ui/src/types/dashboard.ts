import type { Balance, Order, Position } from './index'

// Engine state types
export type EngineState = 'ACTIVE' | 'PAUSED' | 'STOPPED'

// Guard status types
export type GuardStatus = 'OK' | 'BLOCKED'

// Individual guard state used by GuardStatusPanel
export type GuardState = {
  status: GuardStatus
  blockedReason: string | null
}

// Guards object keyed by guard name
export type Guards = {
  drawdownGuard: GuardState
  maxPositionsGuard: GuardState
  newsGuard: GuardState
  volatilityGuard: GuardState
  correlationGuard: GuardState
}

// Response from /api/engine/guard-status
export type GuardStatusResponse = {
  engineState: EngineState
  guards: Guards
  overallStatus: GuardStatus
  lastChecked: string
}

export type EngineStatus = {
  state: EngineState
  autoTrading: boolean
  lastDecisionAt: string | null
  lastDecisionReason: string | null
}

// KPI types with null for insufficient data
export type TradingKPIs = {
  winRate: number | null
  profitFactor: number | null
  sharpeRatio: number | null
  maxDrawdown: number | null
  tradeCount: number
  tradingDays: number
  totalPnL: number
  dailyPnL: number
}

// Exposure summary - used by ExposurePanel
export type ExposureSummary = {
  totalNotional: number
  spotNotional: number
  futuresNotional: number
  unrealizedPnl: number
  realizedPnlToday: number
  totalEquity: number
  availableMargin: number
  marginUsagePercent: number
  positionCount: number
  spotPositionCount: number
  futuresPositionCount: number
}

// Equity curve point
export type EquityPoint = {
  timestamp: string
  equity: number
}

// Time range for equity curve
export type EquityTimeRange = '1D' | '1W' | '1M' | 'ALL'

// Dashboard snapshot (unified response)
export type DashboardSnapshot = {
  balances: Balance[]
  positions: Position[]
  recentOrders: Order[]
  kpis: TradingKPIs
  exposure: ExposureSummary
  engineStatus: EngineStatus
  updatedAt: string
}

// Pipeline health types
export type SymbolHealth = {
  symbol: string
  timeframe: string
  lastCandleTime: string
  lastProcessedTime: string
  lagMs: number
}

export type LastDecision = {
  timestamp: string
  symbol: string
  action: 'BUY' | 'SELL' | 'HOLD'
  reason: string
}

export type PipelineStatus = 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY'

export type PipelineHealthResponse = {
  symbols: SymbolHealth[]
  lastDecision: LastDecision | null
  averageLagMs: number
  status: PipelineStatus
}

// Emergency close types - strict scope for type safety
export type EmergencyCloseScope = 'ALL' | 'SPOT' | 'FUTURES'

export type EmergencyCloseRequest = {
  scope: EmergencyCloseScope
  stopEngine: boolean
  idempotencyKey: string
}

export type EmergencyCloseResponse = {
  success: boolean
  canceledOrders: number
  closedPositions: number
  engineStopped: boolean
  errors: string[]
  executionTimeMs: number
}

// Result type used by useEmergencySell hook
export type EmergencyCloseResult = {
  success: boolean
  closedCount: number
}

// Emergency close state machine
export type EmergencyCloseState = 'IDLE' | 'CONFIRMING' | 'EXECUTING' | 'COMPLETED' | 'FAILED'

// Position summary for confirmation modal
export type PositionSummary = {
  spotPositions: number
  spotNotional: number
  spotPnL: number
  futuresPositions: number
  futuresNotional: number
  futuresPnL: number
  totalPositions: number
  totalNotional: number
  totalPnL: number
}
