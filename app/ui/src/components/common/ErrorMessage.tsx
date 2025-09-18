import React from 'react'
import { formatErrorMessage } from '../../utils/formatErrorMessage'
import './ErrorMessage.css'

type ErrorMessageProps = {
  error: string | Error | unknown
  variant?: 'error' | 'warning' | 'info'
  title?: string
  dismissible?: boolean
  onDismiss?: () => void
  onRetry?: () => void
  retryText?: string
  compact?: boolean
  className?: string
}

export function ErrorMessage({
  error,
  variant = 'error',
  title,
  dismissible = false,
  onDismiss,
  onRetry,
  retryText = 'Retry',
  compact = false,
  className = '',
}: ErrorMessageProps) {
  const message = formatErrorMessage(error)

  const classes = ['error-message', `variant-${variant}`, compact && 'compact', className]
    .filter(Boolean)
    .join(' ')

  const ariaLive = variant === 'error' ? 'assertive' : 'polite'

  return (
    <div className={classes} data-testid="error-message" role="alert" aria-live={ariaLive}>
      <div className="error-content">
        {/* Icon */}
        <div className="error-icon-wrapper">
          {variant === 'error' && (
            <svg
              className="error-icon"
              data-testid="error-icon"
              width="20"
              height="20"
              viewBox="0 0 20 20"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M10 0C4.48 0 0 4.48 0 10s4.48 10 10 10 10-4.48 10-10S15.52 0 10 0zm1 15H9v-2h2v2zm0-4H9V5h2v6z"
                fill="currentColor"
              />
            </svg>
          )}
          {variant === 'warning' && (
            <svg
              className="error-icon"
              data-testid="warning-icon"
              width="20"
              height="20"
              viewBox="0 0 20 20"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M0 17.5h20L10 0 0 17.5zm11-3h-2v-2h2v2zm0-4h-2v-4h2v4z"
                fill="currentColor"
              />
            </svg>
          )}
          {variant === 'info' && (
            <svg
              className="error-icon"
              data-testid="info-icon"
              width="20"
              height="20"
              viewBox="0 0 20 20"
              fill="none"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                d="M10 0C4.48 0 0 4.48 0 10s4.48 10 10 10 10-4.48 10-10S15.52 0 10 0zm1 15H9V9h2v6zm0-8H9V5h2v2z"
                fill="currentColor"
              />
            </svg>
          )}
        </div>

        {/* Text content */}
        <div className="error-text">
          {title && <div className="error-title">{title}</div>}
          <div className="error-message-text">{message}</div>
        </div>
      </div>

      {/* Actions */}
      {(dismissible || onRetry) && (
        <div className="error-actions">
          {onRetry && (
            <button type="button" className="error-button retry-button" onClick={onRetry}>
              {retryText}
            </button>
          )}
          {dismissible && (
            <button
              type="button"
              className="error-button dismiss-button"
              onClick={onDismiss}
              aria-label="Dismiss"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 14 14"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M14 1.41L12.59 0L7 5.59L1.41 0L0 1.41L5.59 7L0 12.59L1.41 14L7 8.41L12.59 14L14 12.59L8.41 7L14 1.41Z"
                  fill="currentColor"
                />
              </svg>
            </button>
          )}
        </div>
      )}
    </div>
  )
}
