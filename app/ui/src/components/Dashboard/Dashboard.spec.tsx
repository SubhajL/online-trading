import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { Dashboard } from './Dashboard'
import type { Position, Order, Balance } from '@/types'

// Mock child components
vi.mock('../trading/OrderForm', () => ({
  OrderForm: ({ onSubmit }: any) => (
    <div data-testid="order-form">Order Form Mock</div>
  ),
}))

vi.mock('../trading/PositionsList', () => ({
  PositionsList: ({ positions }: any) => (
    <div data-testid="positions-list">Positions: {positions.length}</div>
  ),
}))

vi.mock('../trading/OrderHistory', () => ({
  OrderHistory: ({ orders }: any) => (
    <div data-testid="order-history">Orders: {orders.length}</div>
  ),
}))

vi.mock('../trading/AccountBalance', () => ({
  AccountBalance: ({ balances }: any) => (
    <div data-testid="account-balance">Balances: {balances.length}</div>
  ),
}))

vi.mock('../charts/CandlestickChart', () => ({
  CandlestickChart: () => (
    <div data-testid="candlestick-chart">Candlestick Chart Mock</div>
  ),
}))

vi.mock('../charts/VolumeChart', () => ({
  VolumeChart: () => (
    <div data-testid="volume-chart">Volume Chart Mock</div>
  ),
}))

describe('Dashboard', () => {
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
  ]

  const mockOrders: Order[] = [
    {
      orderId: 'ORD001' as any,
      symbol: 'BTCUSDT' as any,
      side: 'BUY',
      type: 'MARKET',
      quantity: 0.1,
      status: 'FILLED',
      venue: 'SPOT',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      executedQuantity: 0.1,
      avgPrice: 40000,
    },
  ]

  const mockBalances: Balance[] = [
    {
      asset: 'USDT',
      free: 10000,
      locked: 500,
      venue: 'SPOT',
    },
  ]

  it('renders dashboard with all components', () => {
    const onSubmitOrder = vi.fn()
    render(
      <Dashboard
        positions={mockPositions}
        orders={mockOrders}
        balances={mockBalances}
        onSubmitOrder={onSubmitOrder}
      />
    )

    expect(screen.getByTestId('dashboard')).toBeInTheDocument()
    expect(screen.getByTestId('order-form')).toBeInTheDocument()
    expect(screen.getByTestId('positions-list')).toBeInTheDocument()
    expect(screen.getByTestId('order-history')).toBeInTheDocument()
    expect(screen.getByTestId('account-balance')).toBeInTheDocument()
    expect(screen.getByTestId('candlestick-chart')).toBeInTheDocument()
  })

  it('displays key metrics cards', () => {
    const onSubmitOrder = vi.fn()
    render(
      <Dashboard
        positions={mockPositions}
        orders={mockOrders}
        balances={mockBalances}
        onSubmitOrder={onSubmitOrder}
      />
    )

    // Check for key metrics
    expect(screen.getByText('Total P&L')).toBeInTheDocument()
    expect(screen.getByText('Daily P&L')).toBeInTheDocument()
    expect(screen.getByText('Open Positions')).toBeInTheDocument()
    expect(screen.getByText('Total Balance')).toBeInTheDocument()
  })

  it('calculates total P&L from positions', () => {
    const positions: Position[] = [
      { ...mockPositions[0]!, pnl: 200 },
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

    const onSubmitOrder = vi.fn()
    render(
      <Dashboard
        positions={positions}
        orders={[]}
        balances={mockBalances}
        onSubmitOrder={onSubmitOrder}
      />
    )

    // Total P&L should be 300 (appears in multiple places)
    const pnlValues = screen.getAllByText('$300.00')
    expect(pnlValues.length).toBeGreaterThan(0)
  })

  it('calculates daily P&L from positions and trades', () => {
    const todayOrders: Order[] = [
      {
        orderId: 'BUY1' as any,
        symbol: 'BTCUSDT' as any,
        side: 'BUY',
        type: 'MARKET',
        quantity: 0.1,
        status: 'FILLED',
        venue: 'SPOT',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        executedQuantity: 0.1,
        avgPrice: 40000,
      },
      {
        orderId: 'SELL1' as any,
        symbol: 'BTCUSDT' as any,
        side: 'SELL',
        type: 'MARKET',
        quantity: 0.1,
        status: 'FILLED',
        venue: 'SPOT',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        executedQuantity: 0.1,
        avgPrice: 41000,
      },
    ]

    render(
      <Dashboard
        positions={mockPositions}
        orders={todayOrders}
        balances={mockBalances}
      />
    )

    // Position P&L: 200, Trade P&L: (41000-40000)*0.1 = 100, Total: 300
    expect(screen.getByTestId('daily-pnl-value')).toHaveTextContent('$300.00')
  })

  it('displays open positions count', () => {
    const positions = [
      mockPositions[0]!,
      { ...mockPositions[0]!, symbol: 'ETHUSDT' as any },
      { ...mockPositions[0]!, symbol: 'BNBUSDT' as any },
    ]

    render(
      <Dashboard
        positions={positions}
        orders={[]}
        balances={mockBalances}
      />
    )

    expect(screen.getByTestId('positions-count')).toHaveTextContent('3')
  })

  it('calculates total balance from all venues', () => {
    const balances: Balance[] = [
      { asset: 'USDT', free: 5000, locked: 500, venue: 'SPOT' },
      { asset: 'USDT', free: 3000, locked: 200, venue: 'USD_M' },
      { asset: 'BTC', free: 0.1, locked: 0, venue: 'SPOT', usdValue: 4200 },
    ]

    const onSubmitOrder = vi.fn()
    render(
      <Dashboard
        positions={[]}
        orders={[]}
        balances={balances}
        onSubmitOrder={onSubmitOrder}
      />
    )

    // Total: 5500 + 3200 + 4200 = 12900
    expect(screen.getByTestId('total-balance')).toHaveTextContent('$12,900.00')
  })

  it('shows loading state', () => {
    const onSubmitOrder = vi.fn()
    render(
      <Dashboard
        positions={[]}
        orders={[]}
        balances={[]}
        loading
        onSubmitOrder={onSubmitOrder}
      />
    )

    // There are 6 metrics cards showing loading state
    expect(screen.getAllByTestId('metrics-loading')).toHaveLength(6)
  })

  it('shows error state', () => {
    render(
      <Dashboard
        positions={[]}
        orders={[]}
        balances={[]}
        error="Failed to load data"
      />
    )

    expect(screen.getByText('Failed to load data')).toBeInTheDocument()
  })

  it('handles order submission', () => {
    const onSubmitOrder = vi.fn()
    render(
      <Dashboard
        positions={mockPositions}
        orders={mockOrders}
        balances={mockBalances}
        onSubmitOrder={onSubmitOrder}
      />
    )

    // Order form should be present
    expect(screen.getByTestId('order-form')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(
      <Dashboard
        positions={[]}
        orders={[]}
        balances={[]}
        className="custom-dashboard"
      />
    )

    const dashboard = screen.getByTestId('dashboard')
    expect(dashboard).toHaveClass('dashboard', 'custom-dashboard')
  })

  it('displays win rate metric', () => {
    const orders: Order[] = [
      { ...mockOrders[0]!, status: 'FILLED' as any },
      { ...mockOrders[0]!, orderId: 'ORD002' as any, status: 'FILLED' as any },
      { ...mockOrders[0]!, orderId: 'ORD003' as any, status: 'CANCELED' as any },
    ]

    render(
      <Dashboard
        positions={[]}
        orders={orders}
        balances={mockBalances}
      />
    )

    // Win rate: 2 filled / 3 total = 66.67%
    expect(screen.getByText('Win Rate')).toBeInTheDocument()
    expect(screen.getByText('66.67%')).toBeInTheDocument()
  })

  it('displays today trades count', () => {
    const todayOrders = Array(5).fill(null).map((_, i) => ({
      ...mockOrders[0]!,
      orderId: `ORD${i}` as any,
      createdAt: new Date().toISOString(),
    }))

    render(
      <Dashboard
        positions={[]}
        orders={todayOrders}
        balances={mockBalances}
      />
    )

    expect(screen.getByText("Today's Trades")).toBeInTheDocument()
    expect(screen.getByTestId('trades-count')).toHaveTextContent('5')
  })

  it('integrates with auto trading toggle', () => {
    const onSubmitOrder = vi.fn()
    const onToggleAutoTrading = vi.fn()
    render(
      <Dashboard
        positions={mockPositions}
        orders={mockOrders}
        balances={mockBalances}
        autoTradingEnabled={true}
        onSubmitOrder={onSubmitOrder}
        onToggleAutoTrading={onToggleAutoTrading}
      />
    )

    expect(screen.getByText('Auto Trading')).toBeInTheDocument()
  })
})