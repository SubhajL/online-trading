import { render, screen, fireEvent } from '@testing-library/react'
import { vi, describe, it, expect } from 'vitest'
import { LogoutModal } from './LogoutModal'
import type { Position, Symbol } from '@/types'

const mockPositions: Position[] = [
  {
    symbol: 'BTCUSDT' as Symbol,
    side: 'LONG',
    quantity: 0.1,
    entryPrice: 40000,
    markPrice: 42000,
    pnl: 200,
    pnlPercent: 5,
    venue: 'SPOT',
  },
  {
    symbol: 'ETHUSDT' as Symbol,
    side: 'SHORT',
    quantity: 2,
    entryPrice: 2500,
    markPrice: 2400,
    pnl: 200,
    pnlPercent: 4,
    venue: 'USD_M',
  },
]

describe('LogoutModal', () => {
  it('displays open positions with symbol, size, and P&L', () => {
    render(<LogoutModal positions={mockPositions} onCancel={vi.fn()} onConfirm={vi.fn()} />)

    expect(screen.getByText('Open Positions Warning')).toBeInTheDocument()
    expect(screen.getByText('BTCUSDT')).toBeInTheDocument()
    expect(screen.getByText('ETHUSDT')).toBeInTheDocument()
    expect(screen.getByText('0.1')).toBeInTheDocument()
  })

  it('calls onCancel when Cancel button is clicked', () => {
    const onCancel = vi.fn()
    render(<LogoutModal positions={mockPositions} onCancel={onCancel} onConfirm={vi.fn()} />)

    fireEvent.click(screen.getByTestId('logout-cancel'))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('calls onConfirm when Confirm Logout button is clicked', () => {
    const onConfirm = vi.fn()
    render(<LogoutModal positions={mockPositions} onCancel={vi.fn()} onConfirm={onConfirm} />)

    fireEvent.click(screen.getByTestId('logout-confirm'))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('shows warning message about open positions', () => {
    render(<LogoutModal positions={mockPositions} onCancel={vi.fn()} onConfirm={vi.fn()} />)

    expect(screen.getByText(/open positions that will remain active/i)).toBeInTheDocument()
  })

  it('displays loading state when provided', () => {
    render(<LogoutModal positions={[]} loading onCancel={vi.fn()} onConfirm={vi.fn()} />)

    expect(screen.getByText(/loading positions/i)).toBeInTheDocument()
  })
})
