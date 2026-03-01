import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IndicatorPanel } from './IndicatorPanel'
import type { IndicatorType } from '@/types'
import { DEFAULT_TOKENS } from '@/constants/defaultTokens'

describe('IndicatorPanel', () => {
  const mockOnToggleIndicator = vi.fn()
  const mockOnClose = vi.fn()

  const allIndicators: IndicatorType[] = ['EMA', 'SMA', 'RSI', 'MACD', 'BB', 'VOLUME']

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('should render indicator panel', () => {
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      expect(screen.getByTestId('indicator-panel')).toBeInTheDocument()
    })

    it('should render all available indicators', () => {
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      allIndicators.forEach(indicator => {
        expect(screen.getByLabelText(indicator)).toBeInTheDocument()
      })
    })

    it('should show indicator descriptions', () => {
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      expect(screen.getByText(/Exponential Moving Average/)).toBeInTheDocument()
      expect(screen.getByText(/Simple Moving Average/)).toBeInTheDocument()
      expect(screen.getByText(/Relative Strength Index/)).toBeInTheDocument()
      expect(screen.getByText(/Moving Average Convergence/)).toBeInTheDocument()
      expect(screen.getByText(/Bollinger Bands/)).toBeInTheDocument()
      expect(screen.getByText(/Volume bars/)).toBeInTheDocument()
    })

    it('should show panel title', () => {
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      expect(screen.getByText('Technical Indicators')).toBeInTheDocument()
    })

    it('should show close button', () => {
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      expect(screen.getByTestId('close-button')).toBeInTheDocument()
    })
  })

  describe('indicator state', () => {
    it('should check active indicators', () => {
      const activeIndicators: IndicatorType[] = ['EMA', 'RSI']
      render(
        <IndicatorPanel
          activeIndicators={activeIndicators}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      const emaCheckbox = screen.getByLabelText('EMA') as HTMLInputElement
      const rsiCheckbox = screen.getByLabelText('RSI') as HTMLInputElement
      const smaCheckbox = screen.getByLabelText('SMA') as HTMLInputElement

      expect(emaCheckbox.checked).toBe(true)
      expect(rsiCheckbox.checked).toBe(true)
      expect(smaCheckbox.checked).toBe(false)
    })

    it('should have all indicators unchecked when none active', () => {
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      allIndicators.forEach(indicator => {
        const checkbox = screen.getByLabelText(indicator) as HTMLInputElement
        expect(checkbox.checked).toBe(false)
      })
    })
  })

  describe('interactions', () => {
    it('should call onToggleIndicator when checkbox clicked', async () => {
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      const emaCheckbox = screen.getByLabelText('EMA')
      fireEvent.click(emaCheckbox)

      expect(mockOnToggleIndicator).toHaveBeenCalledWith('EMA')
    })

    it('should call onClose when close button clicked', async () => {
      const user = userEvent.setup()
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      const closeButton = screen.getByTestId('close-button')
      await user.click(closeButton)

      expect(mockOnClose).toHaveBeenCalled()
    })

    it('should handle toggling multiple indicators', async () => {
      const user = userEvent.setup()
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      await user.click(screen.getByLabelText('EMA'))
      await user.click(screen.getByLabelText('RSI'))
      await user.click(screen.getByLabelText('MACD'))

      expect(mockOnToggleIndicator).toHaveBeenCalledTimes(3)
      expect(mockOnToggleIndicator).toHaveBeenNthCalledWith(1, 'EMA')
      expect(mockOnToggleIndicator).toHaveBeenNthCalledWith(2, 'RSI')
      expect(mockOnToggleIndicator).toHaveBeenNthCalledWith(3, 'MACD')
    })
  })

  describe('styling', () => {
    it('should have proper panel styling', () => {
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      const panel = screen.getByTestId('indicator-panel')
      expect(panel).toHaveStyle({
        backgroundColor: DEFAULT_TOKENS.colors.surface.raised,
        borderLeft: `1px solid ${DEFAULT_TOKENS.colors.border.default}`,
        borderRadius: DEFAULT_TOKENS.radius.lg,
      })
    })

    it('should style active indicator items differently', () => {
      render(
        <IndicatorPanel
          activeIndicators={['EMA']}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      const emaItem = screen.getByTestId('indicator-item-EMA')
      const smaItem = screen.getByTestId('indicator-item-SMA')

      expect(emaItem).toHaveStyle({
        backgroundColor: DEFAULT_TOKENS.colors.surface.overlay,
        color: DEFAULT_TOKENS.colors.text.primary,
      })
      expect(smaItem).toHaveStyle({
        color: DEFAULT_TOKENS.colors.text.secondary,
      })
    })
  })

  describe('accessibility', () => {
    it('should have proper ARIA attributes', () => {
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      const panel = screen.getByTestId('indicator-panel')
      expect(panel).toHaveAttribute('role', 'dialog')
      expect(panel).toHaveAttribute('aria-label', 'Technical Indicators')
    })

    it('should have accessible checkboxes', () => {
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      allIndicators.forEach(indicator => {
        const checkbox = screen.getByLabelText(indicator)
        expect(checkbox).toHaveAttribute('type', 'checkbox')
        expect(checkbox).toHaveAttribute('id', `indicator-${indicator}`)
      })
    })
  })

  describe('edge cases', () => {
    it('should handle all indicators being active', () => {
      render(
        <IndicatorPanel
          activeIndicators={allIndicators}
          onToggleIndicator={mockOnToggleIndicator}
          onClose={mockOnClose}
        />,
      )

      allIndicators.forEach(indicator => {
        const checkbox = screen.getByLabelText(indicator) as HTMLInputElement
        expect(checkbox.checked).toBe(true)
      })
    })

    it('should handle empty callbacks gracefully', () => {
      // This should not throw
      render(
        <IndicatorPanel
          activeIndicators={[]}
          onToggleIndicator={undefined as any}
          onClose={undefined as any}
        />,
      )

      expect(screen.getByTestId('indicator-panel')).toBeInTheDocument()
    })
  })
})
