'use client'

import { AppShell } from '@/components/shell'
import { useOrderHistory } from '@/hooks/useOrderHistory'
import { Card, CardContent } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { MaterialIcon } from '@/components/common/MaterialIcon'
import { PageHeader } from '@/components/common/PageHeader'
import { IntegrationPill } from '@/components/common/IntegrationPill'
import { isUiRevampEnabled } from '@/config/ui-flags'
import { cn } from '@/lib/utils'

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function formatTime(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

type DateRange = '1d' | '7d' | '30d' | '90d' | 'all'

const DATE_RANGE_OPTIONS: { value: DateRange; label: string }[] = [
  { value: '1d', label: '24H' },
  { value: '7d', label: '7D' },
  { value: '30d', label: '30D' },
  { value: '90d', label: '90D' },
  { value: 'all', label: 'All' },
]

export default function HistoryPage() {
  const { filteredOrders, loading, error, stats, dateRange, setDateRange } = useOrderHistory({
    status: 'FILLED',
    limit: 100,
  })
  const revamp = isUiRevampEnabled()
  const surfaceCardClass = revamp
    ? 'bg-[#1A1A2E] border-[#232348] rounded-[18px] text-slate-100 shadow-[0_12px_30px_rgba(0,0,0,0.35)]'
    : 'bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-soft'

  return (
    <AppShell>
      <div className={revamp ? 'flex flex-col gap-6 text-slate-100' : 'flex flex-col gap-8'}>
        <PageHeader
          title="Trade History"
          actions={<IntegrationPill transport="REST" endpoint="/trading/orders?status=FILLED" />}
        />

        {error && (
          <Card
            className={cn(
              revamp
                ? 'rounded-[18px] border border-red-500/40 bg-red-500/10'
                : 'border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950',
            )}
          >
            <CardContent className="flex items-center gap-3 p-4">
              <MaterialIcon name="error" size="lg" className="text-destructive shrink-0" />
              <div>
                <p className="text-sm font-medium text-destructive">Failed to load trade history</p>
                <p className="text-xs text-slate-400 mt-1">{error}. Try refreshing the page.</p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stats Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
          {loading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Card
                key={i}
                className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm"
              >
                <CardContent className="p-5">
                  <Skeleton className="h-3 w-20 mb-2" />
                  <Skeleton className="h-7 w-16" />
                </CardContent>
              </Card>
            ))
          ) : (
            <>
              {[
                { label: 'Total Trades', value: String(stats.totalTrades) },
                { label: 'Buy Orders', value: String(stats.buyOrders), className: 'text-success' },
                { label: 'Sell Orders', value: String(stats.sellOrders), className: 'text-danger' },
                {
                  label: 'Total Volume',
                  value: `$${stats.totalVolume.toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
                },
              ].map(stat => (
                <Card
                  key={stat.label}
                  className={cn(
                    surfaceCardClass,
                    !revamp && 'hover:shadow-md transition-all duration-200',
                    revamp && 'hover:border-primary/40',
                  )}
                >
                  <CardContent className="p-5">
                    <p className="text-xs text-slate-400 uppercase tracking-wide">{stat.label}</p>
                    <p className={`text-xl font-bold font-mono mt-1 ${stat.className || ''}`}>
                      {stat.value}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </>
          )}
        </div>

        {/* Filter Row */}
        <Card className={cn(surfaceCardClass, !revamp && 'shadow-sm')}>
          <CardContent className="flex flex-wrap items-center gap-3 p-4">
            <div className="flex items-center gap-1.5">
              {DATE_RANGE_OPTIONS.map(option => (
                <button
                  key={option.value}
                  onClick={() => setDateRange(option.value)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors duration-fast ${
                    dateRange === option.value
                      ? 'bg-primary text-primary-foreground'
                      : revamp
                        ? 'bg-[#15152a] text-slate-300 hover:bg-[#232348]'
                        : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {revamp && (
          <div data-testid="history-mobile-view" className="space-y-3 md:hidden">
            {loading ? (
              <>
                <p className="text-xs text-slate-500">Loading history…</p>
                {Array.from({ length: 3 }).map((_, index) => (
                  <Card key={`mobile-loading-${index}`} className={surfaceCardClass}>
                    <CardContent className="space-y-3 p-4">
                      <Skeleton className="h-4 w-32" />
                      <div className="grid grid-cols-3 gap-3">
                        <Skeleton className="h-8 w-full" />
                        <Skeleton className="h-8 w-full" />
                        <Skeleton className="h-8 w-full" />
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </>
            ) : filteredOrders.length === 0 ? (
              <Card className={surfaceCardClass}>
                <CardContent className="flex flex-col items-center justify-center gap-3 py-10">
                  <MaterialIcon name="search" size="xl" className="text-slate-300" />
                  <p className="text-base font-medium text-slate-300">
                    No trades match these filters
                  </p>
                  <p className="text-sm text-slate-500">
                    Try widening your search or selecting a different time range.
                  </p>
                </CardContent>
              </Card>
            ) : (
              filteredOrders.slice(0, 20).map(order => (
                <Card key={`mobile-${order.orderId}`} className={surfaceCardClass}>
                  <CardContent className="space-y-3 p-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="font-mono text-sm text-white">{order.symbol}</p>
                        <p className="text-xs text-slate-500">
                          {formatDate(order.createdAt)} • {formatTime(order.createdAt)}
                        </p>
                      </div>
                      <Badge
                        variant="outline"
                        className={
                          order.side === 'BUY'
                            ? 'bg-success/15 text-success border-success/30'
                            : 'bg-destructive/15 text-destructive border-destructive/30'
                        }
                      >
                        {order.side}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-3 gap-3 text-xs">
                      <div>
                        <p className="text-slate-500">Price</p>
                        <p className="font-mono text-slate-200">
                          ${(order.avgPrice || order.price || 0).toFixed(2)}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-500">Qty</p>
                        <p className="font-mono text-slate-200">
                          {(order.executedQuantity || 0).toFixed(4)}
                        </p>
                      </div>
                      <div>
                        <p className="text-slate-500">Total</p>
                        <p className="font-mono text-slate-200">
                          $
                          {(
                            (order.avgPrice || order.price || 0) * (order.executedQuantity || 0)
                          ).toLocaleString('en-US', {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })}
                        </p>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        )}

        {/* History Table */}
        <Card className={cn(surfaceCardClass, revamp && 'hidden md:block')}>
          <CardContent className="p-0">
            {loading ? (
              <div className="p-5 space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : filteredOrders.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <MaterialIcon name="search" size="xl" className="text-slate-300" />
                <p className="text-lg font-medium text-slate-600 dark:text-slate-400">
                  No trades match these filters
                </p>
                <p className="text-sm text-slate-400">
                  Try widening your search or selecting a different time range.
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow
                    className={cn(
                      revamp
                        ? 'bg-[#15152a] hover:bg-[#15152a]'
                        : 'bg-slate-50 dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800',
                    )}
                  >
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                      Date
                    </TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                      Time
                    </TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                      Symbol
                    </TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                      Type
                    </TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                      Side
                    </TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                      Price
                    </TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                      Quantity
                    </TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                      Total
                    </TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                      Status
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredOrders.map((order, idx) => (
                    <TableRow
                      key={order.orderId}
                      className={cn(
                        revamp
                          ? 'border-[#232348] hover:bg-[#15152a] transition-colors duration-fast'
                          : `hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors duration-fast ${idx % 2 === 0 ? '' : 'bg-slate-50/50 dark:bg-slate-800/50'}`,
                      )}
                    >
                      <TableCell className="text-sm text-slate-600 dark:text-slate-400">
                        {formatDate(order.createdAt)}
                      </TableCell>
                      <TableCell className="text-sm text-slate-600 dark:text-slate-400">
                        {formatTime(order.createdAt)}
                      </TableCell>
                      <TableCell className="text-sm font-medium">{order.symbol}</TableCell>
                      <TableCell className="text-sm text-slate-600 dark:text-slate-400">
                        {order.type}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={
                            order.side === 'BUY'
                              ? 'bg-success/15 text-success border-success/30'
                              : 'bg-destructive/15 text-destructive border-destructive/30'
                          }
                        >
                          {order.side}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums text-sm">
                        ${(order.avgPrice || order.price || 0).toFixed(2)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums text-sm">
                        {(order.executedQuantity || 0).toFixed(4)}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums text-sm">
                        $
                        {(
                          (order.avgPrice || order.price || 0) * (order.executedQuantity || 0)
                        ).toLocaleString('en-US', {
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="secondary"
                          className="bg-success/15 text-success border-success/30"
                        >
                          {order.status}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </AppShell>
  )
}
