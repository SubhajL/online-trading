import type { Brand } from './index'

export type ToastId = Brand<string, 'ToastId'>
export type ToastType = 'success' | 'error' | 'info'

export type Toast = {
  id: ToastId
  type: ToastType
  message: string
  createdAt: number
}

export type ToastInput = {
  type: ToastType
  message: string
}

const TOAST_AUTO_DISMISS_MS = 5000
const TOAST_MAX_VISIBLE = 3

export function createToastId(): ToastId {
  return crypto.randomUUID() as ToastId
}

export function createToast(input: ToastInput): Toast {
  return {
    id: createToastId(),
    type: input.type,
    message: input.message,
    createdAt: Date.now(),
  }
}

export function getToastTestId(type: ToastType): string {
  switch (type) {
    case 'success':
      return 'order-success'
    case 'error':
      return 'order-error'
    case 'info':
      return 'order-info'
  }
}

export { TOAST_AUTO_DISMISS_MS, TOAST_MAX_VISIBLE }
