import { describe, expect, test, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import AnalyticsPage from './page'

vi.mock('@/hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    data: {
      performance: {
        totalReturn: 0,
        winRate: 0,
        profitFactor: 0,
        sharpeRatio: 0,
        maxDrawdown: 0,
        avgWin: 0,
        avgLoss: 0,
        bestTrade: 0,
      },
      tradingStats: {
        totalTrades: 0,
        winningTrades: 0,
        losingTrades: 0,
        avgHoldTime: '0h',
        totalVolume: 0,
        totalCommission: 0,
      },
      symbols: [],
      weeklyPnL: [],
    },
    loading: false,
    error: null,
  }),
}))

describe('AnalyticsPage', () => {
  test('renders with CSS module classes', () => {
    render(<AnalyticsPage />)
    expect(screen.getByText('Trading Analytics')).toBeInTheDocument()
  })

  test('applies appLayout CSS module class to root div', () => {
    const { container } = render(<AnalyticsPage />)
    const rootDiv = container.firstChild as HTMLElement
    expect(rootDiv.className).toContain('appLayout')
  })

  test('renders timeframe selector buttons', () => {
    render(<AnalyticsPage />)
    expect(screen.getByText('24h')).toBeInTheDocument()
    expect(screen.getByText('7d')).toBeInTheDocument()
    expect(screen.getByText('30d')).toBeInTheDocument()
  })

  test('renders performance metrics', () => {
    render(<AnalyticsPage />)
    expect(screen.getAllByText('Total Return')[0]).toBeInTheDocument()
    expect(screen.getAllByText('Win Rate')[0]).toBeInTheDocument()
    expect(screen.getAllByText('Sharpe Ratio')[0]).toBeInTheDocument()
  })
})
