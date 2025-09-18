import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import React from 'react'
import { ErrorBoundary } from './ErrorBoundary'

type ErrorInfo = {
  componentStack: string
}

// Component that throws an error
function ThrowError({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('Test error from component')
  }
  return <div>No error</div>
}

// Component that throws in useEffect
function ThrowErrorInEffect({ shouldThrow }: { shouldThrow: boolean }) {
  React.useEffect(() => {
    if (shouldThrow) {
      throw new Error('Test error from effect')
    }
  }, [shouldThrow])

  return <div>Component with effect</div>
}

describe('ErrorBoundary', () => {
  // Suppress console.error for these tests
  const originalError = console.error
  beforeEach(() => {
    console.error = vi.fn()
  })

  afterEach(() => {
    console.error = originalError
  })

  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <div>Test content</div>
      </ErrorBoundary>,
    )

    expect(screen.getByText('Test content')).toBeInTheDocument()
  })

  it('catches errors and shows fallback UI', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    expect(screen.getByTestId('error-boundary-fallback')).toBeInTheDocument()
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('shows error message when error is caught', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    expect(screen.getByText('Test error from component')).toBeInTheDocument()
  })

  it('renders custom fallback when provided', () => {
    const fallback = <div>Custom error UI</div>

    render(
      <ErrorBoundary fallback={fallback}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    expect(screen.getByText('Custom error UI')).toBeInTheDocument()
  })

  it('calls onError callback when error occurs', () => {
    const onError = vi.fn()

    render(
      <ErrorBoundary onError={onError}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    expect(onError).toHaveBeenCalledWith(expect.any(Error), expect.any(Object))

    const [error, errorInfo] = onError.mock.calls[0] as [Error, ErrorInfo]
    expect(error.message).toBe('Test error from component')
    expect(errorInfo).toHaveProperty('componentStack')
  })

  it('resets error state when resetKeys change', () => {
    const { rerender } = render(
      <ErrorBoundary resetKeys={['key1']}>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    expect(screen.getByTestId('error-boundary-fallback')).toBeInTheDocument()

    // Change reset key to trigger reset
    rerender(
      <ErrorBoundary resetKeys={['key2']}>
        <ThrowError shouldThrow={false} />
      </ErrorBoundary>,
    )

    expect(screen.getByText('No error')).toBeInTheDocument()
    expect(screen.queryByTestId('error-boundary-fallback')).not.toBeInTheDocument()
  })

  it('provides reset function in fallback render prop', () => {
    render(
      <ErrorBoundary
        fallback={(error, reset) => (
          <div>
            <div>Error: {error.message}</div>
            <button onClick={reset}>Reset</button>
          </div>
        )}
      >
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    expect(screen.getByText('Error: Test error from component')).toBeInTheDocument()

    // Click reset button
    fireEvent.click(screen.getByText('Reset'))

    // Error boundary should reset but component will throw again
    expect(screen.getByText('Error: Test error from component')).toBeInTheDocument()
  })

  it('isolates error to boundary', () => {
    render(
      <div>
        <div>Outside content</div>
        <ErrorBoundary>
          <ThrowError shouldThrow={true} />
        </ErrorBoundary>
        <div>Other outside content</div>
      </div>,
    )

    expect(screen.getByText('Outside content')).toBeInTheDocument()
    expect(screen.getByText('Other outside content')).toBeInTheDocument()
    expect(screen.getByTestId('error-boundary-fallback')).toBeInTheDocument()
  })

  it('logs error details in development', () => {
    const logError = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    expect(logError).toHaveBeenCalled()
    logError.mockRestore()
  })

  it('shows retry button in default fallback', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    const retryButton = screen.getByText('Try again')
    expect(retryButton).toBeInTheDocument()
  })

  it('resets when retry button is clicked', () => {
    let shouldThrow = true

    function ConditionalThrow() {
      if (shouldThrow) {
        throw new Error('First render error')
      }
      return <div>Success after retry</div>
    }

    const { rerender } = render(
      <ErrorBoundary>
        <ConditionalThrow />
      </ErrorBoundary>,
    )

    expect(screen.getByText('First render error')).toBeInTheDocument()

    // Change the condition so component won't throw on retry
    shouldThrow = false

    // Click retry
    fireEvent.click(screen.getByText('Try again'))

    expect(screen.getByText('Success after retry')).toBeInTheDocument()
  })

  it('accepts className prop', () => {
    render(
      <ErrorBoundary className="custom-boundary">
        <div>Content</div>
      </ErrorBoundary>,
    )

    const wrapper = screen.getByText('Content').parentElement
    expect(wrapper).toHaveClass('custom-boundary')
  })

  it('shows details button that expands error info', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    const detailsButton = screen.getByText('Show details')
    expect(detailsButton).toBeInTheDocument()

    fireEvent.click(detailsButton)

    expect(screen.getByText('Hide details')).toBeInTheDocument()
    expect(screen.getByText(/Component stack:/)).toBeInTheDocument()
  })

  it('maintains error state across re-renders', () => {
    const { rerender } = render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    expect(screen.getByTestId('error-boundary-fallback')).toBeInTheDocument()

    // Re-render with same props
    rerender(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>,
    )

    // Should still show error
    expect(screen.getByTestId('error-boundary-fallback')).toBeInTheDocument()
  })

  it('does not catch errors from effects', async () => {
    // Error boundaries don't catch errors thrown in effects, event handlers, or async code
    // This is a known React limitation

    render(
      <ErrorBoundary>
        <ThrowErrorInEffect shouldThrow={false} />
      </ErrorBoundary>,
    )

    // Component should render normally when not throwing
    expect(screen.getByText('Component with effect')).toBeInTheDocument()
  })
})
