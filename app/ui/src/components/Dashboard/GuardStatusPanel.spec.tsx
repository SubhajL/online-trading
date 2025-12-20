import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { GuardStatusPanel } from './GuardStatusPanel'
import type { GuardStatusResponse, EngineState } from '@/types/dashboard'

const createMockGuardStatus = (
  overrides: Partial<GuardStatusResponse> = {},
): GuardStatusResponse => ({
  engineState: 'ACTIVE' as EngineState,
  guards: {
    drawdownGuard: { status: 'OK', blockedReason: null },
    maxPositionsGuard: { status: 'OK', blockedReason: null },
    newsGuard: { status: 'OK', blockedReason: null },
    volatilityGuard: { status: 'OK', blockedReason: null },
    correlationGuard: { status: 'OK', blockedReason: null },
  },
  overallStatus: 'OK',
  lastChecked: '2025-01-20T12:00:00Z',
  ...overrides,
})

describe('GuardStatusPanel', () => {
  describe('engine state display', () => {
    it('displays ACTIVE state with green indicator', () => {
      const status = createMockGuardStatus({ engineState: 'ACTIVE' })
      render(<GuardStatusPanel status={status} />)

      expect(screen.getByText('ACTIVE')).toBeInTheDocument()
      expect(screen.getByTestId('engine-status-indicator')).toHaveClass('status-active')
    })

    it('displays PAUSED state with yellow indicator', () => {
      const status = createMockGuardStatus({ engineState: 'PAUSED' })
      render(<GuardStatusPanel status={status} />)

      expect(screen.getByText('PAUSED')).toBeInTheDocument()
      expect(screen.getByTestId('engine-status-indicator')).toHaveClass('status-paused')
    })

    it('displays STOPPED state with red indicator', () => {
      const status = createMockGuardStatus({ engineState: 'STOPPED' })
      render(<GuardStatusPanel status={status} />)

      expect(screen.getByText('STOPPED')).toBeInTheDocument()
      expect(screen.getByTestId('engine-status-indicator')).toHaveClass('status-stopped')
    })
  })

  describe('overall guard status', () => {
    it('shows OK status with checkmark when all guards pass', () => {
      const status = createMockGuardStatus({ overallStatus: 'OK' })
      render(<GuardStatusPanel status={status} />)

      expect(screen.getByTestId('overall-status')).toHaveTextContent('OK')
      expect(screen.getByTestId('overall-status-icon')).toHaveTextContent('✓')
    })

    it('shows BLOCKED status with warning when any guard fails', () => {
      const status = createMockGuardStatus({
        overallStatus: 'BLOCKED',
        guards: {
          drawdownGuard: { status: 'BLOCKED', blockedReason: 'Max drawdown exceeded' },
          maxPositionsGuard: { status: 'OK', blockedReason: null },
          newsGuard: { status: 'OK', blockedReason: null },
          volatilityGuard: { status: 'OK', blockedReason: null },
          correlationGuard: { status: 'OK', blockedReason: null },
        },
      })
      render(<GuardStatusPanel status={status} />)

      expect(screen.getByTestId('overall-status')).toHaveTextContent('BLOCKED')
      expect(screen.getByTestId('overall-status-icon')).toHaveTextContent('⚠')
    })
  })

  describe('individual guard display', () => {
    it('displays all guard names', () => {
      const status = createMockGuardStatus()
      render(<GuardStatusPanel status={status} />)

      expect(screen.getByText('Drawdown Guard')).toBeInTheDocument()
      expect(screen.getByText('Max Positions Guard')).toBeInTheDocument()
      expect(screen.getByText('News Guard')).toBeInTheDocument()
      expect(screen.getByText('Volatility Guard')).toBeInTheDocument()
      expect(screen.getByText('Correlation Guard')).toBeInTheDocument()
    })

    it('shows blocked reason for failed guards', () => {
      const status = createMockGuardStatus({
        overallStatus: 'BLOCKED',
        guards: {
          drawdownGuard: { status: 'BLOCKED', blockedReason: 'Max drawdown exceeded' },
          maxPositionsGuard: { status: 'OK', blockedReason: null },
          newsGuard: { status: 'BLOCKED', blockedReason: 'High impact news in 30 minutes' },
          volatilityGuard: { status: 'OK', blockedReason: null },
          correlationGuard: { status: 'OK', blockedReason: null },
        },
      })
      render(<GuardStatusPanel status={status} />)

      expect(screen.getByText('Max drawdown exceeded')).toBeInTheDocument()
      expect(screen.getByText('High impact news in 30 minutes')).toBeInTheDocument()
    })

    it('shows OK indicator for passing guards', () => {
      const status = createMockGuardStatus()
      render(<GuardStatusPanel status={status} />)

      const okIndicators = screen.getAllByTestId('guard-status-ok')
      expect(okIndicators.length).toBe(5)
    })

    it('shows BLOCKED indicator for failing guards', () => {
      const status = createMockGuardStatus({
        overallStatus: 'BLOCKED',
        guards: {
          drawdownGuard: { status: 'BLOCKED', blockedReason: 'Max drawdown exceeded' },
          maxPositionsGuard: { status: 'BLOCKED', blockedReason: 'Max positions reached' },
          newsGuard: { status: 'OK', blockedReason: null },
          volatilityGuard: { status: 'OK', blockedReason: null },
          correlationGuard: { status: 'OK', blockedReason: null },
        },
      })
      render(<GuardStatusPanel status={status} />)

      const blockedIndicators = screen.getAllByTestId('guard-status-blocked')
      expect(blockedIndicators.length).toBe(2)
    })
  })

  describe('loading and error states', () => {
    it('shows loading skeleton when status is null', () => {
      render(<GuardStatusPanel status={null} loading />)

      expect(screen.getByTestId('guard-panel-loading')).toBeInTheDocument()
    })

    it('shows error message when error prop is provided', () => {
      render(<GuardStatusPanel status={null} error="Failed to fetch guard status" />)

      expect(screen.getByText('Failed to fetch guard status')).toBeInTheDocument()
    })
  })

  describe('last checked timestamp', () => {
    it('displays formatted last checked time', () => {
      const status = createMockGuardStatus({ lastChecked: '2025-01-20T12:00:00Z' })
      render(<GuardStatusPanel status={status} />)

      expect(screen.getByTestId('last-checked')).toBeInTheDocument()
    })
  })
})
