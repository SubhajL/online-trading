import type { PipelineHealthResponse, PipelineStatus, LastDecision } from '@/types/dashboard'
import './PipelineHealth.css'

type PipelineHealthProps = {
  data: PipelineHealthResponse | null
  loading?: boolean
  error?: string
}

const LAG_WARNING_THRESHOLD_MS = 5000

function formatLagMs(lagMs: number): string {
  return `${(lagMs / 1000).toFixed(1)}s`
}

function formatTimestamp(isoString: string): string {
  const date = new Date(isoString)
  if (isNaN(date.getTime())) {
    return '-'
  }
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

function assertNever(x: never): never {
  throw new Error(`Unexpected value: ${x}`)
}

function getStatusClass(status: PipelineStatus): string {
  switch (status) {
    case 'HEALTHY':
      return 'status-healthy'
    case 'DEGRADED':
      return 'status-degraded'
    case 'UNHEALTHY':
      return 'status-unhealthy'
    default:
      return assertNever(status)
  }
}

function getActionClass(action: LastDecision['action']): string {
  switch (action) {
    case 'BUY':
      return 'action-buy'
    case 'SELL':
      return 'action-sell'
    case 'HOLD':
      return 'action-hold'
    default:
      return assertNever(action)
  }
}

export function PipelineHealth({ data, loading, error }: PipelineHealthProps) {
  if (loading || (!data && !error)) {
    return (
      <div className="pipeline-health" data-testid="pipeline-health-loading">
        <div className="pipeline-health-header">
          <h3>Pipeline Health</h3>
        </div>
        <div className="pipeline-health-loading">
          <div className="loading-shimmer" />
          <div className="loading-shimmer" />
          <div className="loading-shimmer" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="pipeline-health" data-testid="pipeline-health-error">
        <div className="pipeline-health-header">
          <h3>Pipeline Health</h3>
        </div>
        <div className="pipeline-health-error" role="alert">
          {error}
        </div>
      </div>
    )
  }

  if (!data) {
    return null
  }

  const hasHighLagSymbols = data.symbols.some(s => s.lagMs > LAG_WARNING_THRESHOLD_MS)

  return (
    <div className="pipeline-health" data-testid="pipeline-health">
      <div className="pipeline-health-header">
        <h3>Pipeline Health</h3>
        <div className="status-badge">
          <span
            className={`status-indicator ${getStatusClass(data.status)}`}
            data-testid="status-indicator"
          />
          <span className="status-text">{data.status}</span>
        </div>
      </div>

      <div className="pipeline-health-summary">
        <div className="summary-item">
          <span className="summary-label">Avg Lag:</span>
          <span className="summary-value" data-testid="average-lag">
            {formatLagMs(data.averageLagMs)}
          </span>
        </div>
        {hasHighLagSymbols && (
          <div className="lag-warning" data-testid="lag-warning">
            <span className="warning-icon">⚠</span>
            <span>High lag detected</span>
          </div>
        )}
      </div>

      {data.symbols.length === 0 ? (
        <div className="pipeline-health-empty">No symbols being tracked</div>
      ) : (
        <table className="symbols-table" role="table" data-testid="symbols-list">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>TF</th>
              <th>Last Candle</th>
              <th>Lag</th>
            </tr>
          </thead>
          <tbody>
            {data.symbols.map(symbol => {
              const isHighLag = symbol.lagMs > LAG_WARNING_THRESHOLD_MS
              return (
                <tr
                  key={`${symbol.symbol}-${symbol.timeframe}`}
                  className={`symbol-row ${isHighLag ? 'high-lag' : ''}`}
                  data-testid={`symbol-row-${symbol.symbol}`}
                >
                  <td className="symbol-name">{symbol.symbol}</td>
                  <td className="symbol-timeframe">{symbol.timeframe}</td>
                  <td className="symbol-last-candle">{formatTimestamp(symbol.lastCandleTime)}</td>
                  <td
                    className={`symbol-lag ${isHighLag ? 'lag-high' : ''}`}
                    data-testid={`symbol-lag-${symbol.symbol}`}
                  >
                    {formatLagMs(symbol.lagMs)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      <div className="last-decision-section">
        <h4>Last Decision</h4>
        {data.lastDecision ? (
          <div className="last-decision" data-testid="last-decision">
            <div className="decision-row">
              <span className="decision-label">Symbol:</span>
              <span className="decision-value" data-testid="last-decision-symbol">
                {data.lastDecision.symbol}
              </span>
            </div>
            <div className="decision-row">
              <span className="decision-label">Action:</span>
              <span
                className={`decision-action ${getActionClass(data.lastDecision.action)}`}
                data-testid="last-decision-action"
              >
                {data.lastDecision.action}
              </span>
            </div>
            <div className="decision-row">
              <span className="decision-label">Reason:</span>
              <span className="decision-reason" data-testid="last-decision-reason">
                {data.lastDecision.reason}
              </span>
            </div>
            <div className="decision-row">
              <span className="decision-label">Time:</span>
              <span className="decision-time">{formatTimestamp(data.lastDecision.timestamp)}</span>
            </div>
          </div>
        ) : (
          <div className="no-decision">No recent decisions</div>
        )}
      </div>
    </div>
  )
}
