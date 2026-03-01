'use client'

import { Toaster } from '@/components/ui/sonner'
import { toast } from 'sonner'

type TradeToastType = 'info' | 'warning' | 'error' | 'success'

function showTradeToast(type: TradeToastType, title: string, description?: string) {
  const toastFn =
    type === 'info'
      ? toast.info
      : type === 'warning'
        ? toast.warning
        : type === 'error'
          ? toast.error
          : toast.success

  toastFn(title, { description })
}

function ToastStack() {
  return <Toaster position="bottom-right" richColors closeButton />
}

export { ToastStack, showTradeToast }
