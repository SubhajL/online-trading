'use client'

import { useState, useCallback, useEffect, useRef, type KeyboardEvent } from 'react'
import type {
  ExposureSummary,
  EmergencyCloseScope,
  EmergencyCloseState,
  EmergencyCloseResult,
} from '@/types/dashboard'
import './EmergencyControls.css'

const STEP_ORDER = ['CANCEL_OPEN_ORDERS', 'CLOSE_POSITIONS', 'STOP_AUTO_TRADING'] as const

type StepOrderName = (typeof STEP_ORDER)[number]

function formatStepName(name: StepOrderName): string {
  switch (name) {
    case 'CANCEL_OPEN_ORDERS':
      return 'Cancel open orders'
    case 'CLOSE_POSITIONS':
      return 'Close positions'
    case 'STOP_AUTO_TRADING':
      return 'Stop auto-trading'
  }
}

type EmergencyControlsProps = {
  exposure: ExposureSummary | null
  onEmergencyClose: (
    scope: EmergencyCloseScope,
    stopEngine: boolean,
    idempotencyKey: string,
  ) => Promise<EmergencyCloseResult>
}

type ModalState = 'closed' | 'select-scope' | 'confirming' | 'executing' | 'result'

export function EmergencyControls({ exposure, onEmergencyClose }: EmergencyControlsProps) {
  const [modalState, setModalState] = useState<ModalState>('closed')
  const [selectedScope, setSelectedScope] = useState<EmergencyCloseScope>('ALL')
  const [confirmationText, setConfirmationText] = useState('')
  const [stopEngine, setStopEngine] = useState(false)
  const [executionState, setExecutionState] = useState<EmergencyCloseState>('IDLE')
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null)
  const [result, setResult] = useState<EmergencyCloseResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const closeAllBtnRef = useRef<HTMLButtonElement>(null)
  const closeSpecificBtnRef = useRef<HTMLButtonElement>(null)
  const confirmInputRef = useRef<HTMLInputElement>(null)
  const modalRef = useRef<HTMLDivElement>(null)
  const lastTriggerRef = useRef<'close-all' | 'close-specific' | null>(null)

  const hasPositions = exposure && exposure.positionCount > 0
  const isConfirmValid = confirmationText === 'CLOSE ALL'

  const runEmergencyClose = useCallback(
    async (stableKey: string) => {
      setExecutionState('EXECUTING')
      setModalState('executing')
      setError(null)
      setResult(null)
      setIdempotencyKey(stableKey)

      try {
        const response = await onEmergencyClose(selectedScope, stopEngine, stableKey)
        setResult(response)
        if (response.success) {
          setExecutionState('COMPLETED')
          setError(null)
        } else {
          const stepErrors = response.steps.flatMap(step => step.errors)
          setExecutionState('FAILED')
          setError(stepErrors.length ? stepErrors.join('; ') : 'Emergency close failed.')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An unexpected error occurred.')
        setExecutionState('FAILED')
      } finally {
        setModalState('result')
      }
    },
    [onEmergencyClose, selectedScope, stopEngine],
  )

  const resetState = useCallback(() => {
    setModalState('closed')
    setConfirmationText('')
    setStopEngine(false)
    setExecutionState('IDLE')
    setIdempotencyKey(null)
    setResult(null)
    setError(null)
  }, [])

  const handleCloseAllClick = useCallback(() => {
    lastTriggerRef.current = 'close-all'
    setSelectedScope('ALL')
    setConfirmationText('')
    setStopEngine(false)
    setExecutionState('CONFIRMING')
    setModalState('confirming')
    setIdempotencyKey(crypto.randomUUID())
    setError(null)
    setResult(null)
  }, [])

  const handleCloseSpecificClick = useCallback(() => {
    lastTriggerRef.current = 'close-specific'
    setConfirmationText('')
    setStopEngine(false)
    setModalState('select-scope')
    setError(null)
    setResult(null)
  }, [])

  const handleScopeSelect = useCallback((scope: EmergencyCloseScope) => {
    setSelectedScope(scope)
    setConfirmationText('')
    setExecutionState('CONFIRMING')
    setModalState('confirming')
    setIdempotencyKey(crypto.randomUUID())
    setError(null)
    setResult(null)
  }, [])

  const handleConfirm = useCallback(async () => {
    if (isConfirmValid && executionState !== 'EXECUTING') {
      const stableKey = idempotencyKey ?? crypto.randomUUID()
      await runEmergencyClose(stableKey)
    }
  }, [executionState, idempotencyKey, isConfirmValid, runEmergencyClose])

  const handleCancel = useCallback(() => {
    resetState()
    // Return focus to the trigger button
    if (lastTriggerRef.current === 'close-all') {
      closeAllBtnRef.current?.focus()
    } else if (lastTriggerRef.current === 'close-specific') {
      closeSpecificBtnRef.current?.focus()
    }
  }, [resetState])

  const handleRetry = useCallback(async () => {
    if (executionState === 'EXECUTING') return

    if (!result) {
      const stableKey = idempotencyKey ?? crypto.randomUUID()
      await runEmergencyClose(stableKey)
      return
    }

    // Completed failure: require a new confirmation + new idempotency key.
    setExecutionState('CONFIRMING')
    setModalState('confirming')
    setConfirmationText('')
    setError(null)
    setResult(null)
    setIdempotencyKey(crypto.randomUUID())
  }, [executionState, idempotencyKey, result, runEmergencyClose])

  const handleDone = useCallback(() => {
    resetState()
    // Return focus to the trigger button
    if (lastTriggerRef.current === 'close-all') {
      closeAllBtnRef.current?.focus()
    } else if (lastTriggerRef.current === 'close-specific') {
      closeSpecificBtnRef.current?.focus()
    }
  }, [resetState])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Escape' && modalState !== 'executing') {
        handleCancel()
        return
      }

      // Enter key to confirm (only in confirm modal state)
      if (e.key === 'Enter' && modalState === 'confirming' && isConfirmValid) {
        e.preventDefault()
        handleConfirm()
        return
      }

      // Focus trap: cycle Tab within modal
      if (e.key === 'Tab' && modalRef.current) {
        const focusableElements = modalRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
        )
        const firstElement = focusableElements[0]
        const lastElement = focusableElements[focusableElements.length - 1]

        if (e.shiftKey && document.activeElement === firstElement) {
          e.preventDefault()
          lastElement?.focus()
        } else if (!e.shiftKey && document.activeElement === lastElement) {
          e.preventDefault()
          firstElement?.focus()
        }
      }
    },
    [handleCancel, handleConfirm, modalState, isConfirmValid],
  )

  // Focus management: focus input when modal opens
  useEffect(() => {
    if (modalState === 'confirming' && confirmInputRef.current) {
      confirmInputRef.current.focus()
    }
  }, [modalState])

  const formatPositionCount = (count: number) => (count === 1 ? '1 position' : `${count} positions`)

  const renderSteps = (mode: 'executing' | 'result') => {
    const stepsByName = new Map(result?.steps?.map(s => [s.name, s]))

    return (
      <div className="emergency-steps" data-testid="emergency-steps">
        <h5 className="steps-title">Steps</h5>
        <ol className="steps-list">
          {STEP_ORDER.map(name => {
            const step = stepsByName.get(name)
            const label = formatStepName(name)
            const status =
              mode === 'executing'
                ? 'IN_PROGRESS'
                : (step?.status ?? (executionState === 'COMPLETED' ? 'SUCCESS' : 'FAILED'))

            return (
              <li key={name} className="step-row">
                <span className="step-name">{label}</span>
                <span className="step-status" data-status={status}>
                  {status}
                </span>
              </li>
            )
          })}
        </ol>
      </div>
    )
  }

  const renderModalContent = () => {
    switch (modalState) {
      case 'select-scope':
        return (
          <>
            <h4 id="emergency-modal-title">Select Scope</h4>
            <div className="scope-selector" data-testid="scope-selector">
              <button
                type="button"
                className={`scope-option ${selectedScope === 'SPOT' ? 'selected' : ''}`}
                onClick={() => handleScopeSelect('SPOT')}
                data-testid="scope-spot"
                disabled={!exposure || exposure.spotPositionCount === 0}
              >
                <span className="scope-label">SPOT</span>
                <span className="scope-count" data-testid="scope-spot-count">
                  {exposure && formatPositionCount(exposure.spotPositionCount)}
                </span>
              </button>

              <button
                type="button"
                className={`scope-option ${selectedScope === 'FUTURES' ? 'selected' : ''}`}
                onClick={() => handleScopeSelect('FUTURES')}
                data-testid="scope-futures"
                disabled={!exposure || exposure.futuresPositionCount === 0}
              >
                <span className="scope-label">FUTURES</span>
                <span className="scope-count" data-testid="scope-futures-count">
                  {exposure && formatPositionCount(exposure.futuresPositionCount)}
                </span>
              </button>
            </div>

            <div className="modal-actions">
              <button type="button" className="cancel-btn" onClick={handleCancel}>
                Cancel
              </button>
            </div>
          </>
        )

      case 'confirming':
        return (
          <>
            <h4 id="emergency-modal-title">Confirm Emergency Close</h4>
            <div className="confirmation-details">
              <p>
                You are about to close{' '}
                <strong>
                  {selectedScope === 'ALL'
                    ? 'all positions'
                    : `${selectedScope.toLowerCase()} positions`}
                </strong>
                .
              </p>
              <p className="confirmation-warning">This action cannot be undone.</p>
            </div>

            <div className="stop-engine-option">
              <label htmlFor="stop-engine-checkbox">
                <input
                  id="stop-engine-checkbox"
                  type="checkbox"
                  checked={stopEngine}
                  onChange={e => setStopEngine(e.target.checked)}
                  data-testid="stop-engine-checkbox"
                />
                Also stop auto-trading after close
              </label>
            </div>

            <div className="confirmation-input-group">
              <label htmlFor="confirm-input">Type &quot;CLOSE ALL&quot; to confirm:</label>
              <input
                ref={confirmInputRef}
                id="confirm-input"
                type="text"
                value={confirmationText}
                onChange={e => setConfirmationText(e.target.value)}
                placeholder="CLOSE ALL"
                data-testid="confirmation-input"
                autoComplete="off"
                disabled={executionState === 'EXECUTING'}
              />
            </div>

            <div className="modal-actions">
              <button type="button" className="cancel-btn" onClick={handleCancel}>
                Cancel
              </button>
              <button
                type="button"
                className="confirm-btn"
                onClick={handleConfirm}
                disabled={!isConfirmValid || executionState === 'EXECUTING'}
                data-testid="confirm-close-btn"
              >
                Close Positions
              </button>
            </div>
          </>
        )

      case 'executing':
        return (
          <>
            <h4 id="emergency-modal-title">Closing Positions...</h4>
            <div className="execution-progress" data-testid="execution-progress">
              <div className="progress-spinner" aria-hidden="true" />
              <p>
                Closing{' '}
                {selectedScope === 'ALL'
                  ? 'all positions'
                  : `${selectedScope.toLowerCase()} positions`}
                ...
              </p>
              <p className="progress-note">Please wait, this may take a few seconds.</p>
              {stopEngine && (
                <p className="progress-note">Auto-trading will be stopped after close.</p>
              )}
            </div>
            {renderSteps('executing')}
          </>
        )

      case 'result':
        if (executionState === 'COMPLETED') {
          return (
            <>
              <h4 id="emergency-modal-title" className="success-title">
                Positions Closed
              </h4>
              <div className="result-content success" data-testid="result-success">
                <div className="result-icon" aria-hidden="true">
                  ✓
                </div>
                <p>
                  Successfully closed {result?.closedPositions ?? 0} position
                  {(result?.closedPositions ?? 0) !== 1 ? 's' : ''}.
                </p>
                {result?.autoTradingDisabled && (
                  <p className="result-note">Auto-trading has been stopped.</p>
                )}
              </div>
              {renderSteps('result')}
              <div className="modal-actions">
                <button
                  type="button"
                  className="done-btn"
                  onClick={handleDone}
                  data-testid="done-btn"
                  autoFocus
                >
                  Done
                </button>
              </div>
            </>
          )
        } else {
          return (
            <>
              <h4 id="emergency-modal-title" className="error-title">
                Close Failed
              </h4>
              <div className="result-content error" data-testid="result-error">
                <div className="result-icon" aria-hidden="true">
                  ✗
                </div>
                <p className="error-message">{error || 'Emergency close failed.'}</p>
              </div>
              {renderSteps('result')}
              <div className="modal-actions">
                <button type="button" className="cancel-btn" onClick={handleDone}>
                  Cancel
                </button>
                <button
                  type="button"
                  className="retry-btn"
                  onClick={handleRetry}
                  data-testid="retry-btn"
                >
                  Retry
                </button>
              </div>
            </>
          )
        }

      default:
        return null
    }
  }

  return (
    <div className="emergency-controls">
      <div className="emergency-header">
        <h3>Emergency Controls</h3>
      </div>

      {exposure && exposure.positionCount === 0 && (
        <div className="no-positions-message">No open positions</div>
      )}

      <div className="emergency-buttons">
        <button
          ref={closeAllBtnRef}
          type="button"
          className="emergency-btn close-all-btn"
          onClick={handleCloseAllClick}
          disabled={!hasPositions || executionState === 'EXECUTING'}
        >
          <span className="btn-icon" aria-hidden="true">
            🔴
          </span>
          <span className="btn-text">CLOSE ALL POSITIONS</span>
          {exposure && exposure.positionCount > 0 && (
            <span className="btn-count" data-testid="close-all-count">
              {formatPositionCount(exposure.positionCount)}
            </span>
          )}
        </button>

        <button
          ref={closeSpecificBtnRef}
          type="button"
          className="emergency-btn close-specific-btn"
          onClick={handleCloseSpecificClick}
          disabled={!hasPositions || executionState === 'EXECUTING'}
        >
          <span className="btn-icon" aria-hidden="true">
            ⚙️
          </span>
          <span className="btn-text">Close Specific...</span>
        </button>
      </div>

      {modalState !== 'closed' && (
        <div className="emergency-modal-overlay">
          <div
            ref={modalRef}
            className={`emergency-modal ${executionState === 'FAILED' ? 'modal-error' : ''} ${executionState === 'COMPLETED' ? 'modal-success' : ''}`}
            data-testid="emergency-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="emergency-modal-title"
            onKeyDown={handleKeyDown}
          >
            {renderModalContent()}
          </div>
        </div>
      )}
    </div>
  )
}
