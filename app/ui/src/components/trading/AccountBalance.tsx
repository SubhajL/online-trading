import { useMemo } from 'react'
import type { Balance } from '@/types'
import { formatNumber, formatCurrency } from '@/utils/formatters'
import './AccountBalance.css'

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
  // Group balances by venue
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

  // Calculate total USD value
  const totalUsdValue = useMemo(() => {
    return balances.reduce((sum, balance) => sum + (balance.usdValue || 0), 0)
  }, [balances])

  if (loading) {
    return (
      <div className={`account-balance ${className}`} data-testid="account-balance">
        <h3 className="balance-title">Account Balance</h3>
        <div className="balance-loading" data-testid="balance-loading">
          Loading balances...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`account-balance ${className}`} data-testid="account-balance">
        <h3 className="balance-title">Account Balance</h3>
        <div className="balance-error" data-testid="balance-error">
          {error}
        </div>
      </div>
    )
  }

  if (balances.length === 0) {
    return (
      <div className={`account-balance ${className}`} data-testid="account-balance">
        <h3 className="balance-title">Account Balance</h3>
        <div className="empty-state">No balances available</div>
      </div>
    )
  }

  return (
    <div className={`account-balance ${className}`} data-testid="account-balance">
      <h3 className="balance-title">Account Balance</h3>

      <div className="balances-container">
        {Object.entries(balancesByVenue).map(([venue, venueBalances]) => (
          <div key={venue} className="venue-group">
            <h4 className="venue-title">{venue}</h4>

            <div className="balance-table">
              <div className="table-header">
                <span>Asset</span>
                <span>Free</span>
                <span>Locked</span>
                <span>Total</span>
                {venueBalances.some(b => b.usdValue) && <span>USD Value</span>}
              </div>

              {venueBalances.map(balance => {
                const total = balance.free + balance.locked

                return (
                  <div key={`${balance.asset}-${balance.venue}`} className="balance-row">
                    <span className="asset-name">{balance.asset}</span>
                    <span className="free-amount">{formatNumber(balance.free)}</span>
                    <span className="locked-amount">{formatNumber(balance.locked)}</span>
                    <span className="total-amount">{formatNumber(total)}</span>
                    {venueBalances.some(b => b.usdValue) && (
                      <span className="usd-value">
                        {balance.usdValue ? formatCurrency(balance.usdValue) : '-'}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {totalUsdValue > 0 && (
        <div className="total-usd">
          <span>Total USD Value:</span>
          <span className="total-usd-value">{formatCurrency(totalUsdValue)}</span>
        </div>
      )}
    </div>
  )
}
