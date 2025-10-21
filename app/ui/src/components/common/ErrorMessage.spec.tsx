import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ErrorMessage } from './ErrorMessage'
import * as formatErrorMessageModule from '../../utils/formatErrorMessage'
import { DEFAULT_TOKENS } from '@/constants/defaultTokens'
import { getTokens } from '@/utils/getTokens'

vi.mock('@/utils/getTokens', () => ({
  getTokens: vi.fn(),
}))

// Mock the formatErrorMessage function
vi.mock('../../utils/formatErrorMessage')

describe('ErrorMessage', () => {
  beforeEach(() => {
    // Reset the mock before each test
    vi.mocked(formatErrorMessageModule.formatErrorMessage).mockImplementation((error: unknown) => {
      if (error instanceof Error) return error.message
      if (typeof error === 'string') return error
      return 'Formatted error message'
    })
    vi.mocked(getTokens).mockReturnValue(DEFAULT_TOKENS)
  })

  it('renders error message from string', () => {
    render(<ErrorMessage error="Something went wrong" />)

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('renders error message from Error object', () => {
    const error = new Error('Network connection failed')
    render(<ErrorMessage error={error} />)

    expect(screen.getByText('Network connection failed')).toBeInTheDocument()
  })

  it('uses formatErrorMessage utility', () => {
    const error = new Error('Test error')

    render(<ErrorMessage error={error} />)

    expect(formatErrorMessageModule.formatErrorMessage).toHaveBeenCalledWith(error)
  })

  it('applies token background and text color for error variant', () => {
    render(<ErrorMessage error="Tokenized error" />)

    const container = screen.getByTestId('error-message')
    expect(container.style.backgroundColor).toBe(DEFAULT_TOKENS.colors.error[50])
    expect(container.style.color).toBe(DEFAULT_TOKENS.colors.text.danger)
  })

  it('applies token styling for warning variant', () => {
    render(<ErrorMessage error="Tokenized warning" variant="warning" />)

    const container = screen.getByTestId('error-message')
    expect(container.style.backgroundColor).toBe(DEFAULT_TOKENS.colors.warning[50])
    expect(container.style.color).toBe(DEFAULT_TOKENS.colors.text.warning)
  })

  it('applies token styling for info variant', () => {
    render(<ErrorMessage error="Tokenized info" variant="info" />)

    const container = screen.getByTestId('error-message')
    expect(container.style.backgroundColor).toBe(DEFAULT_TOKENS.colors.info[50])
    expect(container.style.color).toBe(DEFAULT_TOKENS.colors.text.info)
  })

  it('shows dismiss button when dismissible', () => {
    render(<ErrorMessage error="Test error" dismissible />)

    const dismissButton = screen.getByLabelText('Dismiss')
    expect(dismissButton).toBeInTheDocument()
  })

  it('calls onDismiss when dismiss button clicked', () => {
    const onDismiss = vi.fn()
    render(<ErrorMessage error="Test error" dismissible onDismiss={onDismiss} />)

    const dismissButton = screen.getByLabelText('Dismiss')
    fireEvent.click(dismissButton)

    expect(onDismiss).toHaveBeenCalledTimes(1)
  })

  it('shows retry button when onRetry provided', () => {
    const onRetry = vi.fn()
    render(<ErrorMessage error="Test error" onRetry={onRetry} />)

    const retryButton = screen.getByText('Retry')
    expect(retryButton).toBeInTheDocument()
  })

  it('calls onRetry when retry button clicked', () => {
    const onRetry = vi.fn()
    render(<ErrorMessage error="Test error" onRetry={onRetry} />)

    const retryButton = screen.getByText('Retry')
    fireEvent.click(retryButton)

    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('has proper ARIA attributes', () => {
    render(<ErrorMessage error="Test error" />)

    const container = screen.getByTestId('error-message')
    expect(container).toHaveAttribute('role', 'alert')
    expect(container).toHaveAttribute('aria-live', 'assertive')
  })

  it('has assertive aria-live for error variant', () => {
    render(<ErrorMessage error="Test error" variant="error" />)

    const container = screen.getByTestId('error-message')
    expect(container).toHaveAttribute('aria-live', 'assertive')
  })

  it('has polite aria-live for non-error variants', () => {
    const { rerender } = render(<ErrorMessage error="Test" variant="warning" />)
    let container = screen.getByTestId('error-message')
    expect(container).toHaveAttribute('aria-live', 'polite')

    rerender(<ErrorMessage error="Test" variant="info" />)
    container = screen.getByTestId('error-message')
    expect(container).toHaveAttribute('aria-live', 'polite')
  })

  it('shows icon based on variant', () => {
    const { rerender } = render(<ErrorMessage error="Test" variant="error" />)
    expect(screen.getByTestId('error-icon')).toBeInTheDocument()

    rerender(<ErrorMessage error="Test" variant="warning" />)
    expect(screen.getByTestId('warning-icon')).toBeInTheDocument()

    rerender(<ErrorMessage error="Test" variant="info" />)
    expect(screen.getByTestId('info-icon')).toBeInTheDocument()
  })

  it('renders with title when provided', () => {
    render(<ErrorMessage error="Test error" title="Error Title" />)

    expect(screen.getByText('Error Title')).toBeInTheDocument()
    expect(screen.getByText('Test error')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<ErrorMessage error="Test error" className="custom-error" />)

    const container = screen.getByTestId('error-message')
    expect(container).toHaveClass('error-message', 'custom-error')
  })

  it('renders with custom retry button text', () => {
    const onRetry = vi.fn()
    render(<ErrorMessage error="Test error" onRetry={onRetry} retryText="Try Again" />)

    expect(screen.getByText('Try Again')).toBeInTheDocument()
  })

  it('shows both dismiss and retry buttons when both provided', () => {
    const onDismiss = vi.fn()
    const onRetry = vi.fn()

    render(<ErrorMessage error="Test error" dismissible onDismiss={onDismiss} onRetry={onRetry} />)

    expect(screen.getByLabelText('Dismiss')).toBeInTheDocument()
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })

  it('handles complex error object', () => {
    const error = {
      response: {
        data: {
          message: 'Server error occurred',
        },
      },
    }

    render(<ErrorMessage error={error as any} />)

    expect(screen.getByText('Formatted error message')).toBeInTheDocument()
  })

  it('applies compact styling', () => {
    render(<ErrorMessage error="Test error" compact />)

    const container = screen.getByTestId('error-message')
    expect(container).toHaveClass('compact')
  })
})
