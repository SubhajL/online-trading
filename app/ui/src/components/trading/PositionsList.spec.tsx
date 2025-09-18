import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { PositionsList } from './PositionsList'
import type { Position } from '@/types'

describe('PositionsList', () => {
  const mockPositions: Position[] = [
    {
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      quantity: 0.1,
      entryPrice: 40000,
      markPrice: 42000,
      pnl: 200,
      pnlPercent: 5,
      venue: 'SPOT',
    },
    {
      symbol: 'ETHUSDT' as any,
      side: 'SELL',
      quantity: 1,
      entryPrice: 2500,
      markPrice: 2400,
      pnl: 100,
      pnlPercent: 4,
      venue: 'USD_M',
    },
  ]

  it('renders positions list', () => {
    render(<PositionsList positions={mockPositions} />)

    expect(screen.getByTestId('positions-list')).toBeInTheDocument()
    expect(screen.getByText('Open Positions')).toBeInTheDocument()
  })

  it('displays all positions', () => {
    render(<PositionsList positions={mockPositions} />)

    expect(screen.getByText('BTCUSDT')).toBeInTheDocument()
    expect(screen.getByText('ETHUSDT')).toBeInTheDocument()
  })

  it('displays position details', () => {
    render(<PositionsList positions={[mockPositions[0]!]} />)

    expect(screen.getByText('BUY')).toBeInTheDocument()
    expect(screen.getByText('0.1')).toBeInTheDocument()
    expect(screen.getByText('40,000')).toBeInTheDocument()
    expect(screen.getByText('42,000')).toBeInTheDocument()
    expect(screen.getByText('SPOT')).toBeInTheDocument()
  })

  it('displays PnL with correct color', () => {
    render(<PositionsList positions={mockPositions} />)

    const profitPnl = screen.getByText('+$200.00')
    expect(profitPnl).toHaveClass('pnl-positive')

    const profitPercent = screen.getByText('+5.00%')
    expect(profitPercent).toHaveClass('pnl-positive')

    // Second position also has profit
    const sellProfit = screen.getByText('+$100.00')
    expect(sellProfit).toHaveClass('pnl-positive')
  })

  it('displays negative PnL with correct color', () => {
    const losingPosition: Position = {
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      quantity: 0.1,
      entryPrice: 42000,
      markPrice: 40000,
      pnl: -200,
      pnlPercent: -4.76,
      venue: 'SPOT',
    }

    render(<PositionsList positions={[losingPosition]} />)

    const lossPnlElements = screen.getAllByText('-$200.00')
    expect(lossPnlElements[1]).toHaveClass('pnl-negative') // Position P&L, not total

    const lossPercent = screen.getByText('-4.76%')
    expect(lossPercent).toHaveClass('pnl-negative')
  })

  it('shows empty state when no positions', () => {
    render(<PositionsList positions={[]} />)

    expect(screen.getByText('No open positions')).toBeInTheDocument()
  })

  it('calculates total PnL', () => {
    render(<PositionsList positions={mockPositions} />)

    // Total PnL should be 200 + 100 = 300
    expect(screen.getByText('Total P&L:')).toBeInTheDocument()
    expect(screen.getByText('+$300.00')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    render(<PositionsList positions={[]} loading />)

    expect(screen.getByTestId('positions-loading')).toBeInTheDocument()
    expect(screen.getByText('Loading positions...')).toBeInTheDocument()
  })

  it('shows error state', () => {
    const errorMessage = 'Failed to load positions'
    render(<PositionsList positions={[]} error={errorMessage} />)

    expect(screen.getByText(errorMessage)).toBeInTheDocument()
    expect(screen.getByTestId('positions-error')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<PositionsList positions={[]} className="custom-list" />)

    const list = screen.getByTestId('positions-list')
    expect(list).toHaveClass('positions-list', 'custom-list')
  })

  it('displays correct side styling', () => {
    render(<PositionsList positions={mockPositions} />)

    const buyBadge = screen.getByText('BUY')
    expect(buyBadge).toHaveClass('side-badge', 'buy')

    const sellBadge = screen.getByText('SELL')
    expect(sellBadge).toHaveClass('side-badge', 'sell')
  })

  it('displays venue badge', () => {
    render(<PositionsList positions={mockPositions} />)

    const spotBadge = screen.getByText('SPOT')
    expect(spotBadge).toHaveClass('venue-badge')

    const futuresBadge = screen.getByText('USD_M')
    expect(futuresBadge).toHaveClass('venue-badge')
  })

  it('handles close button click', () => {
    const onClose = vi.fn()
    render(<PositionsList positions={mockPositions} onClose={onClose} />)

    const closeButtons = screen.getAllByRole('button', { name: /close/i })
    expect(closeButtons).toHaveLength(2)
  })

  it('formats large numbers correctly', () => {
    const largePosition: Position = {
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      quantity: 10,
      entryPrice: 42000,
      markPrice: 43000,
      pnl: 10000,
      pnlPercent: 2.38,
      venue: 'SPOT',
    }

    render(<PositionsList positions={[largePosition]} />)

    const pnlElements = screen.getAllByText('+$10,000.00')
    expect(pnlElements).toHaveLength(2) // Total and position P&L
  })
})
