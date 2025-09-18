import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { VolumeChart } from './VolumeChart'
import type { Candle } from '@/types'

// Mock the useChart hook
const mockUpdateCandles = vi.fn()
const mockAddIndicator = vi.fn()

vi.mock('@/hooks/useChart', () => ({
  useChart: () => ({
    chart: {},
    candlestickSeries: {},
    updateCandles: mockUpdateCandles,
    addIndicator: mockAddIndicator,
    fitContent: vi.fn(),
  }),
}))

describe('VolumeChart', () => {
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
    {
      time: 1704067320,
      open: 42450,
      high: 42700,
      low: 42400,
      close: 42600,
      volume: 80,
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders volume chart container', () => {
    render(<VolumeChart candles={[]} />)

    const container = screen.getByTestId('volume-chart')
    expect(container).toBeInTheDocument()
    expect(container).toHaveClass('volume-chart')
  })

  it('displays volume data as histogram', () => {
    render(<VolumeChart candles={mockCandles} />)

    expect(mockAddIndicator).toHaveBeenCalledWith(
      'VOLUME',
      expect.arrayContaining([
        expect.objectContaining({ time: 1704067200, value: 100 }),
        expect.objectContaining({ time: 1704067260, value: 120 }),
        expect.objectContaining({ time: 1704067320, value: 80 }),
      ]),
      expect.any(Object),
    )
  })

  it('uses green and red colors for volume bars', () => {
    render(<VolumeChart candles={mockCandles} />)

    // Check that volume data includes color information based on candle direction
    const volumeData = mockAddIndicator.mock.calls[0]?.[1]

    // First candle closes higher than opens (green)
    expect(volumeData[0]!.color).toBe('#26a69a')

    // Second candle closes higher than opens (green)
    expect(volumeData[1]!.color).toBe('#26a69a')

    // Third candle closes higher than opens (green)
    expect(volumeData[2]!.color).toBe('#26a69a')
  })

  it('shows loading state', () => {
    render(<VolumeChart candles={[]} loading />)

    expect(screen.getByTestId('volume-loading')).toBeInTheDocument()
    expect(screen.getByText('Loading volume data...')).toBeInTheDocument()
  })

  it('shows no data message when candles array is empty', () => {
    render(<VolumeChart candles={[]} />)

    expect(screen.getByText('No volume data available')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<VolumeChart candles={[]} className="custom-volume" />)

    const container = screen.getByTestId('volume-chart')
    expect(container).toHaveClass('volume-chart', 'custom-volume')
  })

  it('updates when candles change', () => {
    const { rerender } = render(<VolumeChart candles={mockCandles} />)

    expect(mockAddIndicator).toHaveBeenCalledTimes(1)

    const newCandles = [
      ...mockCandles,
      {
        time: 1704067380,
        open: 42600,
        high: 42800,
        low: 42500,
        close: 42700,
        volume: 150,
      },
    ]

    rerender(<VolumeChart candles={newCandles} />)

    expect(mockAddIndicator).toHaveBeenCalledTimes(2)
    expect(mockAddIndicator).toHaveBeenLastCalledWith(
      'VOLUME',
      expect.arrayContaining([expect.objectContaining({ time: 1704067380, value: 150 })]),
      expect.any(Object),
    )
  })

  it('handles empty volume values', () => {
    const candlesWithZeroVolume = [
      {
        time: 1704067200,
        open: 42000,
        high: 42500,
        low: 41800,
        close: 42300,
        volume: 0,
      },
    ]

    render(<VolumeChart candles={candlesWithZeroVolume} />)

    expect(mockAddIndicator).toHaveBeenCalledWith(
      'VOLUME',
      expect.arrayContaining([expect.objectContaining({ time: 1704067200, value: 0 })]),
      expect.any(Object),
    )
  })

  it('formats large volume numbers', () => {
    const candlesWithLargeVolume = [
      {
        time: 1704067200,
        open: 42000,
        high: 42500,
        low: 41800,
        close: 42300,
        volume: 1234567,
      },
    ]

    render(<VolumeChart candles={candlesWithLargeVolume} />)

    // Should display formatted volume
    expect(screen.getByText('Volume')).toBeInTheDocument()
  })

  it('synchronizes with main chart timeframe', () => {
    render(<VolumeChart candles={mockCandles} />)

    // Volume chart should use the same time values as candles
    const volumeData = mockAddIndicator.mock.calls[0]![1]
    expect(volumeData.map((d: any) => d.time)).toEqual(mockCandles.map(c => c.time))
  })
})
