import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { Toast } from './Toast'
import type { Toast as ToastType, ToastId } from '@/types/toast'
import { TOAST_AUTO_DISMISS_MS } from '@/types/toast'

function createMockToast(overrides: Partial<ToastType> = {}): ToastType {
  return {
    id: 'toast-123' as ToastId,
    type: 'success',
    message: 'Test message',
    createdAt: Date.now(),
    ...overrides,
  }
}

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('rendering', () => {
    it('renders with data-testid="order-success" for success type', () => {
      const toast = createMockToast({ type: 'success' })
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByTestId('order-success')).toBeInTheDocument()
    })

    it('renders with data-testid="order-error" for error type', () => {
      const toast = createMockToast({ type: 'error', message: 'Order failed' })
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByTestId('order-error')).toBeInTheDocument()
    })

    it('renders with data-testid="order-info" for info type', () => {
      const toast = createMockToast({ type: 'info', message: 'Processing' })
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByTestId('order-info')).toBeInTheDocument()
    })

    it('displays the toast message', () => {
      const toast = createMockToast({ message: 'Order placed successfully' })
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByText('Order placed successfully')).toBeInTheDocument()
    })

    it('has role="alert" for accessibility', () => {
      const toast = createMockToast()
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByRole('alert')).toBeInTheDocument()
    })

    it('has aria-live="assertive" for error type', () => {
      const toast = createMockToast({ type: 'error' })
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'assertive')
    })

    it('has aria-live="polite" for success type', () => {
      const toast = createMockToast({ type: 'success' })
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'polite')
    })
  })

  describe('auto-dismiss', () => {
    it('calls onDismiss after TOAST_AUTO_DISMISS_MS', () => {
      const toast = createMockToast()
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(onDismiss).not.toHaveBeenCalled()

      act(() => {
        vi.advanceTimersByTime(TOAST_AUTO_DISMISS_MS)
      })

      expect(onDismiss).toHaveBeenCalledTimes(1)
      expect(onDismiss).toHaveBeenCalledWith(toast.id)
    })

    it('does not call onDismiss before timeout', () => {
      const toast = createMockToast()
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      act(() => {
        vi.advanceTimersByTime(TOAST_AUTO_DISMISS_MS - 1)
      })

      expect(onDismiss).not.toHaveBeenCalled()
    })

    it('clears timer on unmount', () => {
      const toast = createMockToast()
      const onDismiss = vi.fn()

      const { unmount } = render(<Toast toast={toast} onDismiss={onDismiss} />)
      unmount()

      act(() => {
        vi.advanceTimersByTime(TOAST_AUTO_DISMISS_MS)
      })

      expect(onDismiss).not.toHaveBeenCalled()
    })
  })

  describe('manual dismiss', () => {
    it('calls onDismiss when dismiss button is clicked', () => {
      const toast = createMockToast()
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      const dismissButton = screen.getByRole('button', { name: /dismiss/i })
      fireEvent.click(dismissButton)

      expect(onDismiss).toHaveBeenCalledTimes(1)
      expect(onDismiss).toHaveBeenCalledWith(toast.id)
    })

    it('dismiss button has accessible label', () => {
      const toast = createMockToast()
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByRole('button', { name: /dismiss notification/i })).toBeInTheDocument()
    })
  })

  describe('styling', () => {
    it('applies toast-success class for success type', () => {
      const toast = createMockToast({ type: 'success' })
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByRole('alert')).toHaveClass('toast-success')
    })

    it('applies toast-error class for error type', () => {
      const toast = createMockToast({ type: 'error' })
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByRole('alert')).toHaveClass('toast-error')
    })

    it('applies toast-info class for info type', () => {
      const toast = createMockToast({ type: 'info' })
      const onDismiss = vi.fn()

      render(<Toast toast={toast} onDismiss={onDismiss} />)

      expect(screen.getByRole('alert')).toHaveClass('toast-info')
    })
  })
})
