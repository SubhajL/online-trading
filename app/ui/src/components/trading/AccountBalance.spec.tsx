import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { AccountBalance } from './AccountBalance'
import type { Balance } from '@/types'

describe('AccountBalance', () => {
  const mockBalances: Balance[] = [
    {
      asset: 'USDT',
      free: 10000,
      locked: 500,
      venue: 'SPOT',
    },
    {
      asset: 'BTC',
      free: 0.5,
      locked: 0.1,
      venue: 'SPOT',
    },
    {
      asset: 'USDT',
      free: 5000,
      locked: 1000,
      venue: 'USD_M',
    },
  ]

  it('renders account balance', () => {
    render(<AccountBalance balances={mockBalances} />)

    expect(screen.getByTestId('account-balance')).toBeInTheDocument()
    expect(screen.getByText('Account Balance')).toBeInTheDocument()
  })

  it('displays all balances', () => {
    render(<AccountBalance balances={mockBalances} />)

    // Check assets are displayed
    expect(screen.getAllByText('USDT')).toHaveLength(2) // SPOT and USD_M
    expect(screen.getByText('BTC')).toBeInTheDocument()
  })

  it('displays balance details', () => {
    render(<AccountBalance balances={[mockBalances[0]!]} />)

    expect(screen.getByText('10,000')).toBeInTheDocument() // free
    expect(screen.getByText('500')).toBeInTheDocument() // locked
    expect(screen.getByText('10,500')).toBeInTheDocument() // total
    expect(screen.getByText('SPOT')).toBeInTheDocument()
  })

  it('shows empty state when no balances', () => {
    render(<AccountBalance balances={[]} />)

    expect(screen.getByText('No balances available')).toBeInTheDocument()
  })

  it('calculates total correctly', () => {
    const balance: Balance = {
      asset: 'USDT',
      free: 1000.5,
      locked: 500.25,
      venue: 'SPOT',
    }
    render(<AccountBalance balances={[balance]} />)

    expect(screen.getByText('1,000.5')).toBeInTheDocument() // free
    expect(screen.getByText('500.25')).toBeInTheDocument() // locked
    expect(screen.getByText('1,500.75')).toBeInTheDocument() // total
  })

  it('shows loading state', () => {
    render(<AccountBalance balances={[]} loading />)

    expect(screen.getByTestId('balance-loading')).toBeInTheDocument()
    expect(screen.getByText('Loading balances...')).toBeInTheDocument()
  })

  it('shows error state', () => {
    const errorMessage = 'Failed to load balances'
    render(<AccountBalance balances={[]} error={errorMessage} />)

    expect(screen.getByText(errorMessage)).toBeInTheDocument()
    expect(screen.getByTestId('balance-error')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<AccountBalance balances={[]} className="custom-balance" />)

    const container = screen.getByTestId('account-balance')
    expect(container).toHaveClass('account-balance', 'custom-balance')
  })

  it('formats decimal numbers correctly', () => {
    const btcBalance: Balance = {
      asset: 'BTC',
      free: 0.12345678,
      locked: 0.00123456,
      venue: 'SPOT',
    }
    render(<AccountBalance balances={[btcBalance]} />)

    expect(screen.getByText('0.12345678')).toBeInTheDocument()
    expect(screen.getByText('0.00123456')).toBeInTheDocument()
    expect(screen.getByText('0.12469134')).toBeInTheDocument() // total
  })

  it('groups by venue', () => {
    render(<AccountBalance balances={mockBalances} />)

    // Check venue headers
    const venueHeaders = screen.getAllByText(/SPOT|USD_M/)
    expect(venueHeaders.length).toBeGreaterThan(0)
  })

  it('shows locked indicator', () => {
    render(<AccountBalance balances={[mockBalances[0]!]} />)

    // Should show locked amount with visual indicator
    const lockedElement = screen.getByText('500')
    expect(lockedElement.closest('.locked-amount')).toBeInTheDocument()
  })

  it('handles zero balances', () => {
    const zeroBalance: Balance = {
      asset: 'ETH',
      free: 0,
      locked: 0,
      venue: 'SPOT',
    }
    render(<AccountBalance balances={[zeroBalance]} />)

    expect(screen.getAllByText('0')).toHaveLength(3) // free, locked, total
  })

  it('displays USD equivalent when provided', () => {
    const balanceWithUsd: Balance = {
      asset: 'BTC',
      free: 1,
      locked: 0,
      venue: 'SPOT',
      usdValue: 42000,
    }
    render(<AccountBalance balances={[balanceWithUsd]} />)

    // USD value appears in both the row and total
    const usdValues = screen.getAllByText('$42,000.00')
    expect(usdValues).toHaveLength(2)
  })

  it('shows total USD value', () => {
    const balancesWithUsd: Balance[] = [
      {
        asset: 'BTC',
        free: 1,
        locked: 0,
        venue: 'SPOT',
        usdValue: 42000,
      },
      {
        asset: 'USDT',
        free: 1000,
        locked: 0,
        venue: 'SPOT',
        usdValue: 1000,
      },
    ]
    render(<AccountBalance balances={balancesWithUsd} />)

    expect(screen.getByText('Total USD Value:')).toBeInTheDocument()
    expect(screen.getByText('$43,000.00')).toBeInTheDocument()
  })
})
