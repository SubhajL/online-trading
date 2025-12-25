import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { EmergencyControls } from './EmergencyControls'
import type { ExposureSummary } from '@/types/dashboard'
import type { EmergencyCloseResult } from '@/types/dashboard'

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
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      expect(screen.getByRole('button', { name: /close all/i })).toBeInTheDocument()
    })

    it('renders Close Specific button', () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      expect(screen.getByRole('button', { name: /close specific/i })).toBeInTheDocument()
    })

    it('shows position count on CLOSE ALL button', () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      expect(screen.getByTestId('close-all-count')).toHaveTextContent('3 positions')
    })
  })

  describe('CLOSE ALL confirmation flow', () => {
    it('opens confirmation modal when CLOSE ALL is clicked', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      expect(screen.getByTestId('emergency-modal')).toBeInTheDocument()
      expect(screen.getByText(/type "CLOSE ALL" to confirm/i)).toBeInTheDocument()
    })

    it('requires typing CLOSE ALL to enable confirm button', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const confirmBtn = screen.getByTestId('confirm-close-btn')
      expect(confirmBtn).toBeDisabled()

      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })

      expect(confirmBtn).not.toBeDisabled()
    })

    it('calls onEmergencyClose with ALL scope, stopEngine=false, and idempotency key', async () => {
      vi.stubGlobal('crypto', { randomUUID: () => 'uuid-1' })
      const onEmergencyClose = vi
        .fn()
        .mockResolvedValue({ success: true } satisfies Partial<EmergencyCloseResult>)
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={onEmergencyClose} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })
      await fireEvent.click(screen.getByTestId('confirm-close-btn'))

      await waitFor(() => {
        expect(onEmergencyClose).toHaveBeenCalledWith('ALL', false, 'uuid-1')
      })
    })

    it('calls onEmergencyClose with stopEngine=true when checkbox is checked', async () => {
      vi.stubGlobal('crypto', { randomUUID: () => 'uuid-1' })
      const onEmergencyClose = vi
        .fn()
        .mockResolvedValue({ success: true } satisfies Partial<EmergencyCloseResult>)
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={onEmergencyClose} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      await fireEvent.click(screen.getByTestId('stop-engine-checkbox'))
      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })
      await fireEvent.click(screen.getByTestId('confirm-close-btn'))

      await waitFor(() => {
        expect(onEmergencyClose).toHaveBeenCalledWith('ALL', true, 'uuid-1')
      })
    })

    it('closes modal when Cancel is clicked', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      expect(screen.getByTestId('emergency-modal')).toBeInTheDocument()

      await fireEvent.click(screen.getByRole('button', { name: /cancel/i }))
      expect(screen.queryByTestId('emergency-modal')).not.toBeInTheDocument()
    })
  })

  describe('Close Specific flow', () => {
    it('opens scope selector when Close Specific is clicked', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))

      expect(screen.getByTestId('scope-selector')).toBeInTheDocument()
    })

    it('shows SPOT option with position count', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))

      expect(screen.getByTestId('scope-spot')).toHaveTextContent('SPOT')
      expect(screen.getByTestId('scope-spot-count')).toHaveTextContent('1 position')
    })

    it('shows FUTURES option with position count', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))

      expect(screen.getByTestId('scope-futures')).toHaveTextContent('FUTURES')
      expect(screen.getByTestId('scope-futures-count')).toHaveTextContent('2 positions')
    })

    it('calls onEmergencyClose with selected scope when confirmed', async () => {
      vi.stubGlobal('crypto', { randomUUID: () => 'uuid-1' })
      const onEmergencyClose = vi
        .fn()
        .mockResolvedValue({ success: true } satisfies Partial<EmergencyCloseResult>)
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={onEmergencyClose} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))
      await fireEvent.click(screen.getByTestId('scope-spot'))
      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })
      await fireEvent.click(screen.getByTestId('confirm-close-btn'))

      await waitFor(() => {
        expect(onEmergencyClose).toHaveBeenCalledWith('SPOT', false, 'uuid-1')
      })
    })
  })

  describe('result states', () => {
    it('shows execution progress while awaiting response', async () => {
      vi.stubGlobal('crypto', { randomUUID: () => 'uuid-1' })
      let resolvePromise: (value: EmergencyCloseResult) => void
      const onEmergencyClose = vi.fn(
        () =>
          new Promise<EmergencyCloseResult>(resolve => {
            resolvePromise = resolve
          }),
      )
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={onEmergencyClose} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })
      await fireEvent.click(screen.getByTestId('confirm-close-btn'))

      expect(screen.getByTestId('execution-progress')).toBeInTheDocument()

      act(() => {
        resolvePromise({
          success: true,
          scope: 'ALL',
          stopEngine: false,
          idempotencyKey: 'uuid-1',
          canceledOrders: 0,
          closedPositions: 3,
          autoTradingDisabled: false,
          steps: [],
          executionTimeMs: 10,
        })
      })

      await waitFor(() => {
        expect(screen.getByTestId('result-success')).toBeInTheDocument()
      })
    })

    it('keeps idempotency key stable when retrying after a network error', async () => {
      vi.stubGlobal('crypto', { randomUUID: () => 'uuid-1' })

      const onEmergencyClose = vi
        .fn()
        .mockRejectedValueOnce(new Error('Network down'))
        .mockResolvedValueOnce({
          success: true,
          scope: 'ALL',
          stopEngine: false,
          idempotencyKey: 'uuid-1',
          canceledOrders: 0,
          closedPositions: 1,
          autoTradingDisabled: false,
          steps: [],
          executionTimeMs: 10,
        } satisfies EmergencyCloseResult)

      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={onEmergencyClose} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })
      await fireEvent.click(screen.getByTestId('confirm-close-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('result-error')).toBeInTheDocument()
      })

      await fireEvent.click(screen.getByTestId('retry-btn'))

      await waitFor(() => {
        expect(onEmergencyClose).toHaveBeenNthCalledWith(1, 'ALL', false, 'uuid-1')
        expect(onEmergencyClose).toHaveBeenNthCalledWith(2, 'ALL', false, 'uuid-1')
      })
    })

    it('renders the step timeline for completed results', async () => {
      vi.stubGlobal('crypto', { randomUUID: () => 'uuid-1' })
      const onEmergencyClose = vi.fn().mockResolvedValue({
        success: true,
        scope: 'ALL',
        stopEngine: true,
        idempotencyKey: 'uuid-1',
        canceledOrders: 2,
        closedPositions: 3,
        autoTradingDisabled: true,
        steps: [
          {
            name: 'CANCEL_OPEN_ORDERS',
            status: 'SUCCESS',
            startedAt: new Date().toISOString(),
            finishedAt: new Date().toISOString(),
            errors: [],
            result: { canceledOrders: 2 },
          },
          {
            name: 'CLOSE_POSITIONS',
            status: 'SUCCESS',
            startedAt: new Date().toISOString(),
            finishedAt: new Date().toISOString(),
            errors: [],
            result: { closedPositions: 3 },
          },
          {
            name: 'STOP_AUTO_TRADING',
            status: 'SUCCESS',
            startedAt: new Date().toISOString(),
            finishedAt: new Date().toISOString(),
            errors: [],
            result: { autoTradingDisabled: true },
          },
        ],
        executionTimeMs: 10,
      } satisfies EmergencyCloseResult)

      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={onEmergencyClose} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      await fireEvent.click(screen.getByTestId('stop-engine-checkbox'))
      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })
      await fireEvent.click(screen.getByTestId('confirm-close-btn'))

      await waitFor(() => {
        expect(screen.getByTestId('result-success')).toBeInTheDocument()
      })

      expect(screen.getByTestId('emergency-steps')).toBeInTheDocument()
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
      render(<EmergencyControls exposure={noPositions} onEmergencyClose={vi.fn()} />)

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
      render(<EmergencyControls exposure={noPositions} onEmergencyClose={vi.fn()} />)

      expect(screen.getByText(/no open positions/i)).toBeInTheDocument()
    })
  })

  describe('accessibility', () => {
    it('modal has dialog role and aria-modal', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const dialog = screen.getByRole('dialog')
      expect(dialog).toBeInTheDocument()
      expect(dialog).toHaveAttribute('aria-modal', 'true')
    })

    it('modal has accessible label', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const dialog = screen.getByRole('dialog')
      expect(dialog).toHaveAttribute('aria-labelledby')
    })

    it('focuses confirmation input when modal opens', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      await waitFor(() => {
        expect(screen.getByTestId('confirmation-input')).toHaveFocus()
      })
    })

    it('closes modal on Escape key press', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      expect(screen.getByTestId('emergency-modal')).toBeInTheDocument()

      await fireEvent.keyDown(screen.getByTestId('emergency-modal'), {
        key: 'Escape',
        code: 'Escape',
      })

      expect(screen.queryByTestId('emergency-modal')).not.toBeInTheDocument()
    })

    it('returns focus to trigger button when modal closes', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      const closeAllBtn = screen.getByRole('button', { name: /close all/i })
      await fireEvent.click(closeAllBtn)

      await fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

      await waitFor(() => {
        expect(closeAllBtn).toHaveFocus()
      })
    })

    it('scope selector buttons navigate to confirmation screen on click', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))

      const spotBtn = screen.getByTestId('scope-spot')

      // Click SPOT to go to confirmation screen
      await fireEvent.click(spotBtn)

      // Should now be on confirmation screen showing "spot positions"
      expect(screen.getByText(/spot positions/i)).toBeInTheDocument()
    })

    it('confirms with Enter key when input is valid', async () => {
      vi.stubGlobal('crypto', { randomUUID: () => 'uuid-1' })
      const onEmergencyClose = vi
        .fn()
        .mockResolvedValue({ success: true } satisfies Partial<EmergencyCloseResult>)
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={onEmergencyClose} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const input = screen.getByTestId('confirmation-input')
      await fireEvent.change(input, { target: { value: 'CLOSE ALL' } })

      // Press Enter on the modal
      await fireEvent.keyDown(screen.getByTestId('emergency-modal'), {
        key: 'Enter',
        code: 'Enter',
      })

      await waitFor(() => {
        expect(onEmergencyClose).toHaveBeenCalledWith('ALL', false, 'uuid-1')
      })
    })

    it('does not confirm with Enter when input is invalid', async () => {
      const onEmergencyClose = vi.fn()
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={onEmergencyClose} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const input = screen.getByTestId('confirmation-input')
      await fireEvent.change(input, { target: { value: 'WRONG' } })

      await fireEvent.keyDown(screen.getByTestId('emergency-modal'), {
        key: 'Enter',
        code: 'Enter',
      })

      expect(onEmergencyClose).not.toHaveBeenCalled()
    })

    it('closes modal on Escape from scope selector', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close specific/i }))
      expect(screen.getByTestId('scope-selector')).toBeInTheDocument()

      await fireEvent.keyDown(screen.getByTestId('emergency-modal'), {
        key: 'Escape',
        code: 'Escape',
      })

      expect(screen.queryByTestId('emergency-modal')).not.toBeInTheDocument()
    })

    it('confirm button has aria-disabled when not valid', async () => {
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={vi.fn()} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))

      const confirmBtn = screen.getByTestId('confirm-close-btn')
      expect(confirmBtn).toBeDisabled()
    })

    it('does not close modal on Escape during execution', async () => {
      vi.stubGlobal('crypto', { randomUUID: () => 'uuid-1' })
      let resolvePromise: (value: EmergencyCloseResult) => void
      const onEmergencyClose = vi.fn(
        () =>
          new Promise<EmergencyCloseResult>(resolve => {
            resolvePromise = resolve
          }),
      )
      render(<EmergencyControls exposure={mockExposure} onEmergencyClose={onEmergencyClose} />)

      await fireEvent.click(screen.getByRole('button', { name: /close all/i }))
      await fireEvent.change(screen.getByTestId('confirmation-input'), {
        target: { value: 'CLOSE ALL' },
      })
      await fireEvent.click(screen.getByTestId('confirm-close-btn'))

      await fireEvent.keyDown(screen.getByTestId('emergency-modal'), {
        key: 'Escape',
        code: 'Escape',
      })

      // Modal should still be visible during execution
      expect(screen.getByTestId('emergency-modal')).toBeInTheDocument()

      act(() => {
        resolvePromise({
          success: true,
          scope: 'ALL',
          stopEngine: false,
          idempotencyKey: 'uuid-1',
          canceledOrders: 0,
          closedPositions: 1,
          autoTradingDisabled: false,
          steps: [],
          executionTimeMs: 10,
        })
      })
    })
  })
})
