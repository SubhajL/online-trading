import { useState, useEffect } from 'react'
import { alertsService } from '@/services/alerts'
import type { Alert, AlertType, AlertSeverity } from '@/types'

type AlertsPopupProps = {
  isOpen: boolean
  onClose: () => void
}

const SEVERITY_COLORS: Record<AlertSeverity, { bg: string; text: string; border: string }> = {
  critical: { bg: 'bg-red-500/10', text: 'text-red-500', border: 'border-red-500' },
  high: { bg: 'bg-orange-500/10', text: 'text-orange-500', border: 'border-orange-500' },
  medium: { bg: 'bg-yellow-500/10', text: 'text-yellow-500', border: 'border-yellow-500' },
  low: { bg: 'bg-blue-500/10', text: 'text-blue-500', border: 'border-blue-500' },
  info: { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500' },
}

const formatRelativeTime = (dateString: string): string => {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return 'Just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export function AlertsPopup({ isOpen, onClose }: AlertsPopupProps) {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState<AlertType | ''>('')
  const [severityFilter, setSeverityFilter] = useState<AlertSeverity | ''>('')
  const [unreadOnly, setUnreadOnly] = useState(false)

  useEffect(() => {
    if (isOpen) {
      fetchAlerts()
    }
  }, [isOpen])

  const fetchAlerts = async () => {
    try {
      setLoading(true)
      setError(null)
      const { alerts } = await alertsService.getAlerts()
      setAlerts(alerts)
    } catch (err) {
      setError('Failed to load alerts')
    } finally {
      setLoading(false)
    }
  }

  const handleMarkAsRead = async (alertId: string) => {
    try {
      await alertsService.markAsRead(alertId)
      setAlerts(alerts.map(a => (a.id === alertId ? { ...a, read: true } : a)))
    } catch (err) {
      console.error('Failed to mark alert as read:', err)
    }
  }

  const handleDismiss = async (alertId: string) => {
    try {
      await alertsService.dismissAlert(alertId)
      setAlerts(alerts.filter(a => a.id !== alertId))
    } catch (err) {
      console.error('Failed to dismiss alert:', err)
    }
  }

  const handleMarkAllAsRead = async () => {
    const unreadIds = alerts.filter(a => !a.read).map(a => a.id)
    if (unreadIds.length === 0) return

    try {
      await alertsService.markAsRead(unreadIds)
      setAlerts(alerts.map(a => ({ ...a, read: true })))
    } catch (err) {
      console.error('Failed to mark all as read:', err)
    }
  }

  const filteredAlerts = alerts.filter(alert => {
    if (typeFilter && alert.type !== typeFilter) return false
    if (severityFilter && alert.severity !== severityFilter) return false
    if (unreadOnly && alert.read) return false
    return true
  })

  if (!isOpen) return null

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/50 z-40" onClick={onClose} />

      {/* Popup */}
      <div
        data-testid="alerts-popup"
        className="fixed top-4 right-4 w-96 max-h-[80vh] bg-gray-900 rounded-lg shadow-2xl z-50 flex flex-col"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-800">
          <h2 className="text-lg font-semibold text-white">Alerts</h2>
          <button
            data-testid="close-button"
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Filters */}
        <div className="p-4 border-b border-gray-800 space-y-2">
          <div className="flex gap-2">
            <select
              data-testid="type-filter"
              value={typeFilter}
              onChange={e => setTypeFilter(e.target.value as AlertType | '')}
              className="flex-1 px-2 py-1 bg-gray-800 text-white text-sm rounded border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            >
              <option value="">All Types</option>
              <option value="smc_event">SMC Events</option>
              <option value="zone_retest">Zone Retests</option>
              <option value="order_filled">Orders</option>
              <option value="position_update">Positions</option>
              <option value="risk_limit">Risk Limits</option>
            </select>

            <select
              data-testid="severity-filter"
              value={severityFilter}
              onChange={e => setSeverityFilter(e.target.value as AlertSeverity | '')}
              className="flex-1 px-2 py-1 bg-gray-800 text-white text-sm rounded border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            >
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
              <option value="info">Info</option>
            </select>
          </div>

          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-gray-400">
              <input
                data-testid="unread-only-filter"
                type="checkbox"
                checked={unreadOnly}
                onChange={e => setUnreadOnly(e.target.checked)}
                className="rounded border-gray-600 text-blue-500 focus:ring-blue-500"
              />
              Unread only
            </label>

            <button
              data-testid="mark-all-read-button"
              onClick={handleMarkAllAsRead}
              className="text-xs text-blue-500 hover:text-blue-400"
            >
              Mark all as read
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex justify-center items-center h-32">
              <div
                data-testid="loading-spinner"
                className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"
              />
            </div>
          ) : error ? (
            <div className="p-4 text-center text-red-500">{error}</div>
          ) : filteredAlerts.length === 0 ? (
            <div className="p-4 text-center text-gray-500">No new alerts</div>
          ) : (
            <div className="divide-y divide-gray-800">
              {filteredAlerts.map(alert => (
                <div
                  key={alert.id}
                  data-testid={`alert-item-${alert.id}`}
                  onClick={() => !alert.read && handleMarkAsRead(alert.id)}
                  className={`p-4 hover:bg-gray-800/50 cursor-pointer transition-colors ${
                    !alert.read ? 'bg-gray-800/30' : ''
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {/* Unread indicator */}
                    {!alert.read && (
                      <div
                        data-testid="unread-indicator"
                        className="w-2 h-2 bg-blue-500 rounded-full mt-1.5"
                      />
                    )}

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1">
                          <h3 className="text-sm font-medium text-white truncate">{alert.title}</h3>
                          <p className="text-xs text-gray-400 mt-1">{alert.message}</p>

                          {/* Snapshot Image */}
                          {alert.imageUrl && (
                            <div className="mt-2">
                              <img
                                src={alert.imageUrl}
                                alt={`${alert.title} snapshot`}
                                className="w-full rounded border border-gray-700 cursor-pointer hover:opacity-90 transition-opacity"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  window.open(alert.imageUrl, '_blank')
                                }}
                              />
                            </div>
                          )}
                        </div>

                        {/* Severity badge */}
                        <span
                          data-testid={`severity-badge-${alert.severity}`}
                          className={`px-2 py-1 text-xs rounded ${SEVERITY_COLORS[alert.severity]?.bg || ''} ${SEVERITY_COLORS[alert.severity]?.text || ''}`}
                        >
                          {alert.severity}
                        </span>
                      </div>

                      {/* Footer */}
                      <div className="flex items-center justify-between mt-2">
                        <span
                          data-testid={`alert-time-${alert.id}`}
                          className="text-xs text-gray-500"
                        >
                          {formatRelativeTime(alert.createdAt)}
                        </span>

                        <button
                          data-testid={`dismiss-alert-${alert.id}`}
                          onClick={e => {
                            e.stopPropagation()
                            handleDismiss(alert.id)
                          }}
                          className="text-xs text-gray-500 hover:text-red-400 transition-colors"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  )
}
