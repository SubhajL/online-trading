import type { IndicatorType } from '@/types'

type IndicatorPanelProps = {
  activeIndicators: IndicatorType[]
  onToggleIndicator: (indicator: IndicatorType) => void
  onClose: () => void
}

const INDICATORS: { type: IndicatorType; name: string; description: string }[] = [
  { type: 'EMA', name: 'EMA', description: 'Exponential Moving Average' },
  { type: 'SMA', name: 'SMA', description: 'Simple Moving Average' },
  { type: 'RSI', name: 'RSI', description: 'Relative Strength Index' },
  { type: 'MACD', name: 'MACD', description: 'Moving Average Convergence Divergence' },
  { type: 'BB', name: 'BB', description: 'Bollinger Bands' },
  { type: 'VOLUME', name: 'Volume', description: 'Volume bars' },
]

export function IndicatorPanel({
  activeIndicators,
  onToggleIndicator,
  onClose,
}: IndicatorPanelProps) {
  const handleToggle = (indicator: IndicatorType) => {
    if (onToggleIndicator) {
      onToggleIndicator(indicator)
    }
  }

  const handleClose = () => {
    if (onClose) {
      onClose()
    }
  }

  return (
    <div
      data-testid="indicator-panel"
      role="dialog"
      aria-label="Technical Indicators"
      className="absolute right-0 top-0 w-80 h-full bg-gray-800 shadow-lg rounded-l-lg z-30"
    >
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <h3 className="text-lg font-semibold text-white">Technical Indicators</h3>
        <button
          data-testid="close-button"
          onClick={handleClose}
          className="p-1 text-gray-400 hover:text-white transition-colors"
          aria-label="Close panel"
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

      {/* Indicators list */}
      <div className="p-4 space-y-2">
        {INDICATORS.map(indicator => {
          const isActive = activeIndicators.includes(indicator.type)
          return (
            <div
              key={indicator.type}
              data-testid={`indicator-item-${indicator.type}`}
              className={`flex items-center p-3 rounded-lg transition-colors ${
                isActive ? 'bg-gray-700' : 'hover:bg-gray-700'
              }`}
            >
              <label
                htmlFor={`indicator-${indicator.type}`}
                className="flex items-center flex-1 cursor-pointer"
              >
                <input
                  id={`indicator-${indicator.type}`}
                  type="checkbox"
                  checked={isActive}
                  onChange={() => handleToggle(indicator.type)}
                  className="w-4 h-4 text-blue-600 bg-gray-700 border-gray-600 rounded focus:ring-blue-500"
                  aria-label={indicator.type}
                />
                <div className="ml-3 flex-1">
                  <div className="text-sm font-medium text-white">{indicator.name}</div>
                  <div className="text-xs text-gray-400">{indicator.description}</div>
                </div>
              </label>
            </div>
          )
        })}
      </div>

      {/* Help text */}
      <div className="absolute bottom-4 left-4 right-4 p-3 bg-gray-700 rounded-lg">
        <p className="text-xs text-gray-300">
          Select indicators to display on the chart. Some indicators may affect performance.
        </p>
      </div>
    </div>
  )
}
