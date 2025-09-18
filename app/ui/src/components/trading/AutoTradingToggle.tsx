import { useState } from 'react'
import './AutoTradingToggle.css'

type AutoTradingToggleProps = {
  enabled: boolean
  onChange: (enabled: boolean) => void
  loading?: boolean
  error?: string
  className?: string
}

export function AutoTradingToggle({
  enabled,
  onChange,
  loading = false,
  error,
  className = '',
}: AutoTradingToggleProps) {
  const [showTooltip, setShowTooltip] = useState(false)

  const handleToggle = () => {
    if (!loading) {
      onChange(!enabled)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === ' ' && !loading) {
      e.preventDefault()
      onChange(!enabled)
    }
  }

  return (
    <div
      className={`auto-trading-toggle ${className}`}
      data-testid="auto-trading-toggle"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <div className="toggle-header">
        <h4 className="toggle-title">Auto Trading</h4>
        <div className="toggle-status">
          {enabled ? (
            <>
              <svg
                className="status-icon check"
                data-testid="check-icon"
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="currentColor"
              >
                <path d="M13.854 3.646a.5.5 0 0 1 0 .708l-7 7a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L6.5 10.293l6.646-6.647a.5.5 0 0 1 .708 0z" />
              </svg>
              <span className="status-text enabled">Enabled</span>
            </>
          ) : (
            <>
              <svg
                className="status-icon warning"
                data-testid="warning-icon"
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="currentColor"
              >
                <path d="M8.982 1.566a1.13 1.13 0 0 0-1.96 0L.165 13.233c-.457.778.091 1.767.98 1.767h13.713c.889 0 1.438-.99.98-1.767L8.982 1.566zM8 5c.535 0 .954.462.9.995l-.35 3.507a.552.552 0 0 1-1.1 0L7.1 5.995A.905.905 0 0 1 8 5zm.002 6a1 1 0 1 1 0 2 1 1 0 0 1 0-2z" />
              </svg>
              <span className="status-text disabled">Disabled</span>
            </>
          )}
        </div>
      </div>

      <div className="toggle-control">
        <label className="switch">
          <input
            type="checkbox"
            role="switch"
            checked={enabled}
            onChange={handleToggle}
            onKeyDown={handleKeyDown}
            disabled={loading}
            aria-checked={enabled}
            aria-label="Toggle auto trading"
          />
          <span className="slider" />
        </label>
        {loading && <span className="loading-text">Updating...</span>}
      </div>

      {error && (
        <div className="toggle-error" data-testid="toggle-error" role="alert">
          {error}
        </div>
      )}

      {showTooltip && (
        <div className="toggle-tooltip">
          {enabled
            ? 'Auto trading is active. The system will execute trades automatically.'
            : 'Enable to allow automated trading based on system signals.'}
        </div>
      )}
    </div>
  )
}
