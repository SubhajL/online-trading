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

        <main className="app-main">
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

      <style jsx>{`
        .app-layout {
          display: flex;
          flex-direction: column;
          min-height: 100vh;
        }

        .app-body {
          display: flex;
          flex: 1;
        }

        .app-main {
          flex: 1;
          overflow-x: auto;
        }

        .page-container {
          padding: 2rem;
        }

        .page-title {
          margin-bottom: 2rem;
          color: #f0f0f0;
        }

        .portfolio-summary {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
          gap: 1.5rem;
          margin-bottom: 3rem;
        }

        .summary-card {
          background: #2a2d3a;
          padding: 1.5rem;
          border-radius: 0.5rem;
          border: 1px solid #3a3d4a;
        }

        .summary-card h3 {
          font-size: 0.875rem;
          color: #9ca3af;
          margin-bottom: 0.5rem;
          text-transform: uppercase;
        }

        .summary-card .value {
          font-size: 1.5rem;
          font-weight: bold;
          color: #f0f0f0;
        }

        .portfolio-sections {
          display: flex;
          flex-direction: column;
          gap: 3rem;
        }

        .positions-section,
        .balances-section {
          background: #2a2d3a;
          padding: 1.5rem;
          border-radius: 0.5rem;
          border: 1px solid #3a3d4a;
        }

        .positions-section h2,
        .balances-section h2 {
          margin-bottom: 1rem;
          color: #f0f0f0;
        }

        .data-table {
          width: 100%;
          border-collapse: collapse;
        }

        .data-table th {
          text-align: left;
          padding: 0.75rem;
          border-bottom: 1px solid #3a3d4a;
          color: #9ca3af;
          font-weight: 500;
        }

        .data-table td {
          padding: 0.75rem;
          border-bottom: 1px solid #3a3d4a;
          color: #f0f0f0;
        }

        .data-table tr:last-child td {
          border-bottom: none;
        }

        .buy {
          color: #10b981;
        }
        .sell {
          color: #ef4444;
        }
        .positive {
          color: #10b981;
        }
        .negative {
          color: #ef4444;
        }

        .error-message {
          background: #dc2626;
          color: white;
          padding: 1rem;
          border-radius: 0.5rem;
          margin-bottom: 2rem;
        }
      `}</style>
    </div>
  )
}
