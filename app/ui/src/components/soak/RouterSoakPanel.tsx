import type { RouterSoakStatus, RouterReconcileSummary } from '@/types/soak'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { MaterialIcon } from '@/components/common/MaterialIcon'

type RouterSoakPanelProps = {
  status: RouterSoakStatus | null
  loading?: boolean
  error?: string
}

function readinessBadge(readiness: RouterSoakStatus['readiness']): string {
  if (readiness.ready) return 'bg-success/10 text-success border-success/25 shadow-sm'
  if (readiness.status === 'reconciling') return 'bg-warning/10 text-warning border-warning/25'
  return 'bg-destructive/10 text-destructive border-destructive/25'
}

function readinessLabel(readiness: RouterSoakStatus['readiness']): string {
  if (readiness.ready) return 'Ready'
  if (readiness.status === 'reconciling') return 'Reconciling'
  return 'Unreachable'
}

// Counters whose non-zero value signals unrepaired protection needing an
// operator's eye — rendered with an alarm colour.
const ALARM_COUNTERS: (keyof RouterReconcileSummary)[] = ['unrepairedLegs', 'errors']

const COUNTER_LABELS: Record<keyof RouterReconcileSummary, string> = {
  bracketsSwept: 'Swept',
  entriesChecked: 'Entries checked',
  legsResolved: 'Legs resolved',
  exitLegsUpdated: 'Exit legs updated',
  bracketsClosed: 'Closed',
  staleReserved: 'Stale reserved',
  unrepairedLegs: 'Unrepaired legs',
  errors: 'Errors',
}

function formatTimestamp(isoString: string): string {
  return new Date(isoString).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function RouterSoakPanel({ status, loading, error }: RouterSoakPanelProps) {
  if (loading || (!status && !error)) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-sm"
        data-testid="soak-panel-loading"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <MaterialIcon name="monitor_heart" size="sm" className="text-slate-400" />
            Router Soak
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-5 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-2/3" />
        </CardContent>
      </Card>
    )
  }

  // Only replace the whole panel with an error card when there is no
  // last-good data to show; otherwise the operational snapshot is what the
  // operator most wants to keep, with a stale banner over it.
  if (error && !status) {
    return (
      <Card
        className="bg-white dark:bg-slate-800 rounded-2xl border border-red-100 shadow-sm"
        data-testid="soak-panel-error"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <MaterialIcon name="gpp_maybe" size="sm" className="text-destructive" />
            Router Soak
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <MaterialIcon name="gpp_maybe" size="sm" className="shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Soak status unavailable</p>
              <p className="text-xs text-destructive/70 mt-0.5">
                The BFF could not reach the router. Retrying automatically… ({error})
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!status) return null

  const { readiness, reconcile } = status

  return (
    <Card
      className="bg-white dark:bg-slate-800 rounded-2xl border-l-4 border-l-indigo-500 border border-slate-100 dark:border-slate-700 shadow-sm"
      data-testid="soak-panel"
    >
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-3">
          <div className="p-2 bg-indigo-50 rounded-lg text-indigo-500">
            <MaterialIcon name="monitor_heart" size="md" />
          </div>
          <div>
            <span className="text-sm font-bold text-slate-800 dark:text-slate-100">
              Router Soak
            </span>
            <p className="text-[10px] text-slate-400">Reconciler &amp; readiness</p>
          </div>
        </CardTitle>
        <Badge
          variant="outline"
          className={`text-xs font-medium ${readinessBadge(readiness)}`}
          data-testid="readiness-badge"
        >
          <span
            className={`inline-block w-2 h-2 rounded-full mr-1.5 ${
              readiness.ready
                ? 'bg-success animate-pulse'
                : readiness.status === 'reconciling'
                  ? 'bg-warning animate-pulse'
                  : 'bg-destructive'
            }`}
            data-testid="readiness-indicator"
          />
          {readinessLabel(readiness)}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div
            className="flex items-center gap-2 text-xs text-warning bg-warning/10 border border-warning/25 rounded-md px-2 py-1.5"
            role="status"
            data-testid="soak-stale-banner"
          >
            <MaterialIcon name="sync_problem" size="sm" className="shrink-0" />
            <span>Showing last-known status — refresh failed, retrying…</span>
          </div>
        )}

        {readiness.error && (
          <p className="text-xs text-destructive/80" data-testid="readiness-error">
            {readiness.error}
          </p>
        )}

        {reconcile.unavailable ? (
          <p className="text-sm text-slate-500" data-testid="reconcile-unavailable">
            Reconcile status unavailable
          </p>
        ) : !reconcile.hasRun ? (
          <p className="text-sm text-slate-500" data-testid="reconcile-none">
            No reconcile pass yet
          </p>
        ) : (
          <div className="grid grid-cols-2 gap-2" data-testid="reconcile-summary">
            {reconcile.summary &&
              (Object.keys(COUNTER_LABELS) as (keyof RouterReconcileSummary)[]).map(key => {
                const value = reconcile.summary![key]
                const alarm = ALARM_COUNTERS.includes(key) && value > 0
                return (
                  <div
                    key={key}
                    className="flex items-center justify-between px-3 py-2 rounded-md bg-slate-50 dark:bg-slate-700/40"
                    data-testid={`counter-${key}`}
                  >
                    <span className="text-xs text-slate-500">{COUNTER_LABELS[key]}</span>
                    <span
                      className={`text-sm font-semibold ${
                        alarm ? 'text-destructive' : 'text-slate-700 dark:text-slate-200'
                      }`}
                      data-testid={`counter-value-${key}`}
                    >
                      {value}
                    </span>
                  </div>
                )
              })}
          </div>
        )}

        {reconcile.lastRunAt && (
          <p
            className="text-xs text-slate-400 pt-1 border-t border-slate-100"
            data-testid="last-run"
          >
            Last reconcile: {formatTimestamp(reconcile.lastRunAt)}
          </p>
        )}
        <p className="text-xs text-slate-400" data-testid="checked-at">
          Checked: {formatTimestamp(status.checkedAt)}
        </p>
      </CardContent>
    </Card>
  )
}
