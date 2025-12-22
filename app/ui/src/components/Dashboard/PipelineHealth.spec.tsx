import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PipelineHealth } from './PipelineHealth'
import type { PipelineHealthResponse, SymbolHealth, LastDecision } from '@/types/dashboard'

function createMockSymbolHealth(overrides: Partial<SymbolHealth> = {}): SymbolHealth {
  return {
    symbol: 'BTCUSDT',
    timeframe: '15m',
    lastCandleTime: '2025-01-15T12:00:00Z',
    lastProcessedTime: '2025-01-15T12:00:02Z',
    lagMs: 2000,
    ...overrides,
  }
}

function createMockLastDecision(overrides: Partial<LastDecision> = {}): LastDecision {
  return {
    timestamp: '2025-01-15T12:00:01Z',
    symbol: 'BTCUSDT',
    action: 'BUY',
    reason: 'BOS_RETEST_LONG',
    ...overrides,
  }
}

function createMockPipelineHealth(
  overrides: Partial<PipelineHealthResponse> = {},
): PipelineHealthResponse {
  return {
    symbols: [createMockSymbolHealth()],
    lastDecision: createMockLastDecision(),
    averageLagMs: 2000,
    status: 'HEALTHY',
    ...overrides,
  }
}

describe('PipelineHealth', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2025-01-15T12:00:05Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('rendering with data', () => {
    it('renders pipeline health panel', () => {
      const data = createMockPipelineHealth()
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('pipeline-health')).toBeInTheDocument()
    })

    it('displays header title', () => {
      const data = createMockPipelineHealth()
      render(<PipelineHealth data={data} />)

      expect(screen.getByRole('heading', { name: /pipeline health/i })).toBeInTheDocument()
    })

    it('displays symbols list', () => {
      const data = createMockPipelineHealth({
        symbols: [
          createMockSymbolHealth({ symbol: 'BTCUSDT', timeframe: '15m' }),
          createMockSymbolHealth({ symbol: 'ETHUSDT', timeframe: '15m' }),
        ],
        lastDecision: null, // Avoid duplicate text from last decision
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('symbol-row-BTCUSDT')).toBeInTheDocument()
      expect(screen.getByTestId('symbol-row-ETHUSDT')).toBeInTheDocument()
    })

    it('displays timeframe for each symbol', () => {
      const data = createMockPipelineHealth({
        symbols: [createMockSymbolHealth({ symbol: 'BTCUSDT', timeframe: '15m' })],
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByText('15m')).toBeInTheDocument()
    })

    it('displays average lag', () => {
      const data = createMockPipelineHealth({ averageLagMs: 1500 })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('average-lag')).toHaveTextContent('1.5s')
    })
  })

  describe('status indicators', () => {
    it('shows healthy status with green indicator', () => {
      const data = createMockPipelineHealth({ status: 'HEALTHY' })
      render(<PipelineHealth data={data} />)

      const statusIndicator = screen.getByTestId('status-indicator')
      expect(statusIndicator).toHaveClass('status-healthy')
      expect(screen.getByText('HEALTHY')).toBeInTheDocument()
    })

    it('shows degraded status with yellow indicator', () => {
      const data = createMockPipelineHealth({ status: 'DEGRADED' })
      render(<PipelineHealth data={data} />)

      const statusIndicator = screen.getByTestId('status-indicator')
      expect(statusIndicator).toHaveClass('status-degraded')
      expect(screen.getByText('DEGRADED')).toBeInTheDocument()
    })

    it('shows unhealthy status with red indicator', () => {
      const data = createMockPipelineHealth({ status: 'UNHEALTHY' })
      render(<PipelineHealth data={data} />)

      const statusIndicator = screen.getByTestId('status-indicator')
      expect(statusIndicator).toHaveClass('status-unhealthy')
      expect(screen.getByText('UNHEALTHY')).toBeInTheDocument()
    })
  })

  describe('lag warnings', () => {
    it('shows lag warning when symbol lag > 5000ms', () => {
      const data = createMockPipelineHealth({
        symbols: [createMockSymbolHealth({ lagMs: 5001 })],
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('lag-warning')).toBeInTheDocument()
    })

    it('does not show lag warning when lag = 5000ms (boundary)', () => {
      const data = createMockPipelineHealth({
        symbols: [createMockSymbolHealth({ lagMs: 5000 })],
      })
      render(<PipelineHealth data={data} />)

      expect(screen.queryByTestId('lag-warning')).not.toBeInTheDocument()
    })

    it('does not show lag warning when lag < 5000ms', () => {
      const data = createMockPipelineHealth({
        symbols: [createMockSymbolHealth({ lagMs: 4999 })],
      })
      render(<PipelineHealth data={data} />)

      expect(screen.queryByTestId('lag-warning')).not.toBeInTheDocument()
    })

    it('displays lag value for each symbol', () => {
      const data = createMockPipelineHealth({
        symbols: [createMockSymbolHealth({ symbol: 'BTCUSDT', lagMs: 2500 })],
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('symbol-lag-BTCUSDT')).toHaveTextContent('2.5s')
    })

    it('highlights high lag symbols when lag > 5000ms', () => {
      const data = createMockPipelineHealth({
        symbols: [createMockSymbolHealth({ symbol: 'BTCUSDT', lagMs: 5001 })],
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('symbol-row-BTCUSDT')).toHaveClass('high-lag')
    })

    it('does not highlight symbols at exactly 5000ms boundary', () => {
      const data = createMockPipelineHealth({
        symbols: [createMockSymbolHealth({ symbol: 'BTCUSDT', lagMs: 5000 })],
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('symbol-row-BTCUSDT')).not.toHaveClass('high-lag')
    })
  })

  describe('last decision display', () => {
    it('displays last decision timestamp', () => {
      const data = createMockPipelineHealth({
        lastDecision: createMockLastDecision({ timestamp: '2025-01-15T12:00:01Z' }),
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('last-decision')).toBeInTheDocument()
    })

    it('displays last decision symbol', () => {
      const data = createMockPipelineHealth({
        lastDecision: createMockLastDecision({ symbol: 'ETHUSDT' }),
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('last-decision-symbol')).toHaveTextContent('ETHUSDT')
    })

    it('displays last decision action with correct styling', () => {
      const data = createMockPipelineHealth({
        lastDecision: createMockLastDecision({ action: 'BUY' }),
      })
      render(<PipelineHealth data={data} />)

      const actionElement = screen.getByTestId('last-decision-action')
      expect(actionElement).toHaveTextContent('BUY')
      expect(actionElement).toHaveClass('action-buy')
    })

    it('displays SELL action with correct styling', () => {
      const data = createMockPipelineHealth({
        lastDecision: createMockLastDecision({ action: 'SELL' }),
      })
      render(<PipelineHealth data={data} />)

      const actionElement = screen.getByTestId('last-decision-action')
      expect(actionElement).toHaveTextContent('SELL')
      expect(actionElement).toHaveClass('action-sell')
    })

    it('displays HOLD action with correct styling', () => {
      const data = createMockPipelineHealth({
        lastDecision: createMockLastDecision({ action: 'HOLD' }),
      })
      render(<PipelineHealth data={data} />)

      const actionElement = screen.getByTestId('last-decision-action')
      expect(actionElement).toHaveTextContent('HOLD')
      expect(actionElement).toHaveClass('action-hold')
    })

    it('displays last decision reason', () => {
      const data = createMockPipelineHealth({
        lastDecision: createMockLastDecision({ reason: 'CHOCH_BEARISH' }),
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('last-decision-reason')).toHaveTextContent('CHOCH_BEARISH')
    })

    it('shows no decision message when lastDecision is null', () => {
      const data = createMockPipelineHealth({ lastDecision: null })
      render(<PipelineHealth data={data} />)

      expect(screen.getByText(/no recent decisions/i)).toBeInTheDocument()
    })
  })

  describe('loading state', () => {
    it('displays loading skeleton when loading is true', () => {
      render(<PipelineHealth data={null} loading />)

      expect(screen.getByTestId('pipeline-health-loading')).toBeInTheDocument()
    })

    it('hides symbols list when loading', () => {
      render(<PipelineHealth data={null} loading />)

      expect(screen.queryByTestId('symbols-list')).not.toBeInTheDocument()
    })
  })

  describe('error state', () => {
    it('displays error message when error is provided', () => {
      render(<PipelineHealth data={null} error="Failed to fetch pipeline health" />)

      expect(screen.getByTestId('pipeline-health-error')).toBeInTheDocument()
      expect(screen.getByText('Failed to fetch pipeline health')).toBeInTheDocument()
    })

    it('error message has alert role', () => {
      render(<PipelineHealth data={null} error="Error" />)

      expect(screen.getByRole('alert')).toBeInTheDocument()
    })
  })

  describe('empty state', () => {
    it('displays empty message when no symbols', () => {
      const data = createMockPipelineHealth({ symbols: [] })
      render(<PipelineHealth data={data} />)

      expect(screen.getByText(/no symbols being tracked/i)).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has accessible heading', () => {
      const data = createMockPipelineHealth()
      render(<PipelineHealth data={data} />)

      expect(screen.getByRole('heading', { level: 3 })).toBeInTheDocument()
    })

    it('symbols table has accessible structure', () => {
      const data = createMockPipelineHealth({
        symbols: [createMockSymbolHealth()],
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByRole('table')).toBeInTheDocument()
    })
  })

  describe('edge cases', () => {
    it('handles zero lag', () => {
      const data = createMockPipelineHealth({
        symbols: [createMockSymbolHealth({ lagMs: 0 })],
        averageLagMs: 0,
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('average-lag')).toHaveTextContent('0.0s')
    })

    it('handles very high lag values', () => {
      const data = createMockPipelineHealth({
        symbols: [createMockSymbolHealth({ lagMs: 60000 })],
        averageLagMs: 60000,
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('average-lag')).toHaveTextContent('60.0s')
    })

    it('handles multiple symbols with different lag levels', () => {
      const data = createMockPipelineHealth({
        symbols: [
          createMockSymbolHealth({ symbol: 'BTCUSDT', lagMs: 1000 }),
          createMockSymbolHealth({ symbol: 'ETHUSDT', lagMs: 8000 }),
        ],
      })
      render(<PipelineHealth data={data} />)

      expect(screen.getByTestId('symbol-row-BTCUSDT')).not.toHaveClass('high-lag')
      expect(screen.getByTestId('symbol-row-ETHUSDT')).toHaveClass('high-lag')
    })
  })
})
