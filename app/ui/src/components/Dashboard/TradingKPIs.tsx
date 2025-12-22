import type { TradingKPIs as TradingKPIsType } from '@/types/dashboard'
import './TradingKPIs.css'

type TradingKPIsProps = {
  kpis: TradingKPIsType | null
  loading?: boolean
  error?: string
}

const MIN_TRADES_FOR_DISPLAY = 10
const MIN_DAYS_FOR_SHARPE = 7

type KPIThreshold = {
  good: number
  warning: number
  direction: 'higher' | 'lower'
}

const KPI_THRESHOLDS: Record<string, KPIThreshold> = {
  winRate: { good: 55, warning: 45, direction: 'higher' },
  profitFactor: { good: 1.5, warning: 1.0, direction: 'higher' },
  sharpeRatio: { good: 1.0, warning: 0.5, direction: 'higher' },
  maxDrawdown: { good: 5, warning: 10, direction: 'lower' },
}

function getKPIStatus(key: string, value: number): 'good' | 'warning' | 'danger' {
  const threshold = KPI_THRESHOLDS[key]
  if (!threshold) return 'good'

  if (threshold.direction === 'higher') {
    if (value >= threshold.good) return 'good'
    if (value >= threshold.warning) return 'warning'
    return 'danger'
  } else {
    if (value <= threshold.good) return 'good'
    if (value <= threshold.warning) return 'warning'
    return 'danger'
  }
}

function formatKPIValue(key: string, value: number | null): string {
  if (value === null) return '—'

  // Handle non-finite numbers to prevent runtime crashes
  if (!Number.isFinite(value)) {
    if (value === Infinity) return '∞'
    if (value === -Infinity) return '-∞'
    return '—'
  }

  switch (key) {
    case 'winRate':
    case 'maxDrawdown':
      return `${value.toFixed(1)}%`
    case 'profitFactor':
    case 'sharpeRatio':
      return value.toFixed(2)
    default:
      return String(value)
  }
}

function getKPILabel(key: string): string {
  switch (key) {
    case 'winRate':
      return 'Win Rate'
    case 'profitFactor':
      return 'Profit Factor'
    case 'sharpeRatio':
      return 'Sharpe Ratio'
    case 'maxDrawdown':
      return 'Max Drawdown'
    default:
      return key
  }
}

function getKPIDescription(key: string): string {
  switch (key) {
    case 'winRate':
      return 'Percentage of winning trades'
    case 'profitFactor':
      return 'Gross profits divided by gross losses'
    case 'sharpeRatio':
      return 'Risk-adjusted return (annualized)'
    case 'maxDrawdown':
      return 'Maximum peak-to-trough decline'
    default:
      return ''
  }
}

function shouldShowKPI(kpis: TradingKPIsType, key: string): boolean {
  // Check if we have enough trades for this KPI
  if (kpis.tradeCount < MIN_TRADES_FOR_DISPLAY) {
    return false
  }

  // Sharpe ratio requires minimum days
  if (key === 'sharpeRatio' && kpis.tradingDays < MIN_DAYS_FOR_SHARPE) {
    return false
  }

  return true
}

function getInsufficientDataMessage(kpis: TradingKPIsType, key: string): string {
  if (kpis.tradeCount < MIN_TRADES_FOR_DISPLAY) {
    return `Requires ${MIN_TRADES_FOR_DISPLAY} trades (${kpis.tradeCount} completed)`
  }

  if (key === 'sharpeRatio' && kpis.tradingDays < MIN_DAYS_FOR_SHARPE) {
    return `Requires ${MIN_DAYS_FOR_SHARPE} trading days (${kpis.tradingDays} days)`
  }

  return ''
}

export function TradingKPIs({ kpis, loading = false, error }: TradingKPIsProps) {
  if (loading) {
    return (
      <div className="trading-kpis" data-testid="trading-kpis-loading">
        <div className="kpis-header">
          <h3>Trading Performance</h3>
        </div>
        <div className="kpis-skeleton">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="kpi-card skeleton" aria-hidden="true">
              <div className="skeleton-label" />
              <div className="skeleton-value" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="trading-kpis" data-testid="trading-kpis-error">
        <div className="kpis-header">
          <h3>Trading Performance</h3>
        </div>
        <div className="kpis-error" role="alert">
          {error}
        </div>
      </div>
    )
  }

  if (!kpis) {
    return (
      <div className="trading-kpis" data-testid="trading-kpis-empty">
        <div className="kpis-header">
          <h3>Trading Performance</h3>
        </div>
        <div className="kpis-empty">No trading data available</div>
      </div>
    )
  }

  const kpiKeys = ['winRate', 'profitFactor', 'sharpeRatio', 'maxDrawdown'] as const

  return (
    <div className="trading-kpis" data-testid="trading-kpis">
      <div className="kpis-header">
        <h3>Trading Performance</h3>
        <span className="trade-count" data-testid="trade-count">
          {kpis.tradeCount} trades · {kpis.tradingDays} days
        </span>
      </div>

      <div className="kpis-grid">
        {kpiKeys.map(key => {
          const value = kpis[key]
          const showValue = shouldShowKPI(kpis, key)
          const status = value !== null ? getKPIStatus(key, value) : 'neutral'

          return (
            <div
              key={key}
              className={`kpi-card ${showValue ? status : 'insufficient'}`}
              data-testid={`kpi-${key}`}
            >
              <div className="kpi-label">{getKPILabel(key)}</div>
              <div
                className="kpi-value"
                data-testid={`kpi-value-${key}`}
                aria-label={showValue ? undefined : 'Not available'}
              >
                {showValue ? formatKPIValue(key, value) : '—'}
              </div>
              <div className="kpi-description">
                {showValue ? (
                  getKPIDescription(key)
                ) : (
                  <span className="insufficient-message">
                    {getInsufficientDataMessage(kpis, key)}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
