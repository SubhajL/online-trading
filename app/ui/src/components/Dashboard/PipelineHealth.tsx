import type { PipelineHealthResponse, PipelineStatus, LastDecision } from '@/types/dashboard'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { AlertCircle, AlertTriangle, Workflow } from 'lucide-react'

type PipelineHealthProps = {
  data: PipelineHealthResponse | null
  loading?: boolean
  error?: string
}

const LAG_WARNING_THRESHOLD_MS = 5000

function formatLagMs(lagMs: number): string {
  return `${(lagMs / 1000).toFixed(1)}s`
}

function formatTimestamp(isoString: string): string {
  const date = new Date(isoString)
  if (isNaN(date.getTime())) return '-'
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

function assertNever(x: never): never {
  throw new Error(`Unexpected value: ${x}`)
}

function getStatusBadgeClass(status: PipelineStatus): string {
  switch (status) {
    case 'HEALTHY':
      return 'bg-success/10 text-success border-success/25 shadow-sm'
    case 'DEGRADED':
      return 'bg-warning/10 text-warning border-warning/25'
    case 'UNHEALTHY':
      return 'bg-destructive/10 text-destructive border-destructive/25'
    default:
      return assertNever(status)
  }
}

function getActionColor(action: LastDecision['action']): string {
  switch (action) {
    case 'BUY':
      return 'text-success font-bold'
    case 'SELL':
      return 'text-danger font-bold'
    case 'HOLD':
      return 'text-slate-500'
    default:
      return assertNever(action)
  }
}

export function PipelineHealth({ data, loading, error }: PipelineHealthProps) {
  if (loading || (!data && !error)) {
    return (
      <Card
        className="bg-white rounded-2xl border border-slate-100 shadow-sm"
        data-testid="pipeline-health-loading"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <Workflow className="h-4 w-4 text-slate-400" />
            Pipeline Health
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-3/4" />
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card
        className="bg-white rounded-2xl border border-red-100 shadow-sm"
        data-testid="pipeline-health-error"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-xs font-semibold text-slate-500 uppercase tracking-[0.1em] flex items-center gap-2">
            <Workflow className="h-4 w-4 text-destructive" />
            Pipeline Health
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Pipeline unavailable</p>
              <p className="text-xs text-destructive/70 mt-0.5">{error}</p>
            </div>
          </div>
        </CardContent>
      </Card>
    )
  }

  if (!data) return null

  const hasHighLagSymbols = data.symbols.some(s => s.lagMs > LAG_WARNING_THRESHOLD_MS)

  return (
    <Card
      className="bg-white rounded-2xl border border-slate-100 shadow-soft hover:shadow-md transition-all duration-200 flex-1"
      data-testid="pipeline-health"
    >
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="font-bold text-slate-900">Pipeline Health</CardTitle>
        <Badge variant="outline" className={getStatusBadgeClass(data.status)}>
          <span
            className={`inline-block w-2 h-2 rounded-full mr-1.5 ${data.status === 'HEALTHY' ? 'bg-success animate-pulse' : data.status === 'DEGRADED' ? 'bg-warning' : 'bg-destructive'}`}
            data-testid="status-indicator"
          />
          {data.status}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span>
            Avg Lag:{' '}
            <span className="font-mono text-slate-600 tabular-nums" data-testid="average-lag">
              {formatLagMs(data.averageLagMs)}
            </span>
          </span>
          {hasHighLagSymbols && (
            <span className="flex items-center gap-1 text-warning" data-testid="lag-warning">
              <AlertTriangle className="h-3 w-3" /> High lag detected
            </span>
          )}
        </div>

        {data.symbols.length === 0 ? (
          <p className="text-sm text-slate-500">No symbols being tracked</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-xs font-semibold text-slate-400 uppercase pb-3">
                  Symbol
                </TableHead>
                <TableHead className="text-xs font-semibold text-slate-400 uppercase pb-3">
                  TF
                </TableHead>
                <TableHead className="text-xs font-semibold text-slate-400 uppercase pb-3">
                  Last Candle
                </TableHead>
                <TableHead className="text-xs font-semibold text-slate-400 uppercase pb-3 text-right">
                  Lag
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.symbols.map(symbol => {
                const isHighLag = symbol.lagMs > LAG_WARNING_THRESHOLD_MS
                return (
                  <TableRow
                    key={`${symbol.symbol}-${symbol.timeframe}`}
                    className="hover:bg-slate-50 even:bg-slate-50/50 transition-colors duration-150"
                    data-testid={`symbol-row-${symbol.symbol}`}
                  >
                    <TableCell className="text-xs font-medium text-slate-900">
                      {symbol.symbol}
                    </TableCell>
                    <TableCell className="text-xs text-slate-600">{symbol.timeframe}</TableCell>
                    <TableCell className="text-xs text-slate-600 font-mono tabular-nums">
                      {formatTimestamp(symbol.lastCandleTime)}
                    </TableCell>
                    <TableCell
                      className={`text-right font-mono text-xs tabular-nums ${isHighLag ? 'text-warning font-bold' : 'text-slate-600'}`}
                      data-testid={`symbol-lag-${symbol.symbol}`}
                    >
                      {formatLagMs(symbol.lagMs)}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}

        <div className="pt-3 border-t border-slate-100">
          <h4 className="text-[10px] text-slate-400 uppercase tracking-wider font-medium mb-2">
            Last Decision
          </h4>
          {data.lastDecision ? (
            <div className="space-y-1.5 text-xs" data-testid="last-decision">
              <div className="flex justify-between">
                <span className="text-slate-500">Symbol:</span>
                <span className="font-medium text-slate-900" data-testid="last-decision-symbol">
                  {data.lastDecision.symbol}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Action:</span>
                <span
                  className={getActionColor(data.lastDecision.action)}
                  data-testid="last-decision-action"
                >
                  {data.lastDecision.action}
                </span>
              </div>
              <div className="flex justify-between gap-4">
                <span className="text-slate-500 shrink-0">Reason:</span>
                <span className="text-slate-600 text-right" data-testid="last-decision-reason">
                  {data.lastDecision.reason}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Time:</span>
                <span className="font-mono text-slate-600 tabular-nums">
                  {formatTimestamp(data.lastDecision.timestamp)}
                </span>
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-400">No recent decisions</p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
