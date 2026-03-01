import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MonitoringDashboard } from './MonitoringDashboard'

// Mock child components to isolate dashboard layout testing
vi.mock('./GuardStatusPanel', () => ({
  GuardStatusPanel: ({
    status: _status,
    loading,
    error,
  }: {
    status: unknown
    loading?: boolean
    error?: string
  }) => (
    <div data-testid="guard-status-panel" data-loading={loading} data-error={error}>
      GuardStatusPanel
    </div>
  ),
}))

vi.mock('./ExposurePanel', () => ({
  ExposurePanel: ({
    exposure: _exposure,
    loading,
    error,
  }: {
    exposure: unknown
    loading?: boolean
    error?: string
  }) => (
    <div data-testid="exposure-panel" data-loading={loading} data-error={error}>
      ExposurePanel
    </div>
  ),
}))

vi.mock('./TradingKPIs', () => ({
  TradingKPIs: ({
    kpis: _kpis,
    loading,
    error,
  }: {
    kpis: unknown
    loading?: boolean
    error?: string
  }) => (
    <div data-testid="trading-kpis" data-loading={loading} data-error={error}>
      TradingKPIs
    </div>
  ),
}))

vi.mock('./EquityCurve', () => ({
  EquityCurve: ({
    data: _data,
    loading,
    error,
  }: {
    data: unknown[]
    loading?: boolean
    error?: string
  }) => (
    <div data-testid="equity-curve" data-loading={loading} data-error={error}>
      EquityCurve
    </div>
  ),
}))

vi.mock('./PipelineHealth', () => ({
  PipelineHealth: ({
    data: _data,
    loading,
    error,
  }: {
    data: unknown
    loading?: boolean
    error?: string
  }) => (
    <div data-testid="pipeline-health" data-loading={loading} data-error={error}>
      PipelineHealth
    </div>
  ),
}))

vi.mock('./AutoTradingStatus', () => ({
  AutoTradingStatus: ({
    status: _status,
    loading,
    error,
  }: {
    status: unknown
    loading?: boolean
    error?: string
  }) => (
    <div data-testid="auto-trading-status" data-loading={loading} data-error={error}>
      AutoTradingStatus
    </div>
  ),
}))

vi.mock('./EmergencyControls', () => ({
  EmergencyControls: () => <div data-testid="emergency-controls">EmergencyControls</div>,
}))

vi.mock('../trading/PositionsList', () => ({
  PositionsList: ({
    positions: _positions,
    loading,
  }: {
    positions: unknown[]
    loading?: boolean
  }) => (
    <div data-testid="positions-list" data-loading={loading}>
      PositionsList
    </div>
  ),
}))

vi.mock('../trading/AccountBalance', () => ({
  AccountBalance: ({
    balances: _balances,
    loading,
  }: {
    balances: unknown[]
    loading?: boolean
  }) => (
    <div data-testid="account-balance" data-loading={loading}>
      AccountBalance
    </div>
  ),
}))

const defaultProps = {
  guardStatus: null,
  exposure: null,
  kpis: null,
  equityCurve: [],
  pipelineHealth: null,
  engineStatus: null,
  onEmergencyClose: vi.fn(),
  positions: [],
  balances: [],
}

describe('MonitoringDashboard', () => {
  describe('layout structure', () => {
    it('renders the monitoring dashboard', () => {
      render(<MonitoringDashboard {...defaultProps} />)

      expect(screen.getByTestId('monitoring-dashboard')).toBeInTheDocument()
    })

    it('renders all safety components in top section', () => {
      render(<MonitoringDashboard {...defaultProps} />)

      expect(screen.getByTestId('guard-status-panel')).toBeInTheDocument()
      expect(screen.getByTestId('exposure-panel')).toBeInTheDocument()
      expect(screen.getByTestId('emergency-controls')).toBeInTheDocument()
    })

    it('renders KPIs and equity curve in main section', () => {
      render(<MonitoringDashboard {...defaultProps} />)

      expect(screen.getByTestId('trading-kpis')).toBeInTheDocument()
      expect(screen.getByTestId('equity-curve')).toBeInTheDocument()
    })

    it('renders status components in sidebar', () => {
      render(<MonitoringDashboard {...defaultProps} />)

      expect(screen.getByTestId('auto-trading-status')).toBeInTheDocument()
      expect(screen.getByTestId('pipeline-health')).toBeInTheDocument()
    })

    it('renders positions and balances in bottom section', () => {
      render(<MonitoringDashboard {...defaultProps} />)

      expect(screen.getByTestId('positions-list')).toBeInTheDocument()
      expect(screen.getByTestId('account-balance')).toBeInTheDocument()
    })

    it('does NOT render OrderForm (removed per plan)', () => {
      render(<MonitoringDashboard {...defaultProps} />)

      expect(screen.queryByTestId('order-form')).not.toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('has safety section with aria-label', () => {
      render(<MonitoringDashboard {...defaultProps} />)

      expect(screen.getByLabelText(/safety and guards/i)).toBeInTheDocument()
    })

    it('has performance metrics section with aria-label', () => {
      render(<MonitoringDashboard {...defaultProps} />)

      expect(screen.getByLabelText(/performance metrics/i)).toBeInTheDocument()
    })

    it('has system status section with aria-label', () => {
      render(<MonitoringDashboard {...defaultProps} />)

      expect(screen.getByLabelText(/system status/i)).toBeInTheDocument()
    })

    it('has positions section with aria-label', () => {
      render(<MonitoringDashboard {...defaultProps} />)

      expect(screen.getByLabelText(/positions and balances/i)).toBeInTheDocument()
    })
  })

  describe('loading states propagation', () => {
    it('passes loading state to guard status panel', () => {
      render(<MonitoringDashboard {...defaultProps} guardStatusLoading />)

      expect(screen.getByTestId('guard-status-panel')).toHaveAttribute('data-loading', 'true')
    })

    it('passes loading state to exposure panel', () => {
      render(<MonitoringDashboard {...defaultProps} exposureLoading />)

      expect(screen.getByTestId('exposure-panel')).toHaveAttribute('data-loading', 'true')
    })

    it('passes loading state to trading kpis', () => {
      render(<MonitoringDashboard {...defaultProps} kpisLoading />)

      expect(screen.getByTestId('trading-kpis')).toHaveAttribute('data-loading', 'true')
    })

    it('passes loading state to equity curve', () => {
      render(<MonitoringDashboard {...defaultProps} equityCurveLoading />)

      expect(screen.getByTestId('equity-curve')).toHaveAttribute('data-loading', 'true')
    })

    it('passes loading state to pipeline health', () => {
      render(<MonitoringDashboard {...defaultProps} pipelineHealthLoading />)

      expect(screen.getByTestId('pipeline-health')).toHaveAttribute('data-loading', 'true')
    })

    it('passes loading state to auto trading status', () => {
      render(<MonitoringDashboard {...defaultProps} engineStatusLoading />)

      expect(screen.getByTestId('auto-trading-status')).toHaveAttribute('data-loading', 'true')
    })

    it('passes loading state to positions list', () => {
      render(<MonitoringDashboard {...defaultProps} positionsLoading />)

      expect(screen.getByTestId('positions-list')).toHaveAttribute('data-loading', 'true')
    })

    it('passes loading state to account balance', () => {
      render(<MonitoringDashboard {...defaultProps} balancesLoading />)

      expect(screen.getByTestId('account-balance')).toHaveAttribute('data-loading', 'true')
    })
  })

  describe('error states propagation', () => {
    it('passes error to guard status panel', () => {
      render(<MonitoringDashboard {...defaultProps} guardStatusError="Error" />)

      expect(screen.getByTestId('guard-status-panel')).toHaveAttribute('data-error', 'Error')
    })

    it('passes error to exposure panel', () => {
      render(<MonitoringDashboard {...defaultProps} exposureError="Error" />)

      expect(screen.getByTestId('exposure-panel')).toHaveAttribute('data-error', 'Error')
    })

    it('passes error to trading kpis', () => {
      render(<MonitoringDashboard {...defaultProps} kpisError="Error" />)

      expect(screen.getByTestId('trading-kpis')).toHaveAttribute('data-error', 'Error')
    })

    it('passes error to equity curve', () => {
      render(<MonitoringDashboard {...defaultProps} equityCurveError="Error" />)

      expect(screen.getByTestId('equity-curve')).toHaveAttribute('data-error', 'Error')
    })

    it('passes error to pipeline health', () => {
      render(<MonitoringDashboard {...defaultProps} pipelineHealthError="Error" />)

      expect(screen.getByTestId('pipeline-health')).toHaveAttribute('data-error', 'Error')
    })

    it('passes error to auto trading status', () => {
      render(<MonitoringDashboard {...defaultProps} engineStatusError="Error" />)

      expect(screen.getByTestId('auto-trading-status')).toHaveAttribute('data-error', 'Error')
    })
  })

  describe('className prop', () => {
    it('applies custom className', () => {
      render(<MonitoringDashboard {...defaultProps} className="custom-class" />)

      expect(screen.getByTestId('monitoring-dashboard')).toHaveClass('custom-class')
    })
  })
})
