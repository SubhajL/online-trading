import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import userEvent from '@testing-library/user-event'
import { CandlestickChart } from './CandlestickChart'
import type { Candle, Indicator } from '@/types'

// Mock the useChart hook
const mockUpdateCandles = vi.fn()
const mockAddIndicator = vi.fn()
const mockFitContent = vi.fn()

vi.mock('@/hooks/useChart', () => ({
  useChart: () => ({
    chart: {},
    candlestickSeries: {},
    updateCandles: mockUpdateCandles,
    addIndicator: mockAddIndicator,
    fitContent: mockFitContent,
  }),
}))

describe('CandlestickChart', () => {
  const mockCandles: Candle[] = [
    {
      time: 1704067200,
      open: 42000,
      high: 42500,
      low: 41800,
      close: 42300,
      volume: 100,
    },
    {
      time: 1704067260,
      open: 42300,
      high: 42600,
      low: 42200,
      close: 42450,
      volume: 120,
    },
  ]

  const mockIndicators: Indicator[] = [
    {
      type: 'EMA',
      period: 20,
      data: [
        { time: 1704067200, value: 42100 },
        { time: 1704067260, value: 42200 },
      ],
      color: '#2962ff',
    },
    {
      type: 'RSI',
      period: 14,
      data: [
        { time: 1704067200, value: 55 },
        { time: 1704067260, value: 58 },
      ],
      color: '#ff6b6b',
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders chart container', () => {
    render(<CandlestickChart symbol="BTCUSDT" candles={[]} />)

    const container = screen.getByTestId('candlestick-chart')
    expect(container).toBeInTheDocument()
    expect(container).toHaveClass('candlestick-chart')
  })

  it('displays symbol', () => {
    render(<CandlestickChart symbol="BTCUSDT" candles={[]} />)

    expect(screen.getByText('BTCUSDT')).toBeInTheDocument()
  })

  it('updates candles when data changes', async () => {
    const { rerender } = render(<CandlestickChart symbol="BTCUSDT" candles={[]} />)

    expect(mockUpdateCandles).not.toHaveBeenCalled()

    rerender(<CandlestickChart symbol="BTCUSDT" candles={mockCandles} />)

    await waitFor(() => {
      expect(mockUpdateCandles).toHaveBeenCalledWith(mockCandles)
    })
  })

  it('renders indicators', async () => {
    render(<CandlestickChart symbol="BTCUSDT" candles={mockCandles} indicators={mockIndicators} />)

    await waitFor(() => {
      expect(mockAddIndicator).toHaveBeenCalledTimes(2)
      expect(mockAddIndicator).toHaveBeenCalledWith(
        'EMA',
        mockIndicators[0]!.data,
        expect.objectContaining({ color: '#2962ff' }),
      )
      expect(mockAddIndicator).toHaveBeenCalledWith(
        'RSI',
        mockIndicators[1]!.data,
        expect.objectContaining({ color: '#ff6b6b' }),
      )
    })
  })

  it('shows loading state', () => {
    render(<CandlestickChart symbol="BTCUSDT" candles={[]} loading />)

    expect(screen.getByText('Loading chart data...')).toBeInTheDocument()
    expect(screen.getByTestId('chart-loading')).toBeInTheDocument()
  })

  it('shows no data message when candles array is empty', () => {
    render(<CandlestickChart symbol="BTCUSDT" candles={[]} />)

    expect(screen.getByText('No data available')).toBeInTheDocument()
  })

  it('handles error state', () => {
    const errorMessage = 'Failed to load chart data'
    render(<CandlestickChart symbol="BTCUSDT" candles={[]} error={errorMessage} />)

    expect(screen.getByText(errorMessage)).toBeInTheDocument()
    expect(screen.getByTestId('chart-error')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<CandlestickChart symbol="BTCUSDT" candles={[]} className="custom-chart" />)

    const container = screen.getByTestId('candlestick-chart')
    expect(container).toHaveClass('candlestick-chart', 'custom-chart')
  })

  it('renders with correct dimensions', () => {
    render(<CandlestickChart symbol="BTCUSDT" candles={mockCandles} />)

    const chartContainer = screen.getByTestId('chart-container')
    expect(chartContainer).toHaveClass('chart-container')
  })

  it('handles fit to screen action', async () => {
    render(<CandlestickChart symbol="BTCUSDT" candles={mockCandles} />)

    const fitButton = screen.getByTitle('Fit to screen')
    await userEvent.click(fitButton)

    expect(mockFitContent).toHaveBeenCalled()
  })

  it('updates when symbol changes', async () => {
    const { rerender } = render(<CandlestickChart symbol="BTCUSDT" candles={mockCandles} />)

    const newCandles = [
      {
        time: 1704067320,
        open: 1800,
        high: 1850,
        low: 1790,
        close: 1830,
        volume: 50,
      },
    ]

    rerender(<CandlestickChart symbol="ETHUSDT" candles={newCandles} />)

    await waitFor(() => {
      expect(screen.getByText('ETHUSDT')).toBeInTheDocument()
      expect(mockUpdateCandles).toHaveBeenLastCalledWith(newCandles)
    })
  })

  it('handles empty indicators array', () => {
    render(<CandlestickChart symbol="BTCUSDT" candles={mockCandles} indicators={[]} />)

    expect(mockAddIndicator).not.toHaveBeenCalled()
  })

  it('cleans up indicators when removed', async () => {
    const { rerender } = render(
      <CandlestickChart symbol="BTCUSDT" candles={mockCandles} indicators={mockIndicators} />,
    )

    await waitFor(() => {
      expect(mockAddIndicator).toHaveBeenCalledTimes(2)
    })

    vi.clearAllMocks()

    rerender(<CandlestickChart symbol="BTCUSDT" candles={mockCandles} indicators={[]} />)

    // Should not add new indicators
    expect(mockAddIndicator).not.toHaveBeenCalled()
  })
})
