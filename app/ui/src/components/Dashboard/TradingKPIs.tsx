import type { TradingKPIs as TradingKPIsType } from '@/types/dashboard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { AlertCircle, TrendingUp, TrendingDown, Minus, Activity } from 'lucide-react'

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

type KPILevel = 'good' | 'warning' | 'danger'

function getKPILevel(key: string, value: number): KPILevel {
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

function getKPIColor(level: KPILevel): string {
  switch (level) {
    case 'good':
      return 'text-success'
    case 'warning':
      return 'text-warning'
    case 'danger':
      return 'text-danger'
  }
}

const KPI_TILE_COLORS: Record<string, string> = {
  winRate: 'bg-blue-50 border-blue-100',
  profitFactor: 'bg-purple-50 border-purple-100',
  sharpeRatio: 'bg-orange-50 border-orange-100',
  maxDrawdown: 'bg-emerald-50 border-emerald-100',
}

function getKPIBgColor(key: string): string {
  return KPI_TILE_COLORS[key] ?? 'bg-slate-50 border-slate-100'
}

function KPITrendIcon({ level }: { level: KPILevel }) {
  switch (level) {
    case 'good':
      return <TrendingUp className="h-3.5 w-3.5 text-success" aria-label="Good" />
    case 'warning':
      return <Minus className="h-3.5 w-3.5 text-warning" aria-label="Warning" />
    case 'danger':
      return <TrendingDown className="h-3.5 w-3.5 text-danger" aria-label="Poor" />
  }
}

function formatKPIValue(key: string, value: number | null): string {
  if (value === null) return '—'
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

function shouldShowKPI(kpis: TradingKPIsType, key: string): boolean {
  if (kpis.tradeCount < MIN_TRADES_FOR_DISPLAY) return false
  if (key === 'sharpeRatio' && kpis.tradingDays < MIN_DAYS_FOR_SHARPE) return false
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
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-sm"
        data-testid="trading-kpis-loading"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <Activity className="h-4 w-4 text-slate-400" />
            Trading Performance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="bg-slate-50 rounded-md p-3 space-y-2">
                <Skeleton className="h-3 w-16" />
                <Skeleton className="h-7 w-14" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-red-100 shadow-sm"
        data-testid="trading-kpis-error"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <Activity className="h-4 w-4 text-destructive" />
            Trading Performance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 text-sm text-destructive" role="alert">
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!kpis) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-sm"
        data-testid="trading-kpis-empty"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <Activity className="h-4 w-4 text-slate-400" />
            Trading Performance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-slate-500">No trading data available</p>
        </CardContent>
      </Card>
    )
  }

  const kpiKeys = ['winRate', 'profitFactor', 'sharpeRatio', 'maxDrawdown'] as const

  return (
    <Card
      className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-soft hover:shadow-md transition-all duration-200"
      data-testid="trading-kpis"
    >
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-3">
          <div className="p-2 bg-indigo-50 rounded-lg text-indigo-500">
            <Activity className="h-5 w-5" />
          </div>
          <span className="text-lg font-bold text-slate-900">Trading Performance</span>
        </CardTitle>
        <span
          className="text-xs text-slate-400 dark:text-slate-500 font-mono tabular-nums"
          data-testid="trade-count"
        >
          {kpis.tradeCount} trades · {kpis.tradingDays} days
        </span>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {kpiKeys.map(key => {
            const value = kpis[key]
            const showValue = shouldShowKPI(kpis, key)
            const level = value !== null && showValue ? getKPILevel(key, value) : null
            const colorClass = level ? getKPIColor(level) : ''
            const bgClass = getKPIBgColor(key)

            return (
              <div
                key={key}
                className={`p-4 rounded-xl border ${bgClass} flex flex-col gap-1`}
                data-testid={`kpi-${key}`}
              >
                <p className="text-xs text-slate-500 dark:text-slate-400 dark:text-slate-500 font-medium uppercase">
                  {getKPILabel(key)}
                </p>
                <p
                  className={`text-xl font-bold font-mono tabular-nums ${colorClass}`}
                  data-testid={`kpi-value-${key}`}
                  aria-label={showValue ? undefined : 'Not available'}
                >
                  {showValue ? formatKPIValue(key, value) : '—'}
                </p>
                {level && (
                  <span
                    className={`text-xs font-medium flex items-center gap-0.5 ${getKPIColor(level)}`}
                  >
                    <KPITrendIcon level={level} />
                  </span>
                )}
                {!showValue && (
                  <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-1">
                    {getInsufficientDataMessage(kpis, key)}
                  </p>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}
