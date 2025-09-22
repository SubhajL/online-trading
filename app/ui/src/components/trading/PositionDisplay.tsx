import type { Position } from '@/types'

type PositionDisplayProps = {
  position: Position | null
  compact?: boolean
  onClose?: (position: Position) => void
}

export function PositionDisplay({ position, compact = false, onClose }: PositionDisplayProps) {
  if (!position) {
    return (
      <div
        data-testid="no-position"
        className="bg-gray-900 rounded-lg p-4 text-center text-gray-500"
      >
        No open position
      </div>
    )
  }

  const positionValue = position.quantity * position.markPrice
  const isLong = position.side === 'BUY'
  const isProfit = position.pnl > 0
  const isBreakeven = position.pnl === 0

  const pnlColorClass = isBreakeven
    ? 'text-gray-400'
    : isProfit
    ? 'text-green-500'
    : 'text-red-500'

  const formatPrice = (price: number) => {
    return `$${price.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`
  }

  const formatPnl = (value: number) => {
    const prefix = value > 0 ? '+' : value < 0 ? '-' : ''
    return `${prefix}$${Math.abs(value).toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })}`
  }

  const formatPercent = (value: number) => {
    const prefix = value > 0 ? '+' : ''
    return `${prefix}${value.toFixed(2)}%`
  }

  const formatQuantity = (qty: number) => {
    if (qty < 0.0001) {
      return qty.toString()
    }
    return qty.toLocaleString(undefined, {
      minimumFractionDigits: 0,
      maximumFractionDigits: 8,
    })
  }

  return (
    <div
      data-testid="position-display"
      className={`bg-gray-900 rounded-lg ${compact ? 'py-2 px-4' : 'p-4'} space-y-3`}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-semibold text-white">{position.symbol}</h3>
          <span
            className={`px-2 py-1 text-xs font-medium rounded ${
              isLong
                ? 'bg-green-500/10 text-green-500'
                : 'bg-red-500/10 text-red-500'
            }`}
          >
            {isLong ? 'LONG' : 'SHORT'}
          </span>
          <span className="px-2 py-1 text-xs font-medium bg-gray-700 text-gray-300 rounded">
            {position.venue}
          </span>
        </div>
        {onClose && (
          <button
            data-testid="close-position-button"
            onClick={() => onClose(position)}
            className="p-1 text-gray-400 hover:text-white transition-colors"
            title="Close position"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      {/* Position details */}
      <div className={`grid ${compact ? 'grid-cols-2 gap-x-4' : 'grid-cols-2 gap-4'}`}>
        <div>
          <span className="text-sm text-gray-400">Quantity:</span>
          <p className="text-white">{formatQuantity(position.quantity)}</p>
        </div>
        <div>
          <span className="text-sm text-gray-400">Entry:</span>
          <p className="text-white">{formatPrice(position.entryPrice)}</p>
        </div>
        <div>
          <span className="text-sm text-gray-400">Mark:</span>
          <p className="text-white">{formatPrice(position.markPrice)}</p>
        </div>
        {!compact && (
          <div>
            <span className="text-sm text-gray-400">Value:</span>
            <p className="text-white">{formatPrice(positionValue)}</p>
          </div>
        )}
      </div>

      {/* PnL */}
      <div className="flex items-center justify-between pt-2 border-t border-gray-800">
        <div>
          <span className="text-sm text-gray-400">PnL:</span>
          <p className={`text-lg font-semibold ${pnlColorClass}`}>
            {formatPnl(position.pnl)}
          </p>
        </div>
        <div className="text-right">
          <span className="text-sm text-gray-400">%:</span>
          <p className={`text-lg font-semibold ${pnlColorClass}`}>
            {formatPercent(position.pnlPercent)}
          </p>
        </div>
      </div>
    </div>
  )
}