import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TradingKPIs } from './TradingKPIs'
import type { TradingKPIs as TradingKPIsType } from '@/types/dashboard'

const createMockKPIs = (overrides: Partial<TradingKPIsType> = {}): TradingKPIsType => ({
  winRate: 62.5,
  profitFactor: 1.85,
  sharpeRatio: 1.24,
  maxDrawdown: 4.2,
  tradeCount: 45,
  tradingDays: 30,
  totalPnL: 2500.75,
  dailyPnL: 150.25,
  ...overrides,
})

describe('TradingKPIs', () => {
  describe('rendering KPIs with sufficient data', () => {
    it('displays win rate with 1 decimal percentage', () => {
      render(<TradingKPIs kpis={createMockKPIs()} />)

      expect(screen.getByText('Win Rate')).toBeInTheDocument()
      expect(screen.getByText('62.5%')).toBeInTheDocument()
    })

    it('displays profit factor with 2 decimal places', () => {
      render(<TradingKPIs kpis={createMockKPIs()} />)

      expect(screen.getByText('Profit Factor')).toBeInTheDocument()
      expect(screen.getByText('1.85')).toBeInTheDocument()
    })

    it('displays sharpe ratio with 2 decimal places', () => {
      render(<TradingKPIs kpis={createMockKPIs()} />)

      expect(screen.getByText('Sharpe Ratio')).toBeInTheDocument()
      expect(screen.getByText('1.24')).toBeInTheDocument()
    })

    it('displays max drawdown with 1 decimal percentage', () => {
      render(<TradingKPIs kpis={createMockKPIs()} />)

      expect(screen.getByText('Max Drawdown')).toBeInTheDocument()
      expect(screen.getByText('4.2%')).toBeInTheDocument()
    })

    it('displays trade count and trading days in header', () => {
      render(<TradingKPIs kpis={createMockKPIs()} />)

      expect(screen.getByTestId('trade-count')).toHaveTextContent('45 trades · 30 days')
    })
  })

  describe('insufficient data (< 10 trades)', () => {
    it('shows dash for all KPIs when fewer than 10 trades', () => {
      render(<TradingKPIs kpis={createMockKPIs({ tradeCount: 5 })} />)

      expect(screen.getByTestId('kpi-value-winRate')).toHaveTextContent('—')
      expect(screen.getByTestId('kpi-value-profitFactor')).toHaveTextContent('—')
      expect(screen.getByTestId('kpi-value-sharpeRatio')).toHaveTextContent('—')
      expect(screen.getByTestId('kpi-value-maxDrawdown')).toHaveTextContent('—')
    })

    it('shows insufficient data message for low trade count', () => {
      render(<TradingKPIs kpis={createMockKPIs({ tradeCount: 5 })} />)

      expect(screen.getAllByText('Requires 10 trades (5 completed)').length).toBeGreaterThan(0)
    })

    it('shows no color class on value when data is insufficient', () => {
      render(<TradingKPIs kpis={createMockKPIs({ tradeCount: 5 })} />)

      const winRateValue = screen.getByTestId('kpi-value-winRate')
      expect(winRateValue).not.toHaveClass('text-success')
      expect(winRateValue).not.toHaveClass('text-warning')
      expect(winRateValue).not.toHaveClass('text-danger')
    })
  })

  describe('insufficient data for Sharpe (< 7 trading days)', () => {
    it('shows dash for Sharpe when fewer than 7 trading days', () => {
      render(<TradingKPIs kpis={createMockKPIs({ tradeCount: 15, tradingDays: 3 })} />)

      // Other KPIs should show values
      expect(screen.getByTestId('kpi-value-winRate')).toHaveTextContent('62.5%')
      expect(screen.getByTestId('kpi-value-profitFactor')).toHaveTextContent('1.85')

      // Sharpe should show dash
      expect(screen.getByTestId('kpi-value-sharpeRatio')).toHaveTextContent('—')
    })

    it('shows trading days message for Sharpe insufficient data', () => {
      render(<TradingKPIs kpis={createMockKPIs({ tradeCount: 15, tradingDays: 3 })} />)

      expect(screen.getByText('Requires 7 trading days (3 days)')).toBeInTheDocument()
    })
  })

  describe('null values for KPIs', () => {
    it('shows dash for null win rate', () => {
      render(<TradingKPIs kpis={createMockKPIs({ winRate: null })} />)

      expect(screen.getByTestId('kpi-value-winRate')).toHaveTextContent('—')
    })

    it('shows dash for null profit factor', () => {
      render(<TradingKPIs kpis={createMockKPIs({ profitFactor: null })} />)

      expect(screen.getByTestId('kpi-value-profitFactor')).toHaveTextContent('—')
    })

    it('shows dash for null sharpe ratio', () => {
      render(<TradingKPIs kpis={createMockKPIs({ sharpeRatio: null })} />)

      expect(screen.getByTestId('kpi-value-sharpeRatio')).toHaveTextContent('—')
    })

    it('shows dash for null max drawdown', () => {
      render(<TradingKPIs kpis={createMockKPIs({ maxDrawdown: null })} />)

      expect(screen.getByTestId('kpi-value-maxDrawdown')).toHaveTextContent('—')
    })
  })

  describe('KPI status styling (thresholds)', () => {
    describe('win rate thresholds', () => {
      it('applies good status for win rate >= 55%', () => {
        render(<TradingKPIs kpis={createMockKPIs({ winRate: 60 })} />)

        const value = screen.getByTestId('kpi-value-winRate')
        expect(value).toHaveClass('text-success')
      })

      it('applies warning status for win rate 45-55%', () => {
        render(<TradingKPIs kpis={createMockKPIs({ winRate: 50 })} />)

        const value = screen.getByTestId('kpi-value-winRate')
        expect(value).toHaveClass('text-warning')
      })

      it('applies danger status for win rate < 45%', () => {
        render(<TradingKPIs kpis={createMockKPIs({ winRate: 40 })} />)

        const value = screen.getByTestId('kpi-value-winRate')
        expect(value).toHaveClass('text-danger')
      })
    })

    describe('profit factor thresholds', () => {
      it('applies good status for profit factor >= 1.5', () => {
        render(<TradingKPIs kpis={createMockKPIs({ profitFactor: 2.0 })} />)

        const value = screen.getByTestId('kpi-value-profitFactor')
        expect(value).toHaveClass('text-success')
      })

      it('applies warning status for profit factor 1.0-1.5', () => {
        render(<TradingKPIs kpis={createMockKPIs({ profitFactor: 1.2 })} />)

        const value = screen.getByTestId('kpi-value-profitFactor')
        expect(value).toHaveClass('text-warning')
      })

      it('applies danger status for profit factor < 1.0', () => {
        render(<TradingKPIs kpis={createMockKPIs({ profitFactor: 0.8 })} />)

        const value = screen.getByTestId('kpi-value-profitFactor')
        expect(value).toHaveClass('text-danger')
      })
    })

    describe('sharpe ratio thresholds', () => {
      it('applies good status for sharpe >= 1.0', () => {
        render(<TradingKPIs kpis={createMockKPIs({ sharpeRatio: 1.5 })} />)

        const value = screen.getByTestId('kpi-value-sharpeRatio')
        expect(value).toHaveClass('text-success')
      })

      it('applies warning status for sharpe 0.5-1.0', () => {
        render(<TradingKPIs kpis={createMockKPIs({ sharpeRatio: 0.7 })} />)

        const value = screen.getByTestId('kpi-value-sharpeRatio')
        expect(value).toHaveClass('text-warning')
      })

      it('applies danger status for sharpe < 0.5', () => {
        render(<TradingKPIs kpis={createMockKPIs({ sharpeRatio: 0.3 })} />)

        const value = screen.getByTestId('kpi-value-sharpeRatio')
        expect(value).toHaveClass('text-danger')
      })
    })

    describe('max drawdown thresholds (inverted)', () => {
      it('applies good status for drawdown <= 5%', () => {
        render(<TradingKPIs kpis={createMockKPIs({ maxDrawdown: 3 })} />)

        const value = screen.getByTestId('kpi-value-maxDrawdown')
        expect(value).toHaveClass('text-success')
      })

      it('applies warning status for drawdown 5-10%', () => {
        render(<TradingKPIs kpis={createMockKPIs({ maxDrawdown: 7 })} />)

        const value = screen.getByTestId('kpi-value-maxDrawdown')
        expect(value).toHaveClass('text-warning')
      })

      it('applies danger status for drawdown > 10%', () => {
        render(<TradingKPIs kpis={createMockKPIs({ maxDrawdown: 15 })} />)

        const value = screen.getByTestId('kpi-value-maxDrawdown')
        expect(value).toHaveClass('text-danger')
      })
    })
  })

  describe('loading state', () => {
    it('displays loading skeleton when loading is true', () => {
      render(<TradingKPIs kpis={null} loading />)

      expect(screen.getByTestId('trading-kpis-loading')).toBeInTheDocument()
    })

    it('shows 4 skeleton groups', () => {
      render(<TradingKPIs kpis={null} loading />)

      const container = screen.getByTestId('trading-kpis-loading')
      const skeletonGroups = container.querySelectorAll('.space-y-2')
      expect(skeletonGroups.length).toBe(4)
    })
  })

  describe('error state', () => {
    it('displays error message when error is provided', () => {
      render(<TradingKPIs kpis={null} error="Failed to load KPIs" />)

      expect(screen.getByTestId('trading-kpis-error')).toBeInTheDocument()
      expect(screen.getByText('Failed to load KPIs')).toBeInTheDocument()
    })

    it('error has alert role', () => {
      render(<TradingKPIs kpis={null} error="Failed to load KPIs" />)

      expect(screen.getByRole('alert')).toHaveTextContent('Failed to load KPIs')
    })
  })

  describe('empty state', () => {
    it('displays empty message when kpis is null', () => {
      render(<TradingKPIs kpis={null} />)

      expect(screen.getByTestId('trading-kpis-empty')).toBeInTheDocument()
      expect(screen.getByText('No trading data available')).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has accessible heading', () => {
      render(<TradingKPIs kpis={createMockKPIs()} />)

      expect(screen.getByText(/trading performance/i)).toBeInTheDocument()
    })

    it('each KPI card is identifiable by test id', () => {
      render(<TradingKPIs kpis={createMockKPIs()} />)

      expect(screen.getByTestId('kpi-winRate')).toBeInTheDocument()
      expect(screen.getByTestId('kpi-profitFactor')).toBeInTheDocument()
      expect(screen.getByTestId('kpi-sharpeRatio')).toBeInTheDocument()
      expect(screen.getByTestId('kpi-maxDrawdown')).toBeInTheDocument()
    })

    it('skeleton loading state renders', () => {
      render(<TradingKPIs kpis={null} loading />)

      expect(screen.getByTestId('trading-kpis-loading')).toBeInTheDocument()
    })
  })

  describe('edge cases', () => {
    it('handles zero win rate', () => {
      render(<TradingKPIs kpis={createMockKPIs({ winRate: 0 })} />)

      expect(screen.getByTestId('kpi-value-winRate')).toHaveTextContent('0.0%')
    })

    it('handles zero max drawdown', () => {
      render(<TradingKPIs kpis={createMockKPIs({ maxDrawdown: 0 })} />)

      expect(screen.getByTestId('kpi-value-maxDrawdown')).toHaveTextContent('0.0%')
    })

    it('handles exactly 10 trades (boundary)', () => {
      render(<TradingKPIs kpis={createMockKPIs({ tradeCount: 10 })} />)

      // Should show values since 10 >= MIN_TRADES_FOR_DISPLAY
      expect(screen.getByTestId('kpi-value-winRate')).toHaveTextContent('62.5%')
    })

    it('handles exactly 9 trades (below boundary)', () => {
      render(<TradingKPIs kpis={createMockKPIs({ tradeCount: 9 })} />)

      // Should show dash since 9 < MIN_TRADES_FOR_DISPLAY
      expect(screen.getByTestId('kpi-value-winRate')).toHaveTextContent('—')
    })

    it('handles exactly 7 trading days for Sharpe (boundary)', () => {
      render(<TradingKPIs kpis={createMockKPIs({ tradeCount: 15, tradingDays: 7 })} />)

      // Should show Sharpe since 7 >= MIN_DAYS_FOR_SHARPE
      expect(screen.getByTestId('kpi-value-sharpeRatio')).toHaveTextContent('1.24')
    })

    it('handles negative sharpe ratio', () => {
      render(<TradingKPIs kpis={createMockKPIs({ sharpeRatio: -0.5 })} />)

      expect(screen.getByTestId('kpi-value-sharpeRatio')).toHaveTextContent('-0.50')
    })

    it('handles Infinity profit factor', () => {
      render(<TradingKPIs kpis={createMockKPIs({ profitFactor: Infinity })} />)

      expect(screen.getByTestId('kpi-value-profitFactor')).toHaveTextContent('∞')
    })

    it('handles -Infinity profit factor', () => {
      render(<TradingKPIs kpis={createMockKPIs({ profitFactor: -Infinity })} />)

      expect(screen.getByTestId('kpi-value-profitFactor')).toHaveTextContent('-∞')
    })

    it('handles NaN profit factor', () => {
      render(<TradingKPIs kpis={createMockKPIs({ profitFactor: NaN })} />)

      expect(screen.getByTestId('kpi-value-profitFactor')).toHaveTextContent('—')
    })

    it('has aria-label for unavailable values', () => {
      render(<TradingKPIs kpis={createMockKPIs({ tradeCount: 5 })} />)

      const winRateValue = screen.getByTestId('kpi-value-winRate')
      expect(winRateValue).toHaveAttribute('aria-label', 'Not available')
    })
  })
})
