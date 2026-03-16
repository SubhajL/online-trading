import { apiClient } from './api'
import { alertsWebsocketService } from './websocket'
import type { Alert, AlertId, AlertFilters, AlertStats } from '@/types/alerts'

export type AlertsResponse = {
  data: Alert[]
  total: number
  page: number
  limit: number
}

export type AlertSearchResponse = {
  data: Alert[]
  total: number
}

class AlertsService {
  async getAlerts(page = 1, limit = 20, filters?: AlertFilters): Promise<AlertsResponse> {
    const params = {
      page,
      limit,
      ...filters,
    }

    return await apiClient.get<AlertsResponse>('/alerts', { params })
  }

  async getAlert(id: AlertId): Promise<Alert> {
    return await apiClient.get<Alert>(`/alerts/${id}`)
  }

  async markAsRead(id: AlertId): Promise<Alert> {
    return await apiClient.put<Alert>(`/alerts/${id}/read`)
  }

  async markAllAsRead(): Promise<{ updated: number }> {
    return await apiClient.put<{ updated: number }>('/alerts/read-all')
  }

  async deleteAlert(id: AlertId): Promise<void> {
    await apiClient.delete(`/alerts/${id}`)
  }

  async getStats(): Promise<AlertStats> {
    return await apiClient.get<AlertStats>('/alerts/stats')
  }

  async getUnreadCount(): Promise<number> {
    const response = await apiClient.get<{ count: number }>('/alerts/unread-count')
    return response.count
  }

  subscribeToAlerts(callback: (alert: Alert) => void): () => void {
    const subscribe = () => {
      try {
        alertsWebsocketService.emit('alerts:subscribe', {})
      } catch {
        // Fail-open: socket may not be connected yet
      }
    }

    // Re-subscribe on reconnect (Socket.IO reconnects can drop rooms)
    alertsWebsocketService.on('connect', subscribe)
    subscribe()

    const unsubscribeAlertNew = alertsWebsocketService.subscribe('alert.new', callback)

    return () => {
      alertsWebsocketService.off('connect', subscribe)
      unsubscribeAlertNew()
      try {
        alertsWebsocketService.emit('alerts:unsubscribe', {})
      } catch {
        // Fail-open on disconnect
      }
    }
  }

  /**
   * @deprecated Use the cleanup function returned by subscribeToAlerts().
   */
  unsubscribeFromAlerts(): void {
    // Deprecated: rely on the cleanup function returned by subscribeToAlerts().
    // Kept as a no-op for backward compatibility.
  }

  async searchAlerts(query: string, limit = 50): Promise<AlertSearchResponse> {
    return await apiClient.get<AlertSearchResponse>('/alerts/search', {
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
    return await apiClient.get<Blob>('/alerts/export', { params })
  }
}

export const alertsService = new AlertsService()
