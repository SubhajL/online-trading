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

        <main className="app-main">
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

        .analytics-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 2rem;
          flex-wrap: wrap;
          gap: 1rem;
        }

        .page-title {
          color: #f0f0f0;
          margin: 0;
        }

        .timeframe-selector {
          display: flex;
          gap: 0.25rem;
        }

        .timeframe-btn {
          padding: 0.5rem 0.75rem;
          background: transparent;
          border: 1px solid #3a3d4a;
          color: #9ca3af;
          border-radius: 0.25rem;
          cursor: pointer;
          transition: all 0.2s;
          font-size: 0.875rem;
        }

        .timeframe-btn:hover {
          background: #3a3d4a;
          color: #f0f0f0;
        }

        .timeframe-btn.active {
          background: #4f46e5;
          border-color: #4f46e5;
          color: white;
        }

        .loading-container {
          display: flex;
          align-items: center;
          justify-content: center;
          min-height: 400px;
          color: #9ca3af;
        }

        .performance-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 1rem;
          margin-bottom: 3rem;
        }

        .metric-card {
          background: #2a2d3a;
          padding: 1.25rem;
          border-radius: 0.5rem;
          border: 1px solid #3a3d4a;
        }

        .metric-card h3 {
          font-size: 0.875rem;
          color: #9ca3af;
          margin-bottom: 0.5rem;
          font-weight: normal;
        }

        .metric-value {
          font-size: 1.5rem;
          font-weight: bold;
          color: #f0f0f0;
        }

        .analytics-sections {
          display: flex;
          flex-direction: column;
          gap: 2rem;
        }

        .trading-stats,
        .symbol-performance,
        .pnl-chart {
          background: #2a2d3a;
          padding: 1.5rem;
          border-radius: 0.5rem;
          border: 1px solid #3a3d4a;
        }

        .trading-stats h2,
        .symbol-performance h2,
        .pnl-chart h2 {
          margin-bottom: 1.5rem;
          color: #f0f0f0;
        }

        .stats-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 1.5rem;
        }

        .stat-item {
          display: flex;
          flex-direction: column;
        }

        .stat-label {
          font-size: 0.875rem;
          color: #9ca3af;
          margin-bottom: 0.25rem;
        }

        .stat-value {
          font-size: 1.25rem;
          font-weight: bold;
          color: #f0f0f0;
        }

        .symbol-table {
          width: 100%;
          border-collapse: collapse;
        }

        .symbol-table th {
          text-align: left;
          padding: 0.75rem;
          border-bottom: 1px solid #3a3d4a;
          color: #9ca3af;
          font-weight: 500;
        }

        .symbol-table td {
          padding: 0.75rem;
          border-bottom: 1px solid #3a3d4a;
          color: #f0f0f0;
        }

        .symbol-table tr:last-child td {
          border-bottom: none;
        }

        .chart-container {
          margin-top: 1rem;
        }

        .simple-bar-chart {
          display: flex;
          align-items: center;
          justify-content: space-around;
          height: 200px;
          padding: 1rem;
        }

        .bar-wrapper {
          display: flex;
          flex-direction: column;
          align-items: center;
          flex: 1;
          height: 100%;
          justify-content: center;
          position: relative;
        }

        .bar {
          width: 40px;
          background: #4f46e5;
          border-radius: 0.25rem;
          transition: all 0.3s;
        }

        .bar.positive {
          background: #10b981;
        }

        .bar.negative {
          background: #ef4444;
        }

        .bar-label {
          font-size: 0.75rem;
          color: #9ca3af;
          margin-top: 0.5rem;
        }

        .bar-value {
          font-size: 0.75rem;
          font-weight: bold;
          color: #f0f0f0;
          position: absolute;
          top: 10px;
        }

        .positive {
          color: #10b981;
        }
        .negative {
          color: #ef4444;
        }
      `}</style>
    </div>
  )
}
