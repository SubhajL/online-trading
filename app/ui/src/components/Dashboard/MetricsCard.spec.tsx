import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { MetricsCard } from './MetricsCard'

describe('MetricsCard', () => {
  it('renders title and value', () => {
    render(<MetricsCard title="Total P&L" value="$1,234.56" />)

    expect(screen.getByText('Total P&L')).toBeInTheDocument()
    expect(screen.getByText('$1,234.56')).toBeInTheDocument()
  })

  it('displays positive change with green color', () => {
    render(
      <MetricsCard
        title="Daily P&L"
        value="$500.00"
        change="+5.25%"
      />
    )

    const changeElement = screen.getByText('+5.25%')
    expect(changeElement).toBeInTheDocument()
    expect(changeElement).toHaveClass('change-positive')
  })

  it('displays negative change with red color', () => {
    render(
      <MetricsCard
        title="Daily P&L"
        value="-$200.00"
        change="-2.50%"
      />
    )

    const changeElement = screen.getByText('-2.50%')
    expect(changeElement).toBeInTheDocument()
    expect(changeElement).toHaveClass('change-negative')
  })

  it('displays neutral change', () => {
    render(
      <MetricsCard
        title="Volume"
        value="1,000"
        change="0.00%"
      />
    )

    const changeElement = screen.getByText('0.00%')
    expect(changeElement).toBeInTheDocument()
    expect(changeElement).toHaveClass('change-neutral')
  })

  it('renders without change', () => {
    render(<MetricsCard title="Open Positions" value="5" />)

    expect(screen.getByText('Open Positions')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
    expect(screen.queryByText('%')).not.toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(
      <MetricsCard
        title="Test"
        value="100"
        className="custom-metrics"
      />
    )

    const card = screen.getByTestId('metrics-card')
    expect(card).toHaveClass('metrics-card', 'custom-metrics')
  })

  it('renders subtitle when provided', () => {
    render(
      <MetricsCard
        title="Account Balance"
        value="$10,000"
        subtitle="USDT"
      />
    )

    expect(screen.getByText('USDT')).toBeInTheDocument()
    expect(screen.getByText('USDT')).toHaveClass('metrics-subtitle')
  })

  it('displays loading state', () => {
    render(
      <MetricsCard
        title="Loading Metric"
        value=""
        loading
      />
    )

    expect(screen.getByTestId('metrics-loading')).toBeInTheDocument()
    expect(screen.queryByText('Loading Metric')).toBeInTheDocument()
  })

  it('displays error state', () => {
    render(
      <MetricsCard
        title="Error Metric"
        value=""
        error="Failed to load data"
      />
    )

    expect(screen.getByText('Failed to load data')).toBeInTheDocument()
    expect(screen.getByTestId('metrics-error')).toBeInTheDocument()
  })

  it('renders with icon', () => {
    render(
      <MetricsCard
        title="Profit"
        value="$1,000"
        icon="📈"
      />
    )

    expect(screen.getByText('📈')).toBeInTheDocument()
    expect(screen.getByText('📈')).toHaveClass('metrics-icon')
  })

  it('handles numeric value formatting', () => {
    render(
      <MetricsCard
        title="Win Rate"
        value={65.5}
        format="percentage"
      />
    )

    expect(screen.getByText('65.50%')).toBeInTheDocument()
  })

  it('handles currency formatting', () => {
    render(
      <MetricsCard
        title="Balance"
        value={1234.567}
        format="currency"
      />
    )

    expect(screen.getByText('$1,234.57')).toBeInTheDocument()
  })

  it('handles number formatting', () => {
    render(
      <MetricsCard
        title="Trades"
        value={1234567}
        format="number"
      />
    )

    expect(screen.getByText('1,234,567')).toBeInTheDocument()
  })

  it('displays trend indicator', () => {
    render(
      <MetricsCard
        title="Volume"
        value="100"
        trend="up"
      />
    )

    const trendElement = screen.getByTestId('trend-indicator')
    expect(trendElement).toBeInTheDocument()
    expect(trendElement).toHaveClass('trend-up')
  })

  it('combines multiple features', () => {
    render(
      <MetricsCard
        title="Total Profit"
        subtitle="Today"
        value={5250.75}
        change="+12.50%"
        icon="💰"
        format="currency"
        trend="up"
      />
    )

    expect(screen.getByText('Total Profit')).toBeInTheDocument()
    expect(screen.getByText('Today')).toBeInTheDocument()
    expect(screen.getByText('$5,250.75')).toBeInTheDocument()
    expect(screen.getByText('+12.50%')).toBeInTheDocument()
    expect(screen.getByText('💰')).toBeInTheDocument()
    expect(screen.getByTestId('trend-indicator')).toHaveClass('trend-up')
  })
})