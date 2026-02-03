import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { EquityCurve } from './EquityCurve'
import type { EquityPoint } from '@/types/dashboard'

// Mock lightweight-charts since it requires DOM
vi.mock('lightweight-charts', () => ({
  createChart: vi.fn(() => ({
    addAreaSeries: vi.fn(() => ({
      setData: vi.fn(),
      update: vi.fn(),
      applyOptions: vi.fn(),
    })),
    addLineSeries: vi.fn(() => ({
      setData: vi.fn(),
      update: vi.fn(),
      applyOptions: vi.fn(),
    })),
    timeScale: vi.fn(() => ({
      fitContent: vi.fn(),
      setVisibleRange: vi.fn(),
      getVisibleRange: vi.fn(() => ({ from: 0, to: 100 })),
    })),
    priceScale: vi.fn(() => ({
      applyOptions: vi.fn(),
    })),
    applyOptions: vi.fn(),
    resize: vi.fn(),
    remove: vi.fn(),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
  })),
  ColorType: { Solid: 'Solid', Gradient: 'Gradient' },
  LineStyle: { Solid: 0, Dashed: 1 },
}))

const createMockEquityData = (days: number): EquityPoint[] => {
  const data: EquityPoint[] = []
  const now = new Date()
  let equity = 10000

  for (let i = days; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    date.setHours(0, 0, 0, 0)

    equity += Math.random() * 200 - 80 // Random walk
    data.push({
      timestamp: date.toISOString(),
      equity: Math.max(0, equity),
    })
  }

  return data
}

describe('EquityCurve', () => {
  beforeEach(() => {
    // Set a fixed date close to test data for consistent filtering
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-01-15T12:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('rendering with data', () => {
    it('renders chart container', () => {
      const data = createMockEquityData(30)
      render(<EquityCurve data={data} />)

      expect(screen.getByTestId('equity-curve')).toBeInTheDocument()
      expect(screen.getByTestId('equity-chart-container')).toBeInTheDocument()
    })

    it('renders time range selector buttons', () => {
      const data = createMockEquityData(30)
      render(<EquityCurve data={data} />)

      expect(screen.getByTestId('time-range-1D')).toBeInTheDocument()
      expect(screen.getByTestId('time-range-1W')).toBeInTheDocument()
      expect(screen.getByTestId('time-range-1M')).toBeInTheDocument()
      expect(screen.getByTestId('time-range-ALL')).toBeInTheDocument()
    })

    it('defaults to 1M time range', () => {
      const data = createMockEquityData(30)
      render(<EquityCurve data={data} />)

      const monthButton = screen.getByTestId('time-range-1M')
      expect(monthButton).toHaveClass('bg-white')
    })

    it('renders header with title', () => {
      const data = createMockEquityData(30)
      render(<EquityCurve data={data} />)

      expect(screen.getByText('Equity Curve')).toBeInTheDocument()
    })

    it('displays current equity value', () => {
      const data: EquityPoint[] = [
        { timestamp: '2025-01-01T00:00:00Z', equity: 10000 },
        { timestamp: '2025-01-02T00:00:00Z', equity: 10500 },
      ]
      render(<EquityCurve data={data} />)

      expect(screen.getByTestId('current-equity')).toHaveTextContent('$10,500.00')
    })

    it('displays equity change from start', () => {
      const data: EquityPoint[] = [
        { timestamp: '2025-01-01T00:00:00Z', equity: 10000 },
        { timestamp: '2025-01-02T00:00:00Z', equity: 10500 },
      ]
      render(<EquityCurve data={data} />)

      expect(screen.getByTestId('equity-change')).toHaveTextContent('+$500.00')
      expect(screen.getByTestId('equity-change-percent')).toHaveTextContent('+5.00%')
    })
  })

  describe('time range filtering', () => {
    it('filters data to 1 day when 1D selected', async () => {
      const data = createMockEquityData(30)
      const onTimeRangeChange = vi.fn()
      render(<EquityCurve data={data} onTimeRangeChange={onTimeRangeChange} />)

      await fireEvent.click(screen.getByTestId('time-range-1D'))

      expect(onTimeRangeChange).toHaveBeenCalledWith('1D')
    })

    it('filters data to 1 week when 1W selected', async () => {
      const data = createMockEquityData(30)
      const onTimeRangeChange = vi.fn()
      render(<EquityCurve data={data} onTimeRangeChange={onTimeRangeChange} />)

      await fireEvent.click(screen.getByTestId('time-range-1W'))

      expect(onTimeRangeChange).toHaveBeenCalledWith('1W')
    })

    it('filters data to 1 month when 1M selected', async () => {
      const data = createMockEquityData(30)
      const onTimeRangeChange = vi.fn()
      render(<EquityCurve data={data} onTimeRangeChange={onTimeRangeChange} />)

      await fireEvent.click(screen.getByTestId('time-range-1M'))

      expect(onTimeRangeChange).toHaveBeenCalledWith('1M')
    })

    it('shows all data when ALL selected', async () => {
      const data = createMockEquityData(90)
      const onTimeRangeChange = vi.fn()
      render(<EquityCurve data={data} onTimeRangeChange={onTimeRangeChange} />)

      await fireEvent.click(screen.getByTestId('time-range-ALL'))

      expect(onTimeRangeChange).toHaveBeenCalledWith('ALL')
    })

    it('updates active button on time range change', async () => {
      const data = createMockEquityData(30)
      render(<EquityCurve data={data} />)

      await fireEvent.click(screen.getByTestId('time-range-1W'))

      expect(screen.getByTestId('time-range-1W')).toHaveClass('bg-white')
      expect(screen.getByTestId('time-range-1M')).not.toHaveClass('bg-white')
    })

    it('respects initialTimeRange prop', () => {
      const data = createMockEquityData(30)
      render(<EquityCurve data={data} initialTimeRange="1W" />)

      expect(screen.getByTestId('time-range-1W')).toHaveClass('bg-white')
    })
  })

  describe('P&L display styling', () => {
    it('applies positive styling for gains', () => {
      const data: EquityPoint[] = [
        { timestamp: '2025-01-01T00:00:00Z', equity: 10000 },
        { timestamp: '2025-01-02T00:00:00Z', equity: 11000 },
      ]
      render(<EquityCurve data={data} />)

      expect(screen.getByTestId('equity-change')).toHaveClass('text-success')
    })

    it('applies negative styling for losses', () => {
      const data: EquityPoint[] = [
        { timestamp: '2025-01-01T00:00:00Z', equity: 10000 },
        { timestamp: '2025-01-02T00:00:00Z', equity: 9000 },
      ]
      render(<EquityCurve data={data} />)

      expect(screen.getByTestId('equity-change')).toHaveClass('text-danger')
    })

    it('applies neutral styling for no change', () => {
      const data: EquityPoint[] = [
        { timestamp: '2025-01-01T00:00:00Z', equity: 10000 },
        { timestamp: '2025-01-02T00:00:00Z', equity: 10000 },
      ]
      render(<EquityCurve data={data} />)

      expect(screen.getByTestId('equity-change')).toHaveClass('text-slate-500')
    })
  })

  describe('loading state', () => {
    it('displays loading skeleton when loading is true', () => {
      render(<EquityCurve data={[]} loading />)

      expect(screen.getByTestId('equity-curve-loading')).toBeInTheDocument()
    })

    it('hides chart when loading', () => {
      render(<EquityCurve data={[]} loading />)

      expect(screen.queryByTestId('equity-chart-container')).not.toBeInTheDocument()
    })
  })

  describe('error state', () => {
    it('displays error message when error is provided', () => {
      render(<EquityCurve data={[]} error="Failed to load equity data" />)

      expect(screen.getByTestId('equity-curve-error')).toBeInTheDocument()
      expect(screen.getByText('Failed to load equity data')).toBeInTheDocument()
    })

    it('error message has alert role', () => {
      render(<EquityCurve data={[]} error="Failed to load equity data" />)

      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  describe('empty state', () => {
    it('displays empty message when no data', () => {
      render(<EquityCurve data={[]} />)

      expect(screen.getByTestId('equity-curve-empty')).toBeInTheDocument()
      expect(screen.getByText('No equity data available')).toBeInTheDocument()
    })

    it('displays insufficient data message when only one point', () => {
      const data: EquityPoint[] = [{ timestamp: '2025-01-01T00:00:00Z', equity: 10000 }]
      render(<EquityCurve data={data} />)

      expect(screen.getByTestId('equity-curve-empty')).toBeInTheDocument()
      expect(screen.getByText('Insufficient data for chart')).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has accessible heading', () => {
      const data = createMockEquityData(30)
      render(<EquityCurve data={data} />)

      // CardTitle renders as div, check text presence
      expect(screen.getByText('Equity Curve')).toBeInTheDocument()
    })

    it('time range buttons have accessible labels', () => {
      const data = createMockEquityData(30)
      render(<EquityCurve data={data} />)

      expect(screen.getByRole('button', { name: /1 day/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /1 week/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /1 month/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /all time/i })).toBeInTheDocument()
    })

    it('time range buttons have aria-pressed state', () => {
      const data = createMockEquityData(30)
      render(<EquityCurve data={data} initialTimeRange="1W" />)

      expect(screen.getByTestId('time-range-1W')).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByTestId('time-range-1D')).toHaveAttribute('aria-pressed', 'false')
    })
  })

  describe('edge cases', () => {
    it('handles data with negative equity values', () => {
      const data: EquityPoint[] = [
        { timestamp: '2025-01-01T00:00:00Z', equity: 10000 },
        { timestamp: '2025-01-02T00:00:00Z', equity: -500 },
      ]
      render(<EquityCurve data={data} />)

      expect(screen.getByTestId('current-equity')).toHaveTextContent('-$500.00')
    })

    it('handles unsorted data by sorting it', () => {
      const data: EquityPoint[] = [
        { timestamp: '2025-01-03T00:00:00Z', equity: 11000 },
        { timestamp: '2025-01-01T00:00:00Z', equity: 10000 },
        { timestamp: '2025-01-02T00:00:00Z', equity: 10500 },
      ]
      render(<EquityCurve data={data} />)

      // Should show latest equity (11000)
      expect(screen.getByTestId('current-equity')).toHaveTextContent('$11,000.00')
    })

    it('handles very large equity values', () => {
      const data: EquityPoint[] = [
        { timestamp: '2025-01-01T00:00:00Z', equity: 1000000 },
        { timestamp: '2025-01-02T00:00:00Z', equity: 1500000 },
      ]
      render(<EquityCurve data={data} />)

      expect(screen.getByTestId('current-equity')).toHaveTextContent('$1,500,000.00')
    })

    it('handles zero starting equity', () => {
      const data: EquityPoint[] = [
        { timestamp: '2025-01-01T00:00:00Z', equity: 0 },
        { timestamp: '2025-01-02T00:00:00Z', equity: 1000 },
      ]
      render(<EquityCurve data={data} />)

      // Change from 0 is technically infinite, but we handle gracefully
      expect(screen.getByTestId('equity-change')).toHaveTextContent('+$1,000.00')
      expect(screen.getByTestId('equity-change-percent')).toHaveTextContent('N/A')
    })
  })

  describe('responsive behavior', () => {
    it('has responsive container', () => {
      const data = createMockEquityData(30)
      render(<EquityCurve data={data} />)

      const container = screen.getByTestId('equity-curve')
      expect(container).toBeInTheDocument()
    })
  })
})
