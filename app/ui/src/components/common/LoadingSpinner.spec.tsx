import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { LoadingSpinner } from './LoadingSpinner'

describe('LoadingSpinner', () => {
  it('renders loading spinner', () => {
    render(<LoadingSpinner />)

    const spinner = screen.getByTestId('loading-spinner')
    expect(spinner).toBeInTheDocument()
  })

  it('applies default size styles', () => {
    render(<LoadingSpinner />)

    const circle = screen.getByTestId('loading-spinner').querySelector('.spinner-circle')
    expect(circle).toHaveStyle({ width: '24px', height: '24px', borderWidth: '3px' })
  })

  it('applies small size styles', () => {
    render(<LoadingSpinner size="small" />)

    const circle = screen.getByTestId('loading-spinner').querySelector('.spinner-circle')
    expect(circle).toHaveStyle({ width: '16px', height: '16px', borderWidth: '2px' })
  })

  it('applies medium size styles', () => {
    render(<LoadingSpinner size="medium" />)

    const circle = screen.getByTestId('loading-spinner').querySelector('.spinner-circle')
    expect(circle).toHaveStyle({ width: '24px', height: '24px', borderWidth: '3px' })
  })

  it('applies large size styles', () => {
    render(<LoadingSpinner size="large" />)

    const circle = screen.getByTestId('loading-spinner').querySelector('.spinner-circle')
    expect(circle).toHaveStyle({ width: '32px', height: '32px', borderWidth: '4px' })
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

  it('applies color variant with token', () => {
    render(<LoadingSpinner color="primary" />)

    const circle = screen.getByTestId('loading-spinner').querySelector('.spinner-circle')
    expect(circle).toHaveStyle({ borderColor: expect.stringContaining('transparent') })
  })

  it('applies secondary color variant with token', () => {
    render(<LoadingSpinner color="secondary" />)

    const circle = screen.getByTestId('loading-spinner').querySelector('.spinner-circle')
    expect(circle).toHaveStyle({ borderColor: expect.stringContaining('transparent') })
  })

  it('applies white color variant with token', () => {
    render(<LoadingSpinner color="white" />)

    const circle = screen.getByTestId('loading-spinner').querySelector('.spinner-circle')
    expect(circle).toHaveStyle({ borderColor: expect.stringContaining('transparent') })
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
    expect(spinner).toHaveClass('loading-spinner', 'inline', 'custom-class')

    const circle = spinner.querySelector('.spinner-circle')
    expect(circle).toHaveStyle({ width: '32px', height: '32px', borderWidth: '4px' })
    expect(screen.getByText('Processing...')).toBeInTheDocument()
  })
})
