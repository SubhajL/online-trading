import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { EmergencyControls } from './EmergencyControls'
import type { ExposureSummary, EmergencyCloseScope } from '@/types/dashboard'

const mockExposure: ExposureSummary = {
  totalNotional: 15000,
  spotNotional: 5000,
  futuresNotional: 10000,
  unrealizedPnl: 250.75,
  realizedPnlToday: 150.25,
  totalEquity: 50000,
  availableMargin: 35000,
  marginUsagePercent: 30,
  positionCount: 3,
  spotPositionCount: 1,
  futuresPositionCount: 2,
}

describe('EmergencyControls', () => {
  describe('two button layout (Option C)', () => {
    it('renders CLOSE ALL button', () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      expect(screen.getByRole('button', { name: /close all/i })).toBeInTheDocument()
    })

    it('renders Close Specific button', () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      expect(screen.getByRole('button', { name: /close specific/i })).toBeInTheDocument()
    })

    it('shows position count on CLOSE ALL button', () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      expect(screen.getByTestId('close-all-count')).toHaveTextContent('3 positions')
    })
  })

  describe('CLOSE ALL confirmation flow', () => {
    it('opens confirmation modal when CLOSE ALL is clicked', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      expect(screen.getByTestId('emergency-modal')).toBeInTheDocument()
      expect(screen.getByText(/type "CLOSE ALL" to confirm/i)).toBeInTheDocument()
    })

    it('requires typing CLOSE ALL to enable confirm button', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const confirmBtn = screen.getByTestId('confirm-close-btn')
      expect(confirmBtn).toBeDisabled()

      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })

      expect(confirmBtn).not.toBeDisabled()
    })

    it('calls onCloseAll with ALL scope when confirmed', async () => {
      const onCloseAll = vi.fn()
      render(<EmergencyControls exposure={mockExposure} onCloseAll={onCloseAll} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })
      await fireEvent.click(screen.getByTestId('confirm-close-btn'))

      expect(onCloseAll).toHaveBeenCalledWith('ALL')
    })

    it('closes modal when Cancel is clicked', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      expect(screen.getByTestId('emergency-modal')).toBeInTheDocument()

      await fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
      expect(screen.queryByTestId('emergency-modal')).not.toBeInTheDocument()
    })
  })

  describe('Close Specific flow', () => {
    it('opens scope selector when Close Specific is clicked', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))

      expect(screen.getByTestId('scope-selector')).toBeInTheDocument()
    })

    it('shows SPOT option with position count', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))

      expect(screen.getByTestId('scope-spot')).toHaveTextContent('SPOT')
      expect(screen.getByTestId('scope-spot-count')).toHaveTextContent('1 position')
    })

    it('shows FUTURES option with position count', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))

      expect(screen.getByTestId('scope-futures')).toHaveTextContent('FUTURES')
      expect(screen.getByTestId('scope-futures-count')).toHaveTextContent('2 positions')
    })

    it('calls onCloseAll with selected scope when confirmed', async () => {
      const onCloseAll = vi.fn()
      render(<EmergencyControls exposure={mockExposure} onCloseAll={onCloseAll} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))
      await fireEvent.click(screen.getByTestId('scope-spot'))
      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })
      await fireEvent.click(screen.getByTestId('confirm-close-btn'))

      expect(onCloseAll).toHaveBeenCalledWith('SPOT')
    })
  })

  describe('loading state', () => {
    it('shows loading spinner when isClosing is true', () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} isClosing />)

      expect(screen.getByTestId('closing-spinner')).toBeInTheDocument()
    })

    it('disables buttons when isClosing is true', () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} isClosing />)

      expect(screen.getByRole('button', { name: /close all/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /close specific/i })).toBeDisabled()
    })
  })

  describe('no positions state', () => {
    it('disables buttons when no positions exist', () => {
      const noPositions: ExposureSummary = {
        ...mockExposure,
        positionCount: 0,
        spotPositionCount: 0,
        futuresPositionCount: 0,
      }
      render(<EmergencyControls exposure={noPositions} onCloseAll={vi.fn()} />)

      expect(screen.getByRole('button', { name: /close all/i })).toBeDisabled()
      expect(screen.getByRole('button', { name: /close specific/i })).toBeDisabled()
    })

    it('shows no positions message', () => {
      const noPositions: ExposureSummary = {
        ...mockExposure,
        positionCount: 0,
        spotPositionCount: 0,
        futuresPositionCount: 0,
      }
      render(<EmergencyControls exposure={noPositions} onCloseAll={vi.fn()} />)

      expect(screen.getByText(/no open positions/i)).toBeInTheDocument()
    })
  })

  describe('error handling', () => {
    it('displays error message when error prop is set', () => {
      render(
        <EmergencyControls
          exposure={mockExposure}
          onCloseAll={vi.fn()}
          error="Failed to close positions"
        />,
      )

      expect(screen.getByText('Failed to close positions')).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('modal has dialog role and aria-modal', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const dialog = screen.getByRole('dialog')
      expect(dialog).toBeInTheDocument()
      expect(dialog).toHaveAttribute('aria-modal', 'true')
    })

    it('modal has accessible label', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const dialog = screen.getByRole('dialog')
      expect(dialog).toHaveAttribute('aria-labelledby')
    })

    it('focuses confirmation input when modal opens', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      await waitFor(() => {
        expect(screen.getByTestId('confirmation-input')).toHaveFocus()
      })
    })

    it('closes modal on Escape key press', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      expect(screen.getByTestId('emergency-modal')).toBeInTheDocument()

      await fireEvent.keyDown(screen.getByTestId('emergency-modal'), {
        key: 'Escape',
        code: 'Escape',
      })

      expect(screen.queryByTestId('emergency-modal')).not.toBeInTheDocument()
    })

    it('returns focus to trigger button when modal closes', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      const closeAllBtn = screen.getByRole('button', { name: /close all/i })
      await fireEvent.click(closeAllBtn)

      await fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

      await waitFor(() => {
        expect(closeAllBtn).toHaveFocus()
      })
    })

    it('scope selector buttons navigate to confirmation screen on click', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))

      const spotBtn = screen.getByTestId('scope-spot')

      // Click SPOT to go to confirmation screen
      await fireEvent.click(spotBtn)

      // Should now be on confirmation screen showing "spot positions"
      expect(screen.getByText(/spot positions/i)).toBeInTheDocument()
    })

    it('confirms with Enter key when input is valid', async () => {
      const onCloseAll = vi.fn()
      render(<EmergencyControls exposure={mockExposure} onCloseAll={onCloseAll} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const input = screen.getByTestId('confirmation-input')
      await fireEvent.change(input, { target: { value: 'CLOSE ALL' } })

      // Press Enter on the modal
      await fireEvent.keyDown(screen.getByTestId('emergency-modal'), {
        key: 'Enter',
        code: 'Enter',
      })

      expect(onCloseAll).toHaveBeenCalledWith('ALL')
    })

    it('does not confirm with Enter when input is invalid', async () => {
      const onCloseAll = vi.fn()
      render(<EmergencyControls exposure={mockExposure} onCloseAll={onCloseAll} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const input = screen.getByTestId('confirmation-input')
      await fireEvent.change(input, { target: { value: 'WRONG' } })

      await fireEvent.keyDown(screen.getByTestId('emergency-modal'), {
        key: 'Enter',
        code: 'Enter',
      })

      expect(onCloseAll).not.toHaveBeenCalled()
    })

    it('closes modal on Escape from scope selector', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))
      expect(screen.getByTestId('scope-selector')).toBeInTheDocument()

      await fireEvent.keyDown(screen.getByTestId('emergency-modal'), {
        key: 'Escape',
        code: 'Escape',
      })

      expect(screen.queryByTestId('emergency-modal')).not.toBeInTheDocument()
    })

    it('disables confirm button and input while closing', () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} isClosing />)

      // Modal should not be openable while closing (buttons disabled)
      expect(screen.getByRole('button', { name: /close all/i })).toBeDisabled()
    })

    it('confirm button has aria-disabled when not valid', async () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const confirmBtn = screen.getByTestId('confirm-close-btn')
      expect(confirmBtn).toBeDisabled()
    })

    it('error message has alert role', () => {
      render(
        <EmergencyControls
          exposure={mockExposure}
          onCloseAll={vi.fn()}
          error="Failed to close positions"
        />,
      )

      const errorEl = screen.getByRole('alert')
      expect(errorEl).toHaveTextContent('Failed to close positions')
    })

    it('loading spinner has aria-live region', () => {
      render(<EmergencyControls exposure={mockExposure} onCloseAll={vi.fn()} isClosing />)

      const spinner = screen.getByTestId('closing-spinner')
      expect(spinner).toHaveAttribute('aria-live', 'polite')
    })
  })
})
