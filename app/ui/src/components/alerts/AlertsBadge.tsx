type AlertsBadgeProps = {
  count: number
  onClick: () => void
  loading?: boolean
  hasNew?: boolean
}

export function AlertsBadge({ count, onClick, loading = false, hasNew = false }: AlertsBadgeProps) {
  const displayCount = count > 99 ? '99+' : count.toString()
  const ariaLabel = count > 0 ? `Alerts (${count} unread)` : 'Alerts'

  return (
    <button
      data-testid="alerts-badge"
      onClick={onClick}
      disabled={loading}
      aria-label={ariaLabel}
      className="relative p-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {loading ? (
        <div
          data-testid="loading-spinner"
          className="w-5 h-5 border-2 border-gray-400 border-t-transparent rounded-full animate-spin"
        />
      ) : (
        <svg
          data-testid="bell-icon"
          className="w-5 h-5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
          />
        </svg>
      )}

      {count > 0 && (
        <span
          data-testid="alert-count"
          className={`absolute -top-1 -right-1 px-1.5 py-0.5 text-xs text-white bg-red-500 rounded-full min-w-[20px] text-center ${
            hasNew ? 'animate-pulse' : ''
          }`}
        >
          {displayCount}
        </span>
      )}
    </button>
  )
}