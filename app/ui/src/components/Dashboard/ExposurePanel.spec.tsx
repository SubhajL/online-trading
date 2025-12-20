import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ExposurePanel } from './ExposurePanel'
import type { ExposureSummary } from '@/types/dashboard'

const createMockExposure = (overrides: Partial<ExposureSummary> = {}): ExposureSummary => ({
  totalNotional: 15000,
  spotNotional: 5000,
  futuresNotional: 10000,
  unrealizedPnl: 250.75,
  realizedPnlToday: 150.25,
  totalEquity: 50000,
  availableMargin: 35000,
  marginUsagePercent: 30,
  positionCount: 3,
  spotPositionCount: 1,
  futuresPositionCount: 2,
  ...overrides,
})

describe('ExposurePanel', () => {
  describe('notional display', () => {
    it('displays total notional value', () => {
      const exposure = createMockExposure({ totalNotional: 15000 })
      render(<ExposurePanel exposure={exposure} />)

      expect(screen.getByTestId('total-notional')).toHaveTextContent('$15,000')
    })

    it('displays spot and futures notional breakdown', () => {
      const exposure = createMockExposure({
        spotNotional: 5000,
        futuresNotional: 10000,
      })
      render(<ExposurePanel exposure={exposure} />)

      expect(screen.getByTestId('spot-notional')).toHaveTextContent('$5,000')
      expect(screen.getByTestId('futures-notional')).toHaveTextContent('$10,000')
    })
  })

  describe('P&L display', () => {
    it('displays unrealized P&L with correct sign', () => {
      const exposure = createMockExposure({ unrealizedPnl: 250.75 })
      render(<ExposurePanel exposure={exposure} />)

      const unrealizedPnl = screen.getByTestId('unrealized-pnl')
      expect(unrealizedPnl).toHaveTextContent('+$250.75')
      expect(unrealizedPnl).toHaveClass('pnl-positive')
    })

    it('displays negative unrealized P&L with correct styling', () => {
      const exposure = createMockExposure({ unrealizedPnl: -120.5 })
      render(<ExposurePanel exposure={exposure} />)

      const unrealizedPnl = screen.getByTestId('unrealized-pnl')
      expect(unrealizedPnl).toHaveTextContent('-$120.50')
      expect(unrealizedPnl).toHaveClass('pnl-negative')
    })

    it('displays realized P&L for today', () => {
      const exposure = createMockExposure({ realizedPnlToday: 150.25 })
      render(<ExposurePanel exposure={exposure} />)

      expect(screen.getByTestId('realized-pnl-today')).toHaveTextContent('+$150.25')
    })
  })

  describe('equity and margin display', () => {
    it('displays total equity', () => {
      const exposure = createMockExposure({ totalEquity: 50000 })
      render(<ExposurePanel exposure={exposure} />)

      expect(screen.getByTestId('total-equity')).toHaveTextContent('$50,000')
    })

    it('displays available margin', () => {
      const exposure = createMockExposure({ availableMargin: 35000 })
      render(<ExposurePanel exposure={exposure} />)

      expect(screen.getByTestId('available-margin')).toHaveTextContent('$35,000')
    })

    it('displays margin usage percentage with progress bar', () => {
      const exposure = createMockExposure({ marginUsagePercent: 30 })
      render(<ExposurePanel exposure={exposure} />)

      expect(screen.getByTestId('margin-usage')).toHaveTextContent('30%')
      const progressBar = screen.getByTestId('margin-progress-bar')
      expect(progressBar).toHaveStyle({ width: '30%' })
    })

    it('shows warning color when margin usage exceeds 70%', () => {
      const exposure = createMockExposure({ marginUsagePercent: 75 })
      render(<ExposurePanel exposure={exposure} />)

      const progressBar = screen.getByTestId('margin-progress-bar')
      expect(progressBar).toHaveClass('margin-warning')
    })

    it('shows danger color when margin usage exceeds 90%', () => {
      const exposure = createMockExposure({ marginUsagePercent: 95 })
      render(<ExposurePanel exposure={exposure} />)

      const progressBar = screen.getByTestId('margin-progress-bar')
      expect(progressBar).toHaveClass('margin-danger')
    })
  })

  describe('position counts', () => {
    it('displays total position count', () => {
      const exposure = createMockExposure({ positionCount: 3 })
      render(<ExposurePanel exposure={exposure} />)

      expect(screen.getByTestId('position-count')).toHaveTextContent('3')
    })

    it('displays spot and futures position breakdown', () => {
      const exposure = createMockExposure({
        spotPositionCount: 1,
        futuresPositionCount: 2,
      })
      render(<ExposurePanel exposure={exposure} />)

      expect(screen.getByTestId('spot-position-count')).toHaveTextContent('1')
      expect(screen.getByTestId('futures-position-count')).toHaveTextContent('2')
    })
  })

  describe('loading and error states', () => {
    it('shows loading skeleton when exposure is null', () => {
      render(<ExposurePanel exposure={null} loading />)

      expect(screen.getByTestId('exposure-panel-loading')).toBeInTheDocument()
    })

    it('shows error message when error prop is provided', () => {
      render(<ExposurePanel exposure={null} error="Failed to fetch exposure data" />)

      expect(screen.getByText('Failed to fetch exposure data')).toBeInTheDocument()
    })
  })

  describe('zero values', () => {
    it('displays zero values correctly', () => {
      const exposure = createMockExposure({
        totalNotional: 0,
        unrealizedPnl: 0,
        positionCount: 0,
      })
      render(<ExposurePanel exposure={exposure} />)

      expect(screen.getByTestId('total-notional')).toHaveTextContent('$0')
      expect(screen.getByTestId('unrealized-pnl')).toHaveTextContent('$0.00')
      expect(screen.getByTestId('position-count')).toHaveTextContent('0')
    })
  })
})
