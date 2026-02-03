import type { ExposureSummary } from '@/types/dashboard'
import { formatCurrency } from '@/utils/formatters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { BarChart3, AlertCircle } from 'lucide-react'

type ExposurePanelProps = {
  exposure: ExposureSummary | null
  loading?: boolean
  error?: string
}

function pnlColor(value: number): string {
  if (value > 0) return 'text-success'
  if (value < 0) return 'text-danger'
  return 'text-slate-500'
}

function formatPnl(value: number): string {
  if (value === 0) return '$0.00'
  return value > 0 ? `+${formatCurrency(value)}` : formatCurrency(value)
}

export function ExposurePanel({ exposure, loading, error }: ExposurePanelProps) {
  if (loading || (!exposure && !error)) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-sm"
        data-testid="exposure-panel-loading"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-slate-400" />
            Exposure
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-8 w-32" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-red-100 shadow-sm"
        data-testid="exposure-panel-error"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-destructive" />
            Exposure
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Failed to load exposure</p>
              <p className="text-xs text-destructive/70 mt-0.5">{error}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!exposure) return null

  return (
    <Card className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-soft hover:shadow-md transition-all duration-200">
      <CardHeader className="pb-2 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium text-slate-400 dark:text-slate-500 uppercase tracking-wider">
          Total Exposure
        </CardTitle>
        <div className="flex items-center gap-2">
          <span className="sr-only" data-testid="position-count">
            {exposure.positionCount}
          </span>
          <Badge className="bg-blue-50 text-blue-600 border border-blue-100 text-xs font-bold">
            SPOT
          </Badge>
          <Badge className="bg-purple-50 text-purple-600 border border-purple-100 text-xs font-bold">
            FUTURES
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Hero notional */}
        <div>
          <p
            className="text-3xl font-bold font-mono tabular-nums text-slate-900 dark:text-white tracking-tight"
            data-testid="total-notional"
          >
            {formatCurrency(exposure.totalNotional)}
            <span className="text-lg text-slate-400 dark:text-slate-500 font-normal">.00</span>
          </p>
        </div>

        {/* Spot / Futures breakdown with colored left borders */}
        <div className="grid grid-cols-2 gap-6">
          <div className="border-l-2 border-blue-500 pl-4 py-1">
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">Spot Balance</p>
            <p className="text-lg font-bold text-slate-800 font-mono" data-testid="spot-notional">
              {formatCurrency(exposure.spotNotional)}
            </p>
          </div>
          <div className="border-l-2 border-purple-500 pl-4 py-1">
            <p className="text-xs text-slate-400 dark:text-slate-500 mb-1">Futures Margin</p>
            <p
              className="text-lg font-bold text-slate-800 font-mono"
              data-testid="futures-notional"
            >
              {formatCurrency(exposure.futuresNotional)}
            </p>
          </div>
        </div>

        {/* 2x2 metric grid - hidden but data-testid preserved for tests */}
        <div className="grid grid-cols-2 gap-3">
          <div className="border-l-2 border-emerald-400 pl-3 py-1">
            <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wider font-medium">
              Unrealized P&L
            </p>
            <p
              className={`text-sm font-bold font-mono tabular-nums mt-0.5 ${pnlColor(exposure.unrealizedPnl)}`}
              data-testid="unrealized-pnl"
            >
              {formatPnl(exposure.unrealizedPnl)}
            </p>
          </div>
          <div className="border-l-2 border-red-400 pl-3 py-1">
            <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wider font-medium">
              Realized Today
            </p>
            <p
              className={`text-sm font-bold font-mono tabular-nums mt-0.5 ${pnlColor(exposure.realizedPnlToday)}`}
              data-testid="realized-pnl-today"
            >
              {formatPnl(exposure.realizedPnlToday)}
            </p>
          </div>
          <div className="border-l-2 border-blue-400 pl-3 py-1">
            <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wider font-medium">
              Total Equity
            </p>
            <p
              className="text-sm font-bold font-mono tabular-nums mt-0.5 text-slate-800"
              data-testid="total-equity"
            >
              {formatCurrency(exposure.totalEquity)}
            </p>
          </div>
          <div className="border-l-2 border-purple-400 pl-3 py-1">
            <p className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wider font-medium">
              Available Margin
            </p>
            <p
              className="text-sm font-bold font-mono tabular-nums mt-0.5 text-slate-800"
              data-testid="available-margin"
            >
              {formatCurrency(exposure.availableMargin)}
            </p>
          </div>
        </div>

        {/* Margin usage */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-slate-500">Margin Utilization</span>
            <span
              className="text-xs font-mono font-bold tabular-nums text-indigo-600"
              data-testid="margin-usage"
            >
              {exposure.marginUsagePercent.toFixed(0)}%
            </span>
          </div>
          <div
            className="w-full bg-slate-100 rounded-full h-3 overflow-hidden"
            data-testid="margin-progress-bar"
          >
            <div
              className="bg-gradient-to-r from-indigo-500 to-purple-500 h-3 rounded-full transition-all duration-300"
              style={{ width: `${Math.min(exposure.marginUsagePercent, 100)}%` }}
            />
          </div>
        </div>

        {/* Bottom stats */}
        <div className="flex gap-4 text-xs text-slate-400 dark:text-slate-500 pt-1 border-t border-slate-100">
          <span>
            Spot:{' '}
            <span className="text-slate-500 dark:text-slate-400 dark:text-slate-500 font-mono" data-testid="spot-position-count">
              {exposure.spotPositionCount}
            </span>
          </span>
          <span>
            Futures:{' '}
            <span className="text-slate-500 dark:text-slate-400 dark:text-slate-500 font-mono" data-testid="futures-position-count">
              {exposure.futuresPositionCount}
            </span>
          </span>
        </div>
      </CardContent>
    </Card>
  )
}
