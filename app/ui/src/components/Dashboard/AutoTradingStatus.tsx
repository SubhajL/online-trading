import type { EngineStatus, EngineState } from '@/types/dashboard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { AlertCircle, Bot } from 'lucide-react'

type AutoTradingStatusProps = {
  status: EngineStatus | null
  activeSignals?: number
  onToggle?: (enabled: boolean) => void
  loading?: boolean
  error?: string
}

function assertNever(x: never): never {
  throw new Error(`Unexpected value: ${x}`)
}

function getStateBadgeClass(state: EngineState): string {
  switch (state) {
    case 'ACTIVE':
      return 'bg-success/10 text-success border-success/25 shadow-sm'
    case 'PAUSED':
      return 'bg-warning/10 text-warning border-warning/25'
    case 'STOPPED':
      return 'bg-destructive/10 text-destructive border-destructive/25'
    default:
      return assertNever(state)
  }
}

function getStateDotColor(state: EngineState): string {
  switch (state) {
    case 'ACTIVE':
      return 'bg-success'
    case 'PAUSED':
      return 'bg-warning'
    case 'STOPPED':
      return 'bg-destructive'
    default:
      return assertNever(state)
  }
}

function formatRelativeTime(isoString: string, now: number = Date.now()): string {
  const date = new Date(isoString)
  if (isNaN(date.getTime())) return '-'
  const diffMs = now - date.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays > 0) return `${diffDays}d ago`
  if (diffHours > 0) return `${diffHours}h ago`
  if (diffMinutes > 0) return `${diffMinutes}m ago`
  return `${diffSeconds}s ago`
}

export function AutoTradingStatus({
  status,
  activeSignals,
  onToggle,
  loading,
  error,
}: AutoTradingStatusProps) {
  if (loading) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-sm"
        data-testid="auto-trading-status-loading"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <Bot className="h-4 w-4 text-slate-400" />
            Auto Trading
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
        </CardContent>
      </Card>
    )
  }

  if (!status && !error) return null

  if (error) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-red-100 shadow-sm"
        data-testid="auto-trading-status-error"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <Bot className="h-4 w-4 text-destructive" />
            Auto Trading
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Engine unavailable</p>
              <p className="text-xs text-destructive/70 mt-0.5">{error}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!status) return null

  const isDisabled = status.state === 'STOPPED'

  return (
    <Card
      className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-soft hover:shadow-md transition-all duration-200"
      data-testid="auto-trading-status"
    >
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-4">
          <div className="p-3 bg-indigo-50 rounded-full text-indigo-500">
            <Bot className="h-5 w-5" />
          </div>
          <div>
            <span className="text-lg font-bold text-slate-900">Auto Trading</span>
            <p className="text-xs text-slate-400">Master Switch</p>
          </div>
        </CardTitle>
        <div className="flex items-center gap-2">
          {onToggle ? (
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                className="sr-only peer"
                checked={status.autoTrading}
                onChange={() => onToggle(!status.autoTrading)}
                disabled={isDisabled}
                aria-label={status.autoTrading ? 'Turn off auto trading' : 'Turn on auto trading'}
                data-testid="toggle-button"
              />
              <div className="w-14 h-8 bg-slate-200 peer-focus:outline-none rounded-full peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white dark:bg-slate-800 after:border-gray-300 after:border after:rounded-full after:h-7 after:w-7 after:transition-all peer-checked:bg-indigo-500 disabled:opacity-50" />
            </label>
          ) : (
            <Badge
              variant="outline"
              className={
                status.autoTrading
                  ? 'bg-emerald-100 text-emerald-700 border-emerald-200 font-bold'
                  : 'bg-slate-100 text-slate-500 dark:text-slate-400 dark:text-slate-500 border-slate-200'
              }
              data-testid="auto-trading-toggle"
            >
              {status.autoTrading ? 'ON' : 'OFF'}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between text-sm px-3 py-2 rounded-md bg-slate-50">
          <span className="text-slate-500 dark:text-slate-400 dark:text-slate-500 text-xs">Engine State:</span>
          <Badge variant="outline" className={getStateBadgeClass(status.state)}>
            <span
              className={`inline-block w-2 h-2 rounded-full mr-1.5 ${getStateDotColor(status.state)} ${status.state === 'ACTIVE' ? 'animate-pulse' : ''}`}
              data-testid="engine-state-indicator"
            />
            <span data-testid="engine-state-text">{status.state}</span>
          </Badge>
        </div>

        {activeSignals !== undefined && (
          <div className="flex items-center justify-between text-sm px-3 py-2 rounded-md bg-slate-50">
            <span className="text-slate-500 dark:text-slate-400 dark:text-slate-500 text-xs">Active Signals:</span>
            <span
              className="font-mono font-bold tabular-nums text-slate-900"
              data-testid="active-signals"
            >
              {activeSignals}
            </span>
          </div>
        )}

        <div className="pt-3 border-t border-slate-100">
          <h4 className="text-[10px] text-slate-400 dark:text-slate-500 uppercase tracking-wider font-medium mb-2">
            Last Decision
          </h4>
          {status.lastDecisionAt ? (
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between">
                <span className="text-slate-500 dark:text-slate-400 dark:text-slate-500 text-xs">Time:</span>
                <span
                  className="font-mono text-slate-600 text-xs tabular-nums"
                  data-testid="last-decision-time"
                >
                  {formatRelativeTime(status.lastDecisionAt)}
                </span>
              </div>
              {status.lastDecisionReason && (
                <div className="flex justify-between gap-4">
                  <span className="text-slate-500 dark:text-slate-400 dark:text-slate-500 text-xs shrink-0">Reason:</span>
                  <span
                    className="text-slate-600 text-xs text-right"
                    data-testid="last-decision-reason"
                  >
                    {status.lastDecisionReason}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <p className="text-xs text-slate-400">No decisions yet</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
