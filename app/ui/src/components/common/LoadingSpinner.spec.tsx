import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { LoadingSpinner } from './LoadingSpinner'

describe('LoadingSpinner', () => {
  it('renders loading spinner', () => {
    render(<LoadingSpinner />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toBeInTheDocument()
  })

  it('applies default size class', () => {
    render(<LoadingSpinner />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveClass('loading-spinner', 'size-medium')
  })

  it('applies small size class', () => {
    render(<LoadingSpinner size="small" />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveClass('loading-spinner', 'size-small')
  })

  it('applies medium size class', () => {
    render(<LoadingSpinner size="medium" />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveClass('loading-spinner', 'size-medium')
  })

  it('applies large size class', () => {
    render(<LoadingSpinner size="large" />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveClass('loading-spinner', 'size-large')
  })

  it('renders with custom className', () => {
    render(<LoadingSpinner className="custom-spinner" />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveClass('loading-spinner', 'custom-spinner')
  })

  it('renders with label', () => {
    render(<LoadingSpinner label="Loading data..." />)

    expect(screen.getByText('Loading data...')).toBeInTheDocument()
  })

  it('does not render label when not provided', () => {
    render(<LoadingSpinner />)

    expect(screen.queryByText('Loading')).not.toBeInTheDocument()
  })

  it('applies proper ARIA attributes', () => {
    render(<LoadingSpinner label="Loading" />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveAttribute('role', 'status')
    expect(spinner).toHaveAttribute('aria-label', 'Loading')
  })

  it('uses default aria-label when label not provided', () => {
    render(<LoadingSpinner />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveAttribute('aria-label', 'Loading...')
  })

  it('renders as inline element', () => {
    render(<LoadingSpinner inline />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveClass('inline')
  })

  it('renders with overlay', () => {
    render(<LoadingSpinner overlay />)

    const overlay = screen.getByTestId('loading-overlay')
    expect(overlay).toBeInTheDocument()
    expect(overlay).toHaveClass('loading-overlay')
  })

  it('renders spinner inside overlay', () => {
    render(<LoadingSpinner overlay />)

    const overlay = screen.getByTestId('loading-overlay')
    const spinner = screen.getByTestId('loading-spinner')

    expect(overlay).toContainElement(spinner)
  })

  it('applies fullscreen class to overlay', () => {
    render(<LoadingSpinner overlay fullscreen />)

    const overlay = screen.getByTestId('loading-overlay')
    expect(overlay).toHaveClass('loading-overlay', 'fullscreen')
  })

  it('centers spinner with centerText prop', () => {
    render(<LoadingSpinner label="Loading..." centerText />)

    const container = screen.getByTestId('loading-container')
    expect(container).toHaveClass('center-text')
  })

  it('applies color variant', () => {
    render(<LoadingSpinner color="primary" />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveClass('color-primary')
  })

  it('applies secondary color variant', () => {
    render(<LoadingSpinner color="secondary" />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveClass('color-secondary')
  })

  it('applies white color variant', () => {
    render(<LoadingSpinner color="white" />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveClass('color-white')
  })

  it('combines multiple props correctly', () => {
    render(
      <LoadingSpinner
        size="large"
        color="primary"
        label="Processing..."
        inline
        className="custom-class"
      />,
    )

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toHaveClass(
      'loading-spinner',
      'size-large',
      'color-primary',
      'inline',
      'custom-class',
    )
    expect(screen.getByText('Processing...')).toBeInTheDocument()
  })
})
