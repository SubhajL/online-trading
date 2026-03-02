'use client'

import { useState } from 'react'
import { AppShell } from '@/components/shell'
import { usePositions } from '@/hooks/usePositions'
import { useBalances } from '@/hooks/useBalances'
import { getPositionKey, getBalanceKey } from '@/utils/keyHelpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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

export default function PortfolioPage() {
  const [viewMode, setViewMode] = useState<'positions' | 'assets'>('positions')
  const {
    positions,
    loading: positionsLoading,
    error: positionsError,
    totalValue: positionsTotalValue,
    totalPnl,
  } = usePositions()
  const { balances, loading: balancesLoading, error: balancesError } = useBalances()

  const loading = positionsLoading || balancesLoading
  const error = positionsError || balancesError

  const balancesValue = balances.reduce((sum, balance) => {
    if (balance.usdValue) return sum + balance.usdValue
    if (balance.asset === 'USDT' || balance.asset === 'USDC') return sum + balance.total
    return sum
  }, 0)
  const totalValue = positionsTotalValue + balancesValue
  const pnlPercent = totalValue > 0 ? (totalPnl / totalValue) * 100 : 0
  const revamp = isUiRevampEnabled()
  const availableCash = balances
    .filter(balance => balance.asset === 'USDT' || balance.asset === 'USDC')
    .reduce((sum, balance) => sum + balance.total, 0)
  const surfaceCardClass = revamp
    ? 'bg-[#1A1A2E] border-[#232348] rounded-[18px] text-slate-100 shadow-[0_12px_30px_rgba(0,0,0,0.35)]'
    : 'bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-soft'

  return (
    <AppShell>
      <div className={revamp ? 'flex flex-col gap-6 text-slate-100' : 'flex flex-col gap-8'}>
        <PageHeader
          title="Portfolio Overview"
          actions={<IntegrationPill transport="REST" endpoint="/trading/positions" />}
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
                <p className="text-sm font-medium text-destructive">
                  Failed to load portfolio data
                </p>
                <p className="text-xs text-slate-400 mt-1">{error}. Try refreshing the page.</p>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Summary Row */}
        <div
          className={cn(
            'grid gap-5',
            revamp ? 'grid-cols-2 lg:grid-cols-4' : 'grid-cols-2 lg:grid-cols-3',
          )}
        >
          {loading ? (
            Array.from({ length: revamp ? 4 : 3 }).map((_, i) => (
              <Card
                key={i}
                className={cn(
                  revamp
                    ? 'bg-[#1A1A2E] border-[#232348] rounded-[18px] shadow-sm'
                    : 'bg-white dark:bg-slate-900 rounded-2xl border border-slate-100 dark:border-slate-800 shadow-sm',
                )}
              >
                <CardContent className="p-5">
                  <Skeleton className="h-3 w-24 mb-2" />
                  <Skeleton className="h-8 w-32" />
                </CardContent>
              </Card>
            ))
          ) : (
            <>
              <Card
                className={cn(
                  surfaceCardClass,
                  !revamp && 'hover:shadow-md transition-all duration-200',
                )}
              >
                <CardContent className="p-5">
                  <p className="text-xs text-slate-400 uppercase tracking-wide">
                    Total Portfolio Value
                  </p>
                  <p className="text-2xl font-bold font-mono mt-1">
                    $
                    {totalValue.toLocaleString('en-US', {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </p>
                </CardContent>
              </Card>
              <Card
                className={cn(
                  surfaceCardClass,
                  !revamp && 'hover:shadow-md transition-all duration-200',
                )}
              >
                <CardContent className="p-5">
                  <p className="text-xs text-slate-400 uppercase tracking-wide">Total P&L</p>
                  <p
                    className={`text-2xl font-bold font-mono mt-1 ${totalPnl >= 0 ? 'text-success' : 'text-danger'}`}
                  >
                    {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
                    <span className="text-sm ml-1">
                      ({pnlPercent >= 0 ? '+' : ''}
                      {pnlPercent.toFixed(2)}%)
                    </span>
                  </p>
                </CardContent>
              </Card>
              <Card
                className={cn(
                  surfaceCardClass,
                  !revamp && 'hover:shadow-md transition-all duration-200',
                )}
              >
                <CardContent className="p-5">
                  <p className="text-xs text-slate-400 uppercase tracking-wide">Open Positions</p>
                  <p className="text-2xl font-bold font-mono mt-1">{positions.length}</p>
                </CardContent>
              </Card>
              {revamp && (
                <Card className={surfaceCardClass}>
                  <CardContent className="p-5">
                    <p className="text-xs text-slate-400 uppercase tracking-wide">Available Cash</p>
                    <p className="text-2xl font-bold font-mono mt-1">
                      ${availableCash.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </p>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </div>

        {revamp && (
          <div className="inline-flex rounded-xl border border-[#232348] bg-[#15152a] p-1">
            <button
              onClick={() => setViewMode('positions')}
              className={cn(
                'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                viewMode === 'positions'
                  ? 'bg-[#1A1A2E] text-white'
                  : 'text-slate-400 hover:text-slate-200',
              )}
            >
              Positions
            </button>
            <button
              onClick={() => setViewMode('assets')}
              className={cn(
                'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                viewMode === 'assets'
                  ? 'bg-[#1A1A2E] text-white'
                  : 'text-slate-400 hover:text-slate-200',
              )}
            >
              Assets & Allocation
            </button>
          </div>
        )}

        {/* Tables */}
        <div className={cn('grid gap-5', revamp ? 'grid-cols-1' : 'grid-cols-1 lg:grid-cols-2')}>
          {/* Positions Table */}
          {(!revamp || viewMode === 'positions') && (
            <Card className={surfaceCardClass}>
              <CardHeader className="pb-0">
                <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide flex items-center gap-2">
                  <MaterialIcon name="work" size="md" />
                  Open Positions
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0 pt-3">
                {loading ? (
                  <div className="p-5 space-y-3">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} className="h-10 w-full" />
                    ))}
                  </div>
                ) : positions.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 gap-3">
                    <MaterialIcon name="work" size="xl" className="text-slate-300" />
                    <p className="text-lg font-medium text-slate-600 dark:text-slate-400">
                      No open positions
                    </p>
                    <p className="text-sm text-slate-400">
                      Positions will appear here when you open trades.
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
                          Symbol
                        </TableHead>
                        <TableHead className="text-xs text-slate-400 uppercase tracking-wide">
                          Side
                        </TableHead>
                        <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                          Qty
                        </TableHead>
                        <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                          Entry
                        </TableHead>
                        <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                          Mark
                        </TableHead>
                        <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                          P&L
                        </TableHead>
                        <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                          P&L %
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {positions.map((pos, idx) => (
                        <TableRow
                          key={getPositionKey(pos.symbol, idx)}
                          className={cn(
                            revamp
                              ? 'border-[#232348] hover:bg-[#15152a] transition-colors duration-fast'
                              : 'hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors duration-fast',
                          )}
                        >
                          <TableCell className="font-medium text-sm">{pos.symbol}</TableCell>
                          <TableCell>
                            <Badge
                              variant="outline"
                              className={
                                pos.side === 'LONG'
                                  ? 'bg-success/15 text-success border-success/30'
                                  : 'bg-destructive/15 text-destructive border-destructive/30'
                              }
                            >
                              {pos.side}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums text-sm">
                            {pos.quantity}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums text-sm">
                            ${pos.entryPrice.toFixed(2)}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums text-sm">
                            ${pos.markPrice.toFixed(2)}
                          </TableCell>
                          <TableCell
                            className={`text-right font-mono tabular-nums text-sm ${pos.pnl >= 0 ? 'text-success' : 'text-danger'}`}
                          >
                            {pos.pnl >= 0 ? '+' : ''}${pos.pnl.toFixed(2)}
                          </TableCell>
                          <TableCell
                            className={`text-right font-mono tabular-nums text-sm ${pos.pnlPercent >= 0 ? 'text-success' : 'text-danger'}`}
                          >
                            {pos.pnlPercent >= 0 ? '+' : ''}
                            {pos.pnlPercent.toFixed(2)}%
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          )}

          {/* Balances Table */}
          {(!revamp || viewMode === 'assets') && (
            <Card className={surfaceCardClass}>
              <CardHeader className="pb-0">
                <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide flex items-center gap-2">
                  <MaterialIcon name="account_balance_wallet" size="md" />
                  Asset Balances
                </CardTitle>
              </CardHeader>
              <CardContent className="p-0 pt-3">
                {loading ? (
                  <div className="p-5 space-y-3">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <Skeleton key={i} className="h-10 w-full" />
                    ))}
                  </div>
                ) : balances.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 gap-3">
                    <MaterialIcon
                      name="account_balance_wallet"
                      size="xl"
                      className="text-slate-300"
                    />
                    <p className="text-lg font-medium text-slate-600 dark:text-slate-400">
                      No assets
                    </p>
                    <p className="text-sm text-slate-400">
                      Balances will appear once your account is funded.
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
                          Asset
                        </TableHead>
                        <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                          Free
                        </TableHead>
                        <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                          Locked
                        </TableHead>
                        <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                          Total
                        </TableHead>
                        <TableHead className="text-xs text-slate-400 uppercase tracking-wide text-right">
                          USD Value
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {balances.map((balance, idx) => (
                        <TableRow
                          key={getBalanceKey(balance.asset, idx)}
                          className={cn(
                            revamp
                              ? 'border-[#232348] hover:bg-[#15152a] transition-colors duration-fast'
                              : 'hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors duration-fast',
                          )}
                        >
                          <TableCell className="font-medium text-sm">{balance.asset}</TableCell>
                          <TableCell className="text-right font-mono tabular-nums text-sm">
                            {balance.free.toFixed(4)}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums text-sm">
                            {balance.locked.toFixed(4)}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums text-sm">
                            {balance.total.toFixed(4)}
                          </TableCell>
                          <TableCell className="text-right font-mono tabular-nums text-sm">
                            {balance.usdValue
                              ? `$${balance.usdValue.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
                              : balance.asset === 'USDT' || balance.asset === 'USDC'
                                ? `$${balance.total.toFixed(2)}`
                                : 'N/A'}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </AppShell>
  )
}
