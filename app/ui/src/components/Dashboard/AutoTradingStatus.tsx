import type { EngineStatus, EngineState } from '@/types/dashboard'
import './AutoTradingStatus.css'

type AutoTradingStatusProps = {
  status: EngineStatus | null
  activeSignals?: number
  onToggle?: (enabled: boolean) => void
  loading?: boolean
  error?: string
}

function assertNever(x: never): never {
  throw new Error(`Unexpected value: ${x}`)
}

function getStateClass(state: EngineState): string {
  switch (state) {
    case 'ACTIVE':
      return 'state-active'
    case 'PAUSED':
      return 'state-paused'
    case 'STOPPED':
      return 'state-stopped'
    default:
      return assertNever(state)
  }
}

function formatRelativeTime(isoString: string, now: number = Date.now()): string {
  const date = new Date(isoString)
  if (isNaN(date.getTime())) {
    return '-'
  }

  const diffMs = now - date.getTime()
  const diffSeconds = Math.floor(diffMs / 1000)
  const diffMinutes = Math.floor(diffSeconds / 60)
  const diffHours = Math.floor(diffMinutes / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffDays > 0) {
    return `${diffDays}d ago`
  }
  if (diffHours > 0) {
    return `${diffHours}h ago`
  }
  if (diffMinutes > 0) {
    return `${diffMinutes}m ago`
  }
  return `${diffSeconds}s ago`
}

export function AutoTradingStatus({
  status,
  activeSignals,
  onToggle,
  loading,
  error,
}: AutoTradingStatusProps) {
  if (loading || (!status && !error)) {
    if (loading) {
      return (
        <div className="auto-trading-status-panel" data-testid="auto-trading-status-loading">
          <div className="auto-trading-header">
            <h3>Auto Trading</h3>
          </div>
          <div className="auto-trading-loading">
            <div className="loading-shimmer" />
            <div className="loading-shimmer" />
            <div className="loading-shimmer" />
          </div>
        </div>
      )
    }
    return null
  }

  if (error) {
    return (
      <div className="auto-trading-status-panel" data-testid="auto-trading-status-error">
        <div className="auto-trading-header">
          <h3>Auto Trading</h3>
        </div>
        <div className="auto-trading-error" role="alert">
          {error}
        </div>
      </div>
    )
  }

  if (!status) {
    return null
  }

  const isDisabled = status.state === 'STOPPED'
  const toggleLabel = status.autoTrading ? 'Turn off auto trading' : 'Turn on auto trading'

  return (
    <div className="auto-trading-status-panel" data-testid="auto-trading-status">
      <div className="auto-trading-header">
        <h3>Auto Trading</h3>
        <div className="toggle-section">
          <span
            className={`auto-trading-toggle ${status.autoTrading ? 'on' : 'off'}`}
            data-testid="auto-trading-toggle"
          >
            {status.autoTrading ? 'ON' : 'OFF'}
          </span>
          {onToggle && (
            <button
              type="button"
              className="toggle-button"
              onClick={() => onToggle(!status.autoTrading)}
              disabled={isDisabled}
              aria-label={toggleLabel}
              data-testid="toggle-button"
            >
              {status.autoTrading ? 'Disable' : 'Enable'}
            </button>
          )}
        </div>
      </div>

      <div className="engine-state-section">
        <div className="state-row">
          <span className="state-label">Engine State:</span>
          <div className="state-badge">
            <span
              className={`engine-state-indicator ${getStateClass(status.state)}`}
              data-testid="engine-state-indicator"
            />
            <span className="engine-state-text" data-testid="engine-state-text">
              {status.state}
            </span>
          </div>
        </div>

        {activeSignals !== undefined && (
          <div className="signals-row">
            <span className="signals-label">Active Signals:</span>
            <span className="signals-count" data-testid="active-signals">
              {activeSignals}
            </span>
          </div>
        )}
      </div>

      <div className="last-decision-section">
        <h4>Last Decision</h4>
        {status.lastDecisionAt ? (
          <div className="decision-info">
            <div className="decision-row">
              <span className="decision-label">Time:</span>
              <span className="decision-time" data-testid="last-decision-time">
                {formatRelativeTime(status.lastDecisionAt)}
              </span>
            </div>
            {status.lastDecisionReason && (
              <div className="decision-row">
                <span className="decision-label">Reason:</span>
                <span className="decision-reason" data-testid="last-decision-reason">
                  {status.lastDecisionReason}
                </span>
              </div>
            )}
          </div>
        ) : (
          <div className="no-decision">No decisions yet</div>
        )}
      </div>
    </div>
  )
}
