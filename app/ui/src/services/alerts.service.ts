import { apiClient } from './api.client'
import { websocketService } from './websocket.service'
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
  async getAlerts(
    page = 1,
    limit = 20,
    filters?: AlertFilters
  ): Promise<AlertsResponse> {
    const params = {
      page,
      limit,
      ...filters,
    }

    const response = await apiClient.get<AlertsResponse>('/api/alerts', { params })
    return response.data
  }

  async getAlert(id: AlertId): Promise<Alert> {
    const response = await apiClient.get<Alert>(`/api/alerts/${id}`)
    return response.data
  }

  async markAsRead(id: AlertId): Promise<Alert> {
    const response = await apiClient.put<Alert>(`/api/alerts/${id}/read`)
    return response.data
  }

  async markAllAsRead(): Promise<{ updated: number }> {
    const response = await apiClient.put<{ updated: number }>('/api/alerts/read-all')
    return response.data
  }

  async deleteAlert(id: AlertId): Promise<void> {
    await apiClient.delete(`/api/alerts/${id}`)
  }

  async getStats(): Promise<AlertStats> {
    const response = await apiClient.get<AlertStats>('/api/alerts/stats')
    return response.data
  }

  async getUnreadCount(): Promise<number> {
    const response = await apiClient.get<{ count: number }>('/api/alerts/unread-count')
    return response.data.count
  }

  subscribeToAlerts(callback: (alert: Alert) => void): () => void {
    websocketService.emit('alerts:subscribe')
    return websocketService.on('alert.new', callback)
  }

  unsubscribeFromAlerts(): void {
    websocketService.emit('alerts:unsubscribe')
  }

  async searchAlerts(query: string, limit = 50): Promise<AlertSearchResponse> {
    const response = await apiClient.get<AlertSearchResponse>('/api/alerts/search', {
      params: { q: query, limit },
    })
    return response.data
  }

  async exportAlerts(
    format: 'csv' | 'json',
    filters?: AlertFilters
  ): Promise<Blob> {
    const params = {
      format,
      ...filters,
    }

    const response = await apiClient.get<Blob>('/api/alerts/export', {
      params,
      responseType: 'blob',
    })
    return response.data
  }
}

export const alertsService = new AlertsService()