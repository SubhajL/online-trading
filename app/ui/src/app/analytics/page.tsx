'use client'

import { useState } from 'react'
import { AppShell } from '@/components/shell'
import { useAnalytics } from '@/hooks/useAnalytics'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { MaterialIcon } from '@/components/common/MaterialIcon'

type TimeFrame = '24h' | '7d' | '30d' | '90d' | '1y' | 'all'

const TIMEFRAMES: { value: TimeFrame; label: string }[] = [
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
  { value: '30d', label: '30d' },
  { value: '90d', label: '90d' },
  { value: '1y', label: '1y' },
  { value: 'all', label: 'All' },
]

export default function AnalyticsPage() {
  const [timeframe, setTimeframe] = useState<TimeFrame>('7d')
  const { data, loading, error } = useAnalytics(timeframe)

  return (
    <AppShell>
      <div className="flex flex-col gap-8">
        {/* Header + Controls */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Trading Analytics</h1>
          <Tabs value={timeframe} onValueChange={v => setTimeframe(v as TimeFrame)}>
            <TabsList>
              {TIMEFRAMES.map(tf => (
                <TabsTrigger key={tf.value} value={tf.value}>
                  {tf.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>

        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="flex items-center gap-3 p-4">
              <MaterialIcon name="error" size="lg" className="text-destructive shrink-0" />
              <div>
                <p className="text-sm font-medium text-destructive">Failed to load analytics</p>
                <p className="text-xs text-slate-400 mt-1">{error}. Try refreshing the page.</p>
              </div>
            </CardContent>
          </Card>
        )}

        {loading ? (
          <div className="flex flex-col gap-8">
            {/* KPI Skeletons */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-5">
              {Array.from({ length: 5 }).map((_, i) => (
                <Card key={i} className="bg-white rounded-2xl border border-slate-100 shadow-sm">
                  <CardContent className="p-5">
                    <Skeleton className="h-3 w-20 mb-2" />
                    <Skeleton className="h-7 w-16" />
                  </CardContent>
                </Card>
              ))}
            </div>
            {/* Chart Skeletons */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <Card className="bg-white rounded-2xl border border-slate-100 shadow-sm">
                <CardContent className="p-5">
                  <Skeleton className="h-48 w-full" />
                </CardContent>
              </Card>
              <Card className="bg-white rounded-2xl border border-slate-100 shadow-sm">
                <CardContent className="p-5">
                  <Skeleton className="h-48 w-full" />
                </CardContent>
              </Card>
            </div>
            {/* Table Skeleton */}
            <Card className="bg-white rounded-2xl border border-slate-100 shadow-sm">
              <CardContent className="p-5 space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </CardContent>
            </Card>
          </div>
        ) : error ? null : (
          <>
            {/* KPI Grid */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-5">
              {[
                {
                  label: 'Total Return',
                  value: `${data.performance.totalReturn >= 0 ? '+' : ''}${data.performance.totalReturn}%`,
                  colored: true,
                  positive: data.performance.totalReturn >= 0,
                },
                { label: 'Win Rate', value: `${data.performance.winRate}%`, colored: false },
                {
                  label: 'Profit Factor',
                  value: String(data.performance.profitFactor),
                  colored: false,
                },
                {
                  label: 'Sharpe Ratio',
                  value: String(data.performance.sharpeRatio),
                  colored: false,
                },
                {
                  label: 'Max Drawdown',
                  value: `${data.performance.maxDrawdown}%`,
                  colored: true,
                  positive: false,
                },
              ].map(kpi => (
                <Card
                  key={kpi.label}
                  className="bg-white rounded-2xl border border-slate-100 shadow-soft hover:shadow-md transition-all duration-200"
                >
                  <CardContent className="p-5">
                    <p className="text-xs text-slate-400 uppercase tracking-wide">{kpi.label}</p>
                    <p
                      className={`text-xl font-bold font-mono mt-1 ${kpi.colored ? (kpi.positive ? 'text-success' : 'text-danger') : ''}`}
                    >
                      {kpi.value}
                    </p>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Trading Statistics */}
            <Card className="bg-white rounded-2xl border border-slate-100 shadow-soft">
              <CardHeader>
                <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide flex items-center gap-2">
                  <MaterialIcon name="trending_up" size="md" />
                  Trading Statistics
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-5">
                  {[
                    { label: 'Total Trades', value: String(data.tradingStats.totalTrades) },
                    {
                      label: 'Winning Trades',
                      value: String(data.tradingStats.winningTrades),
                      className: 'text-success',
                    },
                    {
                      label: 'Losing Trades',
                      value: String(data.tradingStats.losingTrades),
                      className: 'text-danger',
                    },
                    { label: 'Avg Hold Time', value: data.tradingStats.avgHoldTime },
                    {
                      label: 'Total Volume',
                      value: `$${data.tradingStats.totalVolume.toLocaleString()}`,
                    },
                    { label: 'Total Commission', value: `$${data.tradingStats.totalCommission}` },
                  ].map(stat => (
                    <div key={stat.label} className="flex flex-col gap-1">
                      <span className="text-xs text-slate-400 uppercase tracking-wide">
                        {stat.label}
                      </span>
                      <span className={`text-lg font-bold font-mono ${stat.className || ''}`}>
                        {stat.value}
                      </span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            {/* Weekly PnL Chart */}
            <Card className="bg-white rounded-2xl border border-slate-100 shadow-soft">
              <CardHeader>
                <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide flex items-center gap-2">
                  <MaterialIcon name="bar_chart" size="md" />
                  Weekly P&L
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-end gap-3 h-40">
                  {data.weeklyPnL.map(week => {
                    const maxPnl = Math.max(...data.weeklyPnL.map(w => Math.abs(w.pnl)), 1)
                    const heightPercent = (Math.abs(week.pnl) / maxPnl) * 100
                    return (
                      <div key={week.week} className="flex flex-col items-center gap-1 flex-1">
                        <span
                          className={`text-xs font-mono ${week.pnl >= 0 ? 'text-success' : 'text-danger'}`}
                        >
                          ${week.pnl}
                        </span>
                        <div
                          className={`w-full rounded-t-sm transition-all duration-fast ${week.pnl >= 0 ? 'bg-success/60' : 'bg-destructive/60'}`}
                          style={{ height: `${Math.max(heightPercent, 4)}%` }}
                        />
                        <span className="text-xs text-slate-400">{week.week}</span>
                      </div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Performance by Symbol */}
            <Card className="bg-white rounded-2xl border border-slate-100 shadow-soft">
              <CardHeader>
                <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
                  Performance by Symbol
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50 hover:bg-slate-50">
                      <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                        Symbol
                      </TableHead>
                      <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                        Trades
                      </TableHead>
                      <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                        P&L
                      </TableHead>
                      <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                        Win Rate
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.symbols.map(sym => (
                      <TableRow
                        key={sym.symbol}
                        className="hover:bg-slate-50 transition-colors duration-fast"
                      >
                        <TableCell className="font-medium text-sm">{sym.symbol}</TableCell>
                        <TableCell className="text-right font-mono tabular-nums text-sm">
                          {sym.trades}
                        </TableCell>
                        <TableCell
                          className={`text-right font-mono tabular-nums text-sm ${sym.pnl >= 0 ? 'text-success' : 'text-danger'}`}
                        >
                          {sym.pnl >= 0 ? '+' : ''}${sym.pnl.toFixed(2)}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <Progress value={sym.winRate} className="h-2 flex-1" />
                            <span
                              className={`text-xs font-mono ${sym.winRate >= 50 ? 'text-success' : 'text-danger'}`}
                            >
                              {sym.winRate.toFixed(1)}%
                            </span>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </AppShell>
  )
}
