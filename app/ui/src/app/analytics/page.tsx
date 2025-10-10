'use client'

import { Header } from '@/components/Layout/Header'
import { Sidebar } from '@/components/Layout/Sidebar'
import { useState } from 'react'
import { useAnalytics } from '@/hooks/useAnalytics'
import styles from './analytics.module.css'

type TimeFrame = '24h' | '7d' | '30d' | '90d' | '1y' | 'all'

export default function AnalyticsPage() {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [timeframe, setTimeframe] = useState<TimeFrame>('7d')

  const { data, loading, error } = useAnalytics(timeframe)

  return (
    <div className={styles.appLayout}>
      <Header userName="Trader" onLogout={() => console.warn('TODO: Implement logout')} />

      <div className={styles.appBody}>
        <Sidebar isOpen={sidebarOpen} onToggle={() => setSidebarOpen(!sidebarOpen)} />

        <main id="main-content" className={styles.appMain} tabIndex={-1}>
          <div className={styles.pageContainer}>
            <div className={styles.analyticsHeader}>
              <h1 className={styles.pageTitle}>Trading Analytics</h1>
              <div className={styles.timeframeSelector}>
                {(['24h', '7d', '30d', '90d', '1y', 'all'] as TimeFrame[]).map(tf => (
                  <button
                    key={tf}
                    className={`${styles.timeframeBtn} ${timeframe === tf ? styles.active : ''}`}
                    onClick={() => setTimeframe(tf)}
                  >
                    {tf === 'all' ? 'All' : tf}
                  </button>
                ))}
              </div>
            </div>

            {error && (
              <div className={styles.errorMessage}>
                <p>Failed to load analytics: {error}</p>
              </div>
            )}

            {loading ? (
              <div className={styles.loadingContainer}>
                <p>Loading analytics...</p>
              </div>
            ) : error ? null : (
              <>
                <div className={styles.performanceGrid}>
                  <div className={styles.metricCard}>
                    <h3>Total Return</h3>
                    <p
                      className={`${styles.metricValue} ${data.performance.totalReturn >= 0 ? styles.positive : styles.negative}`}
                    >
                      {data.performance.totalReturn >= 0 ? '+' : ''}
                      {data.performance.totalReturn}%
                    </p>
                  </div>
                  <div className={styles.metricCard}>
                    <h3>Win Rate</h3>
                    <p className={styles.metricValue}>{data.performance.winRate}%</p>
                  </div>
                  <div className={styles.metricCard}>
                    <h3>Profit Factor</h3>
                    <p className={styles.metricValue}>{data.performance.profitFactor}</p>
                  </div>
                  <div className={styles.metricCard}>
                    <h3>Sharpe Ratio</h3>
                    <p className={styles.metricValue}>{data.performance.sharpeRatio}</p>
                  </div>
                  <div className={styles.metricCard}>
                    <h3>Max Drawdown</h3>
                    <p className={`${styles.metricValue} ${styles.negative}`}>
                      {data.performance.maxDrawdown}%
                    </p>
                  </div>
                  <div className={styles.metricCard}>
                    <h3>Avg Win</h3>
                    <p className={`${styles.metricValue} ${styles.positive}`}>
                      ${data.performance.avgWin}
                    </p>
                  </div>
                  <div className={styles.metricCard}>
                    <h3>Avg Loss</h3>
                    <p className={`${styles.metricValue} ${styles.negative}`}>
                      ${data.performance.avgLoss}
                    </p>
                  </div>
                  <div className={styles.metricCard}>
                    <h3>Best Trade</h3>
                    <p className={`${styles.metricValue} ${styles.positive}`}>
                      ${data.performance.bestTrade}
                    </p>
                  </div>
                </div>

                <div className={styles.analyticsSections}>
                  <section className={styles.tradingStats}>
                    <h2>Trading Statistics</h2>
                    <div className={styles.statsGrid}>
                      <div className={styles.statItem}>
                        <span className={styles.statLabel}>Total Trades</span>
                        <span className={styles.statValue}>{data.tradingStats.totalTrades}</span>
                      </div>
                      <div className={styles.statItem}>
                        <span className={styles.statLabel}>Winning Trades</span>
                        <span className={`${styles.statValue} ${styles.positive}`}>
                          {data.tradingStats.winningTrades}
                        </span>
                      </div>
                      <div className={styles.statItem}>
                        <span className={styles.statLabel}>Losing Trades</span>
                        <span className={`${styles.statValue} ${styles.negative}`}>
                          {data.tradingStats.losingTrades}
                        </span>
                      </div>
                      <div className={styles.statItem}>
                        <span className={styles.statLabel}>Avg Hold Time</span>
                        <span className={styles.statValue}>{data.tradingStats.avgHoldTime}</span>
                      </div>
                      <div className={styles.statItem}>
                        <span className={styles.statLabel}>Total Volume</span>
                        <span className={styles.statValue}>
                          ${data.tradingStats.totalVolume.toLocaleString()}
                        </span>
                      </div>
                      <div className={styles.statItem}>
                        <span className={styles.statLabel}>Total Commission</span>
                        <span className={styles.statValue}>
                          ${data.tradingStats.totalCommission}
                        </span>
                      </div>
                    </div>
                  </section>

                  <section className={styles.symbolPerformance}>
                    <h2>Performance by Symbol</h2>
                    <table className={styles.symbolTable}>
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
                            <td className={sym.pnl >= 0 ? styles.positive : styles.negative}>
                              ${sym.pnl.toFixed(2)}
                            </td>
                            <td className={sym.winRate >= 50 ? styles.positive : styles.negative}>
                              {sym.winRate.toFixed(1)}%
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </section>

                  <section className={styles.pnlChart}>
                    <h2>Weekly P&L</h2>
                    <div className={styles.chartContainer}>
                      <div className={styles.simpleBarChart}>
                        {data.weeklyPnL.map(week => (
                          <div key={week.week} className={styles.barWrapper}>
                            <div
                              className={`${styles.bar} ${week.pnl >= 0 ? styles.positive : styles.negative}`}
                              style={{
                                height: `${Math.abs(week.pnl) / 30}px`,
                                marginTop: week.pnl < 0 ? '0' : 'auto',
                                marginBottom: week.pnl >= 0 ? '0' : 'auto',
                              }}
                            />
                            <span className={styles.barLabel}>{week.week}</span>
                            <span className={styles.barValue}>${week.pnl}</span>
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
