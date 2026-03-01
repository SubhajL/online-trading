// Engine state types
export type EngineState = 'ACTIVE' | 'PAUSED' | 'STOPPED';

// Guard status types
export type GuardStatus = 'OK' | 'BLOCKED';

export class GuardStateDto {
  status!: GuardStatus;
  blockedReason!: string | null;
}

export class GuardsDto {
  drawdownGuard!: GuardStateDto;
  maxPositionsGuard!: GuardStateDto;
  newsGuard!: GuardStateDto;
  volatilityGuard!: GuardStateDto;
  correlationGuard!: GuardStateDto;
}

export class GuardStatusResponseDto {
  engineState!: EngineState;
  guards!: GuardsDto;
  overallStatus!: GuardStatus;
  lastChecked!: string;
}

export class EngineStatusDto {
  state!: EngineState;
  autoTrading!: boolean;
  lastDecisionAt!: string | null;
  lastDecisionReason!: string | null;
}

export class TradingKPIsDto {
  winRate!: number | null;
  profitFactor!: number | null;
  sharpeRatio!: number | null;
  maxDrawdown!: number | null;
  tradeCount!: number;
  tradingDays!: number;
  totalPnL!: number;
  dailyPnL!: number;
}

export class ExposureSummaryDto {
  totalNotional!: number;
  spotNotional!: number;
  futuresNotional!: number;
  unrealizedPnl!: number;
  realizedPnlToday!: number;
  totalEquity!: number;
  availableMargin!: number;
  marginUsagePercent!: number;
  positionCount!: number;
  spotPositionCount!: number;
  futuresPositionCount!: number;
}

export class EquityPointDto {
  timestamp!: string;
  equity!: number;
}

export class BalanceDto {
  asset!: string;
  free!: number;
  locked!: number;
  total!: number;
  venue!: string;
  usdValue!: number | null;
}

export class PositionDto {
  symbol!: string;
  side!: 'LONG' | 'SHORT';
  quantity!: number;
  entryPrice!: number;
  markPrice!: number;
  pnl!: number;
  pnlPercent!: number;
  venue!: string;
}

export class OrderDto {
  orderId!: string;
  symbol!: string;
  side!: 'BUY' | 'SELL';
  type!: string;
  status!: string;
  quantity!: number;
  price!: number | null;
  executedQuantity!: number;
  createdAt!: string;
}

export class SymbolHealthDto {
  symbol!: string;
  timeframe!: string;
  lastCandleTime!: string;
  lastProcessedTime!: string;
  lagMs!: number;
}

export class LastDecisionDto {
  timestamp!: string;
  symbol!: string;
  action!: 'BUY' | 'SELL' | 'HOLD';
  reason!: string;
}

export type PipelineStatus = 'HEALTHY' | 'DEGRADED' | 'UNHEALTHY';

export class PipelineHealthResponseDto {
  symbols!: SymbolHealthDto[];
  lastDecision!: LastDecisionDto | null;
  averageLagMs!: number;
  status!: PipelineStatus;
}

export class DashboardSnapshotDto {
  balances!: BalanceDto[];
  positions!: PositionDto[];
  recentOrders!: OrderDto[];
  kpis!: TradingKPIsDto;
  exposure!: ExposureSummaryDto;
  guardStatus!: GuardStatusResponseDto;
  engineStatus!: EngineStatusDto;
  pipelineHealth!: PipelineHealthResponseDto;
  equityCurve!: EquityPointDto[];
  updatedAt!: string;
}
