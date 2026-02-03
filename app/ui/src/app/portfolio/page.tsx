'use client'

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
import { AlertCircle, Briefcase, Wallet } from 'lucide-react'

export default function PortfolioPage() {
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

  return (
    <AppShell>
      <div className="flex flex-col gap-8">
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Portfolio Overview</h1>

        {error && (
          <Card className="border-red-200 bg-red-50">
            <CardContent className="flex items-center gap-3 p-4">
              <AlertCircle className="h-5 w-5 text-destructive shrink-0" />
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
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-5">
          {loading ? (
            Array.from({ length: 3 }).map((_, i) => (
              <Card key={i} className="bg-white rounded-2xl border border-slate-100 shadow-sm">
                <CardContent className="p-5">
                  <Skeleton className="h-3 w-24 mb-2" />
                  <Skeleton className="h-8 w-32" />
                </CardContent>
              </Card>
            ))
          ) : (
            <>
              <Card className="bg-white rounded-2xl border border-slate-100 shadow-soft hover:shadow-md transition-all duration-200">
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
              <Card className="bg-white rounded-2xl border border-slate-100 shadow-soft hover:shadow-md transition-all duration-200">
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
              <Card className="bg-white rounded-2xl border border-slate-100 shadow-soft hover:shadow-md transition-all duration-200">
                <CardContent className="p-5">
                  <p className="text-xs text-slate-400 uppercase tracking-wide">Open Positions</p>
                  <p className="text-2xl font-bold font-mono mt-1">{positions.length}</p>
                </CardContent>
              </Card>
            </>
          )}
        </div>

        {/* Tables */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          {/* Positions Table */}
          <Card className="bg-white rounded-2xl border border-slate-100 shadow-soft">
            <CardHeader className="pb-0">
              <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide flex items-center gap-2">
                <Briefcase className="h-4 w-4" />
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
                  <Briefcase className="h-12 w-12 text-slate-300" />
                  <p className="text-lg font-medium text-slate-600">No open positions</p>
                  <p className="text-sm text-slate-400">
                    Positions will appear here when you open trades.
                  </p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50 hover:bg-slate-50">
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
                        className="hover:bg-slate-50 transition-colors duration-fast"
                      >
                        <TableCell className="font-medium text-sm">{pos.symbol}</TableCell>
                        <TableCell>
                          <Badge
                            variant="outline"
                            className={
                              pos.side === 'BUY'
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

          {/* Balances Table */}
          <Card className="bg-white rounded-2xl border border-slate-100 shadow-soft">
            <CardHeader className="pb-0">
              <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide flex items-center gap-2">
                <Wallet className="h-4 w-4" />
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
                  <Wallet className="h-12 w-12 text-slate-300" />
                  <p className="text-lg font-medium text-slate-600">No assets</p>
                  <p className="text-sm text-slate-400">
                    Balances will appear once your account is funded.
                  </p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow className="bg-slate-50 hover:bg-slate-50">
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
                        className="hover:bg-slate-50 transition-colors duration-fast"
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
        </div>
      </div>
    </AppShell>
  )
}
