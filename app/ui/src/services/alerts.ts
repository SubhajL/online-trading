import { apiClient } from './api'
import type { Alert } from '@/types'

type GetAlertsResponse = {
  alerts: Alert[]
}

type MarkAsReadResponse = {
  success: boolean
}

type DismissAlertResponse = {
  success: boolean
}

class AlertsService {
  async getAlerts(filters?: {
    type?: string
    severity?: string
    read?: boolean
    symbol?: string
    venue?: string
    limit?: number
    startDate?: string
    endDate?: string
  }): Promise<GetAlertsResponse> {
    return apiClient.get<GetAlertsResponse>('/alerts', { params: filters })
  }

  async markAsRead(alertIds: string | string[]): Promise<MarkAsReadResponse> {
    const ids = Array.isArray(alertIds) ? alertIds : [alertIds]
    return apiClient.post<MarkAsReadResponse>('/alerts/mark-read', { alertIds: ids })
  }

  async dismissAlert(alertId: string): Promise<DismissAlertResponse> {
    return apiClient.delete<DismissAlertResponse>(`/alerts/${alertId}`)
  }
}

export const alertsService = new AlertsService()
