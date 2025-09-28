import { useState, useEffect, useCallback } from 'react'
import { alertsService } from '@/services/alerts'
import type { Alert, AlertType, AlertSeverity } from '@/types'

const SEVERITY_COLORS: Record<AlertSeverity, { bg: string; text: string }> = {
  critical: { bg: 'bg-red-500/10', text: 'text-red-500' },
  high: { bg: 'bg-orange-500/10', text: 'text-orange-500' },
  medium: { bg: 'bg-yellow-500/10', text: 'text-yellow-500' },
  low: { bg: 'bg-blue-500/10', text: 'text-blue-500' },
  info: { bg: 'bg-gray-500/10', text: 'text-gray-400' },
}

const ITEMS_PER_PAGE = 20

const getDateRange = (filter: string): { startDate: string; endDate: string } => {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())

  switch (filter) {
    case 'today':
      return {
        startDate: today.toISOString(),
        endDate: now.toISOString(),
      }
    case 'week':
      const weekAgo = new Date(today)
      weekAgo.setDate(weekAgo.getDate() - 7)
      return {
        startDate: weekAgo.toISOString(),
        endDate: now.toISOString(),
      }
    case 'month':
      const monthAgo = new Date(today)
      monthAgo.setMonth(monthAgo.getMonth() - 1)
      return {
        startDate: monthAgo.toISOString(),
        endDate: now.toISOString(),
      }
    default:
      return {
        startDate: '',
        endDate: '',
      }
  }
}

export function AlertsHistory() {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [currentPage, setCurrentPage] = useState(1)

  // Filters
  const [dateFilter, setDateFilter] = useState<string>('all')
  const [typeFilter, setTypeFilter] = useState<AlertType | ''>('')
  const [severityFilter, setSeverityFilter] = useState<AlertSeverity | ''>('')
  const [symbolFilter, setSymbolFilter] = useState('')
  const [debouncedSymbolFilter, setDebouncedSymbolFilter] = useState('')

  // Debounce symbol filter
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSymbolFilter(symbolFilter)
    }, 500)

    return () => clearTimeout(timer)
  }, [symbolFilter])

  const fetchAlerts = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const dateRange = getDateRange(dateFilter)
      const filters: {
        type?: string
        severity?: string
        read?: boolean
        symbol?: string
        venue?: string
        limit?: number
        startDate?: string
        endDate?: string
      } = {}

      if (dateRange.startDate) {
        filters.startDate = dateRange.startDate
        filters.endDate = dateRange.endDate
      }
      if (typeFilter) filters.type = typeFilter
      if (severityFilter) filters.severity = severityFilter
      if (debouncedSymbolFilter) filters.symbol = debouncedSymbolFilter

      const { alerts } = await alertsService.getAlerts(filters)
      setAlerts(alerts)
      setCurrentPage(1)
    } catch {
      setError('Failed to load alert history')
    } finally {
      setLoading(false)
    }
  }, [dateFilter, typeFilter, severityFilter, debouncedSymbolFilter])

  useEffect(() => {
    fetchAlerts()
  }, [fetchAlerts])

  const formatDateTime = (dateString: string): string => {
    const date = new Date(dateString)
    return date.toLocaleString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  // Pagination
  const totalPages = Math.ceil(alerts.length / ITEMS_PER_PAGE)
  const startIndex = (currentPage - 1) * ITEMS_PER_PAGE
  const endIndex = startIndex + ITEMS_PER_PAGE
  const currentAlerts = alerts.slice(startIndex, endIndex)

  return (
    <div data-testid="alerts-history" className="bg-gray-900 rounded-lg p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-white">Alert History</h2>
        <button
          data-testid="refresh-button"
          onClick={fetchAlerts}
          className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
          title="Refresh"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <select
          data-testid="date-filter"
          value={dateFilter}
          onChange={e => setDateFilter(e.target.value)}
          className="px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        >
          <option value="all">All Time</option>
          <option value="today">Today</option>
          <option value="week">Last 7 Days</option>
          <option value="month">Last 30 Days</option>
        </select>

        <select
          data-testid="type-filter"
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value as AlertType | '')}
          className="px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
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
          className="px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        >
          <option value="">All Severities</option>
          <option value="critical">Critical</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
          <option value="info">Info</option>
        </select>

        <input
          type="text"
          placeholder="Filter by symbol..."
          value={symbolFilter}
          onChange={e => setSymbolFilter(e.target.value)}
          className="px-3 py-2 bg-gray-800 text-white rounded-md border border-gray-700 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        />
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex justify-center items-center h-64">
          <div
            data-testid="loading-spinner"
            className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"
          />
        </div>
      ) : error ? (
        <div className="text-center text-red-500 py-8">{error}</div>
      ) : currentAlerts.length === 0 ? (
        <div className="text-center text-gray-500 py-8">No alerts found</div>
      ) : (
        <>
          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-gray-400 border-b border-gray-800">
                  <th className="pb-3 pr-4">Time</th>
                  <th className="pb-3 px-4">Symbol</th>
                  <th className="pb-3 px-4">Type</th>
                  <th className="pb-3 px-4">Title</th>
                  <th className="pb-3 px-4">Message</th>
                  <th className="pb-3 px-4">Severity</th>
                  <th className="pb-3 px-4">Venue</th>
                </tr>
              </thead>
              <tbody className="text-sm">
                {currentAlerts.map(alert => (
                  <tr key={alert.id} className="border-b border-gray-800 hover:bg-gray-800/50">
                    <td
                      className="py-3 pr-4 text-gray-500 whitespace-nowrap"
                      data-testid={`alert-time-${alert.id}`}
                    >
                      {formatDateTime(alert.createdAt)}
                    </td>
                    <td className="py-3 px-4 font-medium">{alert.symbol}</td>
                    <td className="py-3 px-4 text-gray-400">
                      {alert.type
                        .replace(/_/g, ' ')
                        .replace(/\b\w/g, (l: string) => l.toUpperCase())}
                    </td>
                    <td className="py-3 px-4">{alert.title}</td>
                    <td className="py-3 px-4 text-gray-400">
                      <span className="line-clamp-1">{alert.message}</span>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        data-testid={`severity-badge-${alert.severity}`}
                        className={`px-2 py-1 text-xs rounded ${SEVERITY_COLORS[alert.severity]?.bg || ''} ${SEVERITY_COLORS[alert.severity]?.text || ''}`}
                      >
                        {alert.severity}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span
                        className={`px-2 py-1 text-xs rounded ${
                          alert.venue === 'SPOT'
                            ? 'bg-blue-500/10 text-blue-500'
                            : 'bg-purple-500/10 text-purple-500'
                        }`}
                      >
                        {alert.venue}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div
              data-testid="pagination-controls"
              className="flex items-center justify-between mt-6"
            >
              <span className="text-sm text-gray-400">
                Page {currentPage} of {totalPages} ({alerts.length} total)
              </span>
              <div className="flex gap-2">
                <button
                  data-testid="prev-page-button"
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="px-3 py-1 bg-gray-800 text-white rounded-md hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <button
                  data-testid="next-page-button"
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="px-3 py-1 bg-gray-800 text-white rounded-md hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
