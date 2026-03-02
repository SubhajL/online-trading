'use client'

import { useState, useMemo } from 'react'
import { AppShell } from '@/components/shell'
import { useOrders } from '@/hooks/useOrders'
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
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Skeleton } from '@/components/ui/skeleton'
import { MaterialIcon } from '@/components/common/MaterialIcon'
import { PageHeader } from '@/components/common/PageHeader'
import { IntegrationPill } from '@/components/common/IntegrationPill'
import { BusBar } from '@/components/common/BusBar'
import { isUiRevampEnabled } from '@/config/ui-flags'
import { cn } from '@/lib/utils'

type FilterValue = 'all' | 'open' | 'filled' | 'canceled'

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusVariant(status: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'NEW':
    case 'PARTIALLY_FILLED':
      return 'default'
    case 'FILLED':
      return 'secondary'
    case 'CANCELED':
    case 'REJECTED':
    case 'EXPIRED':
      return 'destructive'
    default:
      return 'outline'
  }
}

export default function TradesPage() {
  const [filter, setFilter] = useState<FilterValue>('all')
  const { orders, loading, error, cancelOrder } = useOrders({})
  const revamp = isUiRevampEnabled()
  const surfaceCardClass = revamp
    ? 'bg-[#1A1A2E] border-[#232348] rounded-[18px] text-slate-100 shadow-[0_12px_30px_rgba(0,0,0,0.35)]'
    : 'bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-soft'

  const filteredOrders = useMemo(() => {
    return orders.filter(order => {
      if (filter === 'all') return true
      if (filter === 'open') return order.status === 'NEW' || order.status === 'PARTIALLY_FILLED'
      if (filter === 'filled') return order.status === 'FILLED'
      if (filter === 'canceled')
        return (
          order.status === 'CANCELED' || order.status === 'REJECTED' || order.status === 'EXPIRED'
        )
      return true
    })
  }, [orders, filter])

  const stats = useMemo(
    () => ({
      totalTrades: orders.length,
      openOrders: orders.filter(o => o.status === 'NEW' || o.status === 'PARTIALLY_FILLED').length,
      filledOrders: orders.filter(o => o.status === 'FILLED').length,
      canceledOrders: orders.filter(
        o => o.status === 'CANCELED' || o.status === 'REJECTED' || o.status === 'EXPIRED',
      ).length,
    }),
    [orders],
  )

  const handleCancelOrder = async (orderId: string, symbol: string, venue: 'SPOT' | 'USD_M') => {
    try {
      await cancelOrder(orderId, symbol, venue)
    } catch (err) {
      console.error('Failed to cancel order:', err)
    }
  }

  return (
    <AppShell>
      <div className={revamp ? 'flex flex-col gap-6 text-slate-100' : 'flex flex-col gap-8'}>
        <PageHeader
          title="Active Trades"
          actions={<IntegrationPill transport="WS" endpoint="/trading" />}
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
                <p className="text-sm font-medium text-destructive">Failed to load trades</p>
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
                { label: 'Total Trades', value: stats.totalTrades },
                { label: 'Open Orders', value: stats.openOrders },
                { label: 'Filled Orders', value: stats.filledOrders },
                { label: 'Canceled Orders', value: stats.canceledOrders },
              ].map(stat => (
                <Card
                  key={stat.label}
                  className={cn(
                    surfaceCardClass,
                    revamp && 'hover:border-primary/40',
                    !revamp && 'hover:shadow-md transition-all duration-200',
                  )}
                >
                  <CardContent className="p-5">
                    <p className="text-xs text-slate-400 uppercase tracking-wide">{stat.label}</p>
                    <p className="text-xl font-bold font-mono mt-1">{stat.value}</p>
                  </CardContent>
                </Card>
              ))}
            </>
          )}
        </div>

        {/* Filter Tabs */}
        <Tabs value={filter} onValueChange={v => setFilter(v as FilterValue)}>
          <TabsList className={cn(revamp && 'border border-[#232348] bg-[#1A1A2E]')}>
            <TabsTrigger value="all">All ({stats.totalTrades})</TabsTrigger>
            <TabsTrigger value="open">Open ({stats.openOrders})</TabsTrigger>
            <TabsTrigger value="filled">Filled ({stats.filledOrders})</TabsTrigger>
            <TabsTrigger value="canceled">Canceled ({stats.canceledOrders})</TabsTrigger>
          </TabsList>
        </Tabs>

        {revamp && (
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
            <Card className={cn(surfaceCardClass, 'xl:col-span-8')}>
              <CardContent className="p-5">
                <div className="mb-4 flex items-center justify-between">
                  <div>
                    <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                      Execution View
                    </h2>
                    <p className="mt-1 font-mono text-lg text-white">BTC/USDT • PERP</p>
                  </div>
                  <IntegrationPill transport="WS" endpoint="/trading" />
                </div>
                <div className="relative h-56 overflow-hidden rounded-xl border border-[#323267] bg-[#101022]">
                  <div className="absolute inset-0 [background-image:linear-gradient(to_right,rgba(51,65,85,0.15)_1px,transparent_1px),linear-gradient(to_bottom,rgba(51,65,85,0.15)_1px,transparent_1px)] [background-size:30px_30px]" />
                  <svg
                    className="absolute inset-0 h-full w-full"
                    viewBox="0 0 100 30"
                    preserveAspectRatio="none"
                  >
                    <path
                      d="M0,24 C8,20 14,21 22,16 C30,11 37,13 44,9 C52,5 60,8 68,6 C76,3 84,4 100,2"
                      fill="none"
                      stroke="#6363f2"
                      strokeWidth="1.2"
                    />
                  </svg>
                  <div className="absolute bottom-3 left-3 text-[10px] font-mono text-slate-500">
                    Decision feed overlays active
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className={cn(surfaceCardClass, 'xl:col-span-4')}>
              <CardContent className="space-y-4 p-5">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
                    Order Lifecycle
                  </h2>
                  <p className="mt-1 text-xs text-slate-500">Submit → ACK → Partial → Filled</p>
                </div>
                <BusBar nodes={['SUBMIT', 'ACK', 'PARTIAL', 'FILLED']} activeCount={3} />
                <div className="space-y-2 rounded-xl border border-[#323267] bg-[#15152a] p-3 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Open orders</span>
                    <span className="font-mono text-white">{stats.openOrders}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Fill ratio</span>
                    <span className="font-mono text-emerald-400">
                      {stats.totalTrades > 0
                        ? `${Math.round((stats.filledOrders / stats.totalTrades) * 100)}%`
                        : '0%'}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Canceled</span>
                    <span className="font-mono text-red-400">{stats.canceledOrders}</span>
                  </div>
                </div>
                <IntegrationPill transport="REST" endpoint="/trading/orders" />
              </CardContent>
            </Card>
          </div>
        )}

        {/* Orders Table */}
        <Card className={surfaceCardClass}>
          <CardContent className="p-0">
            {loading ? (
              <div className="p-5 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : filteredOrders.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 gap-3">
                <MaterialIcon name="list" size="xl" className="text-slate-300" />
                <p className="text-lg font-medium text-slate-600 dark:text-slate-400">
                  No trades found
                </p>
                <p className="text-sm text-slate-400">
                  {filter !== 'all'
                    ? 'Try changing the filter to see more trades.'
                    : 'Orders will appear here once you start trading.'}
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
                      Filled
                    </TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                      Status
                    </TableHead>
                    <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                      Action
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredOrders.map(order => (
                    <TableRow
                      key={order.orderId}
                      className={cn(
                        revamp
                          ? 'border-[#232348] hover:bg-[#15152a] transition-colors duration-fast'
                          : 'hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors duration-fast',
                      )}
                    >
                      <TableCell className="text-sm text-slate-600 dark:text-slate-400">
                        {formatDate(order.createdAt)}
                      </TableCell>
                      <TableCell className="text-sm font-medium">{order.symbol}</TableCell>
                      <TableCell className="text-sm text-slate-600 dark:text-slate-400">
                        {order.type}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={order.side === 'BUY' ? 'default' : 'destructive'}
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
                        {order.type === 'MARKET'
                          ? 'Market'
                          : order.avgPrice && order.status === 'FILLED'
                            ? `$${order.avgPrice.toFixed(2)}`
                            : order.price
                              ? `$${order.price.toFixed(2)}`
                              : '-'}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums text-sm">
                        {order.quantity}
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums text-sm">
                        {order.executedQuantity || 0}
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusVariant(order.status)}>{order.status}</Badge>
                      </TableCell>
                      <TableCell>
                        {(order.status === 'NEW' || order.status === 'PARTIALLY_FILLED') && (
                          <button
                            className="text-xs text-destructive hover:text-destructive/80 font-medium transition-colors duration-fast active:scale-[0.98]"
                            onClick={() =>
                              handleCancelOrder(String(order.orderId), order.symbol, order.venue)
                            }
                          >
                            Cancel
                          </button>
                        )}
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
