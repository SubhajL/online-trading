'use client'

import React, { createContext, useContext, useState, useCallback, useMemo } from 'react'
import type { Toast, ToastId, ToastInput } from '@/types/toast'
import { createToast, TOAST_MAX_VISIBLE } from '@/types/toast'
import { Toast as ToastComponent } from '@/components/common/Toast'
import './ToastContext.css'

type ToastContextValue = {
  toasts: Toast[]
  showSuccess: (message: string) => ToastId
  showError: (message: string) => ToastId
  showInfo: (message: string) => ToastId
  dismiss: (id: ToastId) => void
  dismissAll: () => void
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((input: ToastInput): ToastId => {
    const toast = createToast(input)
    setToasts(prev => {
      const next = [...prev, toast]
      if (next.length > TOAST_MAX_VISIBLE) {
        return next.slice(-TOAST_MAX_VISIBLE)
      }
      return next
    })
    return toast.id
  }, [])

  const showSuccess = useCallback(
    (message: string): ToastId => {
      return addToast({ type: 'success', message })
    },
    [addToast],
  )

  const showError = useCallback(
    (message: string): ToastId => {
      return addToast({ type: 'error', message })
    },
    [addToast],
  )

  const showInfo = useCallback(
    (message: string): ToastId => {
      return addToast({ type: 'info', message })
    },
    [addToast],
  )

  const dismiss = useCallback((id: ToastId) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const dismissAll = useCallback(() => {
    setToasts([])
  }, [])

  const value = useMemo(
    () => ({
      toasts,
      showSuccess,
      showError,
      showInfo,
      dismiss,
      dismissAll,
    }),
    [toasts, showSuccess, showError, showInfo, dismiss, dismissAll],
  )

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-container" aria-label="Notifications">
        {toasts.map(toast => (
          <ToastComponent key={toast.id} toast={toast} onDismiss={dismiss} />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (context === undefined) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}
