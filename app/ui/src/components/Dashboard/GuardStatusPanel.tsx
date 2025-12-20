import type { GuardStatusResponse, GuardStatus, EngineState } from '@/types/dashboard'
import './GuardStatusPanel.css'

type GuardStatusPanelProps = {
  status: GuardStatusResponse | null
  loading?: boolean
  error?: string
}

const GUARD_DISPLAY_NAMES: Record<string, string> = {
  drawdownGuard: 'Drawdown Guard',
  maxPositionsGuard: 'Max Positions Guard',
  newsGuard: 'News Guard',
  volatilityGuard: 'Volatility Guard',
  correlationGuard: 'Correlation Guard',
}

function getEngineStateClass(state: EngineState): string {
  switch (state) {
    case 'ACTIVE':
      return 'status-active'
    case 'PAUSED':
      return 'status-paused'
    case 'STOPPED':
      return 'status-stopped'
    default:
      return ''
  }
}

function formatTimestamp(isoString: string): string {
  const date = new Date(isoString)
  return date.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function GuardStatusPanel({ status, loading, error }: GuardStatusPanelProps) {
  if (loading || (!status && !error)) {
    return (
      <div className="guard-panel" data-testid="guard-panel-loading">
        <div className="guard-panel-header">
          <h3>Guard Status</h3>
        </div>
        <div className="guard-panel-loading">
          <div className="loading-shimmer" />
          <div className="loading-shimmer" />
          <div className="loading-shimmer" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="guard-panel guard-panel-error">
        <div className="guard-panel-header">
          <h3>Guard Status</h3>
        </div>
        <div className="guard-error-message">{error}</div>
      </div>
    )
  }

  if (!status) {
    return null
  }

  const guardEntries = Object.entries(status.guards) as [string, GuardStatus][]

  return (
    <div className="guard-panel">
      <div className="guard-panel-header">
        <h3>Guard Status</h3>
        <div className="engine-status">
          <span
            className={`engine-status-indicator ${getEngineStateClass(status.engineState)}`}
            data-testid="engine-status-indicator"
          />
          <span className="engine-state-text">{status.engineState}</span>
        </div>
      </div>

      <div className="overall-status-row">
        <span className="overall-status-label">Overall:</span>
        <span
          className={`overall-status ${status.overallStatus === 'OK' ? 'status-ok' : 'status-blocked'}`}
          data-testid="overall-status"
        >
          <span className="overall-status-icon" data-testid="overall-status-icon">
            {status.overallStatus === 'OK' ? '✓' : '⚠'}
          </span>
          {status.overallStatus}
        </span>
      </div>

      <div className="guards-list">
        {guardEntries.map(([guardKey, guard]) => (
          <div key={guardKey} className="guard-item">
            <div className="guard-name-row">
              <span
                className={`guard-status-indicator ${guard.status === 'OK' ? 'status-ok' : 'status-blocked'}`}
                data-testid={guard.status === 'OK' ? 'guard-status-ok' : 'guard-status-blocked'}
              />
              <span className="guard-name">{GUARD_DISPLAY_NAMES[guardKey] || guardKey}</span>
            </div>
            {guard.blockedReason && (
              <div className="guard-blocked-reason">{guard.blockedReason}</div>
            )}
          </div>
        ))}
      </div>

      <div className="guard-panel-footer">
        <span className="last-checked" data-testid="last-checked">
          Last checked: {formatTimestamp(status.lastChecked)}
        </span>
      </div>
    </div>
  )
}
