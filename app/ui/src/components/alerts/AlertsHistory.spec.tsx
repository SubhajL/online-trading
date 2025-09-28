import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AlertsHistory } from './AlertsHistory'
import { createMockAlert } from '@/test-utils/mocks'
import type { Alert } from '@/types'

// Mock the alerts service
vi.mock('@/services/alerts', () => ({
  alertsService: {
    getAlerts: vi.fn(),
  },
}))

import { alertsService } from '@/services/alerts'

describe('AlertsHistory', () => {
  const mockAlerts: Alert[] = [
    {
      id: 'alert-1',
      symbol: 'BTCUSDT',
      venue: 'SPOT',
      type: 'smc_event',
      title: 'Bullish Change of Character',
      message: 'CHOCH detected on BTCUSDT 1h',
      severity: 'high',
      createdAt: new Date('2024-01-01T10:00:00Z').toISOString(),
      read: true,
    },
    {
      id: 'alert-2',
      symbol: 'ETHUSDT',
      venue: 'USD_M',
      type: 'zone_retest',
      title: 'Supply Zone Retest',
      message: 'Price approaching strong supply zone at $3000',
      severity: 'medium',
      createdAt: new Date('2024-01-01T09:30:00Z').toISOString(),
      read: true,
    },
    {
      id: 'alert-3',
      symbol: 'BTCUSDT',
      venue: 'SPOT',
      type: 'order_filled',
      title: 'Order Filled',
      message: 'Buy order filled at $44,950',
      severity: 'info',
      createdAt: new Date('2024-01-01T09:00:00Z').toISOString(),
      read: true,
    },
    {
      id: 'alert-4',
      symbol: 'BTCUSDT',
      venue: 'USD_M',
      type: 'position_update',
      title: 'Position Closed',
      message: 'Long position closed with +2.5% profit',
      severity: 'info',
      createdAt: new Date('2024-01-01T08:30:00Z').toISOString(),
      read: true,
    },
    {
      id: 'alert-5',
      symbol: 'ETHUSDT',
      venue: 'SPOT',
      type: 'risk_limit',
      title: 'Risk Limit Warning',
      message: 'Daily loss limit reached: -1.5%',
      severity: 'critical',
      createdAt: new Date('2024-01-01T08:00:00Z').toISOString(),
      read: true,
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('should render alerts history', () => {
      render(<AlertsHistory />)

      expect(screen.getByTestId('alerts-history')).toBeInTheDocument()
    })

    it('should show title', () => {
      render(<AlertsHistory />)

      expect(screen.getByText('Alert History')).toBeInTheDocument()
    })
  })

  describe('loading state', () => {
    it('should show loading spinner while fetching', async () => {
      vi.mocked(alertsService.getAlerts).mockImplementation(
        () => new Promise(resolve => setTimeout(() => resolve({ alerts: [] }), 100)),
      )

      render(<AlertsHistory />)

      expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.queryByTestId('loading-spinner')).not.toBeInTheDocument()
      })
    })
  })

  describe('alerts display', () => {
    beforeEach(() => {
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockAlerts })
    })

    it('should display all alerts', async () => {
      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
        expect(screen.getByText('Supply Zone Retest')).toBeInTheDocument()
        // "Order Filled" appears in both Type and Title columns
        expect(screen.getAllByText('Order Filled')).toHaveLength(2)
        expect(screen.getByText('Position Closed')).toBeInTheDocument()
        expect(screen.getByText('Risk Limit Warning')).toBeInTheDocument()
      })
    })

    it('should show alert details', async () => {
      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByText('CHOCH detected on BTCUSDT 1h')).toBeInTheDocument()
        expect(
          screen.getByText('Price approaching strong supply zone at $3000'),
        ).toBeInTheDocument()
      })
    })

    it('should show timestamps', async () => {
      render(<AlertsHistory />)

      await waitFor(() => {
        // Check that time elements exist
        expect(screen.getByTestId('alert-time-alert-1')).toBeInTheDocument()
        expect(screen.getByTestId('alert-time-alert-2')).toBeInTheDocument()
      })
    })

    it('should show severity badges with correct styling', async () => {
      render(<AlertsHistory />)

      await waitFor(() => {
        const criticalBadge = screen.getByTestId('severity-badge-critical')
        expect(criticalBadge).toHaveClass('text-red-500')

        const highBadge = screen.getByTestId('severity-badge-high')
        expect(highBadge).toHaveClass('text-orange-500')

        const mediumBadge = screen.getByTestId('severity-badge-medium')
        expect(mediumBadge).toHaveClass('text-yellow-500')

        const infoBadges = screen.getAllByTestId('severity-badge-info')
        infoBadges.forEach(badge => {
          expect(badge).toHaveClass('text-gray-400')
        })
      })
    })

    it('should show venue badges', async () => {
      render(<AlertsHistory />)

      await waitFor(() => {
        const spotBadges = screen.getAllByText('SPOT')
        expect(spotBadges.length).toBeGreaterThan(0)

        const futuresBadges = screen.getAllByText('USD_M')
        expect(futuresBadges.length).toBeGreaterThan(0)
      })
    })
  })

  describe('filtering', () => {
    beforeEach(() => {
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockAlerts })
    })

    it('should filter by date range', async () => {
      const user = userEvent.setup()
      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      const dateFilter = screen.getByTestId('date-filter')
      await user.selectOptions(dateFilter, 'today')

      // Should call getAlerts with date filter
      expect(alertsService.getAlerts).toHaveBeenCalledWith(
        expect.objectContaining({
          startDate: expect.any(String),
          endDate: expect.any(String),
        }),
      )
    })

    it('should filter by alert type', async () => {
      const user = userEvent.setup()
      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      const typeFilter = screen.getByTestId('type-filter')
      await user.selectOptions(typeFilter, 'smc_event')

      expect(alertsService.getAlerts).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'smc_event',
        }),
      )
    })

    it('should filter by severity', async () => {
      const user = userEvent.setup()
      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      const severityFilter = screen.getByTestId('severity-filter')
      await user.selectOptions(severityFilter, 'critical')

      expect(alertsService.getAlerts).toHaveBeenCalledWith(
        expect.objectContaining({
          severity: 'critical',
        }),
      )
    })

    it('should filter by symbol', async () => {
      const user = userEvent.setup()
      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      const symbolInput = screen.getByPlaceholderText('Filter by symbol...')
      await user.type(symbolInput, 'ETH')

      // Should debounce and then call
      await waitFor(
        () => {
          expect(alertsService.getAlerts).toHaveBeenCalledWith(
            expect.objectContaining({
              symbol: 'ETH',
            }),
          )
        },
        { timeout: 1000 },
      )
    })
  })

  describe('pagination', () => {
    it('should show pagination controls', async () => {
      const mockManyAlerts = Array.from({ length: 25 }, (_, i) =>
        createMockAlert({
          id: `alert-${i + 1}`,
          symbol: 'BTCUSDT',
          venue: 'SPOT',
        }),
      )

      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockManyAlerts })

      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByTestId('pagination-controls')).toBeInTheDocument()
      })
    })

    it('should navigate between pages', async () => {
      const mockManyAlerts = Array.from({ length: 25 }, (_, i) =>
        createMockAlert({
          id: `alert-${i + 1}`,
          title: `Alert ${i + 1}`,
          symbol: 'BTCUSDT',
          venue: 'SPOT',
        }),
      )

      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockManyAlerts })

      const user = userEvent.setup()
      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByText('Alert 1')).toBeInTheDocument()
      })

      const nextButton = screen.getByTestId('next-page-button')
      await user.click(nextButton)

      await waitFor(() => {
        expect(screen.queryByText('Alert 1')).not.toBeInTheDocument()
        expect(screen.getByText('Alert 21')).toBeInTheDocument()
      })
    })
  })

  describe('empty state', () => {
    it('should show empty message when no alerts', async () => {
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: [] })

      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByText('No alerts found')).toBeInTheDocument()
      })
    })
  })

  describe('error handling', () => {
    it('should show error message on fetch failure', async () => {
      vi.mocked(alertsService.getAlerts).mockRejectedValue(new Error('Network error'))

      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByText('Failed to load alert history')).toBeInTheDocument()
      })
    })
  })

  describe('refresh', () => {
    it('should have refresh button', async () => {
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockAlerts })

      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByTestId('refresh-button')).toBeInTheDocument()
      })
    })

    it('should refresh data when button clicked', async () => {
      const user = userEvent.setup()
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockAlerts })

      render(<AlertsHistory />)

      await waitFor(() => {
        expect(screen.getByTestId('refresh-button')).toBeInTheDocument()
      })

      vi.clearAllMocks()

      const refreshButton = screen.getByTestId('refresh-button')
      await user.click(refreshButton)

      expect(alertsService.getAlerts).toHaveBeenCalledTimes(1)
    })
  })
})
