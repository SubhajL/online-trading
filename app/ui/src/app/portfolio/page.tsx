'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { useState } from 'react'
import { usePositions } from '@/hooks/usePositions'
import { useBalances } from '@/hooks/useBalances'

export default function PortfolioPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Use real API hooks
  const {
    positions,
    loading: positionsLoading,
    error: positionsError,
    totalValue: positionsTotalValue,
    totalPnl,
  } = usePositions()
  const { balances, loading: balancesLoading, error: balancesError } = useBalances()

  // Combine loading and error states
  const loading = positionsLoading || balancesLoading
  const error = positionsError || balancesError

  // Calculate total portfolio value (positions + balances)
  const balancesValue = balances.reduce((sum, balance) => {
    if (balance.usdValue) return sum + balance.usdValue
    if (balance.asset === 'USDT' || balance.asset === 'USDC') return sum + balance.total
    return sum
  }, 0)
  const totalValue = positionsTotalValue + balancesValue

  return (
    <div className="app-layout">
      <Header userName="Trader" onLogout={() => console.warn('TODO: Implement logout')} />

      <div className="app-body">
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main id="main-content" className="app-main" tabIndex={-1}>
          <div className="page-container">
            <h1 className="page-title">Portfolio Overview</h1>

            {error ? (
              <div className="error-message">
                <p>Failed to load portfolio data: {error}</p>
              </div>
            ) : (
              <>
                <div className="portfolio-summary">
                  <div className="summary-card">
                    <h3>Total Portfolio Value</h3>
                    <p className="value">
                      $
                      {totalValue.toLocaleString('en-US', {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2,
                      })}
                    </p>
                  </div>
                  <div className="summary-card">
                    <h3>Total P&L</h3>
                    <p className={`value ${totalPnl >= 0 ? 'positive' : 'negative'}`}>
                      ${totalPnl.toFixed(2)} ({totalPnl >= 0 ? '+' : ''}
                      {((totalPnl / totalValue) * 100).toFixed(2)}%)
                    </p>
                  </div>
                  <div className="summary-card">
                    <h3>Open Positions</h3>
                    <p className="value">{positions.length}</p>
                  </div>
                </div>

                <div className="portfolio-sections">
                  <section className="positions-section">
                    <h2>Open Positions</h2>
                    {loading ? (
                      <p>Loading positions...</p>
                    ) : positions.length === 0 ? (
                      <p>No open positions</p>
                    ) : (
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Symbol</th>
                            <th>Side</th>
                            <th>Quantity</th>
                            <th>Entry Price</th>
                            <th>Mark Price</th>
                            <th>P&L</th>
                            <th>P&L %</th>
                          </tr>
                        </thead>
                        <tbody>
                          {positions.map((pos, idx) => (
                            <tr key={idx}>
                              <td>{pos.symbol}</td>
                              <td className={pos.side === 'BUY' ? 'buy' : 'sell'}>{pos.side}</td>
                              <td>{pos.quantity}</td>
                              <td>${pos.entryPrice.toFixed(2)}</td>
                              <td>${pos.markPrice.toFixed(2)}</td>
                              <td className={pos.pnl >= 0 ? 'positive' : 'negative'}>
                                ${pos.pnl.toFixed(2)}
                              </td>
                              <td className={pos.pnlPercent >= 0 ? 'positive' : 'negative'}>
                                {pos.pnlPercent >= 0 ? '+' : ''}
                                {pos.pnlPercent.toFixed(2)}%
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </section>

                  <section className="balances-section">
                    <h2>Asset Balances</h2>
                    {loading ? (
                      <p>Loading balances...</p>
                    ) : balances.length === 0 ? (
                      <p>No assets</p>
                    ) : (
                      <table className="data-table">
                        <thead>
                          <tr>
                            <th>Asset</th>
                            <th>Free</th>
                            <th>Locked</th>
                            <th>Total</th>
                            <th>USD Value</th>
                          </tr>
                        </thead>
                        <tbody>
                          {balances.map((balance, idx) => (
                            <tr key={idx}>
                              <td>{balance.asset}</td>
                              <td>{balance.free.toFixed(4)}</td>
                              <td>{balance.locked.toFixed(4)}</td>
                              <td>{balance.total.toFixed(4)}</td>
                              <td>
                                {balance.usdValue
                                  ? `$${balance.usdValue.toLocaleString('en-US', { minimumFractionDigits: 2 })}`
                                  : balance.asset === 'USDT' || balance.asset === 'USDC'
                                    ? `$${balance.total.toFixed(2)}`
                                    : '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </section>
                </div>
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
