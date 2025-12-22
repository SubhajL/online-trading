import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { AutoTradingStatus } from './AutoTradingStatus'
import type { EngineStatus } from '@/types/dashboard'

function createMockEngineStatus(overrides: Partial<EngineStatus> = {}): EngineStatus {
  return {
    state: 'ACTIVE',
    autoTrading: true,
    lastDecisionAt: '2025-01-15T12:00:00Z',
    lastDecisionReason: 'BOS_RETEST_LONG',
    ...overrides,
  }
}

describe('AutoTradingStatus', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-01-15T12:05:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('rendering with data', () => {
    it('renders auto trading status panel', () => {
      const status = createMockEngineStatus()
      render(<AutoTradingStatus status={status} />)

      expect(screen.getByTestId('auto-trading-status')).toBeInTheDocument()
    })

    it('displays header title', () => {
      const status = createMockEngineStatus()
      render(<AutoTradingStatus status={status} />)

      expect(screen.getByRole('heading', { name: /auto trading/i })).toBeInTheDocument()
    })

    it('displays auto trading toggle state ON', () => {
      const status = createMockEngineStatus({ autoTrading: true })
      render(<AutoTradingStatus status={status} />)

      expect(screen.getByTestId('auto-trading-toggle')).toHaveTextContent('ON')
    })

    it('displays auto trading toggle state OFF', () => {
      const status = createMockEngineStatus({ autoTrading: false })
      render(<AutoTradingStatus status={status} />)

      expect(screen.getByTestId('auto-trading-toggle')).toHaveTextContent('OFF')
    })
  })

  describe('engine state indicators', () => {
    it('shows ACTIVE state with green indicator', () => {
      const status = createMockEngineStatus({ state: 'ACTIVE' })
      render(<AutoTradingStatus status={status} />)

      const indicator = screen.getByTestId('engine-state-indicator')
      expect(indicator).toHaveClass('state-active')
      expect(screen.getByTestId('engine-state-text')).toHaveTextContent('ACTIVE')
    })

    it('shows PAUSED state with yellow indicator', () => {
      const status = createMockEngineStatus({ state: 'PAUSED' })
      render(<AutoTradingStatus status={status} />)

      const indicator = screen.getByTestId('engine-state-indicator')
      expect(indicator).toHaveClass('state-paused')
      expect(screen.getByTestId('engine-state-text')).toHaveTextContent('PAUSED')
    })

    it('shows STOPPED state with red indicator', () => {
      const status = createMockEngineStatus({ state: 'STOPPED' })
      render(<AutoTradingStatus status={status} />)

      const indicator = screen.getByTestId('engine-state-indicator')
      expect(indicator).toHaveClass('state-stopped')
      expect(screen.getByTestId('engine-state-text')).toHaveTextContent('STOPPED')
    })
  })

  describe('last decision display', () => {
    it('displays last decision timestamp', () => {
      const status = createMockEngineStatus({ lastDecisionAt: '2025-01-15T12:00:00Z' })
      render(<AutoTradingStatus status={status} />)

      expect(screen.getByTestId('last-decision-time')).toBeInTheDocument()
    })

    it('displays last decision reason', () => {
      const status = createMockEngineStatus({ lastDecisionReason: 'CHOCH_BEARISH' })
      render(<AutoTradingStatus status={status} />)

      expect(screen.getByTestId('last-decision-reason')).toHaveTextContent('CHOCH_BEARISH')
    })

    it('shows no decision message when lastDecisionAt is null', () => {
      const status = createMockEngineStatus({ lastDecisionAt: null, lastDecisionReason: null })
      render(<AutoTradingStatus status={status} />)

      expect(screen.getByText(/no decisions yet/i)).toBeInTheDocument()
    })

    it('displays relative time since last decision', () => {
      const status = createMockEngineStatus({ lastDecisionAt: '2025-01-15T12:00:00Z' })
      render(<AutoTradingStatus status={status} />)

      // 5 minutes ago based on fake timer
      expect(screen.getByTestId('last-decision-time')).toHaveTextContent('5m ago')
    })
  })

  describe('active signals count', () => {
    it('displays active signals count when provided', () => {
      const status = createMockEngineStatus()
      render(<AutoTradingStatus status={status} activeSignals={3} />)

      expect(screen.getByTestId('active-signals')).toHaveTextContent('3')
    })

    it('displays zero when no active signals', () => {
      const status = createMockEngineStatus()
      render(<AutoTradingStatus status={status} activeSignals={0} />)

      expect(screen.getByTestId('active-signals')).toHaveTextContent('0')
    })

    it('does not display active signals section when not provided', () => {
      const status = createMockEngineStatus()
      render(<AutoTradingStatus status={status} />)

      expect(screen.queryByTestId('active-signals')).not.toBeInTheDocument()
    })
  })

  describe('toggle callback', () => {
    it('calls onToggle when toggle button is clicked', async () => {
      const status = createMockEngineStatus({ autoTrading: true })
      const onToggle = vi.fn()
      render(<AutoTradingStatus status={status} onToggle={onToggle} />)

      await fireEvent.click(screen.getByTestId('toggle-button'))

      expect(onToggle).toHaveBeenCalledWith(false)
    })

    it('passes correct value when turning ON', async () => {
      const status = createMockEngineStatus({ autoTrading: false })
      const onToggle = vi.fn()
      render(<AutoTradingStatus status={status} onToggle={onToggle} />)

      await fireEvent.click(screen.getByTestId('toggle-button'))

      expect(onToggle).toHaveBeenCalledWith(true)
    })

    it('does not render toggle button when onToggle not provided', () => {
      const status = createMockEngineStatus()
      render(<AutoTradingStatus status={status} />)

      expect(screen.queryByTestId('toggle-button')).not.toBeInTheDocument()
    })

    it('disables toggle when engine is STOPPED', () => {
      const status = createMockEngineStatus({ state: 'STOPPED' })
      const onToggle = vi.fn()
      render(<AutoTradingStatus status={status} onToggle={onToggle} />)

      expect(screen.getByTestId('toggle-button')).toBeDisabled()
    })
  })

  describe('loading state', () => {
    it('displays loading skeleton when loading is true', () => {
      render(<AutoTradingStatus status={null} loading />)

      expect(screen.getByTestId('auto-trading-status-loading')).toBeInTheDocument()
    })

    it('hides content when loading', () => {
      render(<AutoTradingStatus status={null} loading />)

      expect(screen.queryByTestId('engine-state-indicator')).not.toBeInTheDocument()
    })
  })

  describe('error state', () => {
    it('displays error message when error is provided', () => {
      render(<AutoTradingStatus status={null} error="Failed to fetch status" />)

      expect(screen.getByTestId('auto-trading-status-error')).toBeInTheDocument()
      expect(screen.getByText('Failed to fetch status')).toBeInTheDocument()
    })

    it('error message has alert role', () => {
      render(<AutoTradingStatus status={null} error="Error" />)

      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has accessible heading', () => {
      const status = createMockEngineStatus()
      render(<AutoTradingStatus status={status} />)

      expect(screen.getByRole('heading', { level: 3 })).toBeInTheDocument()
    })

    it('toggle button has accessible label', () => {
      const status = createMockEngineStatus({ autoTrading: true })
      render(<AutoTradingStatus status={status} onToggle={vi.fn()} />)

      expect(screen.getByRole('button', { name: /turn off auto trading/i })).toBeInTheDocument()
    })

    it('toggle button label changes based on state', () => {
      const status = createMockEngineStatus({ autoTrading: false })
      render(<AutoTradingStatus status={status} onToggle={vi.fn()} />)

      expect(screen.getByRole('button', { name: /turn on auto trading/i })).toBeInTheDocument()
    })
  })

  describe('edge cases', () => {
    it('handles very old last decision (hours ago)', () => {
      vi.setSystemTime(new Date('2025-01-15T18:00:00Z'))
      const status = createMockEngineStatus({ lastDecisionAt: '2025-01-15T12:00:00Z' })
      render(<AutoTradingStatus status={status} />)

      expect(screen.getByTestId('last-decision-time')).toHaveTextContent('6h ago')
    })

    it('handles very recent last decision (seconds ago)', () => {
      vi.setSystemTime(new Date('2025-01-15T12:00:30Z'))
      const status = createMockEngineStatus({ lastDecisionAt: '2025-01-15T12:00:00Z' })
      render(<AutoTradingStatus status={status} />)

      expect(screen.getByTestId('last-decision-time')).toHaveTextContent('30s ago')
    })

    it('handles null status gracefully', () => {
      render(<AutoTradingStatus status={null} />)

      expect(screen.queryByTestId('auto-trading-status')).not.toBeInTheDocument()
    })
  })
})
