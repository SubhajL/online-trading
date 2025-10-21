import React, { useMemo } from 'react'
import { getTokens } from '@/utils/getTokens'
import { getSpinnerStyles } from '@/utils/tokenHelpers'
import type { SpinnerSize, SpinnerVariant } from '@/utils/tokenHelpers'
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
  color = 'primary',
  label,
  inline = false,
  overlay = false,
  fullscreen = false,
  centerText = false,
  className = '',
}: LoadingSpinnerProps) {
  const tokens = useMemo(() => getTokens(), [])

  const sizeMap: Record<typeof size, SpinnerSize> = {
    small: 'sm',
    medium: 'md',
    large: 'lg',
  }

  const spinnerStyles = useMemo(
    () => getSpinnerStyles(sizeMap[size], color as SpinnerVariant, tokens),
    [size, color, tokens],
  )

  const spinnerClasses = ['loading-spinner', inline && 'inline', className]
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
        <div
          className="spinner-circle"
          style={{
            width: spinnerStyles.width,
            height: spinnerStyles.height,
            borderWidth: spinnerStyles.borderWidth,
            borderColor: spinnerStyles.borderColor,
          }}
        />
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
