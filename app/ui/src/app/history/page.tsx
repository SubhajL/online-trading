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
import { AlertCircle, Search } from 'lucide-react'

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

  return (
    <AppShell>
      <div className="flex flex-col gap-8">
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Trade History</h1>

        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="flex items-center gap-3 p-4">
              <AlertCircle className="h-5 w-5 text-destructive shrink-0" />
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
              <Card key={i} className="bg-white rounded-2xl border border-slate-100 shadow-sm">
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
                  className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_-2px_rgba(0,0,0,0.05)] hover:shadow-[0_8px_30px_-4px_rgba(0,0,0,0.08)] transition-all duration-200"
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
        <Card className="bg-white rounded-2xl border border-slate-100 shadow-sm">
          <CardContent className="flex flex-wrap items-center gap-3 p-4">
            <div className="flex items-center gap-1.5">
              {DATE_RANGE_OPTIONS.map(option => (
                <button
                  key={option.value}
                  onClick={() => setDateRange(option.value)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors duration-fast ${
                    dateRange === option.value
                      ? 'bg-primary text-primary-foreground'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>

        {/* History Table */}
        <Card className="bg-white rounded-2xl border border-slate-100 shadow-[0_4px_20px_-2px_rgba(0,0,0,0.05)]">
          <CardContent className="p-0">
            {loading ? (
              <div className="p-5 space-y-3">
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : filteredOrders.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <Search className="h-12 w-12 text-slate-300" />
                <p className="text-lg font-medium text-slate-600">
                  No trades match these filters
                </p>
                <p className="text-sm text-slate-400">
                  Try widening your search or selecting a different time range.
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50 hover:bg-slate-50">
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
                      className={`hover:bg-slate-50 transition-colors duration-fast ${idx % 2 === 0 ? '' : 'bg-slate-50/50'}`}
                    >
                      <TableCell className="text-sm text-slate-600">
                        {formatDate(order.createdAt)}
                      </TableCell>
                      <TableCell className="text-sm text-slate-600">
                        {formatTime(order.createdAt)}
                      </TableCell>
                      <TableCell className="text-sm font-medium">{order.symbol}</TableCell>
                      <TableCell className="text-sm text-slate-600">{order.type}</TableCell>
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
