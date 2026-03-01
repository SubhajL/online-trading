import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { ToastProvider, useToast } from './ToastContext'
import { TOAST_MAX_VISIBLE, TOAST_AUTO_DISMISS_MS } from '@/types/toast'

function TestComponent() {
  const { toasts, showSuccess, showError, showInfo, dismiss, dismissAll } = useToast()
  return (
    <div>
      <span data-testid="toast-count">{toasts.length}</span>
      <button onClick={() => showSuccess('Success message')}>Show Success</button>
      <button onClick={() => showError('Error message')}>Show Error</button>
      <button onClick={() => showInfo('Info message')}>Show Info</button>
      <button onClick={() => dismissAll()}>Dismiss All</button>
      {toasts.length > 0 && <button onClick={() => dismiss(toasts[0].id)}>Dismiss First</button>}
    </div>
  )
}

describe('ToastContext', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('ToastProvider', () => {
    it('renders children', () => {
      render(
        <ToastProvider>
          <div data-testid="child">Child content</div>
        </ToastProvider>,
      )

      expect(screen.getByTestId('child')).toBeInTheDocument()
    })

    it('renders toast container', () => {
      render(
        <ToastProvider>
          <div>Content</div>
        </ToastProvider>,
      )

      expect(screen.getByRole('generic', { name: 'Notifications' })).toBeInTheDocument()
    })
  })

  describe('useToast', () => {
    it('throws error when used outside ToastProvider', () => {
      const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})

      expect(() => {
        render(<TestComponent />)
      }).toThrow('useToast must be used within a ToastProvider')

      consoleError.mockRestore()
    })

    it('returns empty toasts array initially', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>,
      )

      expect(screen.getByTestId('toast-count')).toHaveTextContent('0')
    })
  })

  describe('showSuccess', () => {
    it('adds success toast with data-testid="order-success"', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>,
      )

      fireEvent.click(screen.getByText('Show Success'))

      expect(screen.getByTestId('order-success')).toBeInTheDocument()
      expect(screen.getByText('Success message')).toBeInTheDocument()
    })

    it('increments toast count', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>,
      )

      expect(screen.getByTestId('toast-count')).toHaveTextContent('0')

      fireEvent.click(screen.getByText('Show Success'))

      expect(screen.getByTestId('toast-count')).toHaveTextContent('1')
    })
  })

  describe('showError', () => {
    it('adds error toast with data-testid="order-error"', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>,
      )

      fireEvent.click(screen.getByText('Show Error'))

      expect(screen.getByTestId('order-error')).toBeInTheDocument()
      expect(screen.getByText('Error message')).toBeInTheDocument()
    })
  })

  describe('showInfo', () => {
    it('adds info toast with data-testid="order-info"', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>,
      )

      fireEvent.click(screen.getByText('Show Info'))

      expect(screen.getByTestId('order-info')).toBeInTheDocument()
      expect(screen.getByText('Info message')).toBeInTheDocument()
    })
  })

  describe('dismiss', () => {
    it('removes specific toast', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>,
      )

      fireEvent.click(screen.getByText('Show Success'))
      expect(screen.getByTestId('toast-count')).toHaveTextContent('1')

      fireEvent.click(screen.getByText('Dismiss First'))
      expect(screen.getByTestId('toast-count')).toHaveTextContent('0')
    })
  })

  describe('dismissAll', () => {
    it('removes all toasts', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>,
      )

      fireEvent.click(screen.getByText('Show Success'))
      fireEvent.click(screen.getByText('Show Error'))
      fireEvent.click(screen.getByText('Show Info'))
      expect(screen.getByTestId('toast-count')).toHaveTextContent('3')

      fireEvent.click(screen.getByText('Dismiss All'))
      expect(screen.getByTestId('toast-count')).toHaveTextContent('0')
    })
  })

  describe('toast limits', () => {
    it('limits visible toasts to TOAST_MAX_VISIBLE', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>,
      )

      for (let i = 0; i < TOAST_MAX_VISIBLE + 2; i++) {
        fireEvent.click(screen.getByText('Show Success'))
      }

      expect(screen.getByTestId('toast-count')).toHaveTextContent(String(TOAST_MAX_VISIBLE))
    })

    it('keeps newest toasts when limit exceeded', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>,
      )

      fireEvent.click(screen.getByText('Show Success'))
      fireEvent.click(screen.getByText('Show Success'))
      fireEvent.click(screen.getByText('Show Success'))
      fireEvent.click(screen.getByText('Show Error'))

      const toasts = screen.getAllByRole('alert')
      expect(toasts).toHaveLength(TOAST_MAX_VISIBLE)

      expect(screen.getByTestId('order-error')).toBeInTheDocument()
    })
  })

  describe('auto-dismiss integration', () => {
    it('toast is removed after auto-dismiss timeout', () => {
      render(
        <ToastProvider>
          <TestComponent />
        </ToastProvider>,
      )

      fireEvent.click(screen.getByText('Show Success'))
      expect(screen.getByTestId('toast-count')).toHaveTextContent('1')

      act(() => {
        vi.advanceTimersByTime(TOAST_AUTO_DISMISS_MS + 100)
      })

      expect(screen.getByTestId('toast-count')).toHaveTextContent('0')
    })
  })
})
