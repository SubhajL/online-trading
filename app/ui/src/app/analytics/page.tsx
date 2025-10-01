'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { useState } from 'react'
import { useAnalytics } from '@/hooks/useAnalytics'

type TimeFrame = '24h' | '7d' | '30d' | '90d' | '1y' | 'all'

export default function AnalyticsPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [timeframe, setTimeframe] = useState<TimeFrame>('7d')

  const { data, loading, error } = useAnalytics(timeframe)

  return (
    <div className="app-layout">
      <Header userName="Trader" onLogout={() => console.warn('TODO: Implement logout')} />

      <div className="app-body">
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main id="main-content" className="app-main" tabIndex={-1}>
          <div className="page-container">
            <div className="analytics-header">
              <h1 className="page-title">Trading Analytics</h1>
              <div className="timeframe-selector">
                {(['24h', '7d', '30d', '90d', '1y', 'all'] as TimeFrame[]).map(tf => (
                  <button
                    key={tf}
                    className={`timeframe-btn ${timeframe === tf ? 'active' : ''}`}
                    onClick={() => setTimeframe(tf)}
                  >
                    {tf === 'all' ? 'All' : tf}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <div className="error-message">
                <p>Failed to load analytics: {error}</p>
              </div>
            )}

            {loading ? (
              <div className="loading-container">
                <p>Loading analytics...</p>
              </div>
            ) : error ? null : (
              <>
                <div className="performance-grid">
                  <div className="metric-card">
                    <h3>Total Return</h3>
                    <p
                      className={`metric-value ${data.performance.totalReturn >= 0 ? 'positive' : 'negative'}`}
                    >
                      {data.performance.totalReturn >= 0 ? '+' : ''}
                      {data.performance.totalReturn}%
                    </p>
                  </div>
                  <div className="metric-card">
                    <h3>Win Rate</h3>
                    <p className="metric-value">{data.performance.winRate}%</p>
                  </div>
                  <div className="metric-card">
                    <h3>Profit Factor</h3>
                    <p className="metric-value">{data.performance.profitFactor}</p>
                  </div>
                  <div className="metric-card">
                    <h3>Sharpe Ratio</h3>
                    <p className="metric-value">{data.performance.sharpeRatio}</p>
                  </div>
                  <div className="metric-card">
                    <h3>Max Drawdown</h3>
                    <p className="metric-value negative">{data.performance.maxDrawdown}%</p>
                  </div>
                  <div className="metric-card">
                    <h3>Avg Win</h3>
                    <p className="metric-value positive">${data.performance.avgWin}</p>
                  </div>
                  <div className="metric-card">
                    <h3>Avg Loss</h3>
                    <p className="metric-value negative">${data.performance.avgLoss}</p>
                  </div>
                  <div className="metric-card">
                    <h3>Best Trade</h3>
                    <p className="metric-value positive">${data.performance.bestTrade}</p>
                  </div>
                </div>

                <div className="analytics-sections">
                  <section className="trading-stats">
                    <h2>Trading Statistics</h2>
                    <div className="stats-grid">
                      <div className="stat-item">
                        <span className="stat-label">Total Trades</span>
                        <span className="stat-value">{data.tradingStats.totalTrades}</span>
                      </div>
                      <div className="stat-item">
                        <span className="stat-label">Winning Trades</span>
                        <span className="stat-value positive">
                          {data.tradingStats.winningTrades}
                        </span>
                      </div>
                      <div className="stat-item">
                        <span className="stat-label">Losing Trades</span>
                        <span className="stat-value negative">
                          {data.tradingStats.losingTrades}
                        </span>
                      </div>
                      <div className="stat-item">
                        <span className="stat-label">Avg Hold Time</span>
                        <span className="stat-value">{data.tradingStats.avgHoldTime}</span>
                      </div>
                      <div className="stat-item">
                        <span className="stat-label">Total Volume</span>
                        <span className="stat-value">
                          ${data.tradingStats.totalVolume.toLocaleString()}
                        </span>
                      </div>
                      <div className="stat-item">
                        <span className="stat-label">Total Commission</span>
                        <span className="stat-value">${data.tradingStats.totalCommission}</span>
                      </div>
                    </div>
                  </section>

                  <section className="symbol-performance">
                    <h2>Performance by Symbol</h2>
                    <table className="symbol-table">
                      <thead>
                        <tr>
                          <th>Symbol</th>
                          <th>Trades</th>
                          <th>P&L</th>
                          <th>Win Rate</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.symbols.map(sym => (
                          <tr key={sym.symbol}>
                            <td>{sym.symbol}</td>
                            <td>{sym.trades}</td>
                            <td className={sym.pnl >= 0 ? 'positive' : 'negative'}>
                              ${sym.pnl.toFixed(2)}
                            </td>
                            <td className={sym.winRate >= 50 ? 'positive' : 'negative'}>
                              {sym.winRate.toFixed(1)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </section>

                  <section className="pnl-chart">
                    <h2>Weekly P&L</h2>
                    <div className="chart-container">
                      <div className="simple-bar-chart">
                        {data.weeklyPnL.map(week => (
                          <div key={week.week} className="bar-wrapper">
                            <div
                              className={`bar ${week.pnl >= 0 ? 'positive' : 'negative'}`}
                              style={{
                                height: `${Math.abs(week.pnl) / 30}px`,
                                marginTop: week.pnl < 0 ? '0' : 'auto',
                                marginBottom: week.pnl >= 0 ? '0' : 'auto',
                              }}
                            />
                            <span className="bar-label">{week.week}</span>
                            <span className="bar-value">${week.pnl}</span>
                          </div>
                        ))}
                      </div>
                    </div>
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
