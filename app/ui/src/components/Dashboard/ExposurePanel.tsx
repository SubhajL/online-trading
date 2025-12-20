import type { ExposureSummary } from '@/types/dashboard'
import { formatCurrency } from '@/utils/formatters'
import './ExposurePanel.css'

type ExposurePanelProps = {
  exposure: ExposureSummary | null
  loading?: boolean
  error?: string
}

function formatPnl(value: number): { text: string; className: string } {
  if (value === 0) {
    return { text: '$0.00', className: 'pnl-neutral' }
  }
  // formatCurrency already handles the negative sign, but we need to add + for positive
  const formatted = value > 0 ? `+${formatCurrency(value)}` : formatCurrency(value)
  const className = value > 0 ? 'pnl-positive' : 'pnl-negative'
  return { text: formatted, className }
}

function getMarginClass(percent: number): string {
  if (percent >= 90) return 'margin-danger'
  if (percent >= 70) return 'margin-warning'
  return 'margin-normal'
}

export function ExposurePanel({ exposure, loading, error }: ExposurePanelProps) {
  if (loading || (!exposure && !error)) {
    return (
      <div className="exposure-panel" data-testid="exposure-panel-loading">
        <div className="exposure-panel-header">
          <h3>Exposure</h3>
        </div>
        <div className="exposure-loading">
          <div className="loading-shimmer" />
          <div className="loading-shimmer" />
          <div className="loading-shimmer" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="exposure-panel exposure-panel-error">
        <div className="exposure-panel-header">
          <h3>Exposure</h3>
        </div>
        <div className="exposure-error-message">{error}</div>
      </div>
    )
  }

  if (!exposure) {
    return null
  }

  const unrealizedPnl = formatPnl(exposure.unrealizedPnl)
  const realizedPnl = formatPnl(exposure.realizedPnlToday)
  const marginClass = getMarginClass(exposure.marginUsagePercent)

  return (
    <div className="exposure-panel">
      <div className="exposure-panel-header">
        <h3>Exposure</h3>
        <div className="position-count-badge" data-testid="position-count">
          {exposure.positionCount}
        </div>
      </div>

      <div className="exposure-grid">
        <div className="exposure-section">
          <div className="exposure-label">Total Notional</div>
          <div className="exposure-value" data-testid="total-notional">
            {formatCurrency(exposure.totalNotional)}
          </div>
          <div className="exposure-breakdown">
            <span className="exposure-sub-item">
              <span className="sub-label">Spot:</span>
              <span data-testid="spot-notional">{formatCurrency(exposure.spotNotional)}</span>
            </span>
            <span className="exposure-sub-item">
              <span className="sub-label">Futures:</span>
              <span data-testid="futures-notional">{formatCurrency(exposure.futuresNotional)}</span>
            </span>
          </div>
        </div>

        <div className="exposure-section">
          <div className="exposure-label">Unrealized P&L</div>
          <div className={`exposure-value ${unrealizedPnl.className}`} data-testid="unrealized-pnl">
            {unrealizedPnl.text}
          </div>
        </div>

        <div className="exposure-section">
          <div className="exposure-label">Realized Today</div>
          <div
            className={`exposure-value ${realizedPnl.className}`}
            data-testid="realized-pnl-today"
          >
            {realizedPnl.text}
          </div>
        </div>

        <div className="exposure-section">
          <div className="exposure-label">Total Equity</div>
          <div className="exposure-value" data-testid="total-equity">
            {formatCurrency(exposure.totalEquity)}
          </div>
        </div>

        <div className="exposure-section">
          <div className="exposure-label">Available Margin</div>
          <div className="exposure-value" data-testid="available-margin">
            {formatCurrency(exposure.availableMargin)}
          </div>
        </div>

        <div className="exposure-section margin-section">
          <div className="margin-header">
            <span className="exposure-label">Margin Usage</span>
            <span className="exposure-value" data-testid="margin-usage">
              {exposure.marginUsagePercent.toFixed(0)}%
            </span>
          </div>
          <div className="margin-bar">
            <div
              className={`margin-progress ${marginClass}`}
              data-testid="margin-progress-bar"
              style={{ width: `${exposure.marginUsagePercent}%` }}
            />
          </div>
        </div>
      </div>

      <div className="position-summary">
        <div className="position-item">
          <span className="position-label">Spot Positions:</span>
          <span className="position-value" data-testid="spot-position-count">
            {exposure.spotPositionCount}
          </span>
        </div>
        <div className="position-item">
          <span className="position-label">Futures Positions:</span>
          <span className="position-value" data-testid="futures-position-count">
            {exposure.futuresPositionCount}
          </span>
        </div>
      </div>
    </div>
  )
}
