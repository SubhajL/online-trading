import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AlertsPopup } from './AlertsPopup'
import type { Alert } from '@/types'

// Mock the alerts service
vi.mock('@/services/alerts', () => ({
  alertsService: {
    getAlerts: vi.fn(),
    markAsRead: vi.fn(),
    dismissAlert: vi.fn(),
  },
}))

import { alertsService } from '@/services/alerts'

describe('AlertsPopup', () => {
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
      read: false,
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
      read: false,
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
  ]

  const mockOnClose = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('should render popup when open', () => {
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      expect(screen.getByTestId('alerts-popup')).toBeInTheDocument()
    })

    it('should not render when closed', () => {
      render(<AlertsPopup isOpen={false} onClose={mockOnClose} />)

      expect(screen.queryByTestId('alerts-popup')).not.toBeInTheDocument()
    })

    it('should show popup header', () => {
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      expect(screen.getByText('Alerts')).toBeInTheDocument()
    })

    it('should show close button', () => {
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      expect(screen.getByTestId('close-button')).toBeInTheDocument()
    })
  })

  describe('loading state', () => {
    it('should show loading spinner while fetching', async () => {
      vi.mocked(alertsService.getAlerts).mockImplementation(
        () => new Promise(resolve => setTimeout(() => resolve({ alerts: [] }), 100)),
      )

      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

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
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
        expect(screen.getByText('Supply Zone Retest')).toBeInTheDocument()
        expect(screen.getByText('Order Filled')).toBeInTheDocument()
      })
    })

    it('should show alert messages', async () => {
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('CHOCH detected on BTCUSDT 1h')).toBeInTheDocument()
        expect(
          screen.getByText('Price approaching strong supply zone at $3000'),
        ).toBeInTheDocument()
      })
    })

    it('should show severity badges', async () => {
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByTestId('severity-badge-high')).toBeInTheDocument()
        expect(screen.getByTestId('severity-badge-medium')).toBeInTheDocument()
        expect(screen.getByTestId('severity-badge-info')).toBeInTheDocument()
      })
    })

    it('should show unread indicator', async () => {
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        const unreadIndicators = screen.getAllByTestId('unread-indicator')
        expect(unreadIndicators).toHaveLength(2) // Two unread alerts
      })
    })

    it('should show relative time', async () => {
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        // Check that time elements exist
        expect(screen.getByTestId('alert-time-alert-1')).toBeInTheDocument()
        expect(screen.getByTestId('alert-time-alert-2')).toBeInTheDocument()
        expect(screen.getByTestId('alert-time-alert-3')).toBeInTheDocument()
      })
    })
  })

  describe('interactions', () => {
    beforeEach(() => {
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockAlerts })
      vi.mocked(alertsService.markAsRead).mockResolvedValue({ success: true })
      vi.mocked(alertsService.dismissAlert).mockResolvedValue({ success: true })
    })

    it('should call onClose when close button clicked', async () => {
      const user = userEvent.setup()
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      const closeButton = screen.getByTestId('close-button')
      await user.click(closeButton)

      expect(mockOnClose).toHaveBeenCalledTimes(1)
    })

    it('should mark alert as read when clicked', async () => {
      const user = userEvent.setup()
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      const alertItem = screen.getByTestId('alert-item-alert-1')
      await user.click(alertItem)

      expect(alertsService.markAsRead).toHaveBeenCalledWith('alert-1')
    })

    it('should dismiss alert when dismiss button clicked', async () => {
      const user = userEvent.setup()
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      const dismissButton = screen.getByTestId('dismiss-alert-alert-1')
      await user.click(dismissButton)

      expect(alertsService.dismissAlert).toHaveBeenCalledWith('alert-1')
    })

    it('should remove dismissed alert from list', async () => {
      const user = userEvent.setup()
      vi.mocked(alertsService.dismissAlert).mockResolvedValue({ success: true })

      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      const dismissButton = screen.getByTestId('dismiss-alert-alert-1')
      await user.click(dismissButton)

      await waitFor(() => {
        expect(screen.queryByText('Bullish Change of Character')).not.toBeInTheDocument()
      })
    })
  })

  describe('empty state', () => {
    it('should show empty message when no alerts', async () => {
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: [] })

      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('No new alerts')).toBeInTheDocument()
      })
    })
  })

  describe('error handling', () => {
    it('should show error message on fetch failure', async () => {
      vi.mocked(alertsService.getAlerts).mockRejectedValue(new Error('Network error'))

      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('Failed to load alerts')).toBeInTheDocument()
      })
    })
  })

  describe('filtering', () => {
    beforeEach(() => {
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockAlerts })
    })

    it('should filter by alert type', async () => {
      const user = userEvent.setup()
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      const typeFilter = screen.getByTestId('type-filter')
      await user.selectOptions(typeFilter, 'smc_event')

      expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      expect(screen.queryByText('Supply Zone Retest')).not.toBeInTheDocument()
      expect(screen.queryByText('Order Filled')).not.toBeInTheDocument()
    })

    it('should filter by severity', async () => {
      const user = userEvent.setup()
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      const severityFilter = screen.getByTestId('severity-filter')
      await user.selectOptions(severityFilter, 'high')

      expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      expect(screen.queryByText('Supply Zone Retest')).not.toBeInTheDocument()
      expect(screen.queryByText('Order Filled')).not.toBeInTheDocument()
    })

    it('should filter unread only', async () => {
      const user = userEvent.setup()
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      const unreadOnlyCheckbox = screen.getByTestId('unread-only-filter')
      await user.click(unreadOnlyCheckbox)

      expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      expect(screen.getByText('Supply Zone Retest')).toBeInTheDocument()
      expect(screen.queryByText('Order Filled')).not.toBeInTheDocument()
    })
  })

  describe('mark all as read', () => {
    it('should have mark all as read button', async () => {
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockAlerts })

      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByTestId('mark-all-read-button')).toBeInTheDocument()
      })
    })

    it('should mark all alerts as read', async () => {
      const user = userEvent.setup()
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockAlerts })

      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByTestId('mark-all-read-button')).toBeInTheDocument()
      })

      const markAllButton = screen.getByTestId('mark-all-read-button')
      await user.click(markAllButton)

      expect(alertsService.markAsRead).toHaveBeenCalledWith(['alert-1', 'alert-2'])
    })
  })

  describe('snapshot images', () => {
    it('should display snapshot image when available', async () => {
      const alertsWithImage: Alert[] = [
        {
          id: 'alert-4',
          symbol: 'BTCUSDT',
          venue: 'SPOT',
          type: 'smc_event',
          title: 'Trading Signal',
          message: 'Long entry signal detected',
          severity: 'high',
          createdAt: new Date().toISOString(),
          read: false,
          imageUrl: '/snapshots/signal-123.png',
          signalId: 'signal-123',
        },
      ]

      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: alertsWithImage })

      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        const image = screen.getByAltText('Trading Signal snapshot')
        expect(image).toBeInTheDocument()
        expect(image).toHaveAttribute('src', '/snapshots/signal-123.png')
      })
    })

    it('should open image in new tab when clicked', async () => {
      const alertsWithImage: Alert[] = [
        {
          id: 'alert-4',
          symbol: 'BTCUSDT',
          venue: 'SPOT',
          type: 'smc_event',
          title: 'Trading Signal',
          message: 'Long entry signal detected',
          severity: 'high',
          createdAt: new Date().toISOString(),
          read: false,
          imageUrl: '/snapshots/signal-123.png',
          signalId: 'signal-123',
        },
      ]

      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: alertsWithImage })
      const mockOpen = vi.fn()
      window.open = mockOpen

      const user = userEvent.setup()
      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByAltText('Trading Signal snapshot')).toBeInTheDocument()
      })

      const image = screen.getByAltText('Trading Signal snapshot')
      await user.click(image)

      expect(mockOpen).toHaveBeenCalledWith('/snapshots/signal-123.png', '_blank')
    })

    it('should not display image section when no imageUrl', async () => {
      vi.mocked(alertsService.getAlerts).mockResolvedValue({ alerts: mockAlerts })

      render(<AlertsPopup isOpen={true} onClose={mockOnClose} />)

      await waitFor(() => {
        expect(screen.getByText('Bullish Change of Character')).toBeInTheDocument()
      })

      // No images should be in the document
      const images = screen.queryAllByRole('img')
      expect(images).toHaveLength(0)
    })
  })
})
