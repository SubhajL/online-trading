import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AutoTradingToggle } from './AutoTradingToggle'

describe('AutoTradingToggle', () => {
  const mockOnChange = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders toggle switch', () => {
    render(<AutoTradingToggle enabled={false} onChange={mockOnChange} />)

    expect(screen.getByRole('switch')).toBeInTheDocument()
    expect(screen.getByText('Auto Trading')).toBeInTheDocument()
  })

  it('shows enabled state', () => {
    render(<AutoTradingToggle enabled={true} onChange={mockOnChange} />)

    const toggle = screen.getByRole('switch')
    expect(toggle).toBeChecked()
    expect(toggle).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByText('Enabled')).toBeInTheDocument()
  })

  it('shows disabled state', () => {
    render(<AutoTradingToggle enabled={false} onChange={mockOnChange} />)

    const toggle = screen.getByRole('switch')
    expect(toggle).not.toBeChecked()
    expect(toggle).toHaveAttribute('aria-checked', 'false')
    expect(screen.getByText('Disabled')).toBeInTheDocument()
  })

  it('calls onChange when toggled', async () => {
    const user = userEvent.setup()
    render(<AutoTradingToggle enabled={false} onChange={mockOnChange} />)

    const toggle = screen.getByRole('switch')
    await user.click(toggle)

    expect(mockOnChange).toHaveBeenCalledWith(true)
  })

  it('toggles from enabled to disabled', async () => {
    const user = userEvent.setup()
    render(<AutoTradingToggle enabled={true} onChange={mockOnChange} />)

    const toggle = screen.getByRole('switch')
    await user.click(toggle)

    expect(mockOnChange).toHaveBeenCalledWith(false)
  })

  it('shows loading state', () => {
    render(<AutoTradingToggle enabled={false} onChange={mockOnChange} loading />)

    expect(screen.getByText('Updating...')).toBeInTheDocument()
    expect(screen.getByRole('switch')).toBeDisabled()
  })

  it('disables toggle when loading', () => {
    render(<AutoTradingToggle enabled={false} onChange={mockOnChange} loading />)

    const toggle = screen.getByRole('switch')
    expect(toggle).toBeDisabled()
  })

  it('shows error message', () => {
    const errorMessage = 'Failed to update auto trading status'
    render(<AutoTradingToggle enabled={false} onChange={mockOnChange} error={errorMessage} />)

    expect(screen.getByText(errorMessage)).toBeInTheDocument()
    expect(screen.getByTestId('toggle-error')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<AutoTradingToggle enabled={false} onChange={mockOnChange} className="custom-toggle" />)

    const container = screen.getByTestId('auto-trading-toggle')
    expect(container).toHaveClass('auto-trading-toggle', 'custom-toggle')
  })

  it('shows warning icon when disabled', () => {
    render(<AutoTradingToggle enabled={false} onChange={mockOnChange} />)

    expect(screen.getByTestId('warning-icon')).toBeInTheDocument()
  })

  it('shows check icon when enabled', () => {
    render(<AutoTradingToggle enabled={true} onChange={mockOnChange} />)

    expect(screen.getByTestId('check-icon')).toBeInTheDocument()
  })

  it('handles rapid clicks gracefully', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<AutoTradingToggle enabled={false} onChange={mockOnChange} />)

    const toggle = screen.getByRole('switch')

    // Rapid clicks - since state is controlled, all clicks will call with true
    await user.click(toggle)
    await user.click(toggle)
    await user.click(toggle)

    // All clicks on a controlled component with enabled=false will call onChange(true)
    expect(mockOnChange).toHaveBeenCalledTimes(3)
    expect(mockOnChange).toHaveBeenNthCalledWith(1, true)
    expect(mockOnChange).toHaveBeenNthCalledWith(2, true)
    expect(mockOnChange).toHaveBeenNthCalledWith(3, true)
  })

  it('supports keyboard navigation', async () => {
    const user = userEvent.setup()
    render(<AutoTradingToggle enabled={false} onChange={mockOnChange} />)

    const toggle = screen.getByRole('switch')
    toggle.focus()

    await user.keyboard(' ') // Space key

    expect(mockOnChange).toHaveBeenCalledWith(true)
  })

  it('shows tooltip on hover', async () => {
    const user = userEvent.setup()
    render(<AutoTradingToggle enabled={false} onChange={mockOnChange} />)

    const container = screen.getByTestId('auto-trading-toggle')
    await user.hover(container)

    expect(screen.getByText(/Enable to allow automated trading/i)).toBeInTheDocument()
  })
})
