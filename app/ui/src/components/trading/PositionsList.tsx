import type { Position } from '@/types'
import { formatNumber } from '@/utils/formatters'
import { formatPositionDelta } from '@/utils/tradingHelpers'
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
import { AlertCircle } from 'lucide-react'

type PositionsListProps = {
  positions: Position[]
  loading?: boolean
  error?: string
  onClose?: (position: Position) => void
  className?: string
}

export function PositionsList({
  positions,
  loading = false,
  error,
  onClose,
  className = '',
}: PositionsListProps) {
  const totalPnl = positions.reduce((sum, position) => sum + position.pnl, 0)

  if (loading) {
    return (
      <Card
        className={`bg-surface-raised border-border-subtle shadow-sm ${className}`}
        data-testid="positions-list"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
            Open Positions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3" data-testid="positions-loading">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-6 w-full" />
            <Skeleton className="h-6 w-3/4" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card
        className={`bg-surface-raised border-destructive/30 shadow-sm ${className}`}
        data-testid="positions-list"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
            Open Positions
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div
            className="flex items-center gap-2 text-sm text-destructive"
            data-testid="positions-error"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        </CardContent>
      </Card>
    )
  }

  const totalDelta = formatPositionDelta(totalPnl, 0)

  return (
    <Card
      className={`bg-white rounded-2xl border border-slate-100 shadow-soft hover:shadow-md transition-all duration-200 ${className}`}
      data-testid="positions-list"
    >
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
          Open Positions
        </CardTitle>
        {positions.length > 0 && (
          <div className="flex items-center gap-2 text-sm">
            <span className="text-text-muted">Total P&L:</span>
            <span
              className={`font-bold font-mono ${
                totalPnl > 0 ? 'text-success' : totalPnl < 0 ? 'text-danger' : 'text-text-muted'
              }`}
            >
              {totalDelta.formattedPnl}
            </span>
          </div>
        )}
      </CardHeader>
      <CardContent>
        {positions.length === 0 ? (
          <p className="text-sm text-text-muted py-4 text-center">No open positions</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow className="bg-surface-overlay/50 hover:bg-surface-overlay/50">
                <TableHead className="text-xs text-text-muted uppercase tracking-wide">
                  Symbol
                </TableHead>
                <TableHead className="text-xs text-text-muted uppercase tracking-wide">
                  Side
                </TableHead>
                <TableHead className="text-xs text-text-muted uppercase tracking-wide text-right">
                  Quantity
                </TableHead>
                <TableHead className="text-xs text-text-muted uppercase tracking-wide text-right">
                  Entry
                </TableHead>
                <TableHead className="text-xs text-text-muted uppercase tracking-wide text-right">
                  Mark
                </TableHead>
                <TableHead className="text-xs text-text-muted uppercase tracking-wide text-right">
                  P&L
                </TableHead>
                <TableHead className="text-xs text-text-muted uppercase tracking-wide text-right">
                  P&L %
                </TableHead>
                <TableHead className="text-xs text-text-muted uppercase tracking-wide">
                  Venue
                </TableHead>
                {onClose && (
                  <TableHead className="text-xs text-text-muted uppercase tracking-wide">
                    Action
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {positions.map((position, index) => {
                const delta = formatPositionDelta(position.pnl, position.pnlPercent)
                return (
                  <TableRow
                    key={`${position.symbol}-${index}`}
                    className="hover:bg-surface-hover/50 transition-colors duration-fast"
                  >
                    <TableCell className="text-sm font-medium">{position.symbol}</TableCell>
                    <TableCell>
                      <Badge
                        variant="outline"
                        className={
                          position.side === 'BUY'
                            ? 'bg-success/15 text-success border-success/30'
                            : 'bg-destructive/15 text-destructive border-destructive/30'
                        }
                      >
                        {position.side}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {position.quantity}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {formatNumber(position.entryPrice)}
                    </TableCell>
                    <TableCell className="text-right font-mono text-sm">
                      {formatNumber(position.markPrice)}
                    </TableCell>
                    <TableCell
                      className={`text-right font-mono text-sm font-bold ${
                        position.pnl > 0
                          ? 'text-success'
                          : position.pnl < 0
                            ? 'text-danger'
                            : 'text-text-muted'
                      }`}
                    >
                      {delta.formattedPnl}
                    </TableCell>
                    <TableCell
                      className={`text-right font-mono text-sm ${
                        position.pnl > 0
                          ? 'text-success'
                          : position.pnl < 0
                            ? 'text-danger'
                            : 'text-text-muted'
                      }`}
                    >
                      {delta.formattedPnlPercent}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {position.venue}
                      </Badge>
                    </TableCell>
                    {onClose && (
                      <TableCell>
                        <button
                          className="px-2 py-1 text-xs rounded-md bg-destructive/10 text-destructive hover:bg-destructive/20 transition-colors duration-fast"
                          onClick={() => onClose(position)}
                          type="button"
                          aria-label="Close position"
                        >
                          Close
                        </button>
                      </TableCell>
                    )}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
