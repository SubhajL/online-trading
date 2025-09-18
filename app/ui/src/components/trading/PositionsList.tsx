import type { Position } from '@/types'
import { formatCurrency, formatNumber } from '@/utils/formatters'
import './PositionsList.css'

type PositionsListProps = {
  positions: Position[]
  loading?: boolean
  error?: string
  onClose?: (position: Position) => void
  className?: string
}

export function PositionsList({
  positions,
  loading = false,
  error,
  onClose,
  className = '',
}: PositionsListProps) {
  const totalPnl = positions.reduce((sum, position) => sum + position.pnl, 0)

  if (loading) {
    return (
      <div className={`positions-list ${className}`} data-testid="positions-list">
        <h3 className="positions-title">Open Positions</h3>
        <div className="positions-loading" data-testid="positions-loading">
          Loading positions...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={`positions-list ${className}`} data-testid="positions-list">
        <h3 className="positions-title">Open Positions</h3>
        <div className="positions-error" data-testid="positions-error">
          {error}
        </div>
      </div>
    )
  }

  return (
    <div className={`positions-list ${className}`} data-testid="positions-list">
      <div className="positions-header">
        <h3 className="positions-title">Open Positions</h3>
        {positions.length > 0 && (
          <div className="total-pnl">
            <span>Total P&L:</span>
            <span className={`pnl-value ${totalPnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
              {totalPnl >= 0 ? '+' : ''}
              {formatCurrency(totalPnl)}
            </span>
          </div>
        )}
      </div>

      {positions.length === 0 ? (
        <div className="empty-state">No open positions</div>
      ) : (
        <div className="positions-table">
          <div className="table-header">
            <span>Symbol</span>
            <span>Side</span>
            <span>Quantity</span>
            <span>Entry</span>
            <span>Mark</span>
            <span>P&L</span>
            <span>P&L %</span>
            <span>Venue</span>
            {onClose && <span>Action</span>}
          </div>

          {positions.map((position, index) => (
            <div key={`${position.symbol}-${index}`} className="position-row">
              <span className="symbol">{position.symbol}</span>
              <span className={`side-badge ${position.side.toLowerCase()}`}>{position.side}</span>
              <span>{position.quantity}</span>
              <span>{formatNumber(position.entryPrice)}</span>
              <span>{formatNumber(position.markPrice)}</span>
              <span className={`pnl-value ${position.pnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`}>
                {position.pnl >= 0 ? '+' : ''}
                {formatCurrency(position.pnl)}
              </span>
              <span
                className={`pnl-value ${position.pnlPercent >= 0 ? 'pnl-positive' : 'pnl-negative'}`}
              >
                {position.pnlPercent >= 0 ? '+' : ''}
                {position.pnlPercent.toFixed(2)}%
              </span>
              <span className="venue-badge">{position.venue}</span>
              {onClose && (
                <button
                  className="close-button"
                  onClick={() => onClose(position)}
                  type="button"
                  aria-label="Close position"
                >
                  Close
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
