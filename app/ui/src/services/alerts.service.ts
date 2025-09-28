import { apiClient } from './api'
import { websocketService } from './websocket'
import type { Alert, AlertId, AlertFilters, AlertStats } from '@/types/alerts'

export type AlertsResponse = {
  alerts: Alert[]
  total: number
  page: number
  limit: number
}

export type AlertSearchResponse = {
  alerts: Alert[]
  total: number
}

class AlertsService {
  async getAlerts(page = 1, limit = 20, filters?: AlertFilters): Promise<AlertsResponse> {
    const params = {
      page,
      limit,
      ...filters,
    }

    return await apiClient.get<AlertsResponse>('/api/alerts', { params })
  }

  async getAlert(id: AlertId): Promise<Alert> {
    return await apiClient.get<Alert>(`/api/alerts/${id}`)
  }

  async markAsRead(id: AlertId): Promise<Alert> {
    return await apiClient.put<Alert>(`/api/alerts/${id}/read`)
  }

  async markAllAsRead(): Promise<{ updated: number }> {
    return await apiClient.put<{ updated: number }>('/api/alerts/read-all')
  }

  async deleteAlert(id: AlertId): Promise<void> {
    await apiClient.delete(`/api/alerts/${id}`)
  }

  async getStats(): Promise<AlertStats> {
    return await apiClient.get<AlertStats>('/api/alerts/stats')
  }

  async getUnreadCount(): Promise<number> {
    const response = await apiClient.get<{ count: number }>('/api/alerts/unread-count')
    return response.count
  }

  subscribeToAlerts(callback: (alert: Alert) => void): () => void {
    websocketService.emit('alerts:subscribe', {})
    return websocketService.subscribe('alert.new', callback)
  }

  unsubscribeFromAlerts(): void {
    websocketService.emit('alerts:unsubscribe', {})
  }

  async searchAlerts(query: string, limit = 50): Promise<AlertSearchResponse> {
    return await apiClient.get<AlertSearchResponse>('/api/alerts/search', {
      params: { q: query, limit },
    })
  }

  async exportAlerts(format: 'csv' | 'json', filters?: AlertFilters): Promise<Blob> {
    const params = {
      format,
      ...filters,
    }

    // Note: responseType is not supported in current apiClient
    // This would need special handling for blob responses
    return await apiClient.get<Blob>('/api/alerts/export', { params })
  }
}

export const alertsService = new AlertsService()
