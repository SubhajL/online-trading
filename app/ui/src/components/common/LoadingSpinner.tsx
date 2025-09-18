import React from 'react'
import './LoadingSpinner.css'

type LoadingSpinnerProps = {
  size?: 'small' | 'medium' | 'large'
  color?: 'primary' | 'secondary' | 'white'
  label?: string
  inline?: boolean
  overlay?: boolean
  fullscreen?: boolean
  centerText?: boolean
  className?: string
}

export function LoadingSpinner({
  size = 'medium',
  color,
  label,
  inline = false,
  overlay = false,
  fullscreen = false,
  centerText = false,
  className = '',
}: LoadingSpinnerProps) {
  const spinnerClasses = [
    'loading-spinner',
    `size-${size}`,
    inline && 'inline',
    color && `color-${color}`,
    className,
  ]
    .filter(Boolean)
    .join(' ')

  const spinner = (
    <>
      <div
        className={spinnerClasses}
        data-testid="loading-spinner"
        role="status"
        aria-label={label || 'Loading...'}
      >
        <div className="spinner-circle" />
      </div>
      {label && <span className="loading-label">{label}</span>}
    </>
  )

  if (overlay) {
    const overlayClasses = ['loading-overlay', fullscreen && 'fullscreen'].filter(Boolean).join(' ')

    return (
      <div className={overlayClasses} data-testid="loading-overlay">
        <div className="loading-content">{spinner}</div>
      </div>
    )
  }

  if (centerText || label) {
    const containerClasses = ['loading-container', centerText && 'center-text']
      .filter(Boolean)
      .join(' ')

    return (
      <div className={containerClasses} data-testid="loading-container">
        {spinner}
      </div>
    )
  }

  return spinner
}
