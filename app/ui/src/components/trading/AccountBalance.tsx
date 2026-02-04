import { useMemo } from 'react'
import type { Balance } from '@/types'
import { formatNumber, formatCurrency } from '@/utils/formatters'
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
import { MaterialIcon } from '@/components/common/MaterialIcon'

type AccountBalanceProps = {
  balances: Balance[]
  loading?: boolean
  error?: string
  className?: string
}

export function AccountBalance({
  balances,
  loading = false,
  error,
  className = '',
}: AccountBalanceProps) {
  const balancesByVenue = useMemo(() => {
    return balances.reduce(
      (acc, balance) => {
        if (!acc[balance.venue]) {
          acc[balance.venue] = []
        }
        acc[balance.venue]!.push(balance)
        return acc
      },
      {} as Record<string, Balance[]>,
    )
  }, [balances])

  const totalUsdValue = useMemo(() => {
    return balances.reduce((sum, balance) => sum + (balance.usdValue || 0), 0)
  }, [balances])

  if (loading) {
    return (
      <Card
        className={`bg-surface-raised border-border-subtle shadow-sm ${className}`}
        data-testid="account-balance"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
            Account Balance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3" data-testid="balance-loading">
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
        data-testid="account-balance"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
            Account Balance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div
            className="flex items-center gap-2 text-sm text-destructive"
            data-testid="balance-error"
          >
            <MaterialIcon name="error" size="sm" className="shrink-0" />
            {error}
          </div>
        </CardContent>
      </Card>
    )
  }

  if (balances.length === 0) {
    return (
      <Card
        className={`bg-surface-raised border-border-subtle shadow-sm ${className}`}
        data-testid="account-balance"
      >
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
            Account Balance
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-text-muted py-4 text-center">No balances available</p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card
      className={`bg-white dark:bg-slate-800 rounded-2xl border border-slate-100 dark:border-slate-700 shadow-soft hover:shadow-md transition-all duration-200 ${className}`}
      data-testid="account-balance"
    >
      <CardHeader className="pb-3 flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-medium text-slate-400 uppercase tracking-wide">
          Account Balance
        </CardTitle>
        {totalUsdValue > 0 && (
          <span className="text-sm font-bold font-mono text-text-primary">
            {formatCurrency(totalUsdValue)}
          </span>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {Object.entries(balancesByVenue).map(([venue, venueBalances]) => (
          <div key={venue}>
            <Badge variant="outline" className="mb-2 text-xs">
              {venue}
            </Badge>
            <Table>
              <TableHeader>
                <TableRow className="bg-surface-overlay/50 hover:bg-surface-overlay/50">
                  <TableHead className="text-xs text-text-muted uppercase tracking-wide">
                    Asset
                  </TableHead>
                  <TableHead className="text-xs text-text-muted uppercase tracking-wide text-right">
                    Free
                  </TableHead>
                  <TableHead className="text-xs text-text-muted uppercase tracking-wide text-right">
                    Locked
                  </TableHead>
                  <TableHead className="text-xs text-text-muted uppercase tracking-wide text-right">
                    Total
                  </TableHead>
                  {venueBalances.some(b => b.usdValue) && (
                    <TableHead className="text-xs text-text-muted uppercase tracking-wide text-right">
                      USD Value
                    </TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {venueBalances.map(balance => {
                  const total = balance.free + balance.locked
                  return (
                    <TableRow
                      key={`${balance.asset}-${balance.venue}`}
                      className="hover:bg-surface-hover/50 transition-colors duration-fast"
                    >
                      <TableCell className="text-sm font-medium">{balance.asset}</TableCell>
                      <TableCell className="text-right font-mono text-sm">
                        {formatNumber(balance.free)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm text-text-muted">
                        {formatNumber(balance.locked)}
                      </TableCell>
                      <TableCell className="text-right font-mono text-sm font-bold">
                        {formatNumber(total)}
                      </TableCell>
                      {venueBalances.some(b => b.usdValue) && (
                        <TableCell className="text-right font-mono text-sm">
                          {balance.usdValue ? formatCurrency(balance.usdValue) : '-'}
                        </TableCell>
                      )}
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
