import { describe, it, expect, vi, beforeEach } from 'vitest'
import { alertsService } from './alerts.service'
import { apiClient } from './api'
import { alertsWebsocketService } from './websocket'
import type { Alert, AlertFilters, AlertStats } from '@/types/alerts'

vi.mock('./api', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('./websocket', () => ({
  alertsWebsocketService: {
    on: vi.fn(),
    emit: vi.fn(),
    off: vi.fn(),
    subscribe: vi.fn(),
  },
}))

describe('alertsService', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  const mockAlert: Alert = {
    id: 'alert-123' as any,
    type: 'order',
    priority: 'high',
    title: 'Order Filled',
    message: 'BTC order filled at $45,000',
    data: { symbol: 'BTCUSDT', price: 45000 },
    read: false,
    createdAt: '2024-01-01T00:00:00Z',
  }

  describe('getAlerts', () => {
    it('should fetch alerts with default pagination', async () => {
      const mockResponse = {
        data: [mockAlert],
        total: 1,
        page: 1,
        limit: 20,
      }
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse)

      const result = await alertsService.getAlerts()

      expect(apiClient.get).toHaveBeenCalledWith('/alerts', {
        params: { page: 1, limit: 20 },
      })
      expect(result).toEqual(mockResponse)
    })

    it('should fetch alerts with filters', async () => {
      const filters: AlertFilters = {
        type: 'order',
        priority: 'high',
        read: false,
      }
      const mockResponse = { data: [mockAlert], total: 1, page: 1, limit: 20 }
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse)

      await alertsService.getAlerts(1, 20, filters)

      expect(apiClient.get).toHaveBeenCalledWith('/alerts', {
        params: {
          page: 1,
          limit: 20,
          type: 'order',
          priority: 'high',
          read: false,
        },
      })
    })
  })

  describe('getAlert', () => {
    it('should fetch single alert by id', async () => {
      vi.mocked(apiClient.get).mockResolvedValue(mockAlert)

      const result = await alertsService.getAlert('alert-123' as any)

      expect(apiClient.get).toHaveBeenCalledWith('/alerts/alert-123')
      expect(result).toEqual(mockAlert)
    })
  })

  describe('markAsRead', () => {
    it('should mark alert as read', async () => {
      const updatedAlert = { ...mockAlert, read: true }
      vi.mocked(apiClient.put).mockResolvedValue(updatedAlert)

      const result = await alertsService.markAsRead('alert-123' as any)

      expect(apiClient.put).toHaveBeenCalledWith('/alerts/alert-123/read')
      expect(result.read).toBe(true)
    })
  })

  describe('markAllAsRead', () => {
    it('should mark all alerts as read', async () => {
      vi.mocked(apiClient.put).mockResolvedValue({ updated: 5 })

      const result = await alertsService.markAllAsRead()

      expect(apiClient.put).toHaveBeenCalledWith('/alerts/read-all')
      expect(result).toEqual({ updated: 5 })
    })
  })

  describe('deleteAlert', () => {
    it('should delete alert by id', async () => {
      vi.mocked(apiClient.delete).mockResolvedValue({ success: true })

      await alertsService.deleteAlert('alert-123' as any)

      expect(apiClient.delete).toHaveBeenCalledWith('/alerts/alert-123')
    })
  })

  describe('getStats', () => {
    it('should fetch alert statistics', async () => {
      const mockStats: AlertStats = {
        total: 100,
        unread: 25,
        byType: { order: 30, position: 20, decision: 15, smc: 20, error: 10, info: 5 },
        byPriority: { low: 40, medium: 30, high: 20, critical: 10 },
      }
      vi.mocked(apiClient.get).mockResolvedValue(mockStats)

      const result = await alertsService.getStats()

      expect(apiClient.get).toHaveBeenCalledWith('/alerts/stats')
      expect(result).toEqual(mockStats)
    })
  })

  describe('getUnreadCount', () => {
    it('should fetch unread alert count', async () => {
      vi.mocked(apiClient.get).mockResolvedValue({ count: 5 })

      const result = await alertsService.getUnreadCount()

      expect(apiClient.get).toHaveBeenCalledWith('/alerts/unread-count')
      expect(result).toBe(5)
    })
  })

  describe('subscribeToAlerts', () => {
    it('should subscribe to alert events', () => {
      const callback = vi.fn()
      const unsubscribeAlertNew = vi.fn()
      vi.mocked(alertsWebsocketService.subscribe).mockReturnValue(unsubscribeAlertNew)

      const result = alertsService.subscribeToAlerts(callback)

      expect(alertsWebsocketService.on).toHaveBeenCalledWith('connect', expect.any(Function))
      expect(alertsWebsocketService.emit).toHaveBeenCalledWith('alerts:subscribe', {})
      expect(alertsWebsocketService.subscribe).toHaveBeenCalledWith('alert.new', callback)
      expect(result).toBeTypeOf('function')
    })

    it('should not throw when alerts websocket is disconnected', () => {
      const callback = vi.fn()
      vi.mocked(alertsWebsocketService.emit).mockImplementation(() => {
        throw new Error('WebSocket is not connected')
      })
      vi.mocked(alertsWebsocketService.subscribe).mockReturnValue(() => {})

      expect(() => alertsService.subscribeToAlerts(callback)).not.toThrow()
      expect(alertsWebsocketService.emit).toHaveBeenCalledWith('alerts:subscribe', {})
    })
  })

  describe('unsubscribeFromAlerts', () => {
    it('is deprecated no-op for backward compatibility', () => {
      alertsService.unsubscribeFromAlerts()

      expect(alertsWebsocketService.emit).not.toHaveBeenCalled()
    })
  })

  describe('searchAlerts', () => {
    it('should search alerts by query', async () => {
      const mockResults = { data: [mockAlert], total: 1 }
      vi.mocked(apiClient.get).mockResolvedValue(mockResults)

      const result = await alertsService.searchAlerts('BTC')

      expect(apiClient.get).toHaveBeenCalledWith('/alerts/search', {
        params: { q: 'BTC', limit: 50 },
      })
      expect(result).toEqual(mockResults)
    })

    it('should search with custom limit', async () => {
      const mockResults = { data: [], total: 0 }
      vi.mocked(apiClient.get).mockResolvedValue(mockResults)

      await alertsService.searchAlerts('ETH', 10)

      expect(apiClient.get).toHaveBeenCalledWith('/alerts/search', {
        params: { q: 'ETH', limit: 10 },
      })
    })
  })

  describe('exportAlerts', () => {
    it('should export alerts as CSV', async () => {
      const mockBlob = new Blob(['csv data'])
      vi.mocked(apiClient.get).mockResolvedValue(mockBlob)

      const result = await alertsService.exportAlerts('csv')

      expect(apiClient.get).toHaveBeenCalledWith('/alerts/export', {
        params: { format: 'csv' },
      })
      expect(result).toEqual(mockBlob)
    })

    it('should export alerts as JSON with filters', async () => {
      const mockBlob = new Blob(['json data'])
      const filters: AlertFilters = { type: 'order', priority: 'high' }
      vi.mocked(apiClient.get).mockResolvedValue(mockBlob)

      await alertsService.exportAlerts('json', filters)

      expect(apiClient.get).toHaveBeenCalledWith('/alerts/export', {
        params: { format: 'json', type: 'order', priority: 'high' },
      })
    })
  })
})
