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
      <div className="flex flex-col gap-8">
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Active Trades</h1>

        {error && (
          <Card className="border-red-200 bg-red-50">
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
                { label: 'Total Trades', value: stats.totalTrades },
                { label: 'Open Orders', value: stats.openOrders },
                { label: 'Filled Orders', value: stats.filledOrders },
                { label: 'Canceled Orders', value: stats.canceledOrders },
              ].map(stat => (
                <Card
                  key={stat.label}
                  className="bg-white rounded-2xl border border-slate-100 shadow-soft hover:shadow-md transition-all duration-200"
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
          <TabsList>
            <TabsTrigger value="all">All ({stats.totalTrades})</TabsTrigger>
            <TabsTrigger value="open">Open ({stats.openOrders})</TabsTrigger>
            <TabsTrigger value="filled">Filled ({stats.filledOrders})</TabsTrigger>
            <TabsTrigger value="canceled">Canceled ({stats.canceledOrders})</TabsTrigger>
          </TabsList>
        </Tabs>

        {/* Orders Table */}
        <Card className="bg-white rounded-2xl border border-slate-100 shadow-soft">
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
                <p className="text-lg font-medium text-slate-600">No trades found</p>
                <p className="text-sm text-slate-400">
                  {filter !== 'all'
                    ? 'Try changing the filter to see more trades.'
                    : 'Orders will appear here once you start trading.'}
                </p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="bg-slate-50 hover:bg-slate-50">
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
                      className="hover:bg-slate-50 transition-colors duration-fast"
                    >
                      <TableCell className="text-sm text-slate-600">
                        {formatDate(order.createdAt)}
                      </TableCell>
                      <TableCell className="text-sm font-medium">{order.symbol}</TableCell>
                      <TableCell className="text-sm text-slate-600">{order.type}</TableCell>
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
