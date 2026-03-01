'use client'

import { useEffect, useCallback } from 'react'
import type { Toast as ToastType, ToastType as ToastVariant } from '@/types/toast'
import { getToastTestId, TOAST_AUTO_DISMISS_MS } from '@/types/toast'
import './Toast.css'

type ToastProps = {
  toast: ToastType
  onDismiss: (id: ToastType['id']) => void
}

function getToastIcon(type: ToastVariant): JSX.Element {
  switch (type) {
    case 'success':
      return (
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path
            d="M10 0C4.48 0 0 4.48 0 10s4.48 10 10 10 10-4.48 10-10S15.52 0 10 0zm-2 15l-5-5 1.41-1.41L8 12.17l7.59-7.59L17 6l-9 9z"
            fill="currentColor"
          />
        </svg>
      )
    case 'error':
      return (
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path
            d="M10 0C4.48 0 0 4.48 0 10s4.48 10 10 10 10-4.48 10-10S15.52 0 10 0zm1 15H9v-2h2v2zm0-4H9V5h2v6z"
            fill="currentColor"
          />
        </svg>
      )
    case 'info':
      return (
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path
            d="M10 0C4.48 0 0 4.48 0 10s4.48 10 10 10 10-4.48 10-10S15.52 0 10 0zm1 15H9V9h2v6zm0-8H9V5h2v2z"
            fill="currentColor"
          />
        </svg>
      )
  }
}

export function Toast({ toast, onDismiss }: ToastProps) {
  const handleDismiss = useCallback(() => {
    onDismiss(toast.id)
  }, [onDismiss, toast.id])

  useEffect(() => {
    const timer = setTimeout(handleDismiss, TOAST_AUTO_DISMISS_MS)
    return () => clearTimeout(timer)
  }, [handleDismiss])

  const testId = getToastTestId(toast.type)

  return (
    <div
      className={`toast toast-${toast.type}`}
      data-testid={testId}
      role="alert"
      aria-live={toast.type === 'error' ? 'assertive' : 'polite'}
    >
      <div className="toast-icon">{getToastIcon(toast.type)}</div>
      <div className="toast-message">{toast.message}</div>
      <button
        type="button"
        className="toast-dismiss"
        onClick={handleDismiss}
        aria-label="Dismiss notification"
      >
        <svg
          width="14"
          height="14"
          viewBox="0 0 14 14"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <path
            d="M14 1.41L12.59 0L7 5.59L1.41 0L0 1.41L5.59 7L0 12.59L1.41 14L7 8.41L12.59 14L14 12.59L8.41 7L14 1.41Z"
            fill="currentColor"
          />
        </svg>
      </button>
    </div>
  )
}
