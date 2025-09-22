import { describe, it, expect, vi, beforeEach } from 'vitest'
import { alertsService } from './alerts.service'
import { apiClient } from './api.client'
import { websocketService } from './websocket.service'
import type { Alert, AlertFilters, AlertStats } from '@/types/alerts'

vi.mock('./api.client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('./websocket.service', () => ({
  websocketService: {
    on: vi.fn(),
    emit: vi.fn(),
    off: vi.fn(),
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
        alerts: [mockAlert],
        total: 1,
        page: 1,
        limit: 20,
      }
      vi.mocked(apiClient.get).mockResolvedValue({ data: mockResponse })

      const result = await alertsService.getAlerts()

      expect(apiClient.get).toHaveBeenCalledWith('/api/alerts', {
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
      const mockResponse = { alerts: [mockAlert], total: 1, page: 1, limit: 20 }
      vi.mocked(apiClient.get).mockResolvedValue({ data: mockResponse })

      await alertsService.getAlerts(1, 20, filters)

      expect(apiClient.get).toHaveBeenCalledWith('/api/alerts', {
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
      vi.mocked(apiClient.get).mockResolvedValue({ data: mockAlert })

      const result = await alertsService.getAlert('alert-123' as any)

      expect(apiClient.get).toHaveBeenCalledWith('/api/alerts/alert-123')
      expect(result).toEqual(mockAlert)
    })
  })

  describe('markAsRead', () => {
    it('should mark alert as read', async () => {
      const updatedAlert = { ...mockAlert, read: true }
      vi.mocked(apiClient.put).mockResolvedValue({ data: updatedAlert })

      const result = await alertsService.markAsRead('alert-123' as any)

      expect(apiClient.put).toHaveBeenCalledWith('/api/alerts/alert-123/read')
      expect(result.read).toBe(true)
    })
  })

  describe('markAllAsRead', () => {
    it('should mark all alerts as read', async () => {
      vi.mocked(apiClient.put).mockResolvedValue({ data: { updated: 5 } })

      const result = await alertsService.markAllAsRead()

      expect(apiClient.put).toHaveBeenCalledWith('/api/alerts/read-all')
      expect(result).toEqual({ updated: 5 })
    })
  })

  describe('deleteAlert', () => {
    it('should delete alert by id', async () => {
      vi.mocked(apiClient.delete).mockResolvedValue({ data: { success: true } })

      await alertsService.deleteAlert('alert-123' as any)

      expect(apiClient.delete).toHaveBeenCalledWith('/api/alerts/alert-123')
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
      vi.mocked(apiClient.get).mockResolvedValue({ data: mockStats })

      const result = await alertsService.getStats()

      expect(apiClient.get).toHaveBeenCalledWith('/api/alerts/stats')
      expect(result).toEqual(mockStats)
    })
  })

  describe('getUnreadCount', () => {
    it('should fetch unread alert count', async () => {
      vi.mocked(apiClient.get).mockResolvedValue({ data: { count: 5 } })

      const result = await alertsService.getUnreadCount()

      expect(apiClient.get).toHaveBeenCalledWith('/api/alerts/unread-count')
      expect(result).toBe(5)
    })
  })

  describe('subscribeToAlerts', () => {
    it('should subscribe to alert events', () => {
      const callback = vi.fn()
      const unsubscribe = vi.fn()
      vi.mocked(websocketService.on).mockReturnValue(unsubscribe)

      const result = alertsService.subscribeToAlerts(callback)

      expect(websocketService.emit).toHaveBeenCalledWith('alerts:subscribe')
      expect(websocketService.on).toHaveBeenCalledWith('alert.new', callback)
      expect(result).toBe(unsubscribe)
    })
  })

  describe('unsubscribeFromAlerts', () => {
    it('should unsubscribe from alert events', () => {
      alertsService.unsubscribeFromAlerts()

      expect(websocketService.emit).toHaveBeenCalledWith('alerts:unsubscribe')
    })
  })

  describe('searchAlerts', () => {
    it('should search alerts by query', async () => {
      const mockResults = { alerts: [mockAlert], total: 1 }
      vi.mocked(apiClient.get).mockResolvedValue({ data: mockResults })

      const result = await alertsService.searchAlerts('BTC')

      expect(apiClient.get).toHaveBeenCalledWith('/api/alerts/search', {
        params: { q: 'BTC', limit: 50 },
      })
      expect(result).toEqual(mockResults)
    })

    it('should search with custom limit', async () => {
      const mockResults = { alerts: [], total: 0 }
      vi.mocked(apiClient.get).mockResolvedValue({ data: mockResults })

      await alertsService.searchAlerts('ETH', 10)

      expect(apiClient.get).toHaveBeenCalledWith('/api/alerts/search', {
        params: { q: 'ETH', limit: 10 },
      })
    })
  })

  describe('exportAlerts', () => {
    it('should export alerts as CSV', async () => {
      const mockBlob = new Blob(['csv data'])
      vi.mocked(apiClient.get).mockResolvedValue({ data: mockBlob })

      const result = await alertsService.exportAlerts('csv')

      expect(apiClient.get).toHaveBeenCalledWith('/api/alerts/export', {
        params: { format: 'csv' },
        responseType: 'blob',
      })
      expect(result).toEqual(mockBlob)
    })

    it('should export alerts as JSON with filters', async () => {
      const mockBlob = new Blob(['json data'])
      const filters: AlertFilters = { type: 'order', priority: 'high' }
      vi.mocked(apiClient.get).mockResolvedValue({ data: mockBlob })

      await alertsService.exportAlerts('json', filters)

      expect(apiClient.get).toHaveBeenCalledWith('/api/alerts/export', {
        params: { format: 'json', type: 'order', priority: 'high' },
        responseType: 'blob',
      })
    })
  })
})