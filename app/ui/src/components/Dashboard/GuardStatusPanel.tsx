import type { GuardStatusResponse, GuardState, EngineState, Guards } from '@/types/dashboard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { MaterialIcon } from '@/components/common/MaterialIcon'

type GuardStatusPanelProps = {
  status: GuardStatusResponse | null
  loading?: boolean
  error?: string
}

const GUARD_DISPLAY_NAMES: Record<string, string> = {
  drawdownGuard: 'Drawdown Guard',
  maxPositionsGuard: 'Max Positions Guard',
  newsGuard: 'News Guard',
  volatilityGuard: 'Volatility Guard',
  correlationGuard: 'Correlation Guard',
}

function getEngineStateBadge(state: EngineState) {
  switch (state) {
    case 'ACTIVE':
      return 'bg-success/10 text-success border-success/25 shadow-sm'
    case 'PAUSED':
      return 'bg-warning/10 text-warning border-warning/25'
    case 'STOPPED':
      return 'bg-destructive/10 text-destructive border-destructive/25'
    default:
      return ''
  }
}

function formatTimestamp(isoString: string): string {
  const date = new Date(isoString)
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function GuardStatusPanel({ status, loading, error }: GuardStatusPanelProps) {
  if (loading || (!status && !error)) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-sm"
        data-testid="guard-panel-loading"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <MaterialIcon name="verified_user" size="sm" className="text-slate-400" />
            Guard Status
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-2/3" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-red-100 shadow-sm"
        data-testid="guard-panel-error"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 dark:text-slate-400 dark:text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <MaterialIcon name="gpp_maybe" size="sm" className="text-destructive" />
            Guard Status
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <MaterialIcon name="gpp_maybe" size="sm" className="shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Connection error</p>
              <p className="text-xs text-destructive/70 mt-0.5">{error}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!status) return null

  const guardEntries = Object.entries(status.guards) as [keyof Guards, GuardState][]

  return (
    <Card
      className="bg-white dark:bg-slate-800 rounded-2xl border-l-4 border-l-indigo-500 border border-slate-100 dark:border-slate-700 shadow-soft hover:shadow-md transition-all duration-200 relative overflow-hidden group"
      data-testid="guard-panel"
    >
      <div className="absolute top-0 right-0 p-4 opacity-[0.04] group-hover:opacity-[0.08] transition-opacity pointer-events-none">
        <MaterialIcon name="verified_user" size="xl" className="text-indigo-500 !text-[112px]" />
      </div>
      <CardHeader className="pb-3 flex flex-row items-center justify-between relative z-10">
        <CardTitle className="flex items-center gap-3">
          <div className="p-2 bg-indigo-50 rounded-lg text-indigo-500">
            <MaterialIcon name="verified_user" size="md" />
          </div>
          <div>
            <span className="text-sm font-bold text-slate-800">Guard Status</span>
            <p className="text-[10px] text-slate-400">Risk Management</p>
          </div>
        </CardTitle>
        <Badge
          variant="outline"
          className={`text-xs font-medium ${getEngineStateBadge(status.engineState)}`}
        >
          <span
            className={`inline-block w-2 h-2 rounded-full mr-1.5 ${
              status.engineState === 'ACTIVE'
                ? 'bg-success animate-pulse'
                : status.engineState === 'PAUSED'
                  ? 'bg-warning'
                  : 'bg-destructive'
            }`}
            data-testid="engine-status-indicator"
          />
          {status.engineState}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4 relative z-10">
        <div className="flex items-center justify-between px-3 py-2 rounded-md bg-slate-50">
          <span className="text-xs font-medium text-slate-500">Overall:</span>
          <Badge
            variant="outline"
            className={
              status.overallStatus === 'OK'
                ? 'bg-success/10 text-success border-success/25 shadow-sm'
                : 'bg-destructive/10 text-destructive border-destructive/25'
            }
            data-testid="overall-status"
          >
            <span data-testid="overall-status-icon">
              {status.overallStatus === 'OK' ? (
                <MaterialIcon name="shield" size="sm" className="mr-1 inline !text-[12px]" />
              ) : (
                <MaterialIcon name="gpp_maybe" size="sm" className="mr-1 inline !text-[12px]" />
              )}
            </span>
            {status.overallStatus}
          </Badge>
        </div>

        <div className="space-y-1.5">
          {guardEntries.map(([guardKey, guard]) => (
            <div
              key={guardKey}
              className="flex items-center gap-2.5 px-2 py-1.5 rounded-md hover:bg-slate-50 transition-colors duration-150"
            >
              <span
                className={`w-2 h-2 rounded-full shrink-0 ${
                  guard.status === 'OK' ? 'bg-success ' : 'bg-destructive '
                }`}
                data-testid={guard.status === 'OK' ? 'guard-status-ok' : 'guard-status-blocked'}
              />
              <span className="text-[13px] text-slate-600 flex-1">
                {GUARD_DISPLAY_NAMES[guardKey] || guardKey}
              </span>
              {guard.blockedReason && (
                <span className="text-xs text-destructive/80 font-medium bg-destructive/5 px-1.5 py-0.5 rounded">
                  {guard.blockedReason}
                </span>
              )}
            </div>
          ))}
        </div>

        <p
          className="text-xs text-slate-400 dark:text-slate-500 pt-1 border-t border-slate-100"
          data-testid="last-checked"
        >
          Last checked: {formatTimestamp(status.lastChecked)}
        </p>
      </CardContent>
    </Card>
  )
}
